# Our own translator instead of shadPS4: structure and order of work (2026-10-10)

Goal: move away from emulation and from shadPS4 code — our own translator of PS4 commands and
our own graphics renderer that scale to other games (everything specific to one game lives in its
profile, `gpu/games/`), identical for AMD and NVIDIA. After that — shadnet (network play).

## Current state

Borrowed from shadPS4 (`gpu/VENDOR.txt`, commit b4e7ae7 dated 2026-09-24), about 116k lines:

| Part | Lines | What it does | Ours in it |
|---|---|---|---|
| `video_core/amdgpu` | 8.3k | PM4 parsing (command processor `liverpool.cpp`), registers, tiling | GPU-written labels, occlusion, predication, PM4 self-test |
| `video_core/renderer_vulkan` | 28.6k | Vulkan renderer: pipelines, rasterizer, scheduler, presenter | draw pipeline (stages A/B), recording threads, upscalers, background compilation |
| `video_core/buffer_cache` | 7.4k | game memory for the GPU | almost entirely rewritten (memory module, VRAM copies, traps) |
| `video_core/texture_cache` | 4.8k | textures by address, detiling | time-based collector, uploads |
| `shader_recompiler` | 38.6k | GCN → IR → SPIR-V | paged buffers (BDA), fixes |
| `core`, `common` | 21.8k | VideoOut, GnmDriver, event queues, utilities | vblank, labels |

Our own, outside the shadPS4 code: `gpu/layer/` (memory module `BbLayer::GpuMemory`),
`gpu/games/` (game profiles), `gpu/shim/` (overlay, settings, hooks), the runtime `src/` (kernel,
libc, files, saves).

## The structure we are heading toward

Modules with narrow interfaces; none knows game code addresses (that is the profile) and none
does the GPU's work on the CPU (that is emulation):

1. **memory** — game memory in place, VRAM copies as a cache, common page-protection accounting
   (write traps for copies and textures). Present: `layer/` + the module in
   `buffer_cache_layer.cpp`.
2. **cp** — command processor: PM4 parsing into the translator's command stream (state, draws,
   dispatches, synchronization) in GPU execution order. Replaces `liverpool.cpp`.
3. **state** — context registers → pipeline keys and Vulkan dynamic state. Replaces
   `liverpool_to_vk`, key assembly in `vk_pipeline_cache`.
4. **resources** — V#/T#/S# descriptors → buffers, images, samplers (caches, detiling). Replaces
   `buffer_cache`, `texture_cache` (the buffer part is already almost ours).
5. **render** — Vulkan: command recording by threads, barriers, submission, presentation.
   Replaces `renderer_vulkan` (the scheduler and stages A/B are already ours).
6. **shaders** — GCN → SPIR-V. The biggest part; replaced last, in stages (decoder, IR, passes,
   emission).
7. **platform** — VideoOut, GnmDriver, kernel events (`core/libraries`), next to the runtime.
8. **games** — game profiles (present).

## Order

Replace one module at a time: first an interface in our code with the shadPS4 code behind it
as-is, then our implementation behind the same interface. After each step: the route
(`route_bench.sh`, frames and screenshots), the PM4 self-test (`BB_PM4_SELFTEST=1`), unit tests,
gameplay on AMD and (via testers' logs) NVIDIA.

| Step | What | Why in this order |
|---|---|---|
| 1 | memory: common page-protection accounting; traps under textures by default; model 0.3 and the sparse arena are removed | removes the rest of memory emulation and the tie to game hooks |
| 2 | cp: the translator's command stream; `MEM_SEMAPHORE`, GPU time, compute queues — done by the GPU | the command processor holds the last of the emulation |
| 3 | state + resources | they rely on 1 and 2; the buffer part is already ours |
| 4 | render | the scheduler and stages are already ours; the rasterizer and pipelines remain |
| 5 | shaders | the biggest and riskiest; by then everything else is already ours |
| 6 | shadnet | networking, once the graphics is ours |

Steps 1 and 2 are the emulation-removal plan (`EMULATION_REMOVAL_PLAN.md`, section dated
2026-10-10).

## Work log

### 2026-10-10: our own PM4 decoder (step 2, beginning)

- `gpu/cp/` — our own code, no shadPS4: packet format and opcodes (`cp_pm4.h`), register file and
  decoder (`cp_decoder.{h,cpp}`). The decoder walks the buffer in stream order, applies register
  packets (`SET_*_REG`, `CLEAR_STATE`, registers written by draw packets), descends into nested
  buffers, and hands each packet to a "sink" (`BbCp::Sink`) with the state already applied: draws
  and dispatches — typed; everything else — as packets. `COND_EXEC` is decided by the sink. The
  decoder knows nothing about Vulkan, the game, or the place of execution.
- Unit test `tests/test_cp_decoder.cpp` (target `cp-decoder-test`): registers, partial writes,
  draws, dispatches, nested buffers, `COND_EXEC`, `CLEAR_STATE`, corrupt buffers.
- Register addresses are checked against the shadPS4 layout at build time (`static_assert`): this
  is how a bug was found — on CIK `CP_STRMOUT_CNTL` is in uconfig (`0xC03F`), not config.
- In-game shadow check (`BB_CP_SHADOW=1`): the new decoder parses every top-level buffer from the
  same state; at the end of the buffer the register files are compared. On the route — all
  buffers matched (~800k buffers, ~200M packets, 0 divergences, 0 parse errors). Bloodborne does
  not use nested buffers (checked by a unit test).
- Next: the decoder as a cursor (packet by packet, so the command processor loop can yield to
  other queues on waits); the register file as a shared state store (layout matches the shadPS4
  `Regs` by words); then moving packet handling from `liverpool.cpp` into the translator's sink
  one packet kind at a time, each time with the shadow check and the route.

### 2026-10-10: the new decoder — the real parsing path

- The decoder became a cursor (`BbCp::Cursor`: packet by packet, nested buffers at the caller's
  option); the register file can live in the owner's storage (the command processor's `regs`,
  same layout by words); a write observer (`RegisterObserver`, one call per packet) provides what
  draw preparation needs: written blocks and a packet checksum.
- `ProcessGraphics` takes packets and register writes from the cursor (`BB_CP_DECODER=0` — the
  old traversal); what each packet does is still the previous code. PM4 self-test — 11 of 11; the
  share of prepared draws is the same (747k used, 19k not, vs 755/24k) — checksums match; the
  picture is the same.
