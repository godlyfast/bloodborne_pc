# New memory model on NVIDIA: summary of the work (2026-10-09)

The measurements below relate to the module's development stage. The current `0.5-pre2` changes
and the results of checking the original copy shader: [CHANGES_0.5-pre2.md](CHANGES_0.5-pre2.md) and
[TRANSLATION_GPU_COPY_LABELS.md](TRANSLATION_GPU_COPY_LABELS.md).

## The task

The new memory and translation model (`BB_PC_MODEL=1`) kept the game's memory in a single sparse buffer
(an "arena") and moved hot blocks into VRAM by re-binding pages (`vkQueueBindSparse`). On the
proprietary NVIDIA driver for Linux this does not work: since version 555 the time of
`vkQueueBindSparse` grows with the number of already bound pages, and the call itself holds a global
lock. For the tester (GTX 1660 Ti, driver 615.71) every move held the GPU chip for 10 seconds and
longer, and the desktop froze together with the game. Therefore the new model was available only on AMD.

Goal: the new memory model on all video cards.

## The solution: the layer's memory module

Instead of the sparse arena, a dedicated memory module runs (`gpu/layer/bblayer_gpu_memory.*`,
`gpu/shadps4/video_core/buffer_cache/buffer_cache_layer.cpp`, plan — `MEMORY_MODULE_PLAN.md`):

- the game's memory is bound **in place**, through buffers of its chunks (dma-buf on AMD, host memory
  import `VK_EXT_external_memory_host` on NVIDIA);
- frequently read data is copied into VRAM into separate "mirror" buffers. Moving comes down to a copy
  and bookkeeping in the module, without page re-binding;
- a binding takes the mirror if the range is entirely in VRAM, otherwise the game's memory in place.
  Ranges of 64 MiB and more go through a page table in the translated shaders.

**`vkQueueBindSparse` is not called even once in this mode**: the counter is printed in the log line
`Layer memory: ... vkQueueBindSparse: 0 calls`.

### When it turns on

| Video card | By default |
|---|---|
| AMD | sparse arena, as before |
| NVIDIA, Intel and the rest | memory module, automatically |

`BB_LAYER_MEMORY=1` / `=0` selects it manually. The launcher no longer hides the "New memory
and translation model" switch on video cards not from AMD. The module-mode startup check of host
memory import verifies writes by the GPU chip and the CPU through the imported buffer itself, without
a sparse buffer.

## What had to be fixed for the module to work correctly and fast

### Speed: from 48–60 FPS to ~205 FPS on AMD (standing by the lamp)

1. **Image copy and clear substitution was not firing.** The `IsComputeImageCopy` and
   `IsComputeImageClear` detectors expected the shader to have exactly two buffers, while the module
   added a third to every shader — the page table. The render-target copy (`cs 3d5ebf4e`) and the
   clear (`cs 8b355b5a`, 31 times per frame) ran as real shaders through memory, and the 1080p
   images were re-uploaded every frame. Now the page table is not counted (`ShaderBufferCount`):
   60 → 136 FPS.
