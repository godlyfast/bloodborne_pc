# Plan: splitting the code into modules (2026-10-26)

Goal: the code should be easy for a person to read. Files of 2–4 thousand lines, functions of
200–700 lines and settings via `getenv` scattered across the tree are the main things reviews
complain about. The port's behavior does not change: each step is a move and a rename, not new
logic.

## Status as of the evening of 2026-10-26

Done (Windows build without errors; line-by-line check of the moves; `llvm-nm`: no local variable
ended up in two object files). Originals and the list of new files:
`Desktop\dev\bbport-archive\before-2026-10-26\MANIFEST.md`.

- Stage 1: `buffer_cache.cpp`, `buffer_cache_layer.cpp`, Bloodborne hooks (→ `games/bloodborne/`),
  `vk_temporal_upscaler.cpp`, `shader_rebuild.cpp` (the Linux part → `shader_predict.cpp`, not
  compiled here), `pipeline_cache.cpp`, `rasterizer.cpp`.
- Stage 2: the overlay's `Menu` split by sections; diagnostics moved out of the hot loop
  `CollectRingBindings`.
- Stage 3: inventory `docs/KNOBS.md` with removal candidates (removal — per your list).
- Stage 4: the old online module `gpu/bbnet/` removed.
- Stage 5: root sorted out, map `docs/ARCHITECTURE.md`.

Finished 2026-10-27 on Linux (Linux build and Windows cross-build without errors, `build.sh --test`
passes; not checked in the game). Originals: `bbport-archive/before-2026-10-27-linux-split/`.
- `shim/bbport_guest_memory.cpp` → `bbport_guest_memory.cpp` (model selection, `Install`, chunk
  lookup), `_chunks.cpp` (the chunks themselves: dma-buf export, host import, private regions),
  `_lazy.cpp` (lazy memfd import: udmabuf / host import), `_probes.cpp` (driver checks at
  startup) + `bbport_guest_memory_internal.h` (shared state — `inline` variables in
  `BbGuestMemory::detail`). Functions moved without edits.
- `src/runtime_memory.c` → 7 parts in `src/runtime_memory/`, `src/runtime_pad.c` → 7 parts in
  `src/runtime_pad/`. C code with dozens of shared statics: the parts are pulled in with `#include`
  in order (a single translation unit; expanding the `#include` gives the original source file
  line for line), so there are no renames and no new global symbols (`bb-probe` is built with
  `-rdynamic`).
- `launcher/bbport_launcher.py` (GTK, Linux) → the window and game launch stay in it;
  `bbport_launcher_common.py` (settings, choice lists, game environment, functions that need no
  window); the window pages are mixin classes of `LauncherWindow`: `_content.py` (mods, patches),
  `_online.py`, `_trophies.py`, `_log.py`, `_upscalers.py` (FSR 4.1.1 build, 4.1.2 models, DLSS
  libraries). Cross-checked by AST: all functions and methods are the same; one edit —
  `create_shortcuts` points to `bbport_launcher.py`, not to the module where it now lives. The
  window is built with real GTK; in the `test_launcher_gpu.py` test the `Adw` bases are empty
  classes (a mock base next to a mixin causes a metaclass conflict).
- Long hot functions (`LayerBind`, `BindTextures`, `PostDraw`, `CommandProcessor::Graphics`,
  `RunDrawPacket`) — only with a measurement of draw cost in the game.
- The remaining cold long functions (`CreateDevice`, `OnFlipStats`, `RunUiOnly`, `probe.c main`).

## What it was (measurement before the split) (measured over `gpu/` and `src/`, excluding third_party and vendored code)

**Largest files**

| Lines | File | What is inside |
|---:|---|---|
| 4002 | `gpu/buffers/buffer_cache.cpp` | buffer binding, readback, VRAM residency, write ticks, twins, VRAM traps (debugging), synchronization, config from env |
| 3129 | `gpu/layer/buffer_cache_layer.cpp` | the same `BufferCache` class: layer binding, promote/merge/demote, mirror pool, maintain, paged writes, traps and checks |
| 3039 | `gpu/shim/bbport_guest_hooks.cpp` | all hooks in the game code: detours, heap growth, effects, camera/aspect/HUD, job fixes, Gx guards, input probes |
| 2828 | `gpu/upscale/vk_temporal_upscaler.cpp` | frame dumps, resources and pipelines, TAA/EASU/sharpening/reactive/SMAA, target redirects, UI pass, FSR4/DLSS |
| 2294 | `gpu/render/shader_rebuild.cpp` | recipe packs, export/import, cache rebuild, prediction, metadata merge |
| 2013 | `gpu/render/pipeline_cache.cpp` | pipeline keys, programs, background compilation, shader import |
| 1849 | `src/runtime_memory.c` | |
| 1714 | `gpu/shim/bbport_overlay.cpp` | a single function `Menu` — 721 lines |
| 1665 | `gpu/shim/bbport_guest_memory.cpp` | |
| 1598 | `gpu/render/rasterizer.cpp` | |
| 1546 | `src/runtime_pad.c` | |
| 2465 | `launcher/bbport_launcher.py` | |

