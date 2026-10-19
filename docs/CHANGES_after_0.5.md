# Changes after 0.5 (since 2026-10-10)

Measurements: RX 7800 XT / RADV, a user's save in Cathedral Ward, 1080p.

## All retail editions receive the game profile (#119)

- The Bloodborne profile (`gpu/games/bloodborne.cpp`) was selected only for CUSA03173. The US
  edition (CUSA00900) and other regions use the same 1.09 executable but ran without the
  profile. The new model then crashed when entering the world: `Guest fault ... at guest offset
  0x2085xxx, address (nil)` in the game's allocator (#119, RX 7600, US edition).
- Reproduced on CUSA03173 with `BB_GAME_PROFILE=none`: the same crash (`0x208596a`) on world
  entry. With the profile but no hooks (`BB_GUEST_HOOKS=0`), it does not crash: `DynamicWriters`
  protects the allocator code whose metadata resides in GPU memory. Without that classification,
  its blocks move into VRAM mirrors.
- The profile, game check (`scripts/game_check.py`), patches (`scripts/patches.py`), save-file
  "audio fix" and mod folders now recognize all editions: CUSA00900, CUSA00207, CUSA00208,
  CUSA00299, CUSA01363 and The Old Hunters editions CUSA03179, CUSA03173, CUSA03014, CUSA03023.
