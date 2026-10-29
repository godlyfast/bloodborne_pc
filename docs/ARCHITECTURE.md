# bbport code map (2026-10-26)

A short guide: what lives where and where to look when something is wrong. Details on
individual topics are in the docs referenced by the file headers (`docs/parallel_gpu.md`,
`docs/MEMORY_MODULE_PLAN.md`, `docs/upscaler.md`, ...). All `BB_*` settings with descriptions are in
`docs/ENVIRONMENT.md` (from `gpu/shim/bb_env_vars.def`).

## How startup works

1. `scripts/` (Python, offline): the game's eboot is checked (`game_check.py`) and turned into a flat
   image; the PS4 libc and libSceFios2 are linked into it (`prepare.py`, `link_libc.py`,
   `link_modules.py`); patches are applied (`patches.py`, `patches/Bloodborne.xml`).
2. `run.sh` (Linux) / `run.py` (Windows) assemble the environment from `bbport.ini` and the launcher
   and start `bb-probe`.
3. `src/probe.c` is the loader: it maps the image and jumps into the game code. The game code runs
   on the CPU as is.
4. `src/runtime_*.c` is the runtime in C: what the game calls from the PS4 system libraries (memory,
   threads, synchronization, files, sound with ATRAC9, gamepad, saves, AppContent, network stubs).
   The two largest files are split by topic into subdirectories: `src/runtime_memory/` (the memfd pool
   and its second view, the VMA table, the memory `sceKernel*` functions, the low region, heap growth,
   write traps) and `src/runtime_pad/` (stick calibration, touchpad, gamepad selection, keyboard and
   mouse layout, button prompts, motion without sensors, polling). The parts are pulled in with
   `#include` in `runtime_memory.c` / `runtime_pad.c` in order: this is a single translation unit,
   static variables are shared, and the parts are not compiled separately.
5. Graphics calls and GPU commands go to the `gpu/` library (`libbbgpu`).

## A frame's path to the GPU

```
the game writes PM4 (through the statically linked libGnm)
  -> gpu/cp/              command processor: PM4 parsing, registers, DMA, labels, fences
  -> stage A (GpuComm thread, gpu/render/raster_pipe.cpp):
       program and pipeline selection (render/pipeline_*.cpp),
       constants into the ring (CollectRingBindings), draw packing
  -> stage B (DrawRec thread): buffer/texture binding (render/raster_bind.cpp,
       raster_textures.cpp), render targets (raster_targets.cpp), state (raster_state.cpp)
  -> Vulkan recording thread (VkRecorder, render/scheduler.cpp) -> vkQueueSubmit
  -> presenter (render/presenter.cpp): upscaler, frame generation, UI, swapchain
```

GCN shaders are translated to SPIR-V in `gpu/shader/` (frontend → IR → passes → backend). Finished
pipelines are cached on disk (`render/pipeline_store.cpp`, `render/blob_store.cpp`); shader recipes
(`shader_recipes.bin`) allow almost everything to be compiled ahead of time in the background
(`render/pipeline_import.cpp`, `render/shader_rebuild.cpp`).

## `gpu/` directories

