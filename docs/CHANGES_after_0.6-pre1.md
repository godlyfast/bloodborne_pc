# Changes after 0.6-pre1 (since 2026-10-15)

Measurements: RX 7800 XT / RADV, 1080p, near light shafts.
NVIDIA simulated on AMD using `BB_GUEST_UNCACHED=1` (GPU-uncached game memory,
like imported host memory on NVIDIA). Not tested on actual NVIDIA.

## 2026-10-17: wait for frame readiness before presentation

Fixed the second semaphore wait mask in `Scheduler::QueueSubmit`:
`ColorAttachmentOutput` replaced with `AllCommands`. Presentation reads the prepared
frame through a Transfer blit not covered by the old wait. Found while investigating
isolated black/grey frames; disappearance of the user's symptom is not yet confirmed.
Build, 131 Python tests, native checks and graphics roundtrip pass.
Details: `docs/Present_wait_2026-10-17.md`.

## 2026-10-17: corrupted scene on first load with SSR

Fixed a live SSR-reflection-toggle regression. Only part of the patch applied:
instructions halving target dimensions (`0x22c428d`) remained while pass code
already changed to SSR. Colored-block failure reproduced on first load in both Old
and New, before FSR input. User observed a white frame with Bloom enabled.

SSR again applies as a complete startup patch; both game menus warn about restart.
Bloom and other live effects retain live toggling. RX 7800 XT / RADV verified normal
frames with full startup SSR and with SSR disabled/Bloom enabled.
Details: `docs/SSR_corrupt_load_2026-10-17.md`.

## 2026-10-17: GPU clear and texture cache on reload

GPU WRITE_DATA larger than 8 bytes now marks a texture with the same starting address
for refresh from memory. Previously private FX-history clearing could leave an old
image copy cached. Found investigating the white scene after changing saves;
connection to that specific case and FPS impact require in-game validation:
`docs/White_after_save_2026-10-17.md`.

## 2026-10-17: SSAO in contexts without a resource

Fixed forced re-enabling of SSAO in contexts where the game disabled it for lack
of a resource. Live setting respects the support bit and selected target pointer.
Found analyzing `GXWorker:2 +0x22a3f07` SIGSEGV after item selection.
User scenario still needs repetition: `docs/Inventory_crash_2026-10-17.md`.

## 2026-10-17: cursor

Cursor redesigned as a silver lancet: muted steel, bright edge, hooked guard,
dark wrapped grip and a small burgundy insert. Gold/red gradient removed.
32-px size, 64-px HiDPI variant and original hotspot retained.
Geometry computed once on creation; `BB_CURSOR=0` still uses the system cursor.

## 2026-10-17: GX heap, common hooks in Old, swapchain recreation

