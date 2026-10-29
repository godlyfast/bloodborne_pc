# Fork SrShadowy/bloodborne_pc (branch testing): what is in it and what to take

Checked on 25.10.2026 against the code (not only the descriptions): 110 commits on top of our 0.6 (common ancestor `8185b88`), 420 files, +47 thousand lines. Clone: `../forks/bloodborne_pc-srshadowy`.

Their log `SHADOW_CHANGES.md` is written in broad strokes; some of its items describe less in the code than they sound like. What follows is based on the actual code.

## Take (high value)

### 1. Online: BBSC 0.0.2 + relay (module bbnet20 and the old bbnet)
- **What:** update of Seamless Co-op to 0.0.2 (+2.9 thousand lines in `bloodborne_re.cpp`), BBSC relay client on POSIX sockets (in the original 0.0.2 it was Windows-only), fallback P2P path through the relay when the broker did not provide the peer's address (it used to be "peer endpoint unresolved; connection timeout" after 30 s, CGNAT/strict NAT), a retry queue for signalling re-activation.
- **Fixes:** size limit on the `/message_area` response (Panic 265 on dense maps), synchronization of the PvP bell (0x25), boss progress flags (0x26) and the host's boss bar (0x27), spectator camera for a player who died in co-op, Teefpyre fixes for Linux: stale summon, duplicated port in `online.py`, FPS drop 60→15; lookup of parameter tables via `SoloParamRepository`.
- **How it will merge:** our network modules changed little after 0.6. Trial three-way merge: 40 files are taken as is, 6 conflicts, all minor: `memory.h` — keep our version (#282); `bbsc_persistence.h` — merge the key lists; `bloodborne_re.cpp` — one `inventory != 0` check.
- **Must be carried over together:** `extra/core/bbsc/bbport_bbsc_kit.{h,cpp}` (save folder, memory search, bells).
- **Do not take blindly:** their hooks for the alternative bbhost server (`extra/hosts`, accounts, http_json) are baked into the old bbnet. It is a separate online service, so a decision is needed.
- **Verification:** only a live two-player game (summon, CGNAT, bells).

### 2. Game fixes (`extra/core/engine_fixes/bbport_engine_fixes.cpp`)
- **Game-time clock at high FPS:** every frame the game drops the fractional part of the milliseconds. At 120+ FPS the time in the save runs slower (at 8.33 ms per frame 4% is lost). Their patch carries the remainder over between frames. Take it, but rewrite it onto our hooks: their code is Linux-only.
- **Out-of-bounds protection in the Havok hit collector (pushBack, SIGSEGV 0xf00010):** caps the count at 2048 hits per request. May change physics behavior in rare cases; take it if we have such crashes.
- **Reset of the invalid CharaId 0x8000000000000000 before saving:** save protection; the origin is unclear, needs analysis.
- **Heap doubling (heap headroom):** do NOT take; we have our own on-demand heap growth.

### 3. Video skip (AvPlayer) with Enter/Esc
`extra/core/engine_fixes/bbport_video.cpp`, three lines in `avplayer.cpp`: `player->Stop()` + the OPTIONS button. We have nothing like this.

### 4. DS4/DualSense touchpad and gyroscope disabling
The left and right halves of the touchpad are told apart, plus the `disable_gyro` option. SDL HIDAPI hints in `window.cpp` and `runtime_pad.c`. We cannot disable the gyroscope. Take it.

### 5. Performance settings for weak machines (`bbport_engine_graphics.cpp`)
- `lod_bias` (−2…2): model detail distance, through the game's render settings (+0x530).
- `light_grid_opt`: larger lighting grid tiles.

A potential gain for the laptop and the Deck. Measure first and look at the picture.

### 6. Building with old compilers
- `gcn/isa.cpp`: without C++23 "deducing this", for GCC 13 and Ubuntu 22.04.
- `page_watch.cpp`: fallback `#define`s for UFFD with old kernel headers.

A small thing, but it will help people with old distributions.

## Questionable (measure)
- **The game's debug exceptions do not terminate the process** (`raise_exception` in `runtime_kernel.c`): as on retail without a debugger. With us, any game assert other than the blur-kernel one gives exit code 23. May remove some crashes, but may also hide real errors.
- **Adaptive mutexes** (`PTHREAD_MUTEX_ADAPTIVE_NP` by default) and an EDEADLK check: on 4 cores the spinning may cost CPU.
- **Guest thread pinning to cores and nice by role:** common threads are clamped to the first 7 logical CPUs. Negative nice is not applied without privileges. In theory useful for dual-chiplet Ryzens and Intel P/E cores; on our 5700X3D it may get in the way. Only after measuring.
- **MADV_HUGEPAGE on the memory pool:** for memfd it works only if shmem THP is enabled in the system (usually disabled). Almost no effect.
- **Number of Vulkan recording threads:** 4 with 16+ and 5 with 20+ threads (we have 3). Measure on the PC.

## Do not take
- Debugger, memory scanner, disassembler, hex inspector — developer tools with SIGTRAP/mprotect in the runtime.
- Their GTK4/libadwaita launcher (requires system GTK4) and the "light" AppImage. Ideas can be taken: the `--diagnostics` report, driver checks, gamepad tester.
- "Grimoire" shader precompilation and the MH Rise-style splash: we have our own cache and preloading.
- The 8 GiB memory pool by default (`BB_DMEM_MB`): that is +3 GiB of RAM.
- Brightness in frame generation (1D LUT): we already have our own `fg_display_lut`.
- IndirectDispatch sanitizer: we have IndirectGuard.

## Optional (features, not fixes)
Discord Rich Presence (area, deaths, co-op), photo mode with the HUD hidden, death counter, info HUD, Portuguese localization.

## Shader precompilation: their "Grimoire" and our recipes

| | Their "Grimoire" | Our recipes (`shader_recipes.bin`) |
|---|---|---|
| What is shipped | ready-made SPIR-V + .meta + .key from their own sessions (`caryll_runes.pack` ~24 MB, it is not in git, only in their build) | the game's shader inputs (~1 MB); SPIR-V is produced on the player's machine by the current translator |
| After a translator update | SPIR-V becomes stale (different ShaderBinaryVersion): the pack has to be rebuilt by hand; in their case 368 of ~990 keys were being rejected | re-translated, ~1 ms per shader on a PC |
| Volume | 623 pipelines after cleanup | 626 programs, 1253 variants, 930 pipelines; including the cache of "shadowy" himself from Discord (851 of his shaders were already in ours, 22 added) |
| Where new ones come from | only from their own runs | merging of players' caches (`--merge-shader-metas/packs`), restoring inputs from metadata (97%) |
| When it is compiled | a separate run before the game with a splash screen (Linux only, `run.sh`, if there is no `pipeline_driver.cache`) | in the background at launch on all cores but one; rendering waits only for its own pipeline (laptop: warm-up 11.8 → 3.6 s) |
| Driver cache | own VkPipelineCache file with a vendor/device/UUID check | we checked: on NVIDIA loading such a file slowed warm-up from 1.6 to 55 s, and RADV has the Mesa cache — removed |
| Stale keys | removed from the player's cache automatically | kept: data is taken from them when merging |
| Diagnostics | a tab in the overlay: live compile log, inventory with location, JSON report | `BB_COMPILE_TRACE=1`, compile counter in the frame statistics |
| The game's shader catalog | extracts 4376 programs from `*.shaderbnd.dcx` and cross-checks them against those seen in the game (366 matched) | there was only parsing: 14571 entries in gxflvershader, the plan to link names with hashes has not been started |

**What is useful to us from this:** their static catalog (extracting programs from `shaderbnd` and matching them against those that occur in the game) will be useful for our plan to predict shaders without playing through the game. The splash screen with progress can be made as an indicator in the overlay on top of our background compilation. The rest we have already done more reliably.

## Ported on 25.10.2026 (locally, not published)

| What | Where in ours | Checked |
|---|---|---|
| In-game time at high FPS (fractional ms are carried over between frames) | `gpu/shim/bbport_engine_fixes.cpp`, hook on `vcvttss2si` 0x19419de; `BB_FIX_PLAY_TIME=0` turns it off | installs on PC and Deck |
| Havok hit collector cap: after 65536 hits the writes go to a temporary per-thread array (theirs is 2048 and a shared skip flag, unsafe with several threads) | same place, `BB_HIT_COLLECTOR_CAP`, `BB_FIX_HIT_COLLECTOR=0` | installs |
| Reset of the invalid CharaId before saving | same place, `BB_FIX_CHARA_ID=0` | installs |
| Coarse light grid (`light_grid_opt`, overlay "Coarse light grid", `BB_LIGHT_GRID_OPT`) | same place, RenderView hook | Deck: no difference (58.7 vs 58.6–58.9 FPS); PC: no |
| Video skip: Enter/Esc on the keyboard or Options on the gamepad | `platform/avplayer/avplayer.cpp` (`bbgpu_video_skip`), `src/runtime_pad.c` | built, not checked on a video |
| DS4/DualSense touchpad when SDL does not see it (Linux, evdev), full controller reports, gamepad while another window has focus | `src/runtime_pad.c`, `gpu/shim/window.cpp`; `BB_EVDEV_TOUCHPAD=0` | built; there was no live DS4 |
| Horizontal mouse inversion (`mouse_invert_x`) | runtime, settings schema (Windows launcher), Linux launcher | built |
| The game's shader catalog and cache/recipe coverage | `tools/shader_catalog.py`, `docs/shader_recipes.md` | 8851 programs, recipes cover 626 |
| "Compiling shaders N / M" text at the bottom left while a background build, recipe import or in-game compilation is in progress | `gpu/shim/bbport_overlay.cpp`; `BB_SHADER_PROGRESS=0` | by the log (show/hide) on a cold cache |
| "Shaders (diagnostics)" section in the menu: the last 40 compilations, the hash is copied on press | `gpu/render/compile_log.h`, overlay; `BB_OVERLAY_OPEN=1` opens the menu at startup | the menu opens without a crash |
| BBSC 0.0.2, relay client (Linux), fallback P2P through the relay, `/message_area` limit (Panic 265), PvP/bosses, Teefpyre fixes | `gpu/bbnet20/…` (main module), `bbsc/core/bbport_bbsc_kit.*` | the module loads, the BBSC hooks install, the relay client makes contact; **a two-player game was not tested** |
| `online.py`: User-Agent, a 401/403 response = server is alive (previously a local BBSC server was started), duplicated port :20443, TCP check | `scripts/online.py` | syntax |
| Build without C++23 deducing this (GCC 13) | `gpu/gcn/isa.cpp` | built |

Not ported: the gyroscope (we do not pass a real gyroscope to the game), live `model_lod` (we already have it as a patch at launch), the bbhost server, their summon redirects to thehuntersdream.com, the old `bbnet` module.

## Update 2026-10-27: 10 new commits (25–27.10), performance and memory

- **"Zero-copy memory" (6f47735)** — not code but environment variables enabled by default:
  `BB_GUEST_GPU_MEMORY=1` (in their 0.6 base this is how our new memory model was turned on; for us it is already the only one), `BB_GUEST_MEMORY=host` (on AMD/Linux it forces host import instead of dma-buf; RADV host import does not accept memfd mmaps → for them this means a fallback to private regions or a failure), `BB_CHUNK_UPLOADS=1`,
  `BB_CHUNK_TEXTURES=1` (already enabled for us). Nothing to carry over.
- **Memory & VRAM presets (9582ce5, `extra/memoryDev`)**: the high/medium/low/apu presets = a set of our own knobs (`BB_VRAM_LIMIT_MB`, `BB_GC_BUDGET_MB`, `BB_GC_IDLE_SECONDS`, collector thresholds 50/65/80% instead of 70/85/95%) + "Auto Mip-Clamp".
  - Mip-clamp: the texture view's `baseMipLevel` goes 0→1, but the image is created and uploaded in full —
    **it does not save VRAM**, only slightly reduces reads when sampling; it changes sizes for shaders (textureSize/explicit LOD). Our `texture_quality=half/quarter` really does not allocate or upload mip 0.
  - "Player textures" are excluded by the addresses of the buffers into which the files `chr/c0000*`/`parts/` were read (DCX is unpacked into other memory — the addresses almost never match); the range list grows without being cleared, under a mutex on every view creation.
  - A more aggressive collector: we measured it — eviction and re-uploading cause stutters and an FPS drop.
  - The APU preset is 30 FPS, Performance upscaling, LOD 2, SSR/SSAO/DOF/bloom off, shadow distance 0.4.
  - Conclusion: nothing to carry over except the idea of a ready-made "weak hardware" preset in the launcher (built from our knobs).
- **Shadow distance (`shadow_distance`, old code 17–19.10, `bbport_engine_graphics.cpp`)**: a hook on
  `0xeac210` multiplies the 4 cascade distances (+0x38/+0x3c/+0x44/+0x48 of the block). This is the only real performance lever that we do not have: fewer objects in the shadow passes (GPU and draw thread). A candidate for porting, with measurement on the laptop/Deck.
- Everything else (FPS HUD, logs, F9, versions) has nothing to do with performance.