**Functions longer than 150 lines — 39 of them.** The longest:

| Lines | Function | Hot path (per-draw)? |
|---:|---|:---:|
| 721 | `shim/bbport_overlay.cpp` `Menu` | no |
| 546 | `shader/frontend/translate/vector_alu.cpp` `Translator::EmitVectorAlu` | no (switch over opcodes, shadPS4 style) |
| 419 | `vulkan/instance.cpp` `Instance::CreateDevice` | no |
| 410 | `platform/videoout/frame_stats.cpp` `OnFlipStats` | once per frame |
| 408 | `render/raster_textures.cpp` `Rasterizer::BindTextures` | **yes** |
| 381 | `layer/buffer_cache_layer.cpp` `BufferCache::LayerBind` | **yes** |
| 362 | `upscale/vk_temporal_upscaler.cpp` `RunUiOnly` | once per frame |
| 359 | `cp/cp_graphics.cpp` `CommandProcessor::Graphics` | **yes** (switch over PM4 packets) |
| 316 | `src/probe.c` `main` | no |
| 283 | `render/shader_rebuild.cpp` `MergeMetas` | no |
| 252 | `render/raster_pipe.cpp` `Rasterizer::PostDraw` | **yes** |
| 249 | `layer/buffer_cache_layer.cpp` `LayerMaintain` | once per frame |
| 239 | `render/raster_pipe.cpp` `CollectRingBindings` | **yes** |

**Settings:** 568 distinct `BB_*` variables and 634 `getenv` calls scattered across the files. Many
of them are A/B knobs of experiments that have already ended (for example, `BB_MIRROR_VRAM_ONLY`,
`BB_MIRROR_BURST`, `BB_SPEC_FAST_SIG`, `BB_IDLE_FLUSH_DRAWS`). It is not clear to the reader which of
them are real settings and which are debugging.

**"God" classes:** `BufferCache` (`buffer_cache.h`, 802 lines, methods in two `.cpp` files of 7
thousand lines) and `Rasterizer` (`rasterizer.h`, 924 lines).

## Stages

### Stage 1. Cut the big files by meaning (mechanical move)

Functions move whole, without code edits. The classes stay the same for now: several `.cpp` files
per class, as is already done for `Rasterizer` (`raster_pipe.cpp`, `raster_bind.cpp`,
`raster_textures.cpp`).

1. **`buffers/buffer_cache.cpp`** →
   - `buffer_cache.cpp` — core: `ObtainBufferImpl`, `ObtainBufferForImage`, `BindInPlace`, `CommandWrite*`
   - `buffer_readback.cpp` — `ReadMemory`, `DownloadMemory`, `Readbacks`, `SharedReadback`, `LayerCopyBackForCpu`
   - `buffer_residency.cpp` — `EnsureResident`, `AllocateResidency`, `Evict*`, `ProcessIdleBlocks`, `ProcessDemotions`, `QueuePromotions`
   - `buffer_write_ticks.cpp` — `WriteTicks`, `PreciseTicks`, `Note*Write*`, `ProcessLateWrites`, shadows
   - `buffer_twins.cpp` — twins
   - `buffer_sync.cpp` — `SynchronizeMemory*`, `UploadCopies`, `SubmitPendingArenaBinds`, dead images and unmap
   - `buffer_debug.cpp` — VRAM traps, `Report*`, statistics
   - `buffer_config.cpp` — reading env (`ChunkUploads`, `LayerMode`, `StreamBufferSize`, …)
2. **`layer/buffer_cache_layer.cpp`** →
   - `layer_bind.cpp` — `LayerBind` and the bind memo
   - `layer_promote.cpp` — promote, merge, demote, growth
   - `layer_mirror_pool.cpp` — creation, release, trimming and compaction of mirrors
   - `layer_maintain.cpp` — `LayerMaintain`, `LayerProcessIdle`, `LayerYieldToImages`
   - `layer_paged.cpp` — page writes, paged record/verify
   - `layer_traps.cpp` — traps, probes, read traps, verify
3. **`shim/bbport_guest_hooks.cpp`** → a new folder `shim/hooks/`:
   - `detour.cpp` — `InstallDetour`, `InstallCallDetour`, stubs, jumps
   - `heap_grow.cpp` — heap growth and shrinking, tracing, `HeapFind`
   - `effects.cpp` — hot effects, FXAA stub, `FxInitClear`
   - `camera.cpp` — aspect, free camera, mouse look, viewport, HUD, markers
   - `jobs.cpp` — job slots, allocation probe, resource cache
   - `gx_guards.cpp` — `GxNode`, `GxQuery`
   - `input_probes.cpp` — analog, stick, entry
   - `install.cpp` — `Install`, `OnTrap`
