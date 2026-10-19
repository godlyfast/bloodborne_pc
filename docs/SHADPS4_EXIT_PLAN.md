# Leaving shadPS4: where it remains, obstacles for other games, replacement order (2026-10-12)

> **Outcome (2026-10-13): `gpu/shadps4` removed.** Everything there was replaced with
> our code: command processor (`gpu/cp`), GCN definitions (`gpu/gcn`), shader translator
> (`gpu/shader`, tested against the game's shader corpus: SPIR-V byte-identical to before),
> renderer (`gpu/render`: pipelines, pipeline cache and disk storage, rasterizer in
> `raster_*.cpp` modules), buffer/texture caches, platform libraries.
> Only the online module remains from shadPS4 (`gpu/bbnet/shadps4`: network and NP),
> untouched. Next: optimization preserving asynchrony (section 6), and upscaler-integration
> documentation. The original plan follows as it was written.

Requirements: minimum overhead (CPU per draw, GPU per frame); no single-game knowledge
outside its profile (`gpu/games/`). Generality is checked on games with other engines,
where, for example, particles run entirely on asynchronous compute queues.

Measurements: RX 7800 XT / RADV, Ryzen 7 5700X3D, user's save.

## 1. How much shadPS4 remains

`gpu/shadps4` compared with original commit b4e7ae7: 118,000 lines,
88,800 (75%) original.

| Part | Lines | Own code | On draw hot path |
|---|---|---|---|
| `shader_recompiler` | 38,600 | ~2% | No (pipeline compilation only) |
| `renderer_vulkan` | 29,500 | 60% | Yes: rasterizer, pipeline cache, bindings |
| `amdgpu` (command processor, registers, tiling) | 8,700 | 28% | Yes: PM4 decoding (`liverpool.cpp`) |
| `buffer_cache` | 7,800 | 75% | Yes: `ObtainBuffer` (own code) |
| `texture_cache` | 4,800 | 13% | Yes: image lookup by address |
| `core/libraries` (gnmdriver, videoout, avplayer) | 11,800 | ~8% | Once/frame or submission |
| `common` | 10,000 | 1% | Utilities |

Own code outside shadPS4: memory module (`gpu/layer`), PM4 decoder (`gpu/cp`,
enabled manually), game profiles (`gpu/games`), A/B stage pipeline, Vulkan-recording
threads, upscalers, entire CPU side (loader, `src/` runtime).

## 2. Where the frame goes now (2026-10-13 measurement)

One point (Yharnam, ~885 draws), RX 7800 XT + Ryzen 7 5700X3D.

**GPU, user settings** (3840×1600 output, FSR 4.1.1 Native AA):
14.9 ms/frame, 67 FPS, GPU 99% busy (`BB_GPU_PROFILE=1`):

| What | ms/frame | Share | Owner |
|---|---|---|---|
| Game passes and dispatches | ~7.5 | ~50% | Game (translated by shadPS4 recompiler) |
| FSR 4.1.1 upscaler | 4.18 | 28% | Ours |
| Scene proxies (downscale/upload for passes expecting 1920×1080) | 1.51 | 10% | Ours, cost of resolution translation |
| GPU idle between submissions (7/frame) | 1.44 | 10% | Ours: submission boundary, synchronization |
| Game copy shader (60 dispatches with full barriers between them) | 0.35 | 2% | Barrier translation |

**CPU, light GPU load** (FSR 3 Ultra Performance): 175 FPS, GPU still 99% busy;
stage B 72% busy (`BB_SECTIONS=1`, µs/packet):

| Stage B part | µs | Owner |
|---|---|---|
| Total/packet | 2.54 | |
| Resource binding (buffers 0.36, textures 0.27) | 0.75 | shadPS4 (`BindBuffers`/`BindTextures`) + our caches |
| `ObtainBuffer` (including memory module 0.39) | 0.50 | Ours |
| Vertices/indices | 0.36 | shadPS4 + ours |
| Pass start | 0.20 | shadPS4 + ours |
| Ordered tasks (labels, DMA) | 0.24 | Command processor |
| Compute dispatches | 0.20 | shadPS4 |
| Dynamic state, descriptors, handoff to recording threads | 0.36 | Mixed |

Conclusion: this machine is always GPU-bound; shadPS4's CPU side has headroom
(stage B ceiling ~240 FPS at this draw count). Recoverable time is on the GPU
timeline, almost entirely in our code and synchronization/barrier translation.

## 3. What in shadPS4 obstructs "fast" and "any game"

1. **Command processor (`liverpool.cpp`).** Coroutines, large `switch`;
   CE (`DUMP_CONST_RAM`) and DMA/`WRITE_DATA` outside in-place memory execute on CPU
   during decoding. Compute queues (ASC) are coroutines on the same thread;
   **each packet drains the A/B pipeline** (`DrainDrawPipe(ReasonCompute)`).
   Bloodborne does not use ASC (0 submissions/frame); games with async compute do so
   routinely, losing parallel draw recording and compute/graphics overlap.
2. **Resource binding.** Every draw looks up buffers/images by address again;
   SRT walker (CPU execution of shader descriptor-table traversal) runs on a worker
   and again on stage B to validate. Caches (`texture set memo` 98–99% hits,
   `render state memo` ~80%) cut part of it but sit atop the same lookup.
3. **Address/hash texture cache.** Image inferred from T# address/format;
   overlap and render-target-as-texture use `FindImage` heuristics.
   Main artifact source for another game with different memory layouts.
4. **Pipeline key assembled from registers every draw** (`RefreshGraphicsKey`).
   Little dynamic state means many pipeline variants and compilations.
5. **Memory model** (already ours) has three paths: 0.3, sparse arena, module.
   Today found module's lifetime rules (once GPU-written in place, a block stays
   outside VRAM forever) accumulated across area loads, excluding whole ranges:
   −26% FPS over 17 minutes of lamp travel. Fixed by reset on full loader overwrite.
   General lesson: each block state needs an explicit event-driven exit, not forever.

