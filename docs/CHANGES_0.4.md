# Changes in 0.4 (after 0.3, as of 2026-10-06)

Measurements — RX 7800 XT / RADV, Yahar'gul standing still, 1080p without an FPS cap; "4 cores" — `CPUS=0-3,8-11`
(4 cores / 8 threads, like the Steam Deck).

## PC memory model — default again, and for NVIDIA

- `BB_GUEST_IN_PLACE=1` by default (`run.sh`). In the launcher, instead of "New memory model" —
  an *Old memory model* toggle (the `legacy_memory_model` key): the 0.2 model as a fallback.
- NVIDIA maps dma-buf only at offset 0. Previously the port then fell back to the old model;
  now, with such drivers, each game direct-memory allocation is a separate Vulkan memory chunk
  (the game makes 14 allocations and maps each one once, in full, at offset 0). The startup
  check logs "the driver's dma-buf maps at offset 0 only: one chunk per direct memory allocation".
  `BB_GUEST_WHOLE_CHUNKS=1` enables this mode on other drivers too (testing without NVIDIA):
  on an RX 7800 XT 188–190 FPS, picture is fine. **Not tested on NVIDIA.**

## API level: the game's libGnm

The game is built with a static libGnm: PM4 packets are written not by the driver but by the game
itself, through the `sce::Gnm::DrawCommandBuffer` / `DispatchCommandBuffer` / `ConstantCommandBuffer`
functions in `0x1068000–0x10a0000` and `0x11fd000–0x11fe000`. That is the game's graphics API —
the level at which layers like DXVK operate.

- `tools/re/`: PM4 packet search in code (`pm4_scan.py`), call graph from function boundaries in
  `.eh_frame` (`callgraph.py`), function signatures from registers (`gnm_sigs.py`), hook table
  (`gen_gnm_table.py` → `gpu/shim/bbport_gnm_table.inc`), function names (`gnm_names.txt`).
- `gpu/shim/bbport_gnm_hooks.cpp`: hooks 513 libGnm functions at their entry (a jmp to a stub next
  to the image, relocated prologue), before the game code runs; each site is checked against
  eboot 1.09.
  - `BB_GNM_CENSUS=1` — call counting (`BB_GNM_CENSUS_FILE` — full list to a file).
  - `BB_GNM_OBSERVE=1` — each command-buffer method marks the packets it wrote; on submission it is
    checked where every packet came from. Result: **100.0% of packets (99.9% of words) are written
    by known API calls** — the game's command stream is fully described by Gnm calls.
  - `BB_GNM_TRACE=address[:count]` — arguments, calling code, and written packets.
- Findings: the game calls 99 command-buffer methods; the `0x26af230` reservation callback starts a
  new buffer chunk (the chunk list goes into the submission as separate DCBs); `writeDataInline`
  (`0x1073b80`) from GX zeroes 192 bytes at a time per pass; EOP markers (`writeAtEndOfPipe`, value
  1) are set by the GPU memory allocator, and `waitOnAddress` waits for those same markers — this
  is an in-queue-order barrier, not a CPU wait.

## Faster on weak CPUs