2. **Mixed ranges.** If all blocks of a range are in VRAM except one or two edge ones with
   "unknown" bytes (a gap between images, someone else's data), the whole range was read through
   the bus. Such blocks are now "volatile": they live in the mirror and are updated from the game's
   memory before every read binding. 139 → 207 FPS. Volatile blocks are not used for write bindings.
3. **Promotion to VRAM on the first binding** of a range of known data (as the arena did). It
   respects `BB_GARLIC_VRAM=0` and the VRAM budget (`BB_VRAM_PROMOTE_PERCENT`, important for 6 GB
   cards).
4. **CPU load.** The module's answers are cached by placement generation; repeated "can it be
   promoted" checks happen no more than once per frame per range; the "does the range have a VRAM
   copy" check is lock-free, via the module's version counter. This removed about 20% of binding time
   and almost all locks in the command-processor thread.

### Correctness: vertex explosions and garbage textures

There was one cause: **the VRAM copy diverged from the game's memory**. Several paths were found and
closed:

1. **Game code writes to memory without our knowledge**: its heap headers (`0x2085a60` / `0x20858a0`),
   part of the resource loader (`0x216d420`). Blocks with a VRAM copy are now write-protected by the
   module's own traps. The write goes through immediately, and the block is returned in place before
   the next binding. Frequently written blocks stay in place forever (`NoteCpuWrite`).
2. **Reads bypassing the module.** Small bindings, the constant ring and command-processor copies
   took data from the game's memory even though the GPU chip's new data was in VRAM: in the new
   model `IsRegionGpuModified` knows only about unfinished writes. Now everything that touches a
   block with a VRAM copy goes through the module (`LayerMirrored`).
3. **GPU-chip data overwrote newer CPU data.** When returning a block in place and when handing
   memory back to the game, the module copied the "GPU-modified" data back, including over what the
   CPU had managed to write later: the marks were placed too broadly. Now declared CPU writes clear
   the marks from their bytes (`LayerForgetGpuData`), re-handing memory to the game clears the marks
   from its range, and after an undeclared write the GPU-chip data in the block is considered dead
   and is not copied back.
4. **Where the GPU chip may write in VRAM** (`BB_LAYER_GPU_WRITES`): by default (`1`) — only into
   blocks the CPU has not touched since allocation: render targets and other GPU-only data. `0` —
   never (correct, but 60–70 FPS: writes go through the bus), `2` — everywhere (produced explosions).
5. **The game's copy shader** in `0.5-pre2` is by default translated into SPIR-V and executed
   on the GPU. The page table contains the current GPU representation and game-memory addresses;
   the copy shader writes the result into both representations. This eliminates divergence between
   the VRAM mirror and the game's memory without substituting the original CPU copy list.
   `BB_COPY_SHADER_NATIVE=0` keeps HLE for comparison.

At the previous stage it was verified in game on AMD (module enabled manually, copy shader through
HLE): with `BB_LAYER_GPU_WRITES=0` and with the rule "the GPU chip writes in VRAM only inside
images" — Hunter's Dream, dogs and corpses in Yharnam are clean. On the latest build (the "blocks
the CPU has not touched" rule) no artifacts were noticed during play, but a separate check of all
locations has not been done yet.

## Measurements (RX 7800 XT, AMD, module enabled manually)

| Location | Module | Sparse arena | Old model |
|---|---|---|---|
| By the lamp, in the morning (before the correctness fixes) | ~205 FPS | ~205–238 | ~220 |
| Hunter's Dream, now | 130–144 FPS | — | — |

In Hunter's Dream we hit either the GPU-command thread on the CPU (~3.9 µs per call at
~1500 calls per frame) or the GPU chip itself: G-buffer passes 960×540, FSR ~1.07 ms.

**Open question:** in some runs at the same location the GPU chip works noticeably slower
(70–95 FPS, FSR up to 3.2 ms instead of 1.07). The cause has not been found; the versions involving
shader compilation, per-section profiling `BB_SECTIONS` and volatile-block updates were not
confirmed. Comparing runs is complicated by the game drawing different passes depending on the
camera angle and the scene.

## What is untested

- **NVIDIA itself.** On AMD the NVIDIA path (host memory import + module) cannot be reproduced:
  RADV does not import memfd. The tester's log is needed.
- Cards with a small VRAM size (6 GB): behavior with VRAM full has been checked only
  artificially (`BB_VRAM_PROMOTE_PERCENT=1`: no copies, ~38 FPS, stable).
- Intel.

## What to ask from the NVIDIA tester

A build with the "New memory and translation model" enabled in the launcher. The log must contain
the lines:

- `Guest memory: host memory imported by the GPU (VK_EXT_external_memory_host ...)`;
- `Guest memory: the new memory model through the layer's memory module on this GPU (vendor 0x10de)`;
- `Layer memory: ... vkQueueBindSparse: 0 calls, 0 ranges; write traps hit N`;
- `Frame stats: ... FPS`.

If a line `vkQueueBindSparse of N ranges took X ms` is visible, then sparse is still used
somewhere — that is an error.

## First NVIDIA logs and fixes (evening 2026-10-09, `0.5-pre3`)

