# Session of 27 October 2026: Windows on the main PC

The main PC (Ryzen 7 5700X3D, RX 7800 XT, 32 GB) is now on Windows 11 LTSC. Everything is in
`E:\bloodborne`. The build is native, MSYS2 CLANG64 (`C:\msys64`), script
`out/win-native/build.sh`. Nothing was published: everything is local, nothing was pushed to git.

## Fixed (verified in the game)

| What | Cause | Where |
|---|---|---|
| White world (HUD only) on AMD under Windows | BC6H textures were created with the Storage flag, which the AMD driver does not support; now they are created without it if the driver refuses | `gpu/textures/image.cpp` |
| Menu settings were not saved (`Settings: cannot write`) | `std::rename` on Windows does not replace an existing file → `std::filesystem::rename` | `gpu/shim/bbport_settings.cpp` |
| **Stutters of 50–850 ms** when areas load (also on a friend's RTX 5060) | the `mprotect` wrapper for Windows called `VirtualQuery`, which walks all pages to the end of a uniform region: 5–16 ms per GiB, and the game heap is one view of 2.3 GiB. Now the regions are taken from the arena's `pieces` table | `gpu/platform/win32/posix_memory.cpp` |
| Stutters of ~200 ms when the game heap grows | importing a 320 MiB chunk into the GPU (120–170 ms) ran in the game thread under its lock. Now chunks are imported ahead of time in the background (`runtime_memory_commit_ahead`, `HeapGrowAhead`, `BB_HEAP_GROW_AHEAD=N`, default 2) | `src/runtime_memory.c`, `gpu/games/bloodborne/hooks_heap.cpp` |
| HUD without the vial/bullet icons and frames | the copy of the HUD atlas for the button icons was made with a blit from BC7, which is empty on AMD/Windows. Now a compute pass `atlas_decode.comp` (the double sRGB gamma went away as well) | `gpu/render/vk_button_prompts.*`, `gpu/render/shaders/atlas_decode.comp`, `gpu/CMakeLists.txt` |
| The model in the character editor spins 7 times faster at 200 FPS | `0x1db2780` adds `stick × [0x4928dfc]` (1.5) to the angle per frame; added to the redirected values (49 of 49) | `gpu/shim/bbport_frame_rate.cpp` |
| Crash on the opening cutscene of "New Game" (DL_PANIC "Mutex is not initialized", also on a friend's RTX 4060) | the game processes one player event per frame, and at 200+ FPS it managed to try to start the cutscene before our asynchronous StateReady (~10 ms) → it tore the cutscene down, and the audio thread started on a dead object. Now the tracks are looked up and StateReady is sent synchronously in `sceAvPlayerAddSource` (`BB_AVPLAYER_ASYNC_READY=1` restores the old behavior) | `gpu/platform/avplayer/player.cpp` |

Measurement while standing (one spot, 100 s): time lost in frames > 50 ms **9.6 s → 1.2 s**, median frame
**21.2 → 10.8 ms**.

## Done but not verified by the user

- Mouse in the port menu: coordinates from the window are converted to the frame size (`ToDisplay`); in
  windowed mode the miss was 25% of the width. The menu logic was verified with a scripted click.
- Upscaler markers in the GPU profiler per selected upscaler (FSR 4, FSR 3.1, …).

## Remaining

- The portrait of the "bes" slot in the save list is colored noise. Hypothesis: the portrait is captured
  from the GPU render at save time, and the CPU read stale memory instead of the VRAM copy. Not verified.
- The player sends the game StateStop right after Start although the cutscene is playing (does not affect
  playback).
- World-entry stutters (~470 ms, hundreds of textures) and 100–145 ms frames while textures load.
- A heavy game pass at 1920x800 (ps `6c2323c2`): 5.2 ms of GPU; possibly SSR from the port's patch.
- `VirtualQuery` calls are still in `Carve`/`SaveProtections` (munmap of part of a view).

## Diagnostics (off by default)

- `BB_OVERLAY_TRACE=1`: mouse in the port menu and checkbox toggling; `BB_MENU_KEYS_FILE` understands
  `click X Y`.
- `BB_AVPLAYER_TRACE=1`: video player calls and the events it sends to the game.
- Stutter lines: `write traps (all threads)` (lock wait / protection / MiB), `Windows: N
  VirtualProtect calls`; `heap grown … (import / lock wait / locked / GPU side told)`.
- Watchpoints on Windows (debug registers): `BB_RE_WATCH_ADDR`,
  `BB_RE_WATCH_VIRTUAL`+`BB_RE_WATCH_INDEX`, `BB_RE_WATCH_FOLLOW`, `BB_RE_WATCH_FILE` (address from a
  file, on the fly). `BB_RE_ANALOG` accounts for both sticks.
- `scePthreadMutexInit` writes the reason for a failure to the log.
- `out/win-native/bench/`: `standrun.ps1` (a standing run on a copy of the saves), `stalls.ps1`,
  `gpuprof.ps1`, `watch.ps1` (CPU/GPU/memory load from the outside), `memscan.exe` (value search in the
  game memory: changing/still/find/peek), micro-benchmarks `vp_bench*`, `vq_bench`, `import_*`.

## Changed files

`gpu/CMakeLists.txt`, `gpu/games/bloodborne/hooks_heap.cpp`, `gpu/games/bloodborne/hooks_probes.cpp`,
`gpu/platform/avplayer/avplayer.cpp`, `gpu/platform/avplayer/player.cpp`,
`gpu/platform/videoout/frame_stats.cpp`, `gpu/platform/win32/posix_memory.cpp`,
`gpu/render/shaders/atlas_decode.comp`, `gpu/render/vk_button_prompts.cpp`,
`gpu/render/vk_button_prompts.h`, `gpu/shim/bbport_frame_rate.cpp`,
`gpu/shim/bbport_guest_memory.cpp`, `gpu/shim/bbport_overlay.cpp`, `gpu/shim/bbport_settings.cpp`,
`gpu/textures/image.cpp`, `gpu/upscale/vk_temporal_upscaler.cpp`, `src/runtime_memory.c`,
`src/runtime_mutex.c`, `src/runtime_rewatch.c`. On 2026-10-27 they were carried over to the Linux tree: the
Linux build and `build.sh --test` pass; not verified in the game under Linux.