- `WRITE_DATA` and DMA waited for all pending host copies (22 µs per `WRITE_DATA`, ~35 per frame,
  12% of the draw-recording thread's time on 4 cores). Now they wait only for copies that read the
  range being written (`Scheduler::WaitHostCopiesFor`, a 64 KiB source table); the PS4 command
  processor also no longer waits for previous draws before such a write. Waits: 37 → 2 per frame.
  `BB_HOST_COPY_WAITS=all` — the old behavior.
- The check for concurrent writes into the scheduler (`ProducerScope`) is enabled only with
  `BB_PRODUCER_CHECK=1` (launcher: *Crash diagnostics*).
- 4 cores: 158 → 167 FPS.
- `BB_SECTIONS=1` now also shows stage-B tasks broken down by function.

## Fixes

- A minimized window (Win+D, "Show desktop") no longer terminates the game (issue #31): a 0×0
  surface reaches neither the frame size nor the swapchain; frames are not presented while the
  window is minimized. Only verified that normal output is unchanged: in Hyprland the window does
  not minimize to 0×0.

## Comparison with 0.3

Launcher, "For developers" section: *0.3-style synchronization* (`BB_AS_0_3=1` in `run.sh`)
restores what changed after that release: the old memory model, `WRITE_DATA`/DMA waiting for all
host copies (`BB_HOST_COPY_WAITS=all`), the concurrent-write check (`BB_PRODUCER_CHECK=1`).
Yahar'gul standing still, 1080p: 123 FPS versus ~186 with the new memory and translation model.
From the command line: `bash tools/play_ab.sh v03 BB_AS_0_3=1`.

## Depth of field (DoF) works again (issue #44)

With DoF and any upscaler (FSR 3/4/4.1.1, TAA), the far blur — sky, fog — showed dark rectangles
with sharp edges, bands, and an upside-down copy of the scene; this did not happen in 0.2. The
cause was the targeted constant-dump waits from 0.3 (`DumpConstRam` waits for the draw-recording
thread only when it overlaps with its reads): only constant buffers made it into the read list,
while the recording thread also reads vertices and indices from game memory. The game writes small
draw data (including DoF fullscreen quads) through the constant engine, and the dump for subsequent
draws overwrote it before it could be read. The window opened when the recording thread stalled
right before the DoF passes — during the upscaler passes. Now vertex and index ranges are in the
list too (unprepared draws wait in full). Waits went from ~150/s to ~850/s; FPS in the tested
places did not change. `BB_CONSTRAM_PIPE=0` — full wait on every dump (A/B).

This may also fix the flickering HUD icons and glyphs (issue #11) — not verified.

## Shader cache no longer breaks startup (issues #28, #38, #39)

- Cache files are written under a temporary name and then renamed: a crash or power loss leaves
  the old file or none at all, not a truncated one.
- A truncated record during a read no longer stops the game (`Invalid or corrupted
  deserialization container`, code 23): corrupted records are counted, and the cache is rebuilt.
  The same applies to SPIR-V with a bad header and to pipelines the driver rejected during
  preloading. SRT walker code from the cache is registered only after a length check.

## Misc

- A CPU without AVX, BMI1, MOVBE, LZCNT, POPCNT, or SSE4.2 (pre-Haswell Intel) — a clear startup
  message instead of `Guest fault (signal 4)`, code 132 (issue #26). `BB_SKIP_CPU_CHECK=1` — run
  anyway.
- `tools/fsr4cap/build_assets.sh` exited silently when one of the Steam folders had no GE-Proton
  (issue #40).
- Game-memory copies queued in direct recording mode (draws after the upscaler passes,
  `BB_VK_RECORD_THREAD=0`) are executed immediately rather than with the next submission.
- The in-game menu in English or Russian — a "Language" toggle in the menu (PR #36); defaults to
  the launcher's language. Launcher in Brazilian Portuguese (PR #10); untranslated strings are in
  English. README: repository address in the clone command (PR #43).
- `BB_TOGGLE_FILE` switch: bit 31 disables the texture gatherer; the second number in the file is
  experiment toggle bits (`BbToggle::Experiment`).

## Motion vectors (night of 2026-10-07, under verification)

- The Y-axis sign of the camera vectors is taken from the G-buffer viewport every frame
  (`BB_CAMERA_Y=up/down` — force), rather than being hardcoded: 0.2 and 0.3 were each wrong in
  their own places (issues #41, #42, #47, #18).
- If a frame has several G-buffer passes, the camera is taken from the one whose depth feeds the
  vectors.
- On upscaling presets, FSR 4 receives the frame in linear light (`BB_FSR4_LINEAR=0` — as before).
- The reactivity mask works with FSR 4 too: its output is blended with the current frame on
  effects (fog, lights, particles).

## The draw-recording thread no longer waits for command-recording threads (2026-10-07)

- The presenter (frame barrier, FSR 1, post-processing) is recorded the same way as draws, on the
  command-recording threads. Previously it took a command buffer directly: the draw thread waited
  for the recording threads to finish everything submitted (~90 µs every frame) and submitted the
  frame itself (~45 µs).
- Where commands are still written directly (upscaler passes: motion vectors, TAA, FSR 3/4,
  sharpening), they go into a separate segment with its own command pool, after the submitted
  segments, without waiting (`BB_DIRECT_SEGMENT=0` — wait, as before). Signals and ordered tasks in
  such a segment stay queued so they do not overtake earlier markers.
- The present thread waits for the frame submission (from the recording thread) to reach the queue
  before placing its own wait on it: otherwise one queue could wait on a later submission (GPU
  hang at startup, found during this work).
- DMA into memory the GPU uses in place (PC model) or that the GPU has written is a GPU-side copy
  in stream order; the draw thread no longer waits for copies and deferred signals before it
  (~16 µs each, ~900 per second: 4-byte GDS counters).
- Fixed two long-standing rare cases of writing into an already-submitted command buffer: a size
  change with sharpening above 1 (`Finish()` in the middle of an upscaler pass) and changing the
  FSR 4 preset in the menu.
- `BB_FINAL_DUMP_TRIGGER` (`KIND=final tools/frame.sh`): frame capture after FSR and
  post-processing.

Measurements (Hunter's Dream, standing still, 4 cores / 8 threads, PC model): 143–144 → 146 FPS;
the draw thread is no longer blocked on command recording (was 1.8–3.3% of the time). 16 threads:
PC model ~186, old model 144–151 (±3% spread between runs, no difference from the previous build).

## Operating mode in the launcher (2026-10-07)

- An *Operating mode* group with the *New memory and translation model* toggle (`BB_PC_MODEL=1`),
  off by default. Off — the old memory model, as in 0.3, with all fixes since. On — game memory is
  used in place by the GPU, and command-processor work is translated into Vulkan commands
  (experimental).
- AMD GPUs only: the launcher finds them via `/sys/class/drm/card*/device/vendor` (0x1002) and
  disables the toggle when there is no AMD; the GPU library itself keeps the mode off if the
  selected Vulkan device is not AMD (hybrid laptops). `BB_PC_MODEL_ANY_GPU=1` — force it on, for
  testing.
- The former *As in version 0.3* toggle moved to the "For developers" section as *0.3-style
  synchronization*: it is a rollback for regression hunting, not one of two modes.
- Both READMEs describe both modes, the table of differences from shadPS4, and plans.

## FSR 4.1.1 from your own DLL — via a launcher button (2026-10-07)

- *Upscaler → FSR 4.1.1 from your own AMD DLL → Choose DLL…*: you pick
  `amd_fidelityfx_upscaler_dx12.dll` 4.1.x, the launcher builds the assets
  (`tools/fsr4cap/build_assets.sh`) in the background, progress is shown in the row's caption and
  in the "Log" tab, and FSR 4.1.1 gets selected at the end. Cancel with the same button. Without
  the window: `--build-fsr411 <DLL> [loader]`.
- The DLL is checked before anything is written (`tools/fsr4cap/dll_info.py`: version from the file
  properties, FSR 4 models by shader names). Community OptiScaler builds (4.0.2b/c: model `v07_i8`,
  16 passes instead of 29, different weights) are not supported yet — a message says so right away,
  with nothing written. The loader is searched for next to the DLL and one folder up under both
  names (`amd_fidelityfx_loader_dx12.dll`, for OptiScaler — `amd_fidelityfx_dx12.dll`); otherwise
  the launcher asks for it.
- Proton is launched through umu-run if installed, otherwise inside the Steam container that this
  Proton requires (`toolmanifest.vdf`: Steam Linux Runtime 4 for GE-Proton 11) — umu is no longer
  needed.
- The AppImage contains prebuilt dxil-spirv and fsr4cap.exe (Nix) and SPIRV-Tools: no compilers or
  network needed, only GE-Proton. The working folder (Proton prefix ~300 MB) is deleted after the
  build.
- FidelityFX API headers (MIT) live in `tools/fsr4cap/ffx`: the SDK is no longer cloned.
- A new set replaces the old one only as a whole; script exit codes (2–7) are shown by the launcher
  as readable text. A previously built dxil-spirv that no longer runs (the tree moved) is rebuilt.

Tested: from source (Nix, umu) and as a package (Steam Linux Runtime 4 in an FHS environment) —
the result matches the previous `fsr4_411` byte-for-byte; the launcher button (headless session):
progress "N of 20", rejection for 4.0.2c. Not tested: the AppImage on a regular distro / Steam Deck
(on NixOS the AppImage hides the system `/nix` and the FHS links).
- After the first check (a DLL from Pragmata): this is the official FSR 4.0.3 with the same
  `v07_fp8_no_scale` model, but its AMD provider only exposes it on RDNA4 — on an RX 7800 XT, under
  any Proton, the DLL offers only FSR 3.1.5 and 2.3.4. Now 4.0.x is rejected right away with an
  explanation. A "loader" that is actually the upscaler DLL is rejected too (as happened in the
  video: there was no loader nearby, and the same DLL ended up in the picker window).
- Proton is chosen by trial: the first one under which the DLL enables FSR 4.1 (GE-Proton 10+,
  Proton-CachyOS, Proton Experimental, then Proton 11.0/10.0 from Steam), each with its own prefix.
  Tested on RX 7800 XT: GE-Proton 11-6, Proton-CachyOS 11 (July), Experimental (October) — yes;
  Proton 11.0-2c and GE-Proton 9 — no. The Steam Deck only had GE-Proton 9.
- On NixOS the AppImage says right away that the Steam runtime cannot run there (code 8), instead
  of the cryptic "failed to launch under Proton".

## FSR 4.1.1: one DLL and an FP8 variant for RDNA4 (2026-10-07, daytime)

- **The loader is no longer needed.** AMD's upscaler DLL itself exports the FidelityFX API
  (`ffxCreateContext` …), and `fsr4cap.exe` loads it directly; `dll_info.py` checks the export via
  the PE table. The loader is asked for only for DLLs without these functions (none encountered so
  far). Recording with the DLL directly matches recording through the loader (except for two bytes
  of an uninitialized constant in frame 0); the set matches byte-for-byte.
- Rebuilding from the AppImage failed: `cp: cannot create regular file …/fsr4cap.exe: Permission
  denied` — the file's copy from the AppImage is read-only, and a second copy over it cannot be
  created. Now the old file is deleted before copying (and the DLL too, if it is read-only).
- **FP8 on RDNA4.** On RDNA4, vkd3d-proton gives the DLL FP8 matrices, and it runs a different
  variant of the passes (issue #12): the same 29 passes, constants, and buffers, but WMMA FP8
  shaders, its own weights, and its own group grid (each pass has its own tile: 16×8, 32×1,
  16×4 …; `_post` — tensor width aligned to 32 instead of 4). After INT8, the build tries FP8 at
  the first size and, if the DLL returns different shaders (RDNA4), records all 20 sizes a second
  time (`fp8/capture_*`). `extract.py` checks the rules of both variants and writes `fsr4_411/fp8/`
  (FP8 matrices, `VK_EXT_shader_float8`) and `fsr4_411/fp8emu/` (FP8 via FP16 matrices, like
  vkd3d-proton on RDNA3 — for verification only). The game picks FP8 itself if the GPU has FP8
  matrices and the set is built; `BB_FSR411_VARIANT=int8|fp8|fp8emu` forces it. The
  `Upscaler: FSR 4.1.1 replay, …` line now states the variant.
- Matrix passes are launched with subgroup size 32 and full subgroups, as in vkd3d-proton (their
  wave-size heuristic matches matrix usage — `extract.py` verifies this). The game device enables
  `VK_KHR_cooperative_matrix`, `VK_EXT_shader_float8`, `vulkanMemoryModel`, `computeFullSubgroups`
  when available.
- Tested on RX 7800 XT: FP8 with emulation (GE-Proton 11-6, `BB_FSR4CAP_FP8=1`) — the DLL and the
  replay are **byte-for-byte identical** across 7 sizes, both models, 4 frames (`VARIANT=fp8emu
  verify.sh`; with dxil-spirv of the same version as in GE-Proton 11-6's vkd3d-proton — our pinned
  one is newer and rounds FP8 conversions differently in emulation). INT8 — as before (1600×900
  diverges at the right edge due to a race in the DLL itself). Live on RDNA4 **not tested**: the
  FP8-model passes from both dxil-spirv versions are identical; only `_post` differs.
- On RDNA3, FP8 is not recorded by default: emulation is almost twice as slow as INT8 (1440p
  Balanced, RX 7800 XT: 3.35 ms versus 1.82 ms). `BB_FSR4CAP_FP8=1` — record there too;
  `BB_FSR4CAP_FP8=0` — record nowhere.

## Controls and the game menu (2026-10-07)

- **Gesture menu from the touchpad.** Touchpad touches arrived with id 0 and no hold time, and the
  game rejected them: neither the touchpad, nor Back, nor Tab opened gestures. Now each new touch
  gets its own id (1–127), like on the DualShock 4, and a hold time. Tested in-game: left half of
  the touchpad — "Gestures", right half — "Personal Effects" (with the debug menu enabled, the
  left half opens it). The launcher notes this next to the touchpad bindings.
- **The keyboard works even with a gamepad connected.** Previously it controlled the game only
  when no gamepad was present (on Steam Deck there always is one); only Tab and Backspace worked.
  Now keyboard buttons are added to the gamepad's buttons, and a held movement/camera key fully
  deflects the stick. Not tested live with a keyboard (build and tests only).
- **The settings menu (Insert / L3+R3) remembers its position** — both between openings and
  between launches (`menu_pos` in bbport.ini, as a fraction of the screen: survives resolution
  changes). Previously it opened at the left edge every time.
- **Mouse cursor over the menu.** While the menu is open, the system cursor is shown (in fullscreen
  and after 3 s without movement it is hidden), and the menu knows where the mouse is right away,
  rather than after the first movement.
- **Settings from the menu no longer wipe key bindings.** The menu rewrote bbport.ini wholesale,
  with only its own keys: keyboard and gamepad bindings from the launcher (`key.*`, `pad.*`) and
  its other keys disappeared after any in-game change. Now the menu changes only its own lines and
  leaves the rest; the file is replaced as a whole (an interrupted write leaves the old one). Test:
  `ninja -C out/gpu settings-test`.

## BB_READBACKS=2 no longer hangs at startup

The exact readback mode protects GPU-written pages from reads as well. The port's copy threads read
them too (VRAM upload: `bb:Copy*`, `bb:VkRecorder`): the read fell into the fault handler, which
queued a readback to the GPU thread and waited, while the GPU thread was waiting for the
draw-recording thread, which was waiting for those copies. Now, in exact mode, the port's copies
read game memory through a second mapping of the same pages, which the protection does not touch.
Tested: with `BB_READBACKS=2` the game reaches the title screen and runs (previously it froze
during loading). Not tested in gameplay in this mode. `BB_PROBE=<wrapper>` in run.sh — run under
gdb etc., also from source.

## FSR 4.1.1 from the AppImage on NixOS (2026-10-07, evening)

The AppImage runs in its own mount namespace with a chroot, where its `/nix/store` replaces the
system one: from inside, neither `umu-run`, nor `nix-shell`, nor the Steam FHS environment is
visible, and the build button on NixOS ended with error 8. Now `capture_all.sh` on NixOS without
`umu-run`:
- if `nix-shell` is available (from source, on the system itself) — it re-executes itself in
  `nix-shell -p umu-launcher`;
- in the AppImage — it copies itself and `proton.sh` into the working folder
  (`~/.local/share/bbport/fsr4cap`, visible to both sides) and starts the capture on the system via
  `systemd-run --user --wait --pipe` in a login shell (the user's PATH and NIX_PATH); progress and
  the exit code come back, and canceling stops the service. SPIR-V translation then happens inside
  the AppImage. `systemd-run` from systemd-minimal (already in the package) has been added to the
  launcher's PATH.

Tested on this PC (NixOS): the windowless button (`--build-fsr411`) from the AppImage builds FSR
4.1.1 to completion, the set is byte-for-byte identical to the reference, the working folder is
deleted; canceling mid-capture stops the service on the system.