Tester: GTX 1660 Ti (laptop, 6 GB, PCIe 3.0), driver 615.71, build 0.5-pre2. Host memory
import and the module turned on, `vkQueueBindSparse: 0`.

1. **There were no mirrors at all** (10–15 FPS, background flicker on the title screen):
   `FixedArena()` was enabled by default with host memory import and forbade promotions to the
   module through `GarlicInVramForLayer()`. Now in module mode it is always off. Until the new
   build, the workaround is `BB_FIXED_ARENA=0`: with it the tester gets 30–35 FPS (video),
   versus 60–70 in the old model.
2. **The texture cache and the mirrors shared VRAM without a common budget.** The texture-cache
   collector compares all process VRAM against thresholds, the mirrors too, and the thresholds on
   cards below ~9 GB are 40 and 80% of the starting budget (for the tester: pressure 1963 MiB,
   critical mark 3927 MiB). Promotions, however, stalled only at 90% of the driver budget. The
   result — 3.9–4.0 GB, the collector constantly above the critical mark: 155–1255 evicted images
   per 5 s versus 0–29 on AMD. Now:
   - promotions to VRAM stall 384 MiB before the critical mark (`VramPromotionsPaused`, the line
     `copies of loaded blocks wait`);
   - 128 MiB before it the module frees space itself (`LayerYieldToImages`): first it trims the
     mirrors' growth reserve, then returns whole mirrors unused for 3 s in place
     (`BB_VRAM_PRESSURE_IDLE_SECONDS`).
3. **Mirror rebuilding.** A chunk adjacent to a mirror created a whole new mirror with a copy of
   the old one. During level loading this was 15–27 GB of allocations for 1.3 GB of data and a VRAM
   spike to 7.4 GB (in the tester's log 5.6 GB against 6 physical). During play, when districts
   stream in, the same thing. Now an upward-growing mirror gets a growth reserve equal to its own
   size, but no more than 64 MiB (`BB_LAYER_MIRROR_GROWTH_MB`): 5–10 GB of allocations, worst
   loading frame 555 → 87 ms. Replaced mirrors are freed on every submit, not once a second.
4. **`WRITE_DATA` writes into a mirror.** The command processor writes on the GPU chip into the
   game's memory; a block with a mirror used to go in place. If the range is entirely in one
   mirror, the write goes into both representations (`CommandWriteMirror`).
5. **Watched blocks** (`BB_LAYER_WATCH`, on by default). Blocks in which the CPU had ever written
   without warning were previously always read in place, and that means through the bus on NVIDIA.
   Now for read bindings they too get a mirror under a write trap. A CPU write does not return the
   block in place: it is re-uploaded before the next binding, and the trap is armed again. The GPU
   chip writes into such blocks in place; a block it has written to is no longer watched. Watching
   almost completely replaced volatile blocks (RX 7800 XT: 1.3 GB/s of re-uploads → 36 MB/s; the
   tester had 455 MB/s of volatile ones). Blocks that the CPU writes often (3 frames out of 60)
   still go in place: re-uploading them before bindings ended the render pass (GPU chip 4.8 →
   7.2 ms per frame). `BB_LAYER_WATCH_HOT=1` — an experiment with them.
6. Runtime file reads (`read`/`pread`) are retried if the kernel returned `EFAULT`: the trap could
   have been armed again between touching the pages and the read.

Checked on RX 7800 XT with `BB_VRAM_LIMIT_MB=5600` (collector thresholds like the tester's:
1960/3920): old model ~195 FPS; module ~200–213 FPS, GPU chip 4.6–5.2 ms; VRAM stays below the
critical mark; the `docs/route2.txt` route without frames longer than 25 ms; 3 minutes of walking
without errors; the picture in Hunter's Dream and at the end of the route is the same as without
watching. NVIDIA itself is not checked by these measurements: on AMD in-place reads are almost free.

## Feedback on 0.5-pre3 and fixes (`0.5-pre4`)

- **GTX 1060 6 GB:** the new model is on par with the old one (41–48 FPS at ~1500 calls per frame in
  both, GPU chip 21–24 ms). The early drops are shader compilation in the first session (160–241
  compilations per 5 s, hitches of 1–3.7 s): now new pipelines of passes drawn every frame are
  built in the background (`BB_ASYNC_PIPELINES`), and their draws are skipped for a frame or two.
- **4 GB card:** after ~4.5 minutes 5 FPS — a pre3 regression. Promotions to VRAM stalled
  384 MiB before the texture collector's critical mark (a 4 GB card has the lower threshold
  values, 1536/3072 MiB), while textures and service allocations already held 2808 MiB: copies
  became 124 MiB for 1.9 GB of data, GPU chip ~200 ms per frame. Now the mirrors have their own
  share (25% of the driver budget, `BB_LAYER_MIRROR_FLOOR_PERCENT`): below it the collector pause
  does not apply.