- The game check asks other base-game regions without the update to install 1.09 instead of
  saying "only CUSA03173 is supported". An eboot.bin with the embedded 60 FPS patch, which
  crashes in the gestures menu, receives a separate message (PR #117).
- Remaining: the generic path without a profile should not crash by itself when allocator
  metadata has a VRAM mirror. It is currently needed only for other games.

## Whole-frame motion blur in the new model (#122)

- With motion blur enabled (the default), turning the camera blurred the entire frame in the
  new model but not in the old one (#122, RX 9060 XT). Reproduced: frame sharpness during a
  turn, measured as the standard deviation of the Laplacian, was 6.9 versus 8.5–12 in the old model.
- Investigation used `BB_GARLIC_VRAM_RANGE=start,end`, a new diagnostic option that permits
  VRAM mirrors only within that range, followed by binary search of the range. The affected
  64-KiB block was `0x104ff00000`. Only the GPU reads it, as an 11.4-MiB buffer every frame;
  there are no buffer or CPU writes. It is render-target memory later read by the game as a buffer.
- Cause: downloading an image into guest memory used staging and a deferred CPU write when
  that memory had a VRAM mirror. The mirror was updated only after that write, through
  invalidation, so the buffer read previous frames' data. The GPU now copies the image into
  the arena (VRAM mirror) in stream order as well; guest memory is updated as before.
  `IsRegionGpuModified` also treats GPU writes into the VRAM mirror (`gpu_written_bytes`,
  not in-place writes) as modified. Otherwise an update after a CPU overwrite replaced the
  mirror with old bytes (`BB_GPU_DATA_CHECK=0` restores the former behavior).
  Both changes are required. Afterwards: 11.9–13.0, matching the old model; FPS is unchanged
  (127–131 for both variants, three runs each).

## Running out of VRAM on 4-GB cards no longer stops the game

- RTX 3050 4 GB, old model (Auto on NVIDIA), 0.5: three crashes in one evening with
  `Failed to allocate 64 MiB for guest memory copies: ErrorOutOfDeviceMemory`. There is no
  fallback system-memory type for the arena: NVIDIA sparse buffers use only VRAM. In pre5,
  the texture collector retained textures for 5 seconds to avoid FPS degradation over time,
  exhausting 4 GB of VRAM.
- Now: try a smaller block of exactly the requested size, then any other memory type that
  can bind the arena. For 30 seconds after pressure, the collector again evicts by submission,
  as before 0.5. It also does this automatically when usage exceeds 92% of the driver's budget
  (`VK_EXT_memory_budget`, checked once per second). This requires verification on such a card.

## Exiting the game with a gamepad (#74, #116)

- The overlay (Insert or L3+R3) has a "Quit game" button. A second press confirms and closes
  the game in the same way as the window's close button.

## Mouse

- Mouse camera: clicking the game window captures the mouse in SDL relative mode. F1 or
  leaving the window releases it; the settings menu and name entry release it too. Mouse
  motion controls the right stick: deflection follows mouse speed, with roughly 1000 pixels/s
  giving a full turn at sensitivity 1, and decays over 60 ms. A moving mouse immediately
  passes the game's dead zone (`BB_MOUSE_DEADZONE`, 16 out of 127), so slow aiming still
  turns the camera. Behavior is independent of FPS.
- Mouse buttons and wheel use the same binding "keys": `Mouse Left` is R1, `Mouse Right` L2
  (firearm), `Mouse Middle` R3 (lock-on), `Mouse X1` R2, `Mouse X2` L1, and the wheel is d-pad
  up/down (quick items). Each wheel notch is a short press. Buttons work only while the mouse
  is captured; the click that captures it does not attack.
- bbport.ini: `mouse_look=0/1`, `mouse_sensitivity` (0.05–20), `mouse_invert_y`. In the launcher's
  *Controls* page: mouse camera, sensitivity and inversion. *Keyboard and mouse* configures
  bindings; "Assign" accepts a mouse button or wheel input too. Based on PR #108 (virtual
  stick from mouse motion); the keyboard layout is unchanged.

## Other changes

- Swapchain recreation uses `oldSwapchain` (PR #93). On NVIDIA under Wayland, recreation
  previously failed with "Surface already has a tearing controller".
- `launcher/bb-launcher.sh` forwards arguments such as `--play` through nix-shell too (PR #120).
- Capturing FSR 4.1.1 from the AppImage on SteamOS and other distributions (PR #89): capture
  on the host through systemd, retrying with the GPU presented as RX 7800 XT when the DLL
  does not expose FSR 4.1.
- Launcher: the DLSS row indicates whether it is included in the build. At that historical
  point the AppImage did not include NVIDIA's DLSS SDK, and the game used FSR 3.1.

## DLSS in the AppImage and a user-supplied NVIDIA library

- A build with `DLSS_SDK_ROOT` (DLSS SDK 310.9.1 from github.com/NVIDIA/DLSS) includes
  `libbbport_dlss.so`, `libnvidia-ngx-dlss.so.310.9.1` and `NVIDIA-DLSS-LICENSE.txt`.
  The RTX SDK license permits distribution as part of an application, not separately.
  Test AppImage: `dist/…-test-1010-dlss.AppImage`.
- Launcher: *Upscaler → DLSS: NVIDIA's library → Choose a file…*, as with the FSR 4.1.1 DLL.
  `libnvidia-ngx-dlss.so.<version>` is copied to `<user>/dlss/` and preferred over the bundled
  library (log: `DLSS: NVIDIA's library from …`). Choosing `nvngx_dlss.dll` explains that the
  Linux library is required. The bridge is searched for beside `bb-probe`, then in `<user>/dlss/`.
- The bridge also builds with Nix hardening flags (`-Werror=format-security`).
- Historical verification on RX 7800 XT reached only "not an NVIDIA GPU": the bundled or
  user-supplied library path was selected correctly. Actual DLSS requires NVIDIA RTX verification.

## Building from Git after updating from 0.4 (#124)

- `build.sh` stopped with "patch failed: src/ffx_vk_fsr4_v07.c:35". FSR-Vulkan retained the
  previous version's applied patch, and the new patch applied neither forwards nor backwards.
  The submodule is now reset in this case, then the patches are reapplied. Verified on a copy
  in that state.

## Online play (shadNet) in a separate module

- `gpu/bbnet` builds `out/gpu/libbbnet.so`: shadPS4 network and PSN libraries from shadp2p
  (a GPL-2.0 shadPS4 fork) with the shadNet client, ported from the online Linux bbport fork,
  which in turn came from the Windows port. The module is a separate build target, with its
  C++ hidden (`-fvisibility=hidden`, `-Bsymbolic`); only `bbnet_init` and `bbnet_resolve` are
  exported (`gpu/bbnet/bbnet.h`). Its own headers (`gpu/bbnet/include`) supplement the shared
  ones; nothing in `gpu/shim` or `gpu/shadps4` changed for this module.
- Runtime (`src/runtime_net.c`): with `BB_ONLINE=1`, the first network/PSN import loads the
  module (`dlopen`, `RTLD_LOCAL`; `BB_NET_MODULE` selects another path), supplies game data
  and guest threads for NP callbacks. Trophies, voice and store dialogs remain in the runtime.
  Without `BB_ONLINE`, the module is not loaded; if missing or unable to start, the port remains offline.
- Build dependencies: protobuf, nlohmann_json, OpenSSL, zlib and miniupnpc (`shell.nix`).
  Without them the module is not built; `BB_NET=OFF` disables it explicitly. The port builds
  as before, and the AppImage includes the module.
- `run.sh`: address overrides (`scripts/online.py`: game server → The Hunter's Dream,
  summon signs → shadNet WebAPI). The default shadNet server is `srv.shadps4.net:31313`.
- Launcher: *Online* page with game server, co-op server and WebAPI, shadNet account, UPnP
  and connection check. `settings.json` is owner-only (0600; it contains the password).
- UPnP: the P2P port is opened on the router when the transport is ready and closed on exit
  (#121: `AddMapping` had never been called).
- Verified: `tests/test_online.c` dispatches network/NP imports to the module and trophies to
  the runtime. The game with `BB_ONLINE=1` and no account reaches the level; the module exposes
  1399 functions and reports "no users connected to shadNet". shadNet login and summoning
  were not tested: no account was available, and the public server's UDP side did not respond
  according to #121.
- HTTPS in the AppImage: "Failed to obtain information from the Bloodborne server" occurred
  because The Hunter's Dream certificate verification failed (`SSL server verification failed`).
  Nix OpenSSL reads roots from `/etc/ssl/certs/ca-certificates.crt`, which on NixOS links into
  the host's `/nix/store`, hidden inside the AppImage. Package wrappers now set `SSL_CERT_FILE`
  to their own certificate bundle (`nss-cacert`) if the specified file is unreadable; source
  `run.sh` uses the system's bundle. The launcher's connection-check error text is no longer
  lost to markup (`<urlopen error …>`); icons come from the Adwaita theme.

## Main-menu flicker above 1080p output

- With live resolution changes (3840×2160 output on a 2560×1080 monitor), the main menu
  flickered: some frames were the game's native 1920×1080, while others had UI at output
  resolution (4 of 50 captures). `BB_UI_TRACE=1`, a new diagnostic for frames without
  output-resolution UI, showed that animated highlights use other Scaleform shaders
  (`bb4d5f8c`, `e94b5b06`, `9951d199`, `44072322`, `a334a845`), not just `09957251`.
  They were missing from the UI shader list (`ui_composition.h`), so those frames were not
  composed at output resolution. Afterwards: 0 of 80; the in-level image was unchanged.

## Smaller AppImage

- The package previously included all of Mesa with LLVM (~800 MB, though only RADV and ANV
  Vulkan drivers are needed), full GCC and Vulkan headers (paths referenced by bb-probe's
  debug information), 32-bit MangoHud (a second glibc, gtk3, icu and perl), and GStreamer in
  the GTK4 launcher. It now uses custom RADV (without LLVM; ACO) and ANV without the rest of
  Mesa, bb-probe without debug information, 64-bit MangoHud, and GTK4 without GStreamer,
  printing or tracker.
- Further changes: SDL3 without embedded zenity, which pulled in a second GTK4 with GStreamer
  (use the host's zenity when available); libdecor without its GTK3 plugin, both for SDL3 and
  MangoHud's glfw (frames are drawn by its cairo plugin); MangoHud without xdg-utils/Perl
  (use the host's `xdg-open`). Building custom Mesa enables Dozen only because the nixpkgs
  recipe expects its `spirv2dxil` output; Dozen is not included in the package.
- Result: AppImage 925 → 399 MB; uncompressed package 2.85 → 1.06 GB. Verified: the launcher
  opens, and the packaged game starts on bundled RADV through the title screen.

# After 0.51: moving away from emulation

## The game's occlusion queries are real by default (new model)

- Previously disabled ("everything visible" stub): with the upscaler, the lamp glow once flashed
  grey. Investigation found that a pass drawn at a size different from the game's target
  (reduced scene; UI at output resolution) counted pixels at its own size. The game received
  1/4 or 1/9 of the PS4 count (Oedon Chapel lamp: 84,286 at 960×540 and 37,455 at 640×360
  instead of 337,280 at 1920×1080).
- Each query segment now carries its pass's coefficient (the rasterizer's `target_scale`,
  8.8 fixed point); the summation shader (`occlusion_resolve.comp`) multiplies by it. With
  presets 0, 3 and 4 the game reads equivalent counts: 337,249 / 337,149 / 337,122 and
  43,814 / 43,761 / 43,750.
- No flashes reproduced: 8 stationary camera directions, 25 frames each (brightness variation
  ≤1%, lamp visible in 6 of 8), and a camera turn (80 frames), at 640×360 with 3840×2160
  FSR 4.1.1 output. FPS unchanged (100–104 versus 99–101 with the stub). PM4 self-test:
  11 of 11. `BB_OCCLUSION_QUERIES=0` selects the stub. `BB_OCCLUSION_SAMPLES=N`
  diagnoses how many pixels the game read.

## Layer memory module is the default on every GPU (new model)

- On AMD the new model kept game memory in a sparse arena; elsewhere it used the layer memory
  module (without sparse binding). AMD now uses the module too. On RX 7800 XT it is faster:
  a route in Yharnam takes 4.30 versus 4.60 ms/frame (p99 5.8–6.0 versus 6.6); turning the
  camera in the Hunter's Dream takes 4.8–5.0 versus 5.2–5.3 ms; Oedon Chapel: 234 versus 213 FPS.
- Only the module renders correctly without a game profile. With the arena, reading a 512-KB
  window from a stale VRAM copy overwrote CPU-written allocator bookkeeping, crashing on world
  entry (guest `0x208596a`). This was how the US edition ran before 0.51 (#119).
  With the module and no profile: 196 FPS, no crash.
- `BB_LAYER_MEMORY=0` restores the sparse arena (AMD only).

## Thread load: the bottleneck (new model, RX 7800 XT, Ryzen 7 5700X3D)

Burning Hunter's Dream, standing still, ~860 draws/frame, FSR 4.1.1 preset 3
(960×540 scene → 1080p).

- **GPU-bound**: ~97% busy (sysfs). Of the 5.05-ms frame, FSR 4.1.1 takes 1.09 ms,
  the game's copy shader 0.31 ms (58 dispatches), full-resolution scene copies for the
  game 0.22 ms, and gaps between submissions 0.6 ms.
- CPU: draw-recording thread (`bb:DrawRec`, stage B) uses 92–95% of a core, including 12–15%
  waiting for packets; PM4 decoder (`GpuComm`) 66%; game main thread 53%; its
  `GXRenderThread` 27–30%. The game waits 2.7–2.9 ms/frame for the previous frame: it has headroom.
- With lighter GPU work (FSR 3 preset 4), the CPU ceiling is ~225 FPS: the bottleneck becomes
  single-threaded stage B (~90% busy). Slower CPUs reach that limit sooner.
- The game submits ~62 command buffers/frame in three batches. Frame overlap depth
  (`BB_SUBMIT_AHEAD` 2–6) does not change FPS. Submission interval (`BB_HONEST_FLUSH_US`)
  500–1000 µs gives +0.5%, within noise, at +5% CPU on Vulkan-recording threads; 4000–8000
  is worse (188–196 FPS). Left unchanged.
- Statistics (`BB_FRAME_STATS=1`) cost ~2% FPS: timers are on every binding's path.

**Stage B buffer bindings through the memory module accelerated** (17% of its time → 12%):

- The VRAM-promotion queue (`LayerQueuePromotion`) cached ranges in 256 slots keyed by their
  first block. Single-block ranges (vertex streams in one buffer) evicted one another;
  every eighth call walked ~18 blocks again under the module lock. It now hashes the full
  range (4096 slots), with an additional per-block cache for data the game writes into rings
  at new addresses every frame. Everything is reconsidered once a second. Stage B time:
  4.2% → 0.6%.
- `LayerInPlace` (game-memory chunk buffer and offset) is cached until the game's next unmap:
  2.0% → 1.1%. The `Resolve` cache uses the same hash, 2048 slots.
- Tables are heap-allocated: `thread_local` arrays of hundreds of kilobytes enter every
  thread's static TLS, preventing game threads with small stacks from starting
  (`pthread_create failed: 22`).
- Result: stage B work −6% (packet time 86 → 81%, waiting for packets 8 → 13%). FPS on this
  machine unchanged, alternating A/B runs from one frozen save: FSR 4.1.1 200.1 → 199.7,
  FSR 3 preset 4 226.0 → 225.8 (±1 variation). No resource reaches 100%: GPU ~90%,
  stage B ~85% work, game waits 2.7 ms/frame. Frame time follows the chain
  "game → decoder → recording → GPU"; the game may lead the GPU by only one frame
  (its PS4 rule: farther ahead leaks its heap). Stage B headroom helps slower CPUs.
  Two-minute walk, frames, game without profile, PM4 self-test (11 of 11): no errors.
- Other stage B changes: `GetDrawOffsets` took the vertex-fetch description type without
  `const`, copying its attribute list (malloc) every draw; occlusion-pass scale took a mutex
  every draw; marking GPU writes across the copy shader's enormous range (~60 times/frame,
  one entry per MiB) now happens once per submission.
- Found but not changed: between adjacent copy-shader dispatches the game issues `ACQUIRE_MEM`
  (cache flush), not `CS_PARTIAL_FLUSH`. They overlap on PS4; here each pair has a full
  barrier (0.31 ms GPU/frame for 58 dispatches). Removing it could save up to ~3% GPU time,
  but risks game-data races; left alone without visual validation.

Tools: `BB_FPS_PRINT=1` prints FPS every 5 s without statistics (`tools/restart.sh` enables
it with `BB_FRAME_STATS=0`); `BB_TIMELINE` shows stage B idle time; `BB_GPU_PROFILE`
marks each submission's start (showing that submission gaps are not the copies at the
start: those take 0.006 ms/frame).

## Native mouse camera, without the right stick

- Previously mouse motion became right-stick deflection and followed the game's stick path:
  dead zone, response curve, acceleration and turn-speed limit. The mouse felt like a stick.
- Reverse engineering found the game camera (`ChrExFollowCam`, update `0x143ac60`, `rdi`
  is the camera) derives its angles each frame from its position around the character:
  pitch at `+0x140` (clamped by `+0x1f0`…`+0x1ec`), yaw at `+0x144` (within ±π).
  Normally `0x143cde0`…`0x143cdf0` computes "camera stick × speed × frame time", adds
  that increment to the angles, and positions the camera again. Stick path: pad device
  (`+0x1e4`…), virtual inputs 62/66 (X) and 63/67 (Y), actions `0x48`/`0x49`,
  manipulator (`+0x40`).
- A hook at `0x143cde0` now adds mouse rotation since the last update (radians, atomically
  consumed) to that increment and marks input active as the stick does (otherwise the
  game immediately returns pitch to its resting angle). Mouse displacement gives an exact
  rotation, without dead zone, acceleration or speed limit, independently of FPS; pitch
  clamping and obstacle avoidance remain the game's. Sensitivity 1 is 0.0015 rad/pixel
  (1000 pixels = 86°). Where the camera does not accept rotation (lock-on, menus, movies:
  its normal update does not run and rotation goes unconsumed for 100 ms), the mouse
  drives the right stick as before: moving it switches lock-on targets.
  `BB_NATIVE_MOUSE=0` selects stick-only behavior.
- Keyboard: the PS4 game has no keyboard device; its input library (`DLUserInput*`) knows
  only a pad and game actions are bound to its buttons. Keys remain bindings for those
  actions: there is no more "native" way to supply them.
- Verified: mouse turns left/right and up/down (same directions as the stick), one minute
  walking and turning, no errors. For tests `BB_PAD_FILE` accepts `mdx=`/`mdy=`
  (pixels per pad read).

## Ultrawide and other aspect ratios: live, through hooks

- Separate **aspect ratio** (Auto: monitor; 4:3, 16:10, 16:9, 21:9, 32:9) and
  **resolution** lists for that ratio, starting at 360–480 lines (4:3: 640×480 … 2880×2160;
  16:10: 640×400 … 3840×2400; 16:9: 640×360, 854×480, 960×540, 1280×720 … 3840×2160;
  21:9: 860×360, 1280×540, 1720×720, 2560×1080, 3440×1440, 3840×1600, 5120×2160;
  32:9: 1280×360 … 7680×2160; Auto adds the monitor's actual size). Changing ratio retains
  height. Changes are live (`live_resolution=1`; with a startup resolution patch, restart
  required). bbport.ini: `aspect_ratio=auto|4:3|16:10|16:9|21:9|32:9`,
  `output_res=WxH`. Game menu, overlay and launcher.
- The game's frame stays 1920×1080; game code is not patched. Instead:
  - Camera (hooks at 5 projection-parameter copies in the camera manager, `0x1436c2c` …):
    output aspect ratio; wider shows more at the sides (same vertical FOV), taller (16:10)
    expands vertical FOV (`2·atan(tan(fov/2)·(16/9)/A)`, x87 in the stub), same horizontal FOV.
  - Scene renders in proxy targets with the output ratio (different per-axis scales,
    `FragCoord` converted per axis); the upscaler produces the output frame.
  - UI (Scaleform): each frame the game sets each movie's viewport (`0x1f59100` →
    `MovieImpl::SetViewport` `0x1f510`, ShowAll mode). A hook substitutes the output pixel
    aspect ratio (`Viewport::AspectRatio` = (width/height)/(16/9)). The movie displays
    its 16:9 screen in the middle of a wider/taller visible region, squeezed into 1920×1080;
    output stretches it back. Content outside the game's screen is drawn, not clipped.
  - HUD anchors to output edges and follows ratio changes: `fe.gfx` groups move as the game
    moves clips, through `SetMember("x"/"y")` on Scaleform objects (game ObjectInterface:
    GetMember `+0x28`, SetMember `+0x30`), in the game-screen per-frame update (`0x1bf9e10`;
    HUD at `screen+0xa80`; values acquired and released in the same frame because HUD movies
    unload with areas). Bars, items and effects go left; blood echoes, insight and autosave
    icon go right. At 4:3/16:10 upper elements go up, boss bar down
    (`BB_HUD_ANCHOR=0`: centered 16:9).
  - Full-screen fills and UI backdrops (menu dimming, drawn slightly larger than the game's
    screen; "You Died"; fades) cover the output. The vertex shader moves vertices at or
    beyond game-screen corners to output corners (both x and y). Content the HUD moved
    outside along only one axis, Scaleform masks and everything under them (stencil test:
    for example the item-icon strip sliding within its slot) remain unchanged
    (`motion_param` for those draws; shader cache rebuilt once, version 18).
    Large pictures (title image, 2048×1024) and text are not stretched.
    `BB_UI_DRAWS=<file>` logs one frame's UI draws.
  - Frames without a scene (title screen, loading): margins outside the game screen are
    black (movies fill their expanded region with the background color, grey at the title).
  - Markers above characters (lock-on, enemy health bars, damage): hooks at three UI-coordinate
    conversions (`0x1644379`, `0x1644c45`, `0x16452b7`) multiply by the port's vector,
    placing markers over their characters. The game itself hides them outside the 16:9 region.
- Game menu: *Display* page contains aspect ratio, resolution, upscaler, preset, sharpness
  and detail. Selection uses the game's popup-list row (as in its language settings,
  `0x1b29370`) instead of 0–10 sliders. Rows beneath showed through (ControllSetting lays
  rows "upward"); runtime supplies a copy of `menu/optionsetting.gfx` with that layout's
  row depths reversed, as in LanguageSetting (only depth fields change; disk file untouched;
  `BB_GAME_MENU=0`: unchanged). After a ratio change, Resolution immediately shows the
  new-ratio size at the same height and lists exactly that ratio's sizes. The row owns its
  values (`row+0x3d8`, 0x48 bytes each, count at `+0xce0`), with display text supplied by
  the port's buffers. The page-row input hook (`0x1b26b00`, game menu thread) rewrites
  values and count and refreshes the row (`0x1b2b7c0`: value text; `0x1ad06e0`: list text).
  FPS counter is in the overlay and launcher.
- Also: Auto knows the window's monitor and monitor changes; after failing on unsupported
  output (7680×2160 without 4320 assets), FSR 4 is retried on output change rather than
  remaining on FSR 3.1.
- Limits: FSR 4.1.1 output up to 3840×2160 (5120×2160, 5120×1440, 7680×2160 use FSR 3.1);
  game screen-bound checks hide character markers outside the 16:9 region.
- Removed: the old startup code-patch approach (`bloodborne_display.cpp`, `BB_GAME_FRAME`,
  game frame wider than 1920×1080).

## NVIDIA: 0.51 did not start (CreateDevice: ErrorInitializationFailed) (#135, #147, #152)

- With DLSS (NVIDIA library present), Vulkan device creation uses NGX extensions.
  The driver advertises them but loads `libcuda.so.1` for them (also requiring `nvidia-uvm`).
  The AppImage launcher populated its NVIDIA library directory only with `libnvidia-*`,
  `libGLX_nvidia`, `libEGL_nvidia`. `libcuda` was missing, `vkCreateDevice` returned
  ErrorInitializationFailed, and the game continued into an "Invalid device" crash
  (code 134/-1), even on non-DLSS cards (GTX 1660) because the AppImage contains DLSS.
- The launcher now also supplies `libcuda.so*` (`launcher/bbport_vulkan.py`). If NGX device
  creation still fails it retries without those extensions, disabling DLSS with the reason
  in the log. Game uses FSR 3.1; DLSS remains selectable in settings. No device at all
  gives a clear stop rather than a later crash. PR #137 and #140 proposed the same fixes.

## New model: frame-sized buffers are in VRAM again (#149)

- RX 7900 XT, 3840×2160 output with startup resolution patch (2560×1440 scene):
  0.4 136 FPS, 0.51 58 (old model 128). Here (RX 7800 XT, same settings): new 95 FPS,
  old 130; GPU 10.5 versus 7.85 ms/frame. A per-pixel pass (`cs 3d5ebf4e`, 58,880 groups)
  wrote a frame-sized buffer (19.9 MB) to game memory over the bus, 1.8 GB/s;
  neighboring passes also read it there.
- Cause: the layer memory module (default since 0.5). A GPU-written binding must fit wholly
  in one VRAM mirror or its entire range goes to game memory; on the second occurrence,
  permanently (`dynamic_blocks`). Of this buffer's 305 blocks, 303 had mirrors. First and
  last were only partially covered (start not 64-KB aligned); the module knew nothing about
  their other bytes (neither loader nor GPU had written them), so excluded them.
  At 1080p the buffers did not land this way.
- Such edge blocks now accompany the writable binding into its mirror if CPU writes can be
  trapped (`layer_edge_blocks`). A nearby CPU write returns the block in place, first copying
  back GPU bytes (only GPU-written ranges). Here: 95 → 132 FPS (old 130). Live resolution
  changes and ordinary settings unchanged (120 and ~194 FPS); same frames.
  Diagnostic: `BB_RESIDENCY_MIX=2` (largest-volume in-place bindings and reasons).

## Old memory model: VRAM no longer accumulates until a crash (#142, 4 GB)

- The old model (default on NVIDIA) retained every game-memory copy ever uploaded to VRAM.
  Area after area, "guest blocks in VRAM" grew (1.6 GB on a 4-GB card), until after an hour
  or two "Failed to allocate .. MiB for guest memory copies: VRAM is full" stopped the game
  (NVIDIA's sparse arena accepts only VRAM).
- On cards up to 8 GB, copies unused by the GPU for a minute and containing no GPU writes
  are now evicted (reloaded on reuse) and replaced by new ones; under VRAM pressure,
  after 5 s on any card. If a new block still cannot be allocated, copies unused for
  a second are evicted and replaced; empty chunks return to the driver.
  (`BB_VRAM_IDLE_SECONDS=N`: custom timeout, on any card; `BB_ARENA_VRAM_ONLY=1`
  with `BB_RESIDENCY_VRAM_LIMIT_MB`: simulate such a card.)
- If an area's entire working set cannot fit in VRAM the game still stops, but it no longer
  accumulates copies over hours.

## Frame rate through hooks, not patches; frame-tied behavior uses frame time

- Above 30 FPS (Unlimited, 60, 90), hooks in game code (`gpu/shim/bbport_frame_rate.cpp`)
  control frame rate instead of community Uncap FPS++ / 60 FPS++ / 90 FPS++ and Sprint Fix
  patches (`BB_FRAME_HOOKS=0`: patches again for comparison). Installed when the image loads,
  before game start; every site is byte-checked.
  - Main loop (`0x2018d20`): frame pause (`0x2034770`) waits for 1/30 s and measures the
    frame at `+0x264`, then the game steps a fixed 1/30 s (`0x2018e36`). Hooks keep pause
    mode at one vblank with a 1/240 frame target (60/90 and `BB_FPS_LIMIT`: their frame
    duration; the game itself limits before simulation, not by delaying finished frames).
    Step becomes measured frame time (1/240…1/30 s; below 30 FPS the game slows as always).
    The game's requested flip rate (`sceVideoOutSetFlipRate`, every other vblank) has no effect.
  - Code tied to 30-FPS frames reads the current frame's value: instructions reference a
    constant on a page beside the image (only operand address changes), recalculated each
    frame. Step 1/30 s → frame time; per-frame fraction f → `1−(1−f)^n`;
    damping k → `k^n`; increment → `·n` (n is frame length in 30-FPS frames).
    In total: 48 sites and 2 fixed subsystem steps (`0x17f9b71`, `0x1572a7d`):
    "one frame" in effects and timers, subsystem steps (including one the game makes 1/60
    in its 60-Hz mode), camera smoothing (1/30 and 0.1/frame), character-motion damping
    (0.95/frame), ±0.1/frame ramp (`0x19084b0`, absent in Uncap FPS++), cloth stiffness
    (1.0 at 30 FPS, 0.5 at 60+ FPS as in the 60-FPS patches).
  - Newly found, absent from every patch: physics-driven body-part timers
    (`0x1515ec0` → `0x180df90`, `0x1811650`, each part every frame) advanced 1/30 s/frame,
    6–7× too fast at 200 FPS; running's "against a wall" damping (×0.8/frame).
  - Running's wall check (`0x1514c24`) compared distance/frame ×30. It now divides by frame
    time, giving speed at any FPS; otherwise running fell to walking above ~90 FPS.
  - Converting durations from 30-FPS frames to seconds (effect, sound, animation fades)
    remains 1/30: their timers use real time (patches shortened them 2–8×). Other 1/30 sites
    (67 immediates, ~100 functions with 1/30, 30, 1/60, 60) were checked by call frequency
    (`BB_RE_ENTRY=addresses`: call counts and xmm0); not called every game frame or are
    unit conversions.
- Verification: from one save, 2 s walking and 3 s running put the character in the same
  locations at 30, 60 and ~200 FPS.
- UI (Scaleform) advances every frame by real time (`MovieImpl::Advance`, `0x20f00`,
  `BB_RE_ADVANCE=1`), but all 102 movies in `menu/` were authored at 30 FPS:
  their timeline animations step in 1/30 s increments.

## AppImage: `--play` launches the game again

- `Bloodborne-bbport-x86_64.AppImage --play` (Steam Deck Game Mode, shortcuts) immediately
  failed with "python3: Software caused connection abort". AppImage keeps its image mounted
  while the program holds an inherited pipe, the first free descriptor, 3. With `--play`,
  `run.sh` replaces the launcher, and log saving (`exec 3>…`) closed that pipe, unmounting
  the image under the running script. The Play button worked because the launcher held
  the pipe. Logging now uses a bash-selected descriptor (10 or higher).

## New model: FPS no longer degrades during long sessions with lamp travel

- User: "lost about 10 frames". Measurement at one point (Hunter's Dream, near the Doll,
  ~885 draws, GPU 99% busy): fresh launch 76.6 FPS; after 17 minutes with lamp travel
  55.3 (−28%); returning to menu and reloading in the same process did not help (54.2).
  Loaded game data with a VRAM copy fell from 84% to 50%.
- Cause (`BB_RESIDENCY_MIX=2`: heaviest in-place bindings and their blocks): the module
  promotes a read range only as a whole. One block the GPU once wrote in place
  (`dynamic_blocks`) kept the whole range in game memory: a 7-MB binding was read over
  the bus because of one such block out of 110. Marks never expired; new areas' assets
  loaded into memory marked by previous GPU buffers (164 → 1117 MiB dynamic blocks/session).
- A block fully overwritten by game loaders (all bytes CPU data) can now get a VRAM copy
  again. GPU writes into it stay in place (`layer_cpu_blocks`) so CPU readers (the
  translator reads shader code and descriptors there) never see stale data. Frequently
  CPU-written blocks remain dynamic. `BB_LAYER_RELOAD_RESET=0` restores old behavior.
- Verification: 16 minutes with lamp travel, 366–771 MiB dynamic blocks without growth
  (3 GB of blocks reclaimed); mixed reads ~300 MiB/2 s instead of ~8 GB. At the final
  point: 66–72 FPS after playing, fresh launch 67–73 (between-launch variation ~8%).
  VRAM copying 16 → 23 MB/s.
- Rejected: expiring marks by time (30 s without evidence). Within a minute the translator
  read garbage shader code from game memory (recompiler stopped at an unknown instruction).
  Some marks protect data the GPU writes and CPU reads.
- Unmapping game memory now resets all marks of fully unmapped blocks
  (`BB_LAYER_UNMAP_RESET=0`: previous behavior). Bloodborne does not unmap during play,
  so is unaffected.
- Diagnostic: `Layer memory: held in place` every 10 s reports dynamic blocks, failed
  observation, CPU-written blocks (and GPU writes kept in place because of them over
  10 s), blocks reclaimed after reload, and loaded data lacking a VRAM copy.

## Own code instead of shadPS4 (except the online module)

- `gpu/shadps4` removed: command processor, GCN definitions, shader translator, renderer,
  caches and platform libraries are the port's own code (`gpu/VENDOR.txt`,
  [SHADPS4_EXIT_PLAN.md](SHADPS4_EXIT_PLAN.md)). Tested on the game's shader corpus:
  translator SPIR-V is byte-identical to the previous output.
- Pipeline cache and disk storage: `gpu/render/pipeline_cache.*`, `pipeline_store.*`;
  rasterizer split into `gpu/render/raster_*.cpp` modules.
- NVIDIA disk-cached pipelines lost the clip-distance discard shader (not saved);
  now saved. Old cache entries remain readable without rebuilding.
- Disk-cached geometry-shader pipelines received an empty fetch shader (overwritten
  by a stage without one).
- Draws without a pixel shader inherited the previous draw's fragment settings
  (NVIDIA: presence of the discard shader depended on draw order).
- Vulkan debug markers (`BB_VK_MARKERS=1`) no longer read beyond game strings.