| Directory | What is inside | Where to start |
|---|---|---|
| `cp/` | PM4 command processor: graphics, compute queues, "in stream order" tasks | `command_processor.h`, `cp_graphics.cpp` |
| `render/` | Rasterizer (draw/dispatch → Vulkan), pipeline cache, scheduler, presenter | `rasterizer.h`, `raster_pipe.cpp`, `pipeline_cache.h` |
| `shader/` | GCN → SPIR-V translator (originally from shadPS4) | `recompiler.h`, `specialization.h`, `resource.h` |
| `gcn/` | description of the GCN hardware: ISA, registers, sharps (V#/T#/S#) | `isa.h`, `regs_targets.h`, `sharps.h` |
| `buffers/` | buffer cache: game memory for the GPU, VRAM residency, readback | `buffer_cache.h` (+ `buffer_*.cpp`) |
| `layer/` | memory module of the layer: game memory in place + VRAM mirrors | `bblayer_gpu_memory.h`, `buffer_cache_layer.cpp` |
| `memory/` | dirty page tracking, protections, fault sources | `dirty_tracker.h`, `page_watch.h` |
| `textures/` | texture cache: lookup, upload, detailing, collector, spare images | `texture_cache.h`, `image.h`, `image_spares.h` |
| `upscale/` | FSR 3.1/4/4.1.1, DLSS, frame generation, motion vectors, TAA/SMAA, VBAO | `vk_temporal_upscaler.h` (+ `upscaler_*.cpp`) |
| `vulkan/` | instance, device, swapchain, pools, timeline | `instance.h` |
| `platform/` | system libraries on the GPU-library side (videoout, gnm, kernel) | `videoout/`, `gnm/` |
| `shim/` | glue with the runtime, overlay menu, settings, window, diagnostics, "any game" hooks; game memory for Vulkan (`bbport_guest_memory*.cpp`: model selection and chunk lookup, whole chunks, lazy memfd import, driver checks at startup) | `bbgpu.cpp`, `bbport_settings.h`, `bbport_overlay.h`, `bbport_guest_memory_internal.h` |
| `games/` | everything that knows about a specific game | `game_profile.h`, `bloodborne/` |
| `bbnet20/` | online module (`libbbnet20.so`, Linux only): shadPS4 0.20 network/NP, BBSC, THD | `bbnet.h`, `SHADNET-PORT.md` |
| `third_party/` | third-party libraries (sirit, imgui, fsr-vulkan, ...) | — |

## The "shared layer / game" boundary

- The core (cp, render, shader, buffers, layer, textures) knows nothing about Bloodborne: a game
  without a profile takes the generic paths (`BB_GAME_PROFILE=none`).
- Everything about Bloodborne is in `gpu/games/`:
  - `bloodborne.cpp` is the profile: serials, hooks, known writers of per-frame data;
  - `bloodborne/hooks*.cpp` are hooks into the game code: memory (`hooks.cpp`), effects, job fixes,
    heap growth, camera/HUD for any aspect ratio, GX protections, RE probes;
  - `bloodborne_menu_pointer.cpp`, `bloodborne_kit_restore.cpp`.
- Also game-specific (not yet in `games/`): `shim/bbport_frame_rate.cpp` (FPS unlock),
  `shim/bbport_game_menu.cpp` (pages in the in-game menu), `shim/bbport_engine_fixes.cpp`,
  frame markup for the upscaler (`upscale/vk_camera_motion.cpp`: the camera from the constants of the
  G-buffer pass).

## Conventions

- **One class, several files.** Large classes are split by meaning: `Rasterizer` →
  `rasterizer.cpp`, `raster_*.cpp`; `BufferCache` → `buffer_*.cpp` and `layer/layer_*.cpp`;
  `PipelineCache` → `pipeline_*.cpp`; `TemporalUpscaler` → `upscaler_*.cpp`. Each file's header
  says what is in it.
- **`*_internal.h`** is what the parts of one module share (only they include it). Shared mutable
  state there is marked `inline`: one instance for the whole program. A file's local state goes in
  its anonymous namespace.
- **Settings** are `BB_*` variables (all with descriptions: `docs/ENVIRONMENT.md`); for the player,
  `bbport.ini`, the in-game menu (`shim/bbport_settings.h`) and the launcher. New behavior is usually
  introduced with a switch, so that it can be turned off without a rebuild.
- **Diagnostics** are `BB_*` variables marked "diagnostics"; in hot loops they sit behind a single flag
  check, with the work itself in a separate cold function.

## Build

- Linux: `build.sh` (nix-shell, `shell.nix`), packages in `packaging/` (AppImage, nix).
- Windows: cross-build with `packaging/windows/package.sh` (llvm-mingw + MSYS2 sysroot) or natively
  in MSYS2 CLANG64: `cmake -S gpu -B out/win-native -G Ninja -DBB_NET=OFF` (xbyak: headers
  separately, see `CMAKE_CXX_FLAGS`).
- Tests: `build.sh --test` (C runtime), `*-test` targets in `gpu/CMakeLists.txt` (EXCLUDE_FROM_ALL).
