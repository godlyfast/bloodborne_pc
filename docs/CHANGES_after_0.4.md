# Changes after 0.4 (since 2026-10-08)

Measurements — RX 7800 XT / RADV, Hunter's Dream at the lamp (user's save), 1080p with no FPS
limit, new model (`BB_PC_MODEL=1`); "4 cores" — `CPUS=0-3,8-11` (4 cores / 8 threads).
Details and what remains — [EMULATION_REMOVAL_PLAN.md](EMULATION_REMOVAL_PLAN.md),
"Step 3".

## EOP/EOS labels written by the GPU (new model)

- `EVENT_WRITE_EOP` without interrupt, `EVENT_WRITE_EOS` and `RELEASE_MEM` of the compute
  queues: a Vulkan buffer marker (`VK_AMD_buffer_marker`, end of pipeline) straight into game
  memory, at the same point in the stream where the PS4 command processor writes them. Previously
  each label was written by the CPU thread after all Vulkan submission finished — ~330 labels per
  frame, 61 thousand per second.
- The 64-bit label — two 32-bit writes, high half first (whoever sees the new low half also sees
  the new high one).
- Labels with an interrupt, as well as without `VK_AMD_buffer_marker` (NVIDIA) and with
  `BB_FREE_CHECK=1` — as before. `BB_GPU_LABELS=0` — as before everywhere.
- EOS with a GDS write: a GPU copy in stream order instead of waiting for the whole GPU
  (`Finish()`) and writing from the CPU.
- Statistics: the `EOP fences` line shows how many labels per frame the GPU wrote.
- FPS the same (16 threads: 233; 4 cores: ~217 vs ~215), picture the same; 8 minutes of walking —
  see below.

## Game code hooks without traps

- The points where the game allocates GPU memory (the range allocator, three heap sites) and
  where loaders copy resources (`memcpy`) used to be `int3`: each call — a kernel signal (SIGTRAP),
  ~1200 per second for the allocator alone. Now a jump to a stub near the game image: the stub
  calls the handler and executes the overwritten instructions; the `memcpy` call goes through a
  trampoline.
- The bytes are overwritten on top of the `int3` already in place (a thread hitting it at that
  moment goes to the stub). `BB_GUEST_HOOK_TRAPS=1` — traps, as before. The diagnostic points
  (`BB_FRAME_STATS`, `BB_HEAP_SITES`) remain traps.

## New memory model on NVIDIA

- A new way to hand the game's memory to the GPU — host memory import
  (`VK_EXT_external_memory_host`): a piece of direct memory stays in the runtime's memfd, the GPU
  imports its second mapping. The CPU works with ordinary cacheable memory, the GPU — across the
  bus, as with a PC game's upload heap. Freed memory in such chunks is zeroed rather than
  discarded from the memfd (the GPU holds those pages).
- At startup, a self-check exactly as in operation: import a memfd chunk, bind it to a sparse
  buffer, GPU write — CPU read through the other mapping, CPU write — GPU copy; the sparse buffer
  for such memory must also accept VRAM. If it fails — dma-buf (on NVIDIA — "one chunk per
  allocation"), for which the CPU read speed through the driver's mapping is now measured (below
  1 GB/s — not used: game code runs on this memory). If that fails too — the old model. In the
  log: `Guest memory: host memory imported by the GPU`, `host memory import does not work here:
  …`, `CPU reads through the driver's dma-buf: N MB/s`.
- Order: on AMD — dma-buf (as before; RADV does not import memfd — `ErrorInvalidExternalHandle`,
  verified), on the rest — import first. `BB_GUEST_MEMORY=host` or `dmabuf` forces the choice.
- The arena (the sparse buffer of game memory) is created with whichever external memory type is
  chosen; if the driver doesn't let VRAM into the arena with it — the old model with a message in
  the log.
- Launcher: the *New memory and translation model* switch is available on AMD and NVIDIA (texts in
  three languages). Without the launcher — `BB_PC_MODEL=1`.
- **Not tested on NVIDIA** (the author only has AMD): a log from NVIDIA is needed.

## Diagnostics

- `BB_DCB_STATS=1`: besides the command buffer structure — PM4 packets per second by type,
  `EVENT_WRITE` events by type, EOP by data source and interrupt, EOS by command, `WAIT_REG_MEM`
  by location and engine, and how the waits ended (VO label, in-stream-order label, already done,
  waited — and how many ms per second).

