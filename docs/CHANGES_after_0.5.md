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