## 4. Bloodborne-only knowledge in GPU code

| Where | What | For another game |
|---|---|---|
| `gpu/games/bloodborne.cpp` | Loader, allocator, heap hooks; per-frame writers; copy-shader hash | Profile (already so) |
| `renderer_vulkan/ui_composition.h` | Scaleform shader hashes (UI at output resolution) | Move to profile; no profile means no separate UI |
| `vk_camera_motion.cpp` | Recognizes Bloodborne scene constants (far plane 3000, size) | Profile; games with motion blur may expose their velocity buffer directly to upscaler |
| `vk_scene_resolution.cpp` | Scene = 1920×1080 targets | Profile parameter |
| `gpu/shim` | Frame rate, aspect ratio, menus, mouse, button icons (`KG_*`), hooks at 1.09 addresses | Specific game's port features |

## 5. Missing or unverified requirements for other games

- **ASC as actual Vulkan queues**: separate compute queue per game queue, labels
  and interqueue `WAIT_REG_MEM` as timeline semaphores; queue decoding without A/B drain.
- **GDS** (ordered append, counters, GWS): partial now (DMA/EOS to GDS);
  needs GDS memory as an atomic GPU buffer.
- **MSAA/EQAA with FMASK** (FMASK decompression currently skipped),
  CMASK fast clears, HTILE.
- **Tessellation/geometry shaders**: partial in shadPS4 recompiler;
  Bloodborne does not exercise them.
- **Memory without game hooks**: correctness using only write traps (64 KiB);
  a game with heavy CPU writes to GPU memory triggers a stream of traps.
  Module must work without profile (tested now: Bloodborne, no profile, 196 FPS).
- **Runtime** (`src/`) implements exactly what Bloodborne calls; another game needs
  more system libraries. Not shadPS4, but necessary for a second game to start.

## 6. Target architecture and low-overhead rules

1. **Stage B only records.** Anything decidable from register/descriptor snapshots
   moves to stage A workers (idle cores): pipeline, images, buffers, samplers,
   ready descriptor block. Stage B checks generation (resources unchanged) and copies
   the block (`VK_EXT_descriptor_buffer`): goal ~1 µs/packet instead of 2.5.
2. **Identity instead of search.** Image/buffer registry keyed by descriptor identity
   (address, format, sizes), invalidated by memory generation (write traps, GPU writes),
   without hashing game data on use.