- **~10 FPS less after a teleport:** big bindings over all memory (through the page table) marked
  every 2 MiB as used, so nothing in the game stayed idle, and the mirrors of the departed location
  held VRAM. Now only direct bindings are counted (`layer_group_use`): when VRAM is short, data not
  directly bound for 3 s goes away first, and mirrors with memory without valid blocks are recreated
  only over valid ones (`LayerCompactMirrors`) — otherwise a partially returned-in-place mirror held
  all its memory. On RX 7800 XT with `BB_VRAM_LIMIT_MB=4200–4600` this freed 160–490 MiB at a time,
  the picture unchanged. Not checked on NVIDIA.

## Switches and diagnostics

| Variable | What it does |
|---|---|
| `BB_LAYER_MEMORY=1/0` | memory module on/off (default: on for non-AMD) |
| `BB_LAYER_GPU_WRITES=0/1/2` | where the GPU chip may write in VRAM (see above), default 1 |
| `BB_LAYER_WRITE_TRAPS=0` | without write traps (only for comparison: the explosions return) |
| `BB_LAYER_VOLATILE=1` | with volatile blocks (since 2026-10-10 off by default: their copies broke render passes) |
| `BB_LAYER_PAGED=0` | without the page table for bindings of 64 MiB and more |
| `BB_COPY_SHADER_NATIVE=0/1` | HLE / native game copy shader; in the new model native by default |
| `BB_RESIDENCY_MIX=1/2` | in-place / VRAM / mixed bindings; `2` — also the heaviest ones with block analysis |
| `BB_LAYER_WRITE_LOG=1` | large GPU-chip writes left in place, and the images nearby |
| `BB_TOGGLE_FILE`, experiment bit 8 | in-place reading instead of VRAM copies (checking stale copies) |
| `BB_TOGGLE_FILE`, experiment bit 16 | without volatile-block updates |
| `BB_LAYER_WATCH=0` | without watched blocks (blocks the CPU wrote to are read in place) |
| `BB_LAYER_WATCH_HOT=1` | also watch frequently CPU-written blocks (experiment) |
| `BB_LAYER_MIRROR_GROWTH_MB=N` | mirror growth reserve, default 64; `0` — no reserve |
| `BB_VRAM_PRESSURE_IDLE_SECONDS=N` | when VRAM is short, data not directly bound for N s goes in place (3; `0` — never) |
| `BB_LAYER_MIRROR_FLOOR_PERCENT=N` | share of the VRAM budget the texture collector does not take from the mirrors (25) |
| `BB_ASYNC_PIPELINES=0` | new pipelines compile immediately, the game waits (default — in background for passes drawn every frame) |
| `BB_ASYNC_PIPELINE_THREADS=N` | number of background compilation threads (default a quarter of the CPU threads, 1–4) |
| `BB_VRAM_LIMIT_MB=N` | test: the driver VRAM budget is considered no more than N MiB (simulating a 6 GB card: 5600) |
| `BB_RESIDENCY_MIX=1` | the `Layer in place` line now also says why blocks are not watched |

## What next

1. A log from NVIDIA.
2. Find the cause of the slow runs (or prove that it is a different scene).
3. Volatile blocks update at 0.9–1.6 GB/s — it would be cheaper to update them only after a CPU
   write (the traps already exist).
4. If the module is confirmed on NVIDIA, switch AMD to it too and remove the sparse arena from the
   new model.