## Game copy shader: writes stay in game memory; translation instead of substitution — optional

- The game's copy compute shader (`cs fefebf9f`, 2–50 dispatches per frame) was executed by
  substitution: while recording commands the CPU read the copy list from game memory and made the
  copies with its own shader. Now it can be translated as-is (`BB_COPY_SHADER_NATIVE=1`, new model
  only): the GPU reads the list at execution time, as on PS4.
- Found: next to where it copies lie shader code and descriptor tables that our translator reads
  from the CPU. While those blocks are in game memory, everything is correct; a copy in VRAM (the
  "GPU writes this 3 frames out of 60" rule) gave the translator stale code — a black scene. The
  substitution kept them in game memory by accident (its ranges are different every time). Now
  this shader's writes stay in game memory in both modes (`force_writes_in_place`).
- By default — substitution: the native shader on 4 cores costs the draw-recording thread ~0,3 µs
  per packet (+10 %), the GPU +2 %. Bit 2 of the second number of `BB_TOGGLE_FILE` toggles it on
  the fly.

## Constants in place (optional) and buffer binding

- `BB_CONSTANTS_IN_PLACE=1` (new model): small read-only buffers (constants) are read by the GPU
  straight from game memory instead of a copy made at parse time (the constant ring) or at record
  time (the stream buffer). The copies protected the draw from command processor writes that the
  CPU executed "ahead"; in the new model those writes are executed by the GPU in stream order, so
  the copy is no longer needed for correctness. Measurement (4 cores, at the lamp): parse −0,8 µs
  per draw, GPU +3 % (constants travel over PCIe), FPS the same — hence off by default. Bit 1 of
  the second number of `BB_TOGGLE_FILE` toggles it on the fly.
- The binding of a read-only buffer already residing in game memory is remembered until residency
  changes (no block walk on every bind); the "is the buffer in place" checks for the
  `BB_TRACE_SHADER` diagnostics are no longer performed when it is off (there were two per bind).

## Fix

- The memory access fault handler registry lost a handler with the same priority as an already
  registered one (the set was ordered only by priority). The order is now explicit: VRAM
  diagnostic trap, page manager, SRT walker.

## Diagnostics (new)

- `BB_RES_STATS=1`: where shaders take resource descriptors from — registers or tables in memory
  (SRT walker), by kind, per bind.
- `BB_VRAM_ACCESS_TRAP=1` (+ `BB_VRAM_TRAP_RANGE=address,size`): game memory blocks moved to VRAM
  are closed off from the CPU; the code locations accessing them are printed (who reads the stale
  copy).
- `BB_WATCH=address,size`: what the translator reads from the range (pointers in user data,
  buffers, shader code). `BB_TRACE_ADDR=address,size` (with `BB_TRACE_SIZE`): binds over the range
  from the very beginning. `BB_TILE_BACK_LOG=1`: images written back to memory because they are
  read as a texture buffer. `BB_COPY_SHADER_TRACE=1`: copy shader buffers.

## Game occlusion queries — real Vulkan queries (new model)

- Bloodborne does about 60 occlusion queries per frame (`ZPASS_DONE`); previously they got a
  dummy "everything visible" sequence. Now samples are counted by Vulkan queries, and the results
  are written by the GPU into game memory in PS4 format (depth block counters with a ready bit).
  Render passes are not broken: the query is split at pass and command buffer boundaries, result
  writes are deferred to the nearest point outside a pass and done in a single shader dispatch. On
  4 cores the difference from the dummy counter is within noise. `BB_OCCLUSION_QUERIES=0` — as
  before.
- `COPY_DATA` (constants, registers, clocks, memory, GDS) — GPU writes and copies in stream order;
  `COND_EXEC` — a condition on an in-stream-order label or on GPU work up to the packet;
  `SET_PREDICATION` (ZPass, Bool64/32) — draws and dispatches with a predicate bit are skipped if
  the predicate is false. Bloodborne does not use the last three; this is for porting other games.
- `BB_PM4_SELFTEST=1`: a self-check of all this in a running game (8 checks, prints PASS/FAIL).
- Fixed a deadlock when the CPU reads GPU data from the parse thread.

## Game copy shader — as-is by default

