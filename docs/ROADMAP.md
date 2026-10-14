# Bloodborne native port: what is done and what is next

The main text is as of 2026-09-26; below, the first section covers what changed by 30.09.
The most detailed snapshot: [CURRENT_STATUS_2026-09-29.md](history/CURRENT_STATUS_2026-09-29.md).
Report on the work of 30.09–01.10 (GPU pipeline, upscaler, crash, launcher, AppImage):
[SESSION_2026-09-30.md](history/SESSION_2026-09-30.md).
Details on individual topics:
[parallel_gpu.md](parallel_gpu.md) (GPU multithreading, hitches during streaming),
[upscaler.md](upscaler.md) (analysis of the game's frame, scene constants).

## Update 30.09

- Done after 26.09: FSR 4 INT8 (v07), object motion vectors, preset switching without
  restart (downscaled scene targets; D32S8 depth copied by a shader), LTO and PGO,
  scaling draw preparation to the number of threads (Steam Deck too).
- Problems from the "Known problems" section below: item 3 (restart on preset change)
  solved; item 1 (object vectors) implemented, FSR 4 still has ghosting on the character at
  Ultra Performance; item 2 (blurry interface) — the UI is drawn at 1920×1080.
- Limitation: downscaled scene rendering (`SceneTargets::Eligible`) requires a 1920×1080 target,
  i.e. works only with 1080p output.
- Parallelizing the GPU-command thread (step 2 of [parallel_gpu.md](parallel_gpu.md)): textures on
  a separate thread in parallel with buffers work correctly but give no gain —
  each draw's data moves between cores. The bottleneck is the GPU-command thread: 91% on CPU,
  ~9% waiting for small guest-memory copies before fences. Next — a two-stage pipeline
  (a second thread owns the texture cache and draw recording, register copy from the scanner's
  deltas) or memoizing texture bindings between frames; see "What would scale" in parallel_gpu.md.
- **Two-stage draw pipeline** (`vk_draw_pipe.h`): the GPU-command thread decodes PM4 and
  selects the pipeline, a second thread (`bb:DrawRec`) with its own register copy binds resources
  and records the draw. +19% FPS on 16 threads, +18% on 8 (like Steam Deck). Enabled by default
  with 8+ threads (`BB_DRAW_PIPE=0/1`). The bottleneck is now the second stage; details and plan
  are in parallel_gpu.md.
- Presets and GPU load: the scene on RX 7800 XT costs little, so a preset changes GPU
  time only by ~0.5 ms, and FSR 4 itself at 1080p output — ~1.4 ms (FSR 4 Ultra Performance is
  more expensive than native rendering without an upscaler). Fixed: lighting passes remained at
  1920×1080 at any preset (the check looked at the wrong target slots); downscaled targets are now
  sampled directly, without resampling to native (the shader cache is rebuilt once). Next for
  Steam Deck — the guest copy of render-target memory `3d5ebf4e` (see parallel_gpu.md).
- **Fixed a crash with the pipeline** (guest heap corruption, guest offset `0x263b8e7`, after
  13–17 minutes): the "GPU idle" interrupt left before the EOP timestamps deferred to the Vulkan
  recording thread, and the game freed objects with those timestamps. Now the pipeline and the
  deferred timestamps wait before it; 2 runs of 30 minutes without crashes (before the fix — 7
  out of 7 crashes).
- **1440p/2160p output resolution** ("Output resolution" menu, bbport.ini `output_res`, after a
  restart): the scene is drawn at the preset resolution relative to the output, the upscaler
  (FSR 3 or FSR 4) finishes the frame, the interface is rasterized at the output resolution.
  The game's effects (aberration, DoF, blur, SSAO, in-game AA, dynamic shadows, SSR, splash
  screens, LOD) — there too.
- **Launcher** (`launcher/bb-launcher.sh`, GTK4/libadwaita) and **AppImage** for Steam Deck
  (`bash packaging/appimage.sh` → `dist/`; data in `~/.local/share/bbport`, `--play` —
  launch without the launcher window).
- Tools: `BB_PAD_FILE` (scripted gamepad input), `ab.sh` (A/B of `BB_TOGGLE_FILE` bits in a
  running game), in `Frame stats` — idle time and GPU-thread locks.

## How the port works

- The original eboot (CUSA03173 v01.09) executes directly on x86-64. The PS4 system libraries
  are replaced by our own HLE runtime in C (`runtime_*.c`, `probe.c`).