- [PR #224](https://github.com/deadinside28/bloodborne_pc/pull/224):
  each of two GX per-frame command heaps gets 1 MiB instead of 256 KiB.
  Headroom for commands whose allocation failures caused NULL+8 and NULL in memcpy
  (#162). Default on; `BB_GX_COMMAND_HEAP=0` restores original size.
  Separate buffers, not Laurence's 160 → 512-MiB resource cache.
- [PR #214](https://github.com/deadinside28/bloodborne_pc/pull/214):
  protective hooks, aspect ratio, mouse and our loading/cinematic fixes also install
  in Old. Only GPU-range cache notifications and associated allocator/copy/collector
  hooks require New (`fresh_range != nullptr`).
- [PR #211](https://github.com/deadinside28/bloodborne_pc/pull/211):
  resize, reacquire and HDR changes recreate swapchain under common submit_mutex,
  preventing concurrent submissions while waiting for device idle.

Detailed validation results and limits: `docs/PR_224_214_211_2026-10-17.md`.

## FPS drop looking at a light source in the new model (#204, PR #210)

GPU frame near shafts with `BB_GUEST_UNCACHED=1`: 17.0 → 10.4 ms.

- **Tiling in VRAM (PR #210).** `Detiler::TileImage` wrote tiled texels directly
  to scattered game-memory addresses; NVIDIA sent every write over the bus separately.
  Now tiles in VRAM, then one copy. Time was hidden in the light-shaft pass
  (`vs 637500e0`): tiler dispatch had no profile marker. Now has one ("tile image …").
  Measurement: "after the draw of vs 637500e0" 5.53 → 0.06 ms/frame,
  frame 17.0 → 12.9 ms.
- **Shader reads tiled copy from VRAM** (`SynchronizeMemoryFromImage`, `LayerBind`,
  `ObtainBuffer`); bytes after the image are copied too.
  Small independent gain (3.6 → 3.5 ms/frame): writes were expensive.
  `BB_TILE_BIND_VRAM=0` reads in place as before.
- **Image-to-image copy for targets with a tail** (`IsComputeImageCopy`,
  `raster_compute_hle.cpp`). Game copies the 960x540 shaft target to another through
  memory using `cs 3d5ebf4e` (`dst[i] = src[i]`), back and forth, 5 times/frame.
  Target-copy detection existed but required a buffer exactly image-sized;
  this buffer is 6 KiB longer (0x241800 versus 0x240000).
  Shader ran unchanged, writing 2.3 MiB to game memory each time (target blocks
  marked dynamic), costing 3.4 ms/frame; target then reuploaded from there.
  Now allows a tail up to 64 KiB, copied as a buffer.
  First verified as separate HLE (same shaft image, 12.5 → 10.4 ms/frame),
  then moved into detector. `BB_HLE_OFF=1` disables;
  `BB_HLE_STATS=1` / `BB_IMAGE_COPY_LOG=1` provide counters/logs.
- Remaining: why 960x540 target blocks become permanently dynamic after one write
  into a mixed range (shared boundary block between targets);
  #204's 50-ms stalls with 14–24-MB uploads not checked.

## Launcher GPU selection

- *Operating mode → GPU*, as in shadPS4: *Auto (name)* is the port's choice
  (discrete first), followed by all Vulkan devices; integrated/software (llvmpipe)
  devices labeled. For dual-GPU laptops.
- Stored by name (`gpu` in launcher settings): Vulkan list indices may change.
  Name maps to `BB_GPU_ID` at launch; missing GPU falls back to port selection.
  Shell `BB_GPU_ID` has precedence.
- List from `bb-gpu-capabilities --gpus` (same Vulkan loader/order as game;
  `run.sh --device` already respected `BB_GPU_ID`).
  Tests: `tests/test_launcher_gpu.py`.

## Night of 2026-10-15

- **#205** (Debian 13, NVIDIA): `launcher/bbport_vulkan.py` searches `libnvidia-*`
  beside ICD, then all library directories. `PickPhysicalDevice` warns if NVIDIA
  ICD exists but no 0x10de device.
- **#204** (8 GB): texture-collector pressure threshold =
  min(60% of threshold, max(30% of budget, 2 GB)) (`texture_cache_memory.cpp`):
  8 GB 2.7 → ~4.8 GB; 16 GB+ unchanged.
- `BB_GUEST_UNCACHED=1` (diagnostic): game memory in `DEVICE_UNCACHED_AMD`
  (`VK_AMD_device_coherent_memory`) to reproduce NVIDIA behavior on AMD.
- `BB_TRACE_SHADER` + `BB_GPU_PROFILE`: markers before/after draws of traced vertex
  shader; buffer copies get their own size-class markers.

## Online: second module on shadPS4 0.20 and The Hunter's Dream pool (2026-10-16)

Network stack from Supermedo/bloodborne_pc fork (online assembled by Awaken,
BloodBorneButPc): shadPS4 v0.20.0 network, NP and shadNet source (529ceb3,
almost unchanged: `gpu/bbnet20/vendor-changes.diff`) and The Hunter's Dream
backend (`gpu/bbnet20/thd`, from droogie/bbhost, GPL-3.0-or-later).
Old module (`libbbnet.so`, shadp2p + BBSC) untouched.

- **New `libbbnet20.so` module** (`gpu/bbnet20`): separate library like
  `libbbnet.so` (hidden symbols, `-Bsymbolic`, `bbnet_init`/`bbnet_resolve`).
  Runtime loads `BB_NET_MODULE`; `run.sh` sets its path with `BB_NET_GEN=20`
  (shadNet 0.20) and `BB_NET_BACKEND=thd` (The Hunter's Dream), disabling BBSC.
- **Module interface** (`gpu/bbnet/bbnet.h`, ABI 2): `thread_exit` and
  `memory_is_mapped` added to `BbNetHost`; optional `bbnet_image_mapped`
  (game image relocated, code not patched yet: THD reads original code) and
  `bbnet_start` (game loaded: shadNet/THD session starts here,
  `NpManager::InitializeRuntime`). Callers: `src/runtime_net.c`, `src/probe.c`;
  `runtime_thread_exit` in `src/runtime_thread.c`.
- **Launcher Online page**: Pool list, Seamless Hunt (seamlesshunt.com, default)
  and The Hunter's Dream (thehuntersdream.com). THD: Discord login (code confirmed
  on site, `online.thd_sign_in`), token stored in launcher settings, server check.
  `scripts/online.py`: `thd-signin`, `thd-overrides`, `thd-check`, `overrides --plain`.
- **Client identity**: shadNet sees `bbport <version>` (`BB_CLIENT_VERSION`),
  THD sees `bbport` (source fork used `shadPS4 Awakenchan/v0.20.0`
  and `BloodBorneButPc`).
- Logging classes (`gpu/common/logging/classes.h`) extended with shadPS4 0.20 classes.
- Packaging: `libbbnet20.so` in AppImage and `runtime-paths`.
- Checked without external servers (127.0.0.1:9): module loads in game, THD reaches
  `sceNpMatching2ContextStart`, shadNet 0.20 reports server unavailable and disables
  itself; old BBSC module works as before. **Not tested**: Discord login, live THD
  server play, bbhost player compatibility, co-op over shadNet 0.20.
- Remaining: BBSC port to 0.20, currently old-module-only; README (EN/RU) not updated.

### BBSC on the 0.20 stack (2026-10-16, later that day)

- Seamless Hunt now uses `libbbnet20.so`, not shadp2p (retained as fallback:
  `BB_NET_GEN=19`). Launcher has two pools: Seamless Hunt and The Hunter's Dream.
- Ported onto shadPS4 0.20 source: unchanged BBSC game code, signaling 0x20/0x22,
  room-member replay, summon route/host-placement header in HTTP, UDP relay
  (`core/net/p2p_relay.*`, in `p2p_transport.cpp`). Details: `docs/BBSC.md`.
- Verified: module loads, BBSC installs hooks (`BB_ONLINE=1 BB_BBSC=1`,
  server 127.0.0.1:9). Not tested: two-player play (summon, host-following, relay).
  `bbsc.dll` 0.0.1 has closed source; its fixes not ported.

## Input, cursor, free camera, live effects (2026-10-16, evening)

Not checked in gameplay (built; game reaches intro without failure).

- **Keyboard → stick** (`src/runtime_pad.c`). WASD/IJKL no longer jump straight
  to full deflection: direction on unit circle (diagonal no longer than straight),
  length rises over 70 ms/falls over 45 ms, angle turns along shortest arc at
  1100°/s. Short taps retained: key-down event held through next gamepad read.
  Tuning: `BB_KEY_RISE_MS`, `BB_KEY_FALL_MS`, `BB_KEY_TURN_DPS`.
- **Cursor** (`gpu/shim/bbport_cursor.*`): custom code-drawn window cursor
  (blade: bone → gold → blood, dark outline, 32/64 px).
  `BB_CURSOR=0`: system cursor.
- **Mouse/free camera** (`bbport_guest_hooks.cpp`, `InstallFreeCameraProbe`):
  while Restore Debug Camera patch is on and camera active (manager byte +0xc4),
  mouse rotates free camera through right stick, not normal game camera.
- **Live effects** (`InstallHotEffects`, `BB_HOT_EFFECTS=0`: previous startup patches):
  chromatic aberration, depth of field, motion blur, SSAO, game AA and dynamic-light
  shadows toggle immediately in game/port menus. SSAO/blur/AA/shadows: bytes
  +0x2968/9/a/e of render-options object (address captured at constructor tail,
  0x22c254c). Aberration/DoF: same code bytes as patches, written/restored.
  SSR, intros, free camera and debug menu remain startup patches.

### Keyboard: sprint, roll, jump, back (2026-10-16)

- Space: roll, short Circle press even while held (no sprint). Left Shift:
  sprint (Circle held). Shift+Space: jump, release Circle for 70 ms then press
  again while running, like gamepad B. New `sprint`/`dodge` inputs in bbport.ini
  (`key.sprint=`, `key.dodge=`) and launcher controls page; keyboard `key.circle=` empty.
- With game menu open (`bbgpu_pointer_wanted`), Escape is Circle/back, not Options;
  outside menu Escape still opens it. Space/Shift do nothing in menus.
  Keyboard back prompt shows Esc. Keyboard free camera: F (Cross) + Left Ctrl (L3).
- Jump (Shift+Space) now acts like double Space during sprint: Circle released 70 ms,
  pressed 70 ms, released 70 ms, then held again (`BB_JUMP_GAP_MS`,
  `BB_JUMP_TAP_MS`). One release/press merely interrupted sprint, without jumping.

### Crash "guest raised debug exception 0xa0020007" (2026-10-16)

Not a stack canary (as #207 said), but game's own renderer assertion (Yebis,
`GPUMath.cpp(3199): nBaseSamples >= 3`,
`GPUTextureUtil.cpp(18141): nSamples >= 2`) in blur-kernel calculation,
called from +0xbbc3e0 and +0xc33efe. Value comes from post-effect parameter
data/interpolation. `raise_exception` (`runtime_kernel.c`) now prints and returns
for these two sites (game continues calculation as a retail build).
`BB_GAME_ASSERT_STOP=1`: previous behavior. Root cause of low sample count not found.
- Escape opened and immediately closed the game menu: it became "open" with the key
  still held, converting Escape into Circle/back. A press begun outside stays Options
  until release (`options_latched`, `src/runtime_pad.c`).

### Live SSR reflections, mouse (2026-10-16)

**17 October update:** live SSR path withdrawn due to scene corruption.
Complete startup patch with restart used; see fix above. Original change history follows.

- **SSR toggles without restart** (`bbport_guest_hooks.cpp`, `hot_code` table):
  Enable Screen Space Reflections patch bytes/constants written/restored from menus.
  SSR target size (0x22c428d, half resolution) untouched because it is resource size.
  **Not checked**: whether game creates SSR resources only when enabled at startup;
  if live enabling gives no image, restart needed (`BB_HOT_EFFECTS=0`: as before).
- **Mouse** (`window.cpp`): window always grabs cursor (`SDL_SetWindowMouseGrab`)
  while focused, including game menus/teleport destination selection.
  Look (relative mode) engages on focus without a click.
  F1 releases for another window; click or F1 again recaptures.
- Mouse after menus (`window.cpp`): entering menu centers pointer at the same place;
  cursor hides after 1.5 s motionless also in menus, rather than lingering over
  gameplay during closing animation (game considers menu open another ~0.4 s or longer).
- Cursor after menus: menu closes when menu object disappears (`flow+0xa88`);
  400-ms list-focus tail (for dropdowns without an object) kept pointer ~0.4 s longer.
  Now reset on object disappearance (`InMenu`, `bloodborne_menu_pointer.cpp`);
  `BB_MENU_POINTER_LOG=1` logs signals with times.

### "Bad PM4 packet" on first load (2026-10-16, not fully fixed)

4 failures in ~25 launches, 3 at first save load immediately after startup.
Diagnostics (`BB_FREE_CHECK`, `BB_WRITE_LOG`) enabled: port did not write this buffer
(`Write log: 0 of 51474`). Dump: `SET_SH_REG` packet (`c0047602`, 5-word body)
decoded as one-word body, with values becoming a header. Header in memory differed
at decode time and was already correct at dump time. CPU already writes labels on
this card (`0.0 labels/frame written by the GPU`), so `BB_GPU_LABELS` unrelated.
Now (`cp_graphics.cpp`, `RunGraphics`), if previous packet is register write
(`SetShReg`, `SetContextReg`, `SetUconfigReg`) whose memory header has changed,
it is decoded again (up to 4 times/buffer), logging
`PM4: the header at … changed after it was walked`.
`BB_PM4_RECOVER=0`: previous behavior. Not tested on a live failure.

### Black screen after "blur-kernel assertion ignored" (2026-10-16 17:20)

Ignoring `nBaseSamples >= 3` (above) was inadequate: five "ignored" messages in
`20261016_141307.log` followed by
"GPU stall report: the guest has submitted nothing for 5 s"
(black screen, same report as RX 580 user #203; possibly same cause, assertion hidden
by log truncation there). With two samples the game loops. At function entry
(`0xbbc3e0`, `InstallKernelSampleClamp`) sample count now raised to 3
(`BB_KERNEL_CLAMP=0`: off); assertion should no longer trigger.

### Havok hang and render-options object liveness (2026-10-16 17:40)

Log `20261016_142051.log`: "GPU stall … read pointer 228", `clamp on`, no ignored
assertions. All-thread stacks (SIGUSR2 each) show main and five Havok workers on
one wait (`0x1067fc5 … 0x420965`, Havok job system): game sees no jobs,
suggesting heap-memory corruption. Suspect: live-effect writes into already freed
render-options objects (0/1 byte check also accepts zeroed memory).
Object now considered live only with intact constructor constant block
(32 bytes at `+0x2980`, as in game data `0x5128a40`);
log "written to N of M options objects". `BB_HOT_EFFECTS=0`: no live effects.
Not tested.
- Liveness: constructor-tail hook precedes constant-block copy, so fresh object
  written without block check; others only with intact block.
  `process_vm_readv` returned EFAULT (game pages protected against kernel copying);
  now read through runtime map (`runtime_memory_is_mapped`).
- `Bad PM4 packet`: before treating a word as bad header, reread up to
  `BB_PM4_WAIT_US` (20 ms). If game was still finishing buffer, logs
  `PM4: the dword at … was not a packet header at first`.
  Not tested on a live failure.

### Live frame limit, F3 (2026-10-16 18:10) — Laurence cinematic

User verified no hangs with a 30-FPS limiter. Nexus #163 patch collection
(`Bloodborne.xml`), "60 FPS (With Deltatime v2)", says:
"You may encounter softlock during Laurence (optional DLC boss) cinematic. Disable
patch to progress." shadPS4/ps4_cheats #72 says the same for Laurence, Ludwig,
Rom and Logarius cinematics. Added in-game limit: port menu (Insert) →
Frame rate limit (now), F3 toggles 30 FPS. Not saved. `BbFrameRate::SetLimit`.
No automatic cinematic detection (game-code investigation needed).
Collection's Cutscene Fight Fix/no Cutscenes patches unnecessary: port has its own hooks.
- Hang diagnostics: on "GPU stall report" all process threads now print frames,
  registers, stack top and 8 words at each pointer register (`probe.c: dump_frames`,
  `command_processor.cpp: ReportStall`; once/launch, `BB_STALL_THREADS=0`: off).
  Needed for Laurence hang: main inside a job waits on synchronization object
  (virtual `Wait`, `0x420965 → 0x76a8e5 → 0x75b25e`), Havok workers idle.

### "PM4 type N / end-of-pipe data select" loading failures: buffer copy default (2026-10-16 18:25)

Sixth failure that day, again loading: now `end-of-pipe data select 6`
(`20261016_150634.log`), previously `PM4 type 0/1`.
Common factor: top-level command buffer decoded in place while game rewrites it
before decode ("game reused memory before the thread reached it", as the
`BB_COPY_GPU_BUFFERS` comment says). Copy-at-submit mode already existed but was
off; now on by default (dcb+ccb copy per submit, kilobytes;
`BB_COPY_GPU_BUFFERS=0`: old behavior). Nested IBs not copied.
Not tested on a live failure: intermittent (~every second launch on first load).

### Laurence cinematic hang: render-job-pool slot leak (2026-10-16 19:00)

Cause found from hung-game snapshot (memory read through `/proc/PID/mem`):
- Job-runner step `0x1067f60`: acquire pool slot (`0x1056920`, sleeps if none free),
  check job resource (`0x2165150`), execute (`0x2169c30`), return slot
  (`0x1056990`, only call on success path, `0x106807f`).
- Both error exits (wrong resource state; execution failure) go through `0x1068092`
  with result 1 and slot retained in `[runner+0x120]`; next call takes a new slot
  and overwrites field, losing old slot. Six slots total. Dump: all six pool flags 0,
  six runners hold one slot each, main/five Havok workers spin waiting for a free
  slot, character runners have no work (queues empty).
- Error exit also occurs in normal loading (5+ times/40 s in test), so slots are
  replenished somewhere; Laurence cinematic gets more than six failures together
  above 30 FPS.
`InstallJobSlotFix` (`bbport_guest_hooks.cpp`) hooks common exit `0x1068092`:
if result 1 and slot held, returns it via game function (`0x1056990`) and clears field.
Log "a failed render job gave its slot back (N so far)". `BB_JOB_SLOT_FIX=0`: off.
Not tested on Laurence; reason `0x2165150` rejects resource unknown.
- Expanded slot hook (19:10): second hang (`20261016_153246.log`, error-exit hook
  fired) had six zero pool flags but no runner held a slot. Slots also lost where
  `[runner+0x120]` simply clears: destructor `0x106798a`, reset `0x1067a5c`
  (job cancelled midway). Now returns slot first (global `0x54b8788`, returned by
  `0x1057350`); log "a render job destroyed with its slot gave it back".
  Not tested on Laurence.

### Laurence: fixed pool argument in slot-return hook (2026-10-16, after 19:38)

Live AppImage run `20261016_163749.log`, PID 13705: main/five Havok workers wait
at `0x1067fc5`. Memory confirms pool `0x1115d72ab0`, six flags 0, no runner holding
a slot. GPU completed all work (submitted=decoded=72819, empty queues).
Five "gave its slot back" messages did not prove actual slot returns.

Bug in `InstallJobSlotFix`: `Emitter::SaveVolatile` saves original r12 on stack,
then uses r12 as saved-context pointer. Following `mov rsi,r12` passed stack address
to `JobSlotFix`, not game pool. `0x1056990` found no slot in that "pool";
hook then cleared `[runner+0x120]` and logged success.
Fixed to `mov rsi,[r12]`: real pool address from saved register.

Standalone `out/dev/job-slot-argument-check.cpp` executes both machine-code sequences
with real SaveVolatile/RestoreVolatile: old passes stack, new passes specified pool;
r12 restored in both. GPU library rebuilt. Cinematic completion with fix still needs
gameplay test. This does not establish why original job fails above 30 FPS.

### After slot returns: SRT-walker handler crash (2026-10-16, 19:42 run)

`20261016_164248.log`: slot returns reached 4096, then mass null resource-table reads
and `flatten_extended_userdata_pass.cpp:72` assertion (expected memory MOV).
Assert stack address `0x767c3b804a7f` had just been patched by another handler.
Parallel-thread handlers rewrote one shared MOV to XOR; another saw XOR and failed
the MOV check. Substitution also permanently zeroed that instruction's data even if
the next frame's pointer was valid.

Handler no longer writes machine code: zeros RDI/R10 only in current thread ucontext,
advances RIP past MOV, preserves flags. Ready-code range published atomically,
without reading Xbyak's changing size in signal handler.
Unknown instructions/memory writes not intercepted.
Messages limited to first five/powers of two.

`srt-walker-fault-test`: 517 real SIGSEGV, including simultaneous two-thread faults
and eight parallel threads. Later valid reads return original data, code unchanged.
Checked flags, RIP advancement, refusal to swallow STORE.
Same test with crashed AppImage's library fails R10-restoration check.
Slot-return log now includes original error code and four resource-state bytes
`+0x38..3b` to investigate primary failure. Why resources become invalid remains
unknown; cinematic completion needs retesting.

AppImage rebuilt 19:46. Extra replay of old run3 corpus (312 records, two repeats)
has identical before/after result: 217 same, 95 SPIR-V differs from old reference,
Info/bindings/unreadable/nondeterministic 0. Those 95 differences also exist with
previous AppImage library; this is not a full corpus pass.
Logs: `out/srt-walker-fault-build.log`, `out/srt-walker-old-regression.log`,
`out/srt-walker-corpus{,-before}.log`, `out/srt-walker-appimage-build.log`.

### Laurence: SIGSEGV 139 and primary allocator failure (2026-10-16, 19:47 run)

Log `20261016_164701.log`: job errors code 9, resource state `01010201`.
After 4096 slot returns, inaccessible SRT reads, then host SIGSEGV in
`StageSpecialization+0xfba` (`libbbgpu.so+0x3b1f0a`):
`mov r10,[r14+8]`, r14=0. This is `Info::ReadUdReg<Gcn::Buffer>` during vertex-attribute
specialization: null V# table, access to address 8. This thread is not executing
SRT walker; its handler is inapplicable.
`ReadUdReg` now returns empty descriptor for null table, checks SGPR-pair and direct
user-data-read bounds. Test reproduces null+8 and subsequent valid read.

Game-code analysis narrowed source of 9: check `0x2165150` returns 8;
9 comes from `0x2169c30 -> 0x26d0d30`: buffer allocation failed after collection
attempt, or bookkeeping-block allocation failed. Earlier "wrong resource state"
explanation therefore unsupported for latest runs.
Log sequence suggests connection to inaccessible descriptors; full chain needs validation.

Added byte-checked observers `0x26d0dac`, `0x26d0e82`, `0x26d0ebb`:
on failure log requested size, allocation type/function, object state;
for recognized range heap, free bytes/largest block.
Observers preserve registers/flags and allocation result.
Needed to distinguish exhaustion, fragmentation and helper-pool failure.
Exact primary mechanism not established.

Build/extended `srt-walker-fault-test` passed: null+8, truncated SGPR pair,
direct-user-data overrun, valid table read, previous 517 SIGSEGV.
run3 corpus retains 217 same / 95 old SPIR-V differences,
no Info/bindings differences or nondeterminism.
Diagnostic AppImage built 19:52.

### Separate save-load failure: PM4 type 0, code 23 (2026-10-16, 19:54 run)

User confirmed crash during save loading, no cinematic.
Latest `20261016_165450.log` has no render-job failures.
CP stopped at zero PM4 header in submission 12299: snapshot buffer `0x382fc050`,
length `0x1278`, offset `0x1b4`. Seven zero DWORDs between correct packets.
Stack: RunGraphics → unreachable `PM4 type 0 packet (0x0)` → exit 23.
Separate from SRT/139 and Laurence slots.

This buffer is a malloc copy (`memory type -1`); old report searched port writes
at its addresses. Thus "0 of 74451 logged writes" does not prove no writes to the
original guest buffer. Waiting for a bad-header change also reread the copy,
which does not update after submit.

Added diagnostics: remember first PM4-boundary violation on copy; on failure print
original address, copy age, whether snapshot was bad at submit, current original
word/window and original-range write log. No commands skipped/replaced.
Without original/copy comparison neither reuse race nor incomplete write is proven.
CP decoder test passed. Diagnostic AppImage built 19:59.
Three automated original-build loads on separate savedata copy passed without
Bad PM4; rare-failure root cause unknown.
Script `out/dev/reproduce-pm4-load.py`, log `out/pm4-load-repro.log`.

Crash reproduced on third automated AppImage load (20:02):
`out/dev/pm4-first-reproduced-crash.log`.
Submission 3536, original `0x1039d4eb84`, offset `0x114`: snapshot already bad
at submit. After 20.435 ms original/snapshot failure windows match, including zero
header. Original write log: 0 port writes of 20914.
Late-buffer-reuse hypothesis not confirmed for this reproduction.
NOP `c00a1000` before error contains old ACQUIRE_MEM words; old content is valid
inside NOP padding, not proof of wrong length.
Need buffer-construction trace, not reconstruction from similar data words.

`BB_GNM_WRITES_TRACE=1` keeps recent driver command-builder ring (address,
reserved size, function); failure prints overlapping calls.
Full bad snapshot saved to `$BB_DATA_DIR/out/pm4-bad-<submission>.snapshot.bin`.
Diagnostic build 20:08. Repeated successful loads do not prove intermittent failure fixed.

Repeat with tracing (20:13): sixth AppImage load exited 23,
`out/dev/pm4-load-repro/appimage-load-6.log`, submission 2830.
Full DCB `out/dev/pm4-load-repro/out/pm4-bad-2830.snapshot.bin`.
Zero header at +0x270 already present on submit; original after 20.357 ms matches copy.
Last overlapping driver builder: `sceGnmSetCsShaderWithModifier`,
25 DWORDs from +0x20c to +0x270. Last NOP starts +0x240 and correctly ends
immediately before bad word. Implementation matches saved upstream;
three found game wrappers also advance pointer by 25 DWORDs.
Localizes failure boundary, not proof of SetCsShader/NOP-length bug.
HwInit trace entries contain available-range capacity, not written commands;
broad overlaps do not prove overwrites.

Fifth attempt in this series separately exited 139 before CSChrThread0 creation;
must not group with PM4/23. Other attempts succeeding does not confirm fix.
Malformed DCB construction remains unresolved; no packets skipped/substituted.

### PM4/23 investigation continued (2026-10-16, 20:26–20:31)

`BB_GNM_WRITES_TRACE` extended for `BB_GNM_OBSERVE`: ring stores actual pointer
advancement by game methods, function/caller offsets, command-buffer address,
thread, first 16 words and boundary-check result at return.
Driver-range widths still mean supplied capacity, not write volume.
Old observe exposed separate detour-installation failure on an already RX page:
`PatchImage` now temporarily permits writes per changed range and restores
`GuestCodeProtection`. Pre-game stops in first observe series are not reproduction
of user's crash. AppImage build 20:26; preceding cp-decoder-test passed.

All six loads observing all 513 functions passed without Bad PM4
(`out/pm4-native-trace-repro2.log`). Limiting to indices 140:155 reproduced on
third load: `out/dev/pm4-load-repro/logs/20261016-202938/appimage-load-3.log`,
submission 2859, snapshot `out/dev/pm4-load-repro/out/pm4-bad-2859.snapshot.bin`.
DCB begins EVENT_WRITE_EOP (6 DWORDs), WAIT_REG_MEM (7 DWORDs), then +0x34 word
0x2000, then 0x2f22c and a valid marker NOP. Snapshot already bad at submit,
original after 20.084 ms matches. No final SetCsShader in this window:
earlier localization near its boundary is not universal or a root cause.
Search expanded to game EOP/WAIT builders and submission preparation.

### PM4/23: concurrent main/GXRenderThread writes established (2026-10-17, 06:38–06:43)

`BB_GNM_NATIVE_ONLY=1` enables native observers without coverage/checksum analysis.
Write histories now per-thread (shared mutex no longer serializes all native builders).
`BB_GNM_WRITES_TRACE=1` also retains bounded snapshot history (512 records,
64 MiB maximum) to find earlier submissions of the same address.
Diagnostics, not PM4 alteration or race fix.

First load with observer range 120:170 proved race:
`out/dev/pm4-load-repro/logs/20261017-063741/appimage-load-1.log`, submission 7659.
Same CB `0x10282a2850` used by thread 103568 (SetCsShader, native `0x1075840`,
caller `0x26cd5b1`) and 103473 (dispatch, `0x1074c50`, caller `0x26b52c1`).
SetCsShader writes 100 bytes; wrapper adds 100 to CB.cursor.
Between entry/return cursor advanced 132 bytes. At +100 remained 32 zero bytes;
dispatch begins +132. Another thread thus changed cursor within call;
zero gap is not driver-NOP-length error.

Repeat: `out/dev/pm4-load-repro/logs/20261017-064026/appimage-load-6.log`,
submission 7660. Saved `.threads.json`: 105251 main (`bb-probe`),
105348 `GXRenderThread`. Latter writes shader at `0x103a7c8a64`;
observer sees 152 rather than 100 bytes advanced. Beginning already contains
EVENT_WRITE_EOP + WAIT_REG_MEM (52 bytes), overwriting shader region.
Main nearby writes ACQUIRE_MEM via `0x1075e10`, caller `0x26b98f5`.
Snapshot bad at submit and after 3 seconds.
Write log has no emulator writes to this DCB (GPU mirror-copyback intentions added too).

Crash mechanism localized: concurrent main/GXRenderThread construction in shared CB
with nonatomic cursor. Why the game permits shared access in this port
(waits/frame boundaries/call context) still under investigation.
Serializing individual Gnm packets or skipping zero words does not ensure proper
shader/user-data/dispatch order, so no such "fix".
Second-run dump: `out/dev/pm4-load-repro/out/pm4-bad-7660.snapshot.bin`.

### PM4/23: FX-target initialization isolated (2026-10-17, 06:58 build)

Entry stack at `0x26b4ef0` identified main-thread writes into main context:
`0xebb960` (effect initialization), three clear calls via `0x2168630`
at `0xebbc86`, `0xebbca4`, `0xebbcc2`. Caller `0x2276501`, above `0x22c4fcc`.
Main context `0x10282a2840`, CB `0x10282a2850`; ordinary loaders in same run use
separate context `0x10282b8f20`. Stack/descriptor:
`out/dev/pm4-load-repro/logs/20261017-065307/appimage-load-1.log`.

All three targets created before all three clears. Captured Gnm RenderTarget
(not texture S#):
`10dfe600 00f0000f 0000007f 00000000 00060714 000001ce 00020002 ...`.
RG16F, 2x2 logical pixels, tiled pitch 128, padded height 64, one layer/sample,
32768 bytes/target, no CMASK/FMASK/compression. Clear color (0,0,0,1);
only R/G stored, so zero-fill is correct regardless of tiling.
CPU writes to shared CB both corrupted cursor and submitted unfinished
GXRenderThread commands.

Fix: only these three checked CALLs redirected to `FxInitClear`.
On main thread, for confirmed RG16F layout/color, constructs private zero WRITE_DATA,
submitted to common graphics queue without game context/cursor access or shader/register
state changes. GPU ordering preserved; original function flushing main context not called.
Other formats/sizes/colors/threads use original call.
`BB_FX_INIT_CLEAR=0` disables fix for control. Ordinary clears not intercepted.

Internal temporary commands receive mandatory own copy in `SubmitGfx`,
including `BB_COPY_GPU_BUFFERS`-disabled configurations; temporary vector does not
remain asynchronous decoder's source. Native game buffer unchanged, not "fixed" by
skipping data. Added `bbport_fx_init_clear.h` and `fx-init-clear-test`:
real descriptor, bounds calculation, WRITE_DATA decode, unchanged shader/context
registers, rejection of RGBA/nonblack/MSAA/compression/other size/invalid bounds.

Checks passed: new test, cp-decoder-test, srt-walker-fault-test (517 handled SIGSEGV).
Source build loaded save; all three targets used new path. AppImage built 06:58.
Twelve AppImage loads without native observers succeeded: all 36 targets cleared
by new path; each observed 14 seconds beyond CSChrThread0, no Bad PM4,
host fault or GPU assertion. Log `out/fx-init-clear-appimage-stress.log`,
details `out/dev/pm4-load-repro/logs/20261017-065912/`.
Loaded-scene image: `out/dev/fx-init-clear-gameplay.png` (about 100 FPS).

Control with same AppImage and `BB_FX_INIT_CLEAR=0` reproduced code 23 on fourth load:
zero PM4 header in submission 7666, already corrupt at submit.
Log `out/fx-init-clear-disabled-control.log`; detailed log/snapshot:
`out/dev/pm4-load-repro/logs/20261017-070531/appimage-load-4.log`,
`out/dev/pm4-load-repro/logs/20261017-070531/appimage-load-4.snapshot.bin`.
Fix then reenabled: extra load successful, three targets cleared, no errors
(`out/fx-init-clear-final-smoke.log`, detailed log in `logs/20261017-070758/`
under `out/dev/pm4-load-repro/`). Tests used separate user-data copy.

Result concerns intermittent save-load PM4/23. Separate Laurence allocation error 9
was not tested or declared solved by this run.

### Laurence: wide cinematic without HUD, resource-cache peak (2026-10-17)

Frame-by-frame analysis of `video_2026-10-17_07-33-43.mp4` and independent control
runs on a save copy. Details, table, frame paths: `docs/Laurence_video_2026-10-17.md`.

At game-pacer limits 30/100 FPS, opening passed without allocation error 9.
Original limit 480 (about 100 displayed due to VSync) reproduces failures,
inaccessible SRT and exploding vertices. Normal LOD instead of -2 and general
Increased Graphics Heap Sizes patch do not help.
JobProbeWord now reads stack locals/image vtables safely with process_vm_readv:
real 18–41-KB requests confirmed, unable to fit fragments of separate 160-MiB range heap.

Checked-instruction hook at 0x216b20e enlarges that resource cache's backing allocation
specifically to 512 MiB: creation parameters +0x54 changed before allocation-size
read and range setup. Other original sizes unchanged.
320-MiB candidate rejected: same peak failed, including 4-MiB requests.
512 MiB passed tested section without failure; after loading, live ranges fell
to hundreds and most memory became free again.
`BB_RENDER_RESOURCE_CACHE_MB=160`: original-size control.

Cinematic squeezing was separate: camera already aspect 2.370370, displayed frame
1.777778. No HUD, so composition did not create wide display buffer.
OnDisplayPassStart now finishes ready LDR scene at output size before camera/depth
reset; UI frames use old path. Afterwards camera/frame aspect match (2.370370),
FOV/near/far unchanged. Wide camera view retained, no cinematic 16:9 limit added.
`BB_SCENE_WITHOUT_UI=0`: old-output control.

Checks: ui-composition-test, fx-init-clear-test, cp-decoder-test,
srt-walker-fault-test (517 recovered faults).
Log `out/dev/laurence-final-build-tests.log`. AppImage rebuilt (14:29:35 MSK).
Final `appimage-final-fsr411`: 115 seconds after load, pacer limit 480,
LOD -2, FSR 4.1.1, 2560x1080 output; no allocation error 9, SRT faults,
Bad PM4 or host fault. Cinematic completed, 90s image already shows Laurence fight;
105s shows continued play. Cache after peak: hundreds of live ranges,
hundreds of MiB free. Frame comparison: `docs/Laurence_compare.html`.

## 2026-10-19: map sections missing after teleport — resource cache back to 160 MiB

After teleporting to the Dream and back, map sections disappeared: walls, city below,
distant buildings (castle); objects (barrels, crates, bridges) remained.
Build bisection: test-1016 intact, 17 October 15:18 and later broken.
Cause: render-resource-cache backing allocation 160 → 512 MiB
(0x216b20e hook, for Laurence cinematic) takes memory from map-loading areas.
Ruled out by A/B: occlusion, VRAM memory copies, page table, memory model
(same in Old), `BB_JOB_SLOT_FIX`, `BB_HOT_EFFECTS`, `model_lod`.
`BB_RENDER_RESOURCE_CACHE_MB=160` restores everything.

Default now original 160 MiB; `BB_RENDER_RESOURCE_CACHE_MB=512` restores previous
high-FPS Laurence behavior (otherwise F3, 30-FPS limit).

**19 October update, later:** at 160 MiB, allocation failures/exploding models returned
in Laurence cinematic at ~190 FPS. Cache now 512 MiB again, but not from game allocator:
game allocates original 160 MiB (area-loading heap unchanged), then hook 0x216b21d
replaces result with port-owned direct memory beyond game-visible size
(`runtime_extra_direct_map`, `src/runtime_memory.c`; pool enlarged by
`BB_DMEM_EXTRA_MB`, default 512; `sceKernelGetDirectMemorySize`, game allocations
and queries do not see reserve).
Laurence run `rc-1`: 0 allocation failures, no flashes.
`BB_RENDER_RESOURCE_CACHE_MB=160`: unmodified game cache.
Map after teleport still needs validation with this variant.