- The game copy shader (`cs fefebf9f`, ~36 dispatches per frame) is now translated and executed by
  itself by default: the GPU reads the copy list. `BB_COPY_SHADER_NATIVE=0` — the previous
  substitution (the CPU reads the list). The cost on 4 cores — +6 % to the draw-recording thread,
  GPU and FPS the same.
- To keep the cost at that: a GPU write to memory looks up the affected texture by first byte only
  (only a texture starting at that address is needed; previously the whole range was walked under
  a mutex), and a write over pages the CPU hasn't changed and that are already marked as GPU data
  proceeds without locking the tracker.
- The "texture copy via buffers" and "texture clear via buffer" substitutions are kept: the path
  through memory (dump the rendered frame to memory, run the game shader, re-upload the texture)
  currently gives a frozen picture — render target contents don't reach game memory, and when the
  scene is rendered at reduced resolution it isn't there at all. `BB_HLE_OFF=1|2|4` — an
  experiment with substitutions off, `BB_HLE_STATS=1` — how many times they fire (~4, ~15 and ~10
  per frame).
- Experiment `BB_GUEST_VRAM=1`: all game memory in VRAM via Resizable BAR — 16 FPS already in the
  menu (the CPU reads it over PCIe), not viable.

## Saves no longer corrupted on crash (#64)

- Bloodborne saves about once a second: deletes `backupN`, renames `userdataN` to `backupN` and
  writes a new `userdataN` (1,3 MB). A crash or process kill mid-write left a truncated
  `userdataN`.
- Now a save file (`/savedataN/...`) opened for writing goes to a temporary copy
  (`<name>.<n>.bbtmp` alongside), and on close it is flushed to disk (`fsync`) and put in place of
  the file with a single `rename`. A crash mid-write leaves the previous file (or its absence if
  the game already renamed it to `backupN`: then the game itself reads `backupN` — verified).
- While the file is open, path operations (`stat`, `access`, `truncate`, reopening) see the copy:
  the game checks the size of the file being written by path.
- The copy does not appear in directory listings; copies left after a crash are deleted at mount
  time.
- `param.bin` and `icon0.png` are written the same way (temporary file, `fsync`, `rename`).
- `BB_SAVE_TRACE=1` — all game operations on save files to the log.

## Game file preparation and gamepad

- `prepare.py` and the other scripts, the launcher: text files are read and written in UTF-8
  explicitly, console output doesn't die on characters outside its encoding (#55: Chinese,
  Japanese, Korean Windows locales, `™` in the game title).