- Graphics: the shadPS4 video core and shader recompiler (GPL), built into `libbbgpu.so`
  (`gpu/`), with our own modifications. The shadPS4 emulator as a whole is not used.
- Game patches (FPS, resolution, etc.) are community XML (`patches/Bloodborne.xml`),
  compiled by `patches.py` and applied by the loader at startup.

## Done

### Performance and smoothness

| What | Result |
|---|---|
| Vulkan command recording in a separate thread, texture/buffer caches, rwlock instead of a mutex | 26 → 64 FPS in one scene |
| Draw-call preparation on 4 threads (`bb:DrawPrep`), verification on the GPU thread | +11.5% |
| 256 KiB protection-removal window when the game writes to memory (fewer page faults) | +22% |
| Texture description cache, fast path for the same render target | up to ~94 FPS outdoors |
| Guest-memory copies on a thread pool, staging-buffer pool | streaming hitches 60–170 ms → 40–50 ms |
| Waiting for copies before game-visible fences | removed interface flicker |
| "Readbacks Relaxed" mode | no "vertex explosions" (FaceGen) |
| Vblank 480 Hz + frame limit to min(monitor, 120), output right on flip | even frame delivery; running does not slow down above 120 FPS |

Everything is toggled during play via `BB_TOGGLE_FILE` (bitmask) for A/B comparisons.
Statistics: `BB_FRAME_STATS=1`.

### Sound, input

- Sound output with the correct pacing (previously clicks every 10.7 ms).
- Gamepad via SDL3, fallback keyboard layout.

### Frame analysis

- `BB_CAPTURE_TRIGGER=<file>` records one frame: passes, targets, shaders, textures,
  constants, blend modes.
- The structure of the Bloodborne frame has been analyzed (G-buffer, lighting, scene color
  RGBA16F, fog, post-processing, tonemapping, in-game AA, interface) and the 864-byte scene
  constants (view and projection matrices).

### Temporal upscaler (FSR 3.1)

- **Camera motion vectors**: from scene depth and the current and previous frame matrices
  (`vk_camera_motion.cpp`, `camera_motion.comp`). Verified by reprojecting the previous
  frame: static geometry matches.
- **Jitter**: subpixel shift of scene geometry via the viewport, Halton(2,3) sequence;
  number of phases 8·(output/render)². Interface and post-processing are not shifted.
- **FSR 3.1** (FireBurn/FSR-Vulkan, native Vulkan, submodule `gpu/third_party/fsr-vulkan`):
  - *Native AA*: on the scene's HDR color before post-processing, 1:1.
  - *Quality/Balanced/Performance/Ultra Performance presets* (x1.5/1.7/2/3): the game renders at
    a reduced resolution (a resolution patch that `patches.py` derives from the community 720p
    patch), FSR upscales the finished frame to 1920x1080 before the first interface pass.
    The interface and the output pass are redirected to full-size images, and the presenter
    shows them instead of the game's buffer.
- **Reactivity mask** (a snapshot of the scene before transparent draws, comparison before fog
  application): works, but on Bloodborne's haze it causes shimmer — off by default.
- **In-game menu** (Dear ImGui, Insert or L3+R3): upscaler, preset, sharpness,
  jitter, mask, FPS counter. Settings in `bbport.ini`. Preset change — the
  "Apply and restart game" button.

## Known problems

State of the last commit. In the working tree, moving presets to downscaled render targets while
keeping guest buffers, post-processing and UI at 1920×1080 has been prepared. Transitions
between presets and color/depth/stencil copying passed a Vulkan test on Lavapipe.
RX 7800 XT does not support blit D32S8, so the new path left the FSR input at 1920×1080
and reduced FPS. For such GPUs, startup now automatically selects the proven path with the game
resolution patch and 1920×1080 UI; a preset change again requires a restart. On GPUs with the
needed support, switching without a restart remains. Items 2–3 below relate to the last
commit, before these working-tree changes.

A common object motion-vector pass was too expensive: Performance gave about
49 FPS with it and 77–78 FPS without it. Now the extra target and shaders are enabled only
for G-buffer draws with a pose/bone buffer; the rest use camera vectors.
In a trial run, the selective path held about 81–87 FPS, without drops from history
capacity. Object vectors are on by default; `BB_OBJECT_MOTION=0` disables them, and
`BB_OBJECT_MOTION_ALL=1` restores the old common path for comparison. Selection by buffer
size is heuristic for now: the quality of weapon and clothing in motion needs in-game
verification.

