# 0.5-pre5 — pre-release for testing

Fifth 0.5 prerelease, built from the `testing` branch, after the tests of 0.5-pre4 on NVIDIA
(RTX 3050 4 GB, GTX 1060 6 GB). Changes are listed relative to
[0.5-pre4](https://github.com/deadinside28/bloodborne_pc/releases/tag/0.5-pre4). Plan and progress:
[EMULATION_REMOVAL_PLAN.md](EMULATION_REMOVAL_PLAN.md),
[TRANSLATOR_ARCHITECTURE.md](TRANSLATOR_ARCHITECTURE.md).

## English

- **FPS no longer falls the longer you play on cards with little VRAM.** On budgets under 8 GB
  the texture collector's pressure mark is 40 % of the budget, so usage stayed over it all the
  time and every texture unused for about 80 submissions (0.1–0.3 s) was evicted: turning the
  camera re-created and re-read over the bus about 12 000 textures per 45 s (VRAM budget limited
  to 4.5 GB and 3.7 GB on an RX 7800 XT). Under pressure a texture now goes once unused for 5 s
  (`BB_GC_PRESSURE_IDLE_SECONDS`), over the critical mark after 1 s, and only then by
  submissions as before: 144–167 re-created in the same test.
- **Some launches no longer run the GPU 1.3–1.7 times slower.** In about half of the launches
  (more often with FSR) the new memory model put a few blocks the CPU writes into a VRAM copy as
  "volatile" blocks, refreshed from the game's memory before every binding that read them. A
  refresh is a copy, and a copy cannot run inside a render pass: the game's light volumes (one
  draw each) broke their pass up to ~100 times a frame, each break storing and loading the
  attachments again — 92 000–109 000 breaks per 5 s from these copies instead of ~700, GPU
  5.4–7.3 ms a frame instead of 4.3 on a recorded route. The same happened on NVIDIA. Volatile
  blocks are now off (`BB_LAYER_VOLATILE=1` turns them on; reads in an open render pass then go
  in place): 10 of 10 runs fast (4.29–4.35 ms with FSR, 4.17 without an upscaler), also with the
  VRAM budget limited to 4.5 GB.
- **Occlusion results before later labels.** The results of the game's occlusion queries are now
  written before any later GPU label in the stream, as on the PS4 (`BB_OCCLUSION_LABEL_ORDER=0` —
  the old order). No speed change: the game reads them 2–10 ms after the query and finds them
  written either way.
- **The new memory model uses the same path on AMD as on NVIDIA.** VRAM copies of the game's
  memory are kept by the port itself on every GPU; AMD's sparse arena is left as
  `BB_LAYER_MEMORY=0`. No `vkQueueBindSparse` calls by default.
- **One owner for write traps.** The runtime now keeps the page protections the GPU side uses
  to notice CPU writes, with a reason per page: VRAM copies and textures trap the same pages
  without one clearing the other's trap; the game's own `mprotect` keeps them, a new mapping
  starts without them. Pages under textures are trapped by default (`BB_IMAGE_TRAPS=0` — as
  before); writes by the runtime's libc functions and the game's loaders announce themselves
  first and do not fault. On the recorded route: same GPU time as without the traps, 4–29 trap
  hits per 5 s.
- **Command processor leftovers on the GPU timeline** (Bloodborne uses neither; for other games):
  `MEM_SEMAPHORE` signals once the GPU has finished the work before them, in stream order
  (`BB_MEM_SEMAPHORE_ORDER=0` — when decoded); the GPU clock of end-of-pipe timestamps and
  `COPY_DATA` is the PS4's 100 MHz, written by the GPU itself from Vulkan timestamps, in one time
  line with the CPU's (`BB_GPU_TIMESTAMPS=0` — written by the CPU). The in-game PM4 self-test
  checks both (11 of 11).
- **Game-specific code in one place.** Bloodborne's code hooks, the addresses of its per-frame
  writers and the hash of its buffer copy shader moved into a game profile (`gpu/games/`),
  chosen by the game's TITLE_ID. `BB_GAME_PROFILE=none` runs the game as an unknown one,
  `BB_GUEST_HOOKS=0` without code hooks: a step towards other games on the same translator.
- **Texture mips detiled with their own tiling** (upstream shadPS4 #5196): small mips of tiled
  textures, stored micro-tiled, and thin 3D PRT textures are now detiled the way the GPU stores
  them.
- **In-game settings rows as sliders.** In the game's System menu the quality preset, output
  resolution and model detail rows are sliders with ranges (the help line lists them); the pop-up
  list let the rows below show through it. The upscaler stays a list, the last row of its page.
- **Diagnostics:** frames over 40 ms show where the new model's VRAM copies spent the time
  (traps, page table entries: staging, guest view, copies, copy command); `BB_IMAGE_SYNC_LOG=1`
  prints texture refreshes per 5 s; `BB_PASS_BREAK_TRACE=1` — who ended a render pass that began
  again unchanged; `BB_OCCLUSION_READ_TRACE=1` — when the game first reads its occlusion
  counters and whether the results were there. The runtime's traps can now also stop reads (no
  access), for diagnostics so far.

**How to test:** enable *New memory and translation model* in the launcher, or set
`BB_PC_MODEL=1`; the mode remains **off by default**. NVIDIA owners with 4–6 GB: please compare a
longer session (10+ minutes, the same area) with pre4 and send the log with `BB_FRAME_STATS=1`
and the GPU profile (`BB_GPU_PROFILE=1`).

**Validation and limits:** RX 7800 XT/RADV: recorded 25 s route and camera turns in place,
VRAM budget limited to 4.5 and 3.7 GB (`BB_VRAM_LIMIT_MB`); runtime tests (write traps by reason,
kept across `mprotect`, forgotten on unmap), unit tests (106) and the in-game PM4 self-test
(11 of 11: occlusion, semaphores and the GPU clock included) passed. NVIDIA's own path cannot
run on AMD: the GC fix is not yet confirmed on NVIDIA. Banding in dark gradients is not confirmed
fixed. Without the game profile (`BB_GAME_PROFILE=none`) the recorded route renders the same and
runs as fast (3 of 3 runs, 4.29–4.30 ms), with more write-trap hits.

The AppImage contains no game files. Proprietary FSR 4 model assets and NVIDIA's DLSS SDK/libraries
are not bundled. `SHA256SUMS` accompanies the download.