3. **Change-driven state.** Decoder (`gpu/cp`) supplies written register blocks;
   state groups (rasterization, blending, depth, targets) recompute only on writes.
   More dynamic state (`VK_EXT_extended_dynamic_state3`, dynamic vertex input)
   means fewer pipelines.
4. **Command processor as translator, not emulator.** No CPU work "instead of GPU";
   compute queues are Vulkan queues; labels are GPU writes (already so).
5. **Game profile is the only game-knowledge location**: code addresses, shader hashes,
   motion-vector constant layouts, scene size, UI.

## 6a. Asynchrony: recoverable GPU time

| What | Now | Goal | How |
|---|---|---|---|
| Submission gaps | 1.44 ms | ~0.3 ms | Fewer submissions/frame (7 → 2–3); record next while GPU works on current; GPU label waits (timeline semaphores), not CPU |
| FSR on separate compute queue | 4.18 ms serial | Hide 30–50% | Upscale frame N alongside frame N+1 rasterization (shadows/G-buffer raster-bound, compute units free); two scene-target copies required (our proxy images: +~150 MB at 3840×1600) |
| Scene proxies | 1.51 ms | ~0.5–1 ms | Some passes render directly at scene size (`FragCoord` conversion exists); downscales on compute queue |
| Barriers from game cache flushes | Full barrier on `ACQUIRE_MEM` | Precise barriers | Translate actual request (`ACQUIRE_MEM` without `CS_PARTIAL_FLUSH`: no previous-dispatch wait); copy shader 0.35 → ~0.1 ms, plus other passes |
| Game async compute (ASC) | Same-thread coroutines + A/B drain every packet | Vulkan queues | Zero for Bloodborne (unused), mandatory for async-compute games |

User-settings estimate: −3…−5 ms from 14.9 → 85–100 FPS instead of 67 (+25–45%);
realistically +25–30%. Cheapest: submission gaps and precise barriers.
Most expensive: separate-queue FSR (double scene targets, UI synchronization).

On CPU, asynchrony means moving resource decisions to stage A workers (B only records),
and multiple stage B threads by pass. Here it only adds headroom (stage B 72% → ~30%
busy); on Steam Deck/weak CPUs it can remove the CPU bottleneck.

## 7. Replacement order

| Step | What | Gain | Risk | Check |
|---|---|---|---|---|
| 0 | Memory: module aging (done, under test); remove 0.3/arena after NVIDIA logs | Fewer `ObtainBuffer` branches; one path | Medium (NVIDIA) | Route, long lamp-travel session, tester logs |
| 1 | Command processor: `gpu/cp` default (find +7%), handlers from `liverpool.cpp`; ASC → Vulkan queues + timeline semaphores; GDS | Cheaper decoder; async compute; required for async-compute games | Medium | PM4 self-test + new ASC/GDS tests; Bloodborne |
| 2 | Binding decisions on A, descriptor buffers, identity image registry | B ~1 µs/packet instead of 2.5 (weak CPUs/high FPS) | High (image overlaps) | Route frames 1:1, `BB_SECTIONS` |
| 3 | Change-driven + dynamic state | Fewer pipelines, cheaper key | Medium | Pipeline count, first-session compilations |
| 4 | Profiles: UI, camera, scene size, icons in `gpu/games` | Second game without core edits | Low | Bloodborne unchanged |
| 5 | Platform: own gnmdriver/videoout/avplayer beside runtime | Less shadPS4 code, controlled PS4 API | Low | Bloodborne, then second game |
| 6 | Shader recompiler: retain (port upstream fixes), targeted changes (less descriptor specialization) | — | High if replaced | — |

Recompiler costs nothing per draw; replacing it poses the greatest image risk.
Leave it until last and only if needed (e.g. GPU descriptors).
Replace everything else one module at a time behind interfaces as in
[TRANSLATOR_ARCHITECTURE.md](TRANSLATOR_ARCHITECTURE.md): interface with shadPS4
behind it first, own implementation next; route, PM4 self-test and frames after every step.

## 8. Measurement tools

`Frame stats` (stage B µs/draw, idle), `BB_SECTIONS=1` (stage B breakdown),
`Draw pipe` (ready draws, drains by reason), FPS with light GPU load
(FSR 3 preset 4: CPU-bound), frame-time p99, GPU time (`BB_GPU_PROFILE=1`),
VRAM data share (`Layer memory: held in place`) over long play.