4. **`upscale/vk_temporal_upscaler.cpp`** →
   - `upscaler_dump.cpp`
   - `upscaler_resources.cpp` — `EnsureResources`, `CreatePipelines`
   - `upscaler_passes.cpp` — TAA, EASU, sharpening, reactive, SMAA
   - `upscaler_redirect.cpp` — `Mirror`, `Redirect*`, `OnDraw`, `OnColorTarget`
   - `upscaler_ui.cpp` — `EnsureUiResources`, `PrepareUiDepth`, `RunUiOnly`
   - `upscaler_backends.cpp` — FSR4, DLSS
   - the main `Run` and `RunScaled` stay in the original file
5. **`render/shader_rebuild.cpp`** →
   - `shader_recipes_io.cpp` — packs, export and import
   - `shader_rebuild.cpp` — cache rebuild
   - `shader_predict.cpp` — `PredictTest`, `Spec*`
   - `shader_meta_merge.cpp` — `MergeMetas`, `MetaReconstructTest`
6. **`render/pipeline_cache.cpp`** →
   - `pipeline_key.cpp` — `RefreshGraphicsKey`, `RefreshGraphicsStages`, `BuildRuntimeInfo`, `MakeProfile`
   - `pipeline_programs.cpp` — `GetProgram`, `LookUpProgram`, fetch code, `SpecSignature`
   - `pipeline_compile.cpp` — background compilation, preload queue
   - `pipeline_import.cpp` — `StartShaderImport`, `MergeShaderImport`
7. Second pass: `src/runtime_memory.c`, `src/runtime_pad.c`, `shim/bbport_guest_memory.cpp`,
   `render/rasterizer.cpp`, `launcher/bbport_launcher.py` (tabs and pages into separate modules).

Each new file gets 2–3 lines at the top: what is in it and which files it is related to.

### Stage 2. Long functions → named steps

A long function becomes a short "table of contents" made of calls `Step1()`, `Step2()`, … in the
same order. Cold functions first: `Menu` (by menu section), `CreateDevice` (feature chains),
`OnFlipStats`, `RunUiOnly`, `MergeMetas`, `LayerMaintain`, `probe.c main`.

**Hot functions** (`BindTextures`, `LayerBind`, `PostDraw`, `CollectRingBindings`,
`CommandProcessor::Graphics`, `RunDrawPacket`) — only with `static inline` or
`[[gnu::always_inline]]`. After each one a measurement of draw cost on weak hardware is needed: a
function call on the Deck/laptop costs a noticeable number of percentage points. `EmitVectorAlu` (switch over opcodes)
is left alone: it reads fine as it is.

### Stage 3. Settings (`BB_*`) in one place

- `common/knobs.h` and `knobs.cpp`: one table (name, type, default value, section, one-line
  description). The value is read once and cached. Instead of `getenv` in the code —
  `Knobs::Get(Knob::MirrorFloorPercent)`.
- `docs/KNOBS.md` is generated from this table: the full list of settings with descriptions.
- Sections: player settings / diagnostics / experiments.
- **Removing the knobs of ended experiments** — a separate list for your approval, by groups. I
  delete nothing silently.

### Stage 4. Dead code (only on your decision)

- `gpu/bbnet/` (the old online module, 147 files) and `gpu/bbnet20/`: BBSC 0.0.2 has already been
  moved into bbnet20. Is the old module still needed?
- Leftovers of the old memory model that were kept deliberately (readbacks, `memory_tracker`,
  sparse arena at `BB_LAYER_MEMORY=0`): keep or remove.

### Stage 5. Order in the project root and a module map

- The root holds logs, `message (6/7/8).txt`, 4 backups `shader_recipes.*.bin`,
  `cusa-cache (1).tar.gz`, `Shaders.zip` and so on. They will move to `../bbport-archive`, as on
  20.10 (I am not deleting them).
- `docs/ARCHITECTURE.md`: a module map (the path of a frame (PM4 → stage A → stage B → Vulkan
  recorder → presenter), what is responsible for what and where to look).

## How I verify

- **Build:** each step builds natively on Windows (MSYS2 CLANG64), without warnings where there
  were none before.
- **Tests:** `tests/` pass.
- **Linux code:** code under `#ifdef __linux__` is not compiled here. I will check it by building
  in WSL (nix has to be installed in WSL) or you will build it on a Linux machine.
- **Early launch:** until the game appears, only `bb-gpu-capabilities` works. When you transfer the
  dump, there will be one run in the game after stage 1 and after stage 2, plus a draw cost
  measurement after the hot functions.
- **PGO:** the profile will become partly outdated (static functions moved). I will retrain it
  after stage 2.
- **Git:** I publish nothing until you have reviewed it.

## Order relative to plan B

Stage 1 → (optionally stage 3) → plan B (image creation and binding in a separate thread) →
stage 2 and onward. Plan B touches `textures/` (`image.cpp`, `texture_cache*`). These files are not
among the largest, so stage 1 does not get in its way.

## What you need to decide

1. Do you approve stages 1–2 in this form (file names and boundaries)?
2. Stage 3 (settings): do we do it? Removal of the old knobs — as a list for approval?
3. Stage 4: the old `gpu/bbnet/` — delete or keep?
4. Stage 5: move the junk from the root to `../bbport-archive`?