- `eboot.bin` (and the `sce_module` modules) are also accepted as plain ELF, without the SELF
  wrapper: some dump programs write them that way (#49). Verified: an ELF extracted from our eboot
  gives the same `boot.bin` byte for byte.
- Sticks (PR #71; #70): a Switch Pro clone with all four axes offset at rest by ~±16380 and half
  the travel is calibrated — neutral is taken from a quiet window after connecting, each axis's
  travel from its own range. Dead zone as in shadPS4: `BB_PAD_DEADZONE` (default 5 of 127) and
  `BB_PAD_DEADZONE_OUTER` (127). `BB_PAD_CENTER=lx,ly,rx,ry` — neutral manually,
  `BB_PAD_CENTER_CAL=0` — no measurement.
  Difference from the PR: neutral is accepted only if all four axes are offset (otherwise an
  ordinary gamepad connected with a stick held would remember that tilt as neutral until
  reconnected); until neutral is known, sticks read as before rather than staying in place.
- Historical localized README: the repository address in the `git clone` command (PR #43;
  the English README already had it).

## GPU hangs: indirect dispatches, VRAM, GPU information

- Indirect dispatches (#34, comment on #32; new memory model): twice the game lost the device on a
  particle simulation that got garbage instead of a group count (1,2 and 3,8 billion groups; our
  logs from 2026-10-06 had it too — 1,4 billion and 6,4 million, no harm done). Bloodborne's real
  numbers are no more than a few hundred. Now before each indirect dispatch a single-thread shader
  (`indirect_guard.comp`) copies the group counts into our buffer, zeroing implausible ones (above
  the device limits or `BB_INDIRECT_GUARD_MAX` groups total, default 4M), and the dispatch goes
  from this copy. The worst that happens now is a skipped particle step instead of a crash; skips
  are printed as `Indirect dispatches: N skipped ...`. `BB_INDIRECT_GUARD=0` — as before. The
  cause of the garbage in game memory was not found (new model only, rare). Cost: within noise
  (183–184 FPS, GPU 5,42–5,47 ms in one scene). Tested with threshold 10 (skips trigger, the game
  runs) and under the validation layer (no new errors).
- Moving game memory blocks to VRAM now respects the driver's video memory budget: if usage
  exceeds `BB_VRAM_PROMOTE_PERCENT` (default 90 %), new copies are not created — blocks are read
  in place (slower, but no VRAM overflow on 8 GB cards), and moving resumes when memory frees up.
  A log line on switching. The "MiB of loaded blocks moved ... to VRAM" number is cumulative (how
  much was moved during the session), not space used; used space is in the `Memory:` line.
- The start of the log now has a line with the GPU, VRAM size, driver and Vulkan version (missing
  from hang reports like #56).
- #56 (old model, hang while loading the map): two logs — two different stop points (an ordinary
  5-index draw and copies between passes), the shader from the first runs 4–12 times per frame
  here without problems, the same patches (Disable DoF, Motion Blur) are enabled here. Could not
  reproduce; without the GPU model and Mesa version there is no way forward (they will now be in
  the log).

## Bugs from issues (2026-10-08, day)

- **FSR 4.1.1 capture where the Steam container won't start (#61).** Bazzite + 9070 XT: no Proton
  "started FSR 4.1", the reason in the list was empty, and at the end of the log — `bwrap: No
  permissions to create a new namespace`: the Steam container (pressure-vessel, and under umu-run
  too) cannot create a namespace — this happens when the launcher itself runs in a sandbox
  (Flatpak, a Steam shortcut with a runtime) or the kernel forbids it. Now on such an error Proton
  is run directly, without the container (message `Steam's container could not start here (...):
  running Proton without it`, then the same to the end of the capture); `BB_FSR4CAP_RUNNER=direct`
  — do that right away.
  Each Proton's failure reason is the last non-empty line of the capture log, otherwise the
  container or Wine error (previously — the last line, often empty). The same Proton is no longer
  tried twice via the `/home/...` and `/var/home/...` paths (Fedora Atomic): identical folders are
  recognized by device and inode, not by `realpath`.
  Verified: a capture inside `bwrap --disable-userns` (same container error) — the fallback path
  recorded FSR 4.1.1 frames under GE-Proton 11-6, the result matches an ordinary capture byte for
  byte (except pointer addresses in `trace.txt`).
- **MangoHud works with the system MangoHud again (#66).** Since 0.3, with a system MangoHud,
  `run.sh` disabled the layer built into the AppImage by name (`VK_LOADER_LAYERS_DISABLE`), but
  the system layer usually has the same name (`VK_LAYER_MANGOHUD_overlay_64_x86_64`) — the Vulkan
  loader disabled both. Now the built-in MangoHud is removed from the layer search paths
  (`XDG_DATA_DIRS`), and the system one remains. Verified with the Vulkan loader
  (`VK_LOADER_DEBUG=layer`): previously "forced disabled", now the layer is inserted.
- **The item picture on the loading screen no longer disappears (#67, bmy patch).** Scaleform
  masks are drawn without color writes; with non-1080p output they landed in the game's depth, and
  the next UI draw switched to output-size UI depth with a cleared stencil — the picture failed
  the test. Now UI draws without a color target also go to the UI depth. Not tested in game (on
  the author's macOS — yes).
- **Monitor selection (#69).** Window and fullscreen went to the monitor SDL considers primary.
  *Screen → Monitor* in the launcher (`BB_DISPLAY`: a number or part of the name; list —
  `bb-gpu-capabilities --displays`), at startup the log has `Display N: ...` lines with the
  selected one marked. Tested on Hyprland with two monitors: the fullscreen window opens on the
  selected one (a regular window on Wayland is placed by the compositor).
- **Debug menu: fonts from the mod are found.** The debug menu patch reads fonts from
  `dvdroot_ps4/adhoc/font/DbgFont14h.ccm` and `.tpf` (and the `adhoc/FontShader/debugFont_*`
  shaders), with the game requesting names in lowercase (`dbgfont14h.ccm`, found with the new
  `BB_FILE_TRACE=1`). The check in `patches.py` looked for them in `dvdroot_ps4/font` with exact
  case, and the runtime on Linux was case-sensitive — the fonts were found neither by the mod nor
  in the dump, and startup died with a Python traceback. Now: the runtime, not finding a game
  file, looks for it case-insensitively (like PS4 and shadPS4; only on a miss, no cost for found
  files); the check looks in `adhoc/` case-insensitively; without the fonts the debug menu patch
  is not applied (line `Patches: debug menu off: ...`, a hint if the fonts are in the old
  `dvdroot_ps4/font`), the game starts; the `adhoc` folder in a mod is recognized as a game
  folder. Verified: the mod's `Adhoc/Font/DbgFont14h.*` is opened by the game (`Mods: open
  /app0/dvdroot_ps4/adhoc/font/dbgfont14h.ccm -> .../Adhoc/Font/DbgFont14h.ccm`). Not tested with
  the real fonts (we don't have them).
- `BB_FILE_TRACE=1`: every path the game opens, checks or reads (`File trace: ...`).
- **The "Play online / offline" screen is gone.** The port has no PSN; now the game opens the main
  menu in offline mode right away — at startup and after "Quit Game", with a save and without. The
  game patch "Skip Online/Offline Choice" (`patches/Bloodborne.xml`): the function that builds
  this dialog (`0x1b39030`, found via string IDs 401010/401011 from `menu.msgbnd`) returns what
  its "PLAY OFFLINE" item would return (calling its handler `0x1b49cd0`, vtable `0x533be30`): the
  next dialog in the chain, so the choice is not shown. Enabled by `patches.py` by default
  (launcher: *Game effects → Skip the choice*, `BB_SKIP_NETWORK_CHOICE=0` — show). The previous
  variant (the port pressed Cross, the screen flickered) is removed. `tools/restart.sh` still
  shows the choice (its scenario presses on the title itself). Verified with screenshots: startup
  without input — straight to the main menu; "Continue" → "Quit Game" — straight to the main menu.
- Memory when reloading a location (6 "Continue → quit" cycles, new model): RSS 707 → 733 MiB,
  VRAM climbs to ~3,7 GB; old model (4 cycles): RSS 3735 → 3795 MiB, VRAM ~3 GB. A leak in the
  gigabytes (the Discord report about teleports) is not visible this way; teleporting between
  different locations not tested.
- **VRAM shortage for game memory copies no longer brings the game down.** The old model keeps
  copies of game memory in 64 MiB VRAM blocks; on 4 GB cards (RTX 3050 mobile, Discord report)
  block allocation could return `ErrorOutOfDeviceMemory`, and the game stopped
  (`vk_platform.h:73`, code 23). Now such a block is taken from system memory the GPU reads across
  the bus (line `Guest memory: VRAM is full ...`): slower, but no crash.
  `BB_RESIDENCY_VRAM_LIMIT_MB=N` — for testing (VRAM "runs out" after N MiB of blocks). Tested
  with 32 MiB: the game runs, the picture is correct, 28 FPS (everything in system memory; in real
  life only the excess goes there). Whether this is where the Discord report crashed is unproven —
  it has no lines before the stop.
- **"GPU data read: Precise" no longer freezes the first cutscene.** New game → the cutscene stood
  on the first frame (sound played): the video player wrote a movie frame into memory the GPU had
  written earlier; the handler asked the GPU thread for a read, and that thread, taking a copy of
  game bytes for the "twins" (`BB_GPU_WRITE_TWINS`) under their mutex, itself hit a read-protected
  page and waited on the same mutex in the handler. Found via thread stacks (SIGUSR2). Now game
  bytes for the "twins" are read through a view without protection (`ReadBacking`), and with
  `BB_READBACKS=2` the "twins" are off: a page with GPU bytes the game may write to would be
  "write-only" (the next stop was `page_manager.cpp: ... write-only`). Verified: new game with
  `BB_READBACKS=2` and without — the cutscene plays through to character creation.
- **Settings menu — like in PC games, in Bloodborne style.** Instead of an ImGui window over the
  game (Insert / L3+R3): the game is dimmed, a centered panel with ornamental lines like the
  game's own dialogs (the serif font DejaVu Serif, bundled next to DejaVu Sans), a title and tabs
  "Graphics / Upscaler / Game effects / Advanced" (L1/R1, Q/E, PageUp/PageDown, mouse). Each
  setting is a "name ◀ value ▶" row: up/down (d-pad, stick, arrows) — row selection, left/right —
  value, Cross/Enter — next value, mouse — click on the arrows or the row, sliders drag with the
  mouse. The selected setting's description — at the bottom (instead of "(?)"), with the restart
  warning there too; an "Apply and restart the game" row — when needed. Button hints — in the
  footer; Esc / Circle / Insert / L3+R3 — close. Unavailable values (FSR 4 without support) are
  skipped, dependent rows dim (preset with TAA, sharpness strength without sharpness, reactivity
  mask). Focus is our own (ImGui navigation never reached the rows). `BB_MENU_KEYS_FILE=<file>` —
  scripted menu control for testing (`toggle up down left right enter back l1 r1 kup kdown`).
- **Port settings — native pages in the game's "System" menu.** After "Screen/sound" the items
  "Graphics", "Game effects" and "Game patches" appeared: they are built and drawn by the game
  itself (its strings, lists, slider, the hint at the bottom, "Default" with confirmation), both
  on the title screen and in pause. "Graphics": output resolution, upscaler (the list only has
  what this GPU and build can do: no DLSS without NVIDIA), preset, sharpness (slider 0–10, 0 —
  off, 10 = 2.0), FPS counter — apply immediately and are written to `bbport.ini`. "Game effects"
  / "Game patches": model detail and effect patches (after a restart). "Default" sets the port's
  default values. Texts are in the game's own language (Russian — if its texts are in Cyrillic,
  otherwise English). How it works (`gpu/shim/bbport_game_menu.cpp`): hooking the game's text
  lookup (own ids 0x7F0000+) and menu item addition (0x1b4e2a0, after "Screen/sound"); the page is
  a "ControllSetting" layout with its own strings and title; the last argument of the game's
  strings is a pointer to the default value. Each hooked function is verified byte for byte,
  `BB_GAME_MENU=0` — disable. Verified: 16 page openings — memory growth like the game's native
  pages; the overlay (Insert / L3+R3) remains.
- 60 FPS evenness over time (Discord report: "after some time frames are uneven"): 6 minutes
  standing, `BB_FPS=60` — every minute 16,67 ms, spread 0,00–0,01 ms, not a single frame longer
  than 20 ms (except loading in the first minute). Not reproducible on RX 7800 XT.

## Merged PRs (2026-10-08, evening)

- **PR #84: DLC.** Folders `<user>/addcont/<title>/<label>` (as in shadPS4) are reported to the
  game as installed add-ons: saves with The Old Hunters load, DLC areas are accessible (#33).
  Add-on data is not mounted — The Old Hunters only needs the label, the data is in patch 1.09. On
  merge: `_GNU_SOURCE` under `#ifndef` (the test builds with `-D_GNU_SOURCE` and `-Werror`), in
  the AppContent test — a user folder stub and a check: the folder
  `addcont/CUSA00900/SPEXPANSIONDLC03` yields one "installed" entry.
- **PR #80:** `BB_FSR4_STATS=1` no longer breaks FSR 4 v07 pipelines without
  `VK_EXT_pipeline_executable_statistics`. The patch to the FSR-Vulkan submodule changed: the
  submodule's working copy must be reverted (`git -C gpu/third_party/fsr-vulkan checkout --
  src/ffx_vk_fsr4_v07.c`), and `build.sh` will apply the new version.
- **PR #78:** launcher — "Copy" and "Export log…" buttons on the "Log" tab.
- **PR #75:** launcher in Simplified Chinese (strings added today are in English until
  translated).
- **PR #83: DLSS on Linux.** The `gpu/dlss_bridge` bridge (MIT, the only code with the NVIDIA SDK)
  is built with `DLSS_SDK_ROOT=<github.com/NVIDIA/DLSS> bash build.sh` into
  `out/libbbport_dlss.so`, the NVIDIA library is copied alongside; the game loads the bridge at
  startup. New upscaler `dlss` (launcher, menu, `bbport.ini`): the same inputs as FSR 3.1,
  Native AA = DLAA, on error — FSR 3.1. Without the bridge and library, on non-NVIDIA or with
  `BB_DLSS=0` nothing changes (DLSS unavailable in the menu). On merge: the DLSS item and its
  description moved to the new menu, the launcher upscaler list string — after the PR #75
  languages string. Tested here: build without SDK, game on AMD (FSR 4.1.1, FSR 4 v07 with
  statistics). Not tested with DLSS (no NVIDIA); the author has an RTX 4090. The bridge and the
  NVIDIA library are not included in the AppImage.

## After 0.5-pre1 (2026-10-09)

- **The new memory model is AMD-only again.** Log from a GTX 1660 Ti (driver 615.71, Hyprland):
  host memory import passed the startup check, but after the first block move to VRAM (`84 MiB of
  loaded blocks moved`) — `GPU watchdog: submission 4114 not finished after 10 s`: the GPU
  finished the copy shader and would not start the next dispatch. Submission waits on the memory
  rebind semaphore (the arena's `vkQueueBindSparse`), and on NVIDIA each such rebind held the GPU
  for 10 seconds and longer; the desktop froze along with it — from the outside, "the whole system
  hangs". The startup check doesn't catch this (it does one small bind). Now the switch is
  unavailable on NVIDIA; those who had it on get the old model (the launcher passes
  `BB_PC_MODEL=0`, the GPU library also doesn't enable it on NVIDIA); `BB_PC_MODEL_ANY_GPU=1` —
  try anyway. README and launcher texts fixed.
- `BB_RESIDENCY_REPORT=<file>` (new model diagnostics): when the file appears, the log gets the
  game memory blocks the GPU recently read in place rather than from VRAM, and why they weren't
  moved (the CPU writes often; bytes we don't know were written; waiting to be moved). At the lamp
  in Hunter's Dream: ~1,2 GB of such blocks, whole Garlic memory chunks entirely "unknown".
- The report "first load slower, 90 FPS after teleport" (RX 7900 XTX, new model): did not
  reproduce here — first and repeat load (exit to title, "Continue") 131,7 and 131,9 FPS on
  RX 7800 XT; VRAM moves after loading finish within seconds. A tester's log is needed.

## New model on NVIDIA: analysis (2026-10-09, continued)

- **Hang cause found.** It is a known regression of the proprietary NVIDIA driver on Linux (from
  555 to this day; the tester has 615): the time of `vkQueueBindSparse` grows with the number of
  pages **already** bound in all sparse resources, and the call holds a global lock (NVIDIA
  developer forum, "Sparse texture binding is painfully slow": 9200 pages — 3,6 s; no fix). The
  new model's arena holds gigabytes of 64 KiB pages (the tester had 863 MiB bound in place before
  the first moves), so each block move to VRAM cost seconds. The game itself noticed the GPU stall
  before the first move ("Stall during rendering at flush 1").
- **Why it can't be worked around with "one edit".** A `BB_RESIDENCY_MIX=1` measurement (new
  diagnostics): ~17 thousand binds per second (~85 per frame) — ranges of hundreds of MB where
  blocks in VRAM and in place coexist (shaders bound to all of memory; a third over data written
  by the GPU). One sparse arena mixes them for free; a "VRAM arena + separate game memory buffers"
  scheme won't serve them. With no rebinds at all (`BB_FIXED_ARENA=1`, everything read in place
  across the bus): **48,6 FPS vs ~205** on RX 7800 XT — worse than the old model.
- Bottom line: the new model stays AMD-only. NVIDIA needs either a driver fix (or Mesa NVK, where
  sparse works fine), or software page swapping in translated shaders instead of sparse — a
  multi-day rework.
- Added: `BB_FIXED_ARENA=1/0` (the arena keeps the first binds: no VRAM moves, blocks outside game
  memory chunks in system memory; default — with host memory import, i.e. on NVIDIA with
  `BB_PC_MODEL_ANY_GPU=1`); the log line `vkQueueBindSparse of N ranges took X ms` (longer than
  50 ms, in both models); in the GPU watchdog report — `Arena binds: ...` (are submissions waiting
  on an unfinished bind); `BB_RESIDENCY_MIX=1` — "in place / VRAM / mixed" binds over 2 s.

## New model on all GPUs: the layer memory module (2026-10-09)

- **The new model turns on on any GPU.** On AMD — as before, sparse arena. On NVIDIA, Intel and
  the rest — the layer memory module (`gpu/layer`, docs/MEMORY_MODULE_PLAN.md): game memory is
  bound in place through buffers of its chunks, VRAM copies are separate buffers ("mirrors"), a
  move is a copy plus accounting in the module. `vkQueueBindSparse`, which hung the game and the
  desktop on NVIDIA, is never called in this mode. Manually: `BB_LAYER_MEMORY=1/0`. The launcher
  no longer hides the switch on non-AMD; README and the hint (three languages) fixed. **Not tested
  on NVIDIA** — a tester's log is needed.
- Measurements on RX 7800 XT, standing: was 48–60 FPS in module mode, now ~205 (sparse ~205–238,
  old model ~220). Elsewhere: module 167,5, sparse 164,5, old model 146. 5 minutes of walking with
  area streaming — no errors, 166–240 FPS.
- What was in the way (found from the GPU profile):
  - **HLE of image copies and clears was not firing.** The `IsComputeImageCopy` /
    `IsComputeImageClear` detectors require the shader to have exactly two buffers, but in module
    mode every shader with game buffers got a third — the page table. The render target memory
    copy (`cs 3d5ebf4e`) and the clear (`cs 8b355b5a`, 31 dispatches per frame) ran as real
    shaders through memory, and images were reloaded from it every frame (~16 1080p images instead
    of ~2,6). Now the page table isn't counted (`ShaderBufferCount`): 60 → 136 FPS.
  - **Mixed ranges.** A range with all blocks in VRAM except one with "unknown" bytes (an edge, a
    gap between images) was read entirely over PCIe (8 MB per bind). Now such a block is
    "volatile" in the mirror: updated from game memory before each bind, and what the dispatch
    wrote is copied back after the dispatch. 139 → 207 FPS. `BB_LAYER_VOLATILE=0` — disable.
  - Move to VRAM on the first bind of a range of known data (as the arena did); it respects
    `BB_GARLIC_VRAM=0` and the VRAM budget (`BB_VRAM_PROMOTE_PERCENT`, important for 6 GB cards).
- The startup host memory import check in module mode checks GPU and CPU writes through the
  imported buffer itself, without a sparse buffer.
- Diagnostics: `BB_RESIDENCY_MIX=2` — also the heaviest in-place / mixed binds with a block
  breakdown (VRAM, eligible, "dynamic", unknown bytes); in the `Layer memory:` line — the number
  of `vkQueueBindSparse` calls and bytes copied back.

## Memory module: vertex explosions and speed (2026-10-09, day)

The result of the work on the new model for NVIDIA is in `docs/NVIDIA_MEMORY_MODEL.md`: write
traps on blocks with a VRAM copy, reads through the module everywhere a copy exists, CPU data no
longer overwritten by GPU data, GPU writes to VRAM only into blocks the CPU hasn't touched
(`BB_LAYER_GPU_WRITES`), the copy shader in module mode via HLE, module response caches.

## 0.5-pre2: native GPU copy and portable labels

In the release build the copy shader in the new model is now native by default: its writes are
coherent between game memory and the VRAM mirrors. Standard Vulkan completion labels added for
GPUs without `VK_AMD_buffer_marker`; buffer write/read dependencies and whole-cache migration on
format change fixed. Full description of the release and testing:
[CHANGES_0.5-pre2.md](CHANGES_0.5-pre2.md).

## 0.5-pre3: memory module on NVIDIA

From the first GTX 1660 Ti logs: VRAM copies re-enabled for the module (the sparse-arena
workaround had disabled them), a shared VRAM budget with the texture cache, headroom for copy
growth instead of reallocating them, WRITE_DATA writes into the copy, watched blocks
(`BB_LAYER_WATCH`), file read retry on EFAULT. Details: [CHANGES_0.5-pre3.md](CHANGES_0.5-pre3.md)
and [NVIDIA_MEMORY_MODEL.md](NVIDIA_MEMORY_MODEL.md).

## 0.5-pre4: background shader compilation, VRAM on 4–6 GB cards, menu as in 0.3

New pipelines for passes drawn every frame are compiled in background threads
(`BB_ASYNC_PIPELINES`); game memory copies in VRAM get their own share of the budget (the pre3
regression on 4 GB cards); after moves, VRAM is freed of the departed location's copies; the
in-game settings menu — a single window again, as in 0.3 and 0.4. Details:
[CHANGES_0.5-pre4.md](CHANGES_0.5-pre4.md).