1. **Moving objects "fall apart"** (weapon on the back, the character, cloth, enemies): there
   are only camera motion vectors. The third-person camera follows the character, so
   camera vectors are wrong for it, and the upscaler takes history from the wrong place. This
   concerns any temporal upscaler (FSR 3/4, DLSS, XeSS).
2. **Blurry interface in presets**: with the resolution patch the game considers itself a
   540p game and, apparently, prepares fonts and interface elements for this resolution. Menus
   (title, pause) do not go through the upscaler at all.
3. **Preset change requires a restart**: the resolution is set by a code patch at startup, and
   the game allocates buffers once.

## Plan

### 1. Object motion vectors

Needed by all upscalers and frame generation. The game does not compute them, so we compute
them ourselves.

How:
- For each draw into the G-buffer (passes with 5+ targets) the recompiler makes a second variant
  of the vertex shader that outputs the position twice: with the current constants and with the
  previous frame's constants. The difference of the projections is the motion vector, written to
  an auxiliary RG16F target as an additional pixel-shader output.
- Previous frame constants: for each draw we remember the contents of the constant buffers
  (object matrix, skeleton bones) by the key "shader + draw number in the pass" or by data
  address. We need to find out how the game stores skeleton matrices: in buffers overwritten
  every frame (then we copy the previous version), or in a ring buffer (then the previous frame's
  address is enough).
- Where the object is not found (first frame, new object) — camera vectors, as now.
- Check: debug vector view (`BB_DEBUG_MOTION`), reprojection of the previous frame with full
  vectors, visually — the saw on the back while running.

### 2. Renderer-level scaling (instead of the resolution patch)

The game runs at 1920x1080 (or the monitor resolution), and only the 3D-scene passes are drawn
at the reduced resolution. The interface and menus stay sharp, the preset changes on the fly.

How:
- The texture cache allocates a downscaled copy for scene targets (G-buffer, depth, lighting,
  scene color, effects); guest memory and the game's descriptors do not change.
- Viewport and scissor of passes into these targets are scaled (as already done for the
  interface, including passes with scissoring disabled).
- Shaders that compute from pixel coordinates (`gl_FragCoord`, `texelFetch`,
  compute shaders by pixels) get the scale factor via the recompiler's push constants.
  Samples by normalized coordinates work unchanged.
- FSR is placed where Native AA is: scene color before post-processing (HDR, best
  quality); post-processing and the interface run at full resolution.
- Risks: passes reading scene targets by pixel coordinates in post-processing, and
  reads from guest memory of these targets (they must be forbidden or scaled back).

### 3. Other upscalers

All use the same inputs (color, depth, motion vectors, jitter, masks).

- **FSR 4 (INT8)**: FSR-Vulkan has an experimental FSR 4 v07 INT8 provider — add it
  as a menu variant and compare with FSR 3.1 after step 1.
- **DLSS**: native Linux Vulkan SDK (NGX). Does not work on RX 7800 XT, but needed for
  NVIDIA users.
- **XeSS / XeFG and OptiScaler**: Intel ships them only as Windows DLLs. Options:
  a Windows DLL (PE) loader inside the process, or running the whole build under Proton with
  OptiScaler, to which we hand the inputs through the DLSS interface.
  Checked 29.09: libxess.dll (identical in DOOM: The Dark Ages, PRAGMATA and others) has a
  Vulkan path (`xessVKCreateContext`, `xessVKExecute`), but imports ~300 functions:
  MSVCP140 (iostream), VCRUNTIME140 (C++ exceptions), UCRT, kernel32, setupapi, dxgi.
  Decided to postpone; the most realistic path is a helper under Wine with shared Vulkan memory.

### 4. Frame generation

- FSR 3.1 Frame Generation (present in FSR-Vulkan): an intermediate frame between two finished
  ones, using the same motion vectors; the interface must be drawn on top separately (there is
  interface redirection — it can be rendered into a separate layer).
- XeFG — after the Windows DLL decision (see above).
- Requirement: frame delivery through the presenter (queue and VRR already work).

### 5. Miscellaneous

- Steam Deck: portable build (patchelf, no Nix), checking presets at 1280x800.
- Further offloading of the GPU thread (step 2 of [parallel_gpu.md](parallel_gpu.md)).
