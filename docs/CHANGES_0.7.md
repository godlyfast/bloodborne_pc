# 0.7

bbport is the counterpart of Wine + DXVK for a single game: Bloodborne (v1.09), now on **Linux
and Windows**. Changes since [0.6](https://github.com/deadinside28/bloodborne_pc/releases/tag/0.6).

Questions about this project: Discord https://discord.gg/KYZRKk9CB — not the shadPS4 server.

### Windows

- **A native Windows build** (Windows 10/11, x86-64, Vulkan 1.3), on the new memory model only:
  `bbport-windows.zip` with `Bloodborne.exe`, a launcher in the Windows 11 style (WPF; Russian,
  English, Brazilian Portuguese, Simplified Chinese, French), `bbport-run.exe` for `--play`, the
  shader recipes and `README-Windows.txt`. Unpack it anywhere, start `Bloodborne.exe`, choose the
  game folder. Saves, settings and the shader cache stay inside the folder.
- **Online play on Windows**: the online module is `online\bbnet20.dll` (shadPS4 0.20 network with
  BBSC, the same code as `libbbnet20.so`), set in the launcher's new *Online* section as on
  Linux: both pools (Seamless Hunt with account and BBSC, The Hunter's Dream with Discord
  sign-in), UPnP, connection check, and BBSC's local game server when the server's own does not
  answer. Mods and third-party XML patches from the launcher too (the *Mods and patches* section;
  without Developer Mode the modded game is put together with junctions and hard links).
- **FSR 4 from AMD's own FSR SDK 2.4 DLLs** (`fsr_amd`, in-game menu): put AMD's Vulkan DLLs
  (`amd_fidelityfx_loader_vk.dll`, `amd_fidelityfx_upscaler_vk.dll`) into `user\fsr` or set
  `BB_FFX_DIR`; the driver's newest model (4.1.2 on Radeon) is used. Windows only.
- Built with MSYS2 CLANG64 (`packaging/windows/`), or cross-built from Linux with llvm-mingw.
- Upscalers on Windows: FSR 3.1, FSR 4, **FSR 4.1.1** (assets built from your own DLL on the same
  PC, no Proton needed), **FSR 4.1.2 driver models** on Radeon (INT8 on RDNA2/3, the *Lite* model;
  taken from the driver's `amdxcffx64.dll`), **DLSS** and **DLSS Frame Generation** through the
  bridge (needs NVIDIA's DLSS SDK at build time).
- Fixed on Windows during testing: stalls in `VirtualQuery` while the game's heaps grew,
  BC6H textures that could not be storage images, the opening movie crash, the spinning character
  in the creator, the HUD atlas decoding, DLSS Frame Generation black frames, a lost shader
  cache after an update.
- NVIDIA on Windows: the port puts a *prefer maximum performance* profile for `bb-probe.exe` into
  the driver (NVAPI; your own Control Panel choice is kept; `BB_NV_POWER=0` off). GPUs stuck at
  low clocks halved the FPS in heavy places. A tester's RTX 5060 now runs as expected.
- Windows + NVIDIA uses FIFO instead of Mailbox (present bursts on Optimus laptops;
  `BB_NVIDIA_MAILBOX=1` keeps Mailbox).
- Tested on: Ryzen 7 5700X3D + RX 7800 XT, i5-7300HQ + GTX 1050 2 GB, i5-8250U + GeForce 930MX.

### One memory model

- **The old memory model of 0.3 is gone.** The new memory and translation model is the only
  one, on every GPU; *Memory model* is no longer in the launcher. A driver that cannot use the
  game's memory in place stops with a `STOP: the GPU driver cannot use the game's memory in place`
  line instead of falling back.
- **The game's graphics heaps grow on demand**: about 1.5 GB of the PS4 heaps were allocated
  but never used; now memory is added as the game takes it and given back when freed (`BB_HEAP_GROW=0`: whole from the start).
- Texture packs with upscaled map textures get larger graphics heaps by themselves (PR #360 by
  wheat32; `BB_LARGE_HEAPS=1/0`).
- *Texture quality* (launcher, game menu): full, half, quarter, or *auto* (half on cards with up to
  3 GB for the game). Big mipmapped textures then skip their top levels.
- Cards with up to 3 GB: smaller stream and constant rings.

### Faster

- **Occlusion queries counted only while the game's queries are open**: before, the results
  were collected ~5 times a frame, each time waiting for the GPU (~0.8 ms of GPU time per frame).
  RX 7800 XT, Old Yharnam, 1080p FSR 4 Native AA: **164 → 189 FPS** in the heaviest view
  (`BB_OCCLUSION_INTERVALS=0`: the old way).
- **PGO was silently off** in the releases since the source folder moved; retrained:
  **+15–20 %** on the PC, Steam Deck FSR 4.1.1 48.8 → 51.3 FPS.
- Steam Deck: draws prepared on the threads that use them on CPUs with fewer than 12 hardware
  threads (−CPU power, +GPU clock); register state reset only where touched; fetch-shader decodes
  cached; texture sets reused without draw preparation. Standing in one spot: 68.6 → 72 FPS.
- Stage A no longer waits for the GPU before reading descriptor tables when the frame's tasks only
  read the CPU's data (Deck 63.5 → 65 FPS, laptop pacing).
- Windows: one system call per draw removed (`std::jthread::joinable` → flag): +3 %.
- Frame generation FSR 3.1: the port's own optical-flow and interpolation shaders (bit-exact SAD,
  hardware bilinear) and an early frame retire: Steam Deck 34.9 → 38.4 FPS with FG.
- **Less traffic over PCIe**: constants already in video memory are not sent again (ring dedup,
  ~300 MB/s less), and of the game's copy shader calls only the copies that change something run
  (checked on a separate thread): +1–4 % in heavy views, more with a busy bus
  (`BB_RING_DEDUP=0`, `BB_COPY_SKIP_SAME=0`: off).
- Live resolution changes no longer cost FPS: the game starts at the chosen preset's size and
  smaller **and larger** presets switch live; the output resolution and aspect ratio switch live
  too. *Auto* output = the monitor's resolution. *Live resolution* is on by default.
- **Shaders before you play:** a shader recipe pack (655 programs, 1389 permutations, 1149
  pipelines from players' caches) is compiled in the background at start; the cache is kept across
  updates (rebuilt from the saved inputs). 0 compiles in a repeat session.

### New

- **Anti-aliasing** menu (launcher, game menu, overlay): *auto* (the game's AA only without an
  upscaler), the game's, **FXAA** (Kyo's *Force FXAA2*), **SMAA 1x** (the port's own, before the
  UI), off. Sharpening (RCAS) works without an upscaler too.
- **FSR 1** (spatial) for weak GPUs.
- **GT-VBAO** in place of the game's SSAO (no dark halos around thin objects, ~7 % FPS; port by
  redditor69).
- **FSR 3.1 frame generation** is shown on every GPU (experimental); DLSS FG only on NVIDIA.
- **AMD Anti-Lag 2** (`VK_AMD_anti_lag`) beside NVIDIA Reflex (Reflex and DLSS FG: PR #260 by
  adds39939).
- **Trophies**: earned trophies go to `user/trophies.jsonl` (port of guutol's work).
- Game menu: *Exit to desktop* in *System* (title screen too). A slow-walk key (Left Alt). Up to
  4 keys per action, desktop shortcut button (launcher). *Invert mouse X*. Skipping videos (Enter,
  Esc, Options).
- The game's mouse auto-rotation is off by default (`BB_MOUSE_AUTO_ROTATE=1`: the game's; from
  ArenaMMORPG's #352).
- Engine fixes from SrShadowy's fork: play time counted correctly above 30 FPS, the hit
  collector's cap raised to 65536, a character-id guard; BBSC 0.0.2 with the relay client and P2P
  relay fallback (Teefpyre's BBSC Linux fixes included).
- BBSC: the hunter's kit and Kin Bell signs and summons in every area (PR #342 by whp199, the
  signs and summons part); vanilla bells back when BBSC is off (PR #346 by DominickCobb-rs).
- Launcher: French (PR #347 by Sarxzer), Simplified Chinese completed (PR #157 by Qiming-Liu);
  settings grouped in sections with descriptions; monitor and controller choice.
- Steam Deck: the Steam overlay is no longer taken out of the game (#217, #77); hold L3+R3 for the port's menu; Steam Input
  only (no doubled keyboard/mouse events).
- Every `BB_*` variable is listed with what it does in [ENVIRONMENT.md](ENVIRONMENT.md); the log's
  `Environment:` line names unknown ones (typos).

### Fixes

- **Cloth fluttering above 30 FPS** (#58): Havok's cloth solver ran fps/30 times a second with
  the stiffness of one 30 FPS step; the stiffness factor now follows the solves per second (the
  old 0.5 clamp was only a range check and did nothing).
- **Wedges in the shadows of lamps and other point lights**: each face of the point-light
  shadow cube is cleared on its own.
- **Grid of item icons over the left half of the screen**: the HUD's stencil masks went into the
  UI depth while the masked icons tested the scene's stencil.
- Vertex explosions (stretched railings in the Hunter's Dream) where a buffer crossed a boundary
  between two pieces of a grown heap.
- FPS drop to 16 after quitting to the title and loading another save (GTX 1060 and other
  NVIDIA): marks from the previous save's loading stayed on memory the game reused for GPU data.
- GTX 10xx: changing the resolution live dropped FPS (no depth proxy without D32S8 blits or
  stencil export): such GPUs now apply it at the next start.
- FG ghosts (bushes where there are none) while moving: instanced foliage got another object's
  previous positions.
- Black effects after a live preset change.
- Crash at `0x2169edc` (GX occlusion query without a handle, #336; PR #343 by whp199).
- Online module: QueryProtection of the game's low memory (#282; "connection appeared" confirmed
  by the user).
- FSR 3.1 never in protected memory (ROG Ally and others, #85; PR #293 by iannitram).
- FIFO Relaxed present mode accepted (PR #225 by AndiMajore).
- Exit 139 with FG on and Mesa's anti-lag layer; Mesa's layer bug with `vkQueueSubmit`
  (the port submits with `vkQueueSubmit2`).
- Frame limiter: no catch-up slots (48/18 ms saw-tooth at 30 FPS).
- Sewers: no AA and an FPS drop (the upscaler was recreated twice a frame by the reactive mask).
- Wayland HiDPI scaling (#328, #378, #234); AppImage `.desktop` and AppStream data (#362, #287).
- Heap shrink race (black blotches on the ground); single crashes at load under raised thread
  priorities (priorities stay normal).
- Steam Deck lazy-memory imports counted twice in GTT (device lost after ~80 min).

### Removed

- The old memory model (see above) and the former online module on shadp2p (`libbbnet.so`):
  `libbbnet20.so` is the only one.
- Texture preload at load time (did not find its images).
- What other games needed and Bloodborne never calls: the LEGO Dimensions toy pad (USB), NGS2
  sound, event flags, time zones, dialogs and PSN services beyond Bloodborne's set (checked
  against the eboot's and libc's 734 imports).

**Known limits:** two-player co-op is tested by players, not by the author; NVIDIA on Windows
(FPS halving in heavy places on RTX 3080/5060) improved, more reports welcome; RDNA4 FP8 runs untested on
hardware; Polaris (RX 400/500) unverified. Bug #32 (rare guest fault at `0x263b8e7`) is still
open.

**Downloads:** `Bloodborne-bbport-0.7-windows-x64.zip` (Windows 10/11: unpack, start
`Bloodborne.exe`), `Bloodborne-bbport-0.7-x86_64.AppImage` (Linux and Steam Deck, one file) and
`Bloodborne-bbport-0.7-linux-x86_64.tar.zst` (Linux as a folder: `Bloodborne.sh` opens the
launcher; the online module `online/libbbnet20.so` lies open, so a BBSC build can replace it).

The packages contain no game files and no AMD FSR 4 model assets. `SHA256SUMS` accompanies the
download.

**Related projects:** [Bloodborne-Android](https://github.com/ducvd89/Bloodborne-Android) (a
fork of bbport for Android) and [bloodborne-mac](https://github.com/bloodborne-native/bloodborne-mac)
(native on Apple Silicon, built on bbport and shadPS4).

**Thanks** to everyone whose work is in this release: wheat32 (#360), Sarxzer (#347), whp199
(#342, #343), DominickCobb-rs (#346), maiconjsv (#339), iannitram (#293), adds39939 (#260),
AndiMajore (#225), Qiming-Liu (#157), ArenaMMORPG (#352/#353), guutol (trophies), redditor69
(GT-VBAO), SrShadowy and Teefpyre (engine and BBSC fixes in SrShadowy's fork), Supermedo and Awaken (the
online module's network stack), IFreemz (DLSS
bridge), the players who sent their shader caches, and everyone who reported bugs with logs.
The authors of the pull requests taken into 0.4–0.6 are credited as co-authors of this release
too ([docs/CONTRIBUTORS_0.7.md](CONTRIBUTORS_0.7.md)).
