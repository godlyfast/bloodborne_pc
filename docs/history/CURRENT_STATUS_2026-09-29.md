# Bloodborne on PC: actual state of the port and the upscaler

Snapshot as of **September 29, 2026**. Sources — files in `game_files`, the Git
history of `native_probe` up to `ac9fe90`, current uncommitted changes, saved
run logs and local tests. In this document, "present in code", "has been
launched" and "verified by image" are not considered the same thing.

## Short summary

This is a working experimental **native Linux port**, not a run through a full
emulator: the original x86-64 `CUSA03173/eboot.bin` executes on the PC CPU,
PS4 system calls are handled by a custom HLE runtime, and graphics are output
by a Vulkan core based on shadPS4. The game reaches the character scene,
accepts input, and works with sound and saves; this is confirmed by run logs,
screenshots and videos in the `native_probe` root. A full playthrough of the
game, all locations and the absence of crashes are **not confirmed** by these
materials.

**FSR 3.1 temporal upscaling genuinely works on the verified path with the
scene resolution set at startup**: the `logs.md` log shows `960×540 → 1920×1080`,
UI composition at 1920×1080 and a run on RX 7800 XT. The current preset
switching path without a restart remains problematic on this graphics card:
the latest `last_run.log` shows switching of the requested scene sizes, but an
FSR context of `1920×1080 → 1920×1080`. From the code, reduced targets are not
selected here when `D32S8` does not support blit. Therefore, the preset
switching log **does not prove a real reduction of 3D resolution or an FPS
gain**.

## Project layout and development

| Path | Role |
|---|---|
| `../CUSA03173/` | Local game files, `eboot.bin`, PS4 resources and modules. |
| `../np_base/` | Snapshot of the early port base; active development happens in `native_probe`. |
| `prepare.py`, `link_libc.py`, `link_modules.py`, `probe.c`, `runtime_*.c` | Executable image preparation, module linking, loader and HLE. |
| `gpu/` | Vulkan video core, shader recompiler, game-specific fixes, FSR and ImGui. The borrowed shadPS4 core is described in `gpu/VENDOR.txt`. |
| `patches/Bloodborne.xml`, `patches.py` | FPS and resolution patches applied to guest code at startup. |
| `bbport.ini`, `run.sh`, `build.sh` | Settings, full launch and build. |
| `out/`, `out/dev/`, `last_run.log`, `logs.md` | Built binaries and verification traces; some logs relate to earlier code versions. |

Development by Git: on September 25 the loader, HLE, graphics, sound and
CPU/GPU optimizations were added; on September 26 — frame analysis, camera
vectors, jitter, FSR 3.1, presets and the menu; on September 27 the last
commit `ac9fe90` fixed preset switching and mask display. After it, the
working tree contains uncommitted work on object vectors, reduced render
targets, scene/UI resolution separation, scripts and tests. This is the
**current working tree**, not a finished release. Older sections of
`README.md`, `docs/upscaler.md` and `docs/ROADMAP.md` describe different
stages and are partially outdated.

## What is implemented

### Launch and performance

- The guest `eboot` and some of the original PRX modules run together with
  implementations of memory, threads, files, time, controller, audio, saves
  and services. Networking works offline; PSN is not implemented.
- SDL3 handles the gamepad and fallback keyboard control. Sound is output
  through the host audio system; the code contains an `AudioOut` tempo fix
  and a save flag for sounds that were missing.
- The Vulkan renderer gained a separate command recording thread, draw
  preparation on four threads, texture and buffer caches, guest memory
  copying and a staging buffer pool. `docs/parallel_gpu.md` and
  `docs/ROADMAP.md` contain measurements in individual scenes; they cannot
  be transferred to all configurations.
- `BB_FPS=uncap` by default applies a patch with per-frame time simulation
  stepping; `30`, `60`, `90` are available. Output rate is limited by the
  monitor and a maximum of 120 FPS. For diagnostics there are
  `BB_FRAME_STATS=1`, `BB_TOGGLE_FILE` and frame structure capture via
  `BB_CAPTURE_TRIGGER`.

### Upscaler

- The game has no ready-made velocity buffer. The port computes camera
  vectors from depth and matrices of two frames; for scene geometry it does
  subpixel Halton jitter. Static-geometry reprojection was verified earlier
  (`docs/upscaler.md`).
- FSR 3.1 is integrated via `gpu/third_party/fsr-vulkan`. Native AA works
  1:1 on the scene HDR color before post-processing. The verified
  reduced-resolution mode uses a guest resolution patch, FSR after tone
  mapping and separate UI composition at 1920×1080. The UI patch in the
  current tree keeps its coordinates native. An explicit `BB_RENDER_RES=WxH`
  enables this path; for example, the `logs.md` log confirms `960x540`.
- Presets in the code: Native AA `1920×1080`, Quality `1280×720`, Balanced
  `1130×636`, Performance `960×540`, Ultra Performance `640×360` for
  1920×1080 output. The ImGui menu opens with `Insert` or `L3+R3`.
  `bbport.ini` saves FSR, preset, sharpness, jitter, reactive mask, debug
  mode, object vectors and the FPS counter. The current config contains
  `upscaler=fsr3`, `preset=4`, `jitter=1`, `reactive=1`,
  `object_motion=1`, `debug_view=0`.
- The reactive mask is formed by comparing color before and after the
  transparent passes. It is optional: earlier observations noted thin haze
  flickering when it is enabled. The default setting in the code is off,
  but it is enabled in the current `bbport.ini`.
- The working tree contains experimental animated-object vectors:
  previous vertex positions, an additional G-buffer target, draw matching
  between frames and a restriction to suitable pose/bone buffers.
  Changing `object_motion` requires a restart. According to
  `out/dev/motion-selective.log`, history in the selected draws is often
  found, with no capacity skips in the shown intervals. This is a draw
  metric, **not an assessment of pixel coverage or visual quality**.

## Current dynamic preset defect

In `vk_scene_resolution.cpp` the `SceneTargets::Eligible` function requires
`BlitSrc|BlitDst` on the format of each candidate. In `vk_rasterizer.cpp`
the reduced pass is disabled if the depth is unsuitable; the choice of the
reduced FSR input in `vk_temporal_upscaler.cpp` also depends on it. The saved
log for RX 7800 XT reports the absence of `blit` for `D32S8`. A fallback was
added later that **clears UI depth** instead of copying it, but it does not
remove the `blit` requirement for **3D scene** depth.

The result on this machine: the `last_run.log` of September 28 lists switches
of `640×360`, `1280×720`, `960×540` and other presets, yet the created FSR
context remained `1920×1080 → 1920×1080 (HDR scene color)`. The
`Scene resolution: raster ...` message reflects the requested size of the
proxy targets; it does not measure the actually used size of each draw. The
claims of `README_FIXES.md` and the menu hints about dynamic scaling working
on all GPUs are stronger than what the code and the latest log allow.
`logs.md` relates to an earlier run with automatic startup patch selection,
which was later changed in `run.sh`.

## Verifications and confidence limits

| Check | Result |
|---|---|
| Game run logs and frames from September 27–28 | Loading into the game scene and image output confirmed. No full playthrough test was performed. |
| `logs.md` on RX 7800 XT | Confirmed scene patch `960×540`, UI `1920×1080`, FSR context `960×540 → 1920×1080`. |
| `last_run.log` | The menu changed presets without a restart, but FSR was 1:1; no FPS statistics for this run. |
| `out/dev/motion-selective.log` | For one series of scenes with selective object vectors, intervals of roughly 72–100 FPS are visible, with no `capacity skips` in the given summaries; this is not a controlled preset comparison. |
| `out/gpu/motion-history-test` and `out/gpu/ui-composition-test` | Re-run on September 29: both `PASS`. |
| `nix-shell shell.nix --run 'python3 -m unittest -v test_patches'` | Re-run on September 29: 5 tests `OK`. |
| `out/dev/scene-validation.log` | The Vulkan reduced-targets test on Lavapipe **ended in an assertion** due to a Vulkan headers/dispatcher version mismatch. The log does not provide a fully successful verification of this path. |

Object vectors in the game and their effect on weapon and clothing trails
have not been visually confirmed by a systematic A/B test. Early measurements
of about 49 FPS with all draws versus 77–78 FPS without them, and about
81–87 FPS on a narrower selection, belong to different runs; this is a
guideline for further testing, not a guaranteed performance figure for the
current config. The screenshot `image_2026-09-28_00-44-14.png` shows a game
scene and an overlay at about 59 FPS, but does not disclose the measurement
conditions.

## What is not done yet / what to check next

1. Fix and confirm real reduced 3D rendering in dynamic mode on RX 7800 XT:
   check the actual size of color/depth attachments and the FSR input on each
   preset. If the path remains incompatible with `D32S8`, explicitly select
   the startup resolution patch and show the restart requirement in the menu.
2. After the fix, run the same game scene with Native AA, Quality and
   Performance: record FSR input/output, FPS, frame time, UI sharpness and
   the image in motion.
3. Visually compare object vectors on/off while running, turning the camera
   and in combat; check trails, history coverage and GPU cost.
4. Sort out the assertion in `scene-resolution-test`; the other tests do not
   replace the in-game Vulkan test. There is no frame generation, FSR 4,
   DLSS or XeSS in the current port — they are listed in `docs/ROADMAP.md`
   as plans.

## How to reproduce the verified path

From `game_files` on this configuration:

```bash
BB_RENDER_RES=960x540 BB_FRAME_STATS=1 bash native_probe/run.sh
```

`BB_RENDER_RES` selects the startup scene resolution patch, and the current
`patches.py` keeps UI at 1920×1080. Changing resolution this way requires a
new launch. Without `BB_RENDER_RES`, the experimental dynamic path described
above is enabled. The launch rebuilds the port and uses the local `CUSA03173`
files; the presence of sources and the binary by itself does not confirm
reproducibility on another PC.

## September 29 fix: live preset switching

There were two reasons why changing the preset in the menu did not change
the picture:

1. `SceneTargets` copied targets between native and reduced size only via
   `vkCmdBlitImage`, and RADV provides no blit for `D32S8`. Therefore scene
   depth was considered unsuitable and the reduced render was not enabled.
   Now, for depth/stencil formats without blit, copying is done by a
   full-screen draw (`host_shaders/depth_resample.frag`): depth is written
   via `gl_FragDepth`, stencil via `VK_EXT_shader_stencil_export`.
2. The reactive mask (`reactive=1`) sampled color at 1920×1080 and recreated
   the FSR context as 1920→1920, while the main pass immediately recreated
   it for the reduced input. The context was recreated every frame. Now the
   mask reads the reduced scene target.

Verified on RX 7800 XT (`out/dyn-res-test.log`): menu switches produce
`FSR 3 context 1280x720 / 1130x636 / 960x540 / 640x360 -> 1920x1080`,
one recreation per preset change, no crashes. FPS in this scene is about
54–56 on all presets, meaning the bottleneck here is not the 3D resolution.

## September 30: FSR 4 INT8 and performance

### FSR 4 (v07 INT8/DOT4)

- `vk_fsr4.cpp/.h`: FSR-Vulkan provider `ffxFsr4V07*` with a per-preset model
  (native, quality, balanced, performance, ultraperf), 1080 tier. Same inputs
  as FSR 3.1. In the menu "Upscaler → FSR 4 (INT8)", in ini `upscaler=fsr4`,
  env `BB_UPSCALER=fsr4`. If assets or GPU capabilities are missing, FSR 3.1
  is enabled automatically.
- Assets: `fetch_fsr4_assets.sh` downloads the set assembled by Q2RTX from
  the MIT-licensed FidelityFX SDK sources (`fsr4_shaders/`, in `.gitignore`,
  98 SHA-256 sums verified against manifests). `BB_FSR4_DIR` sets a different
  directory.
- Device: `shaderIntegerDotProduct` and `VK_KHR_compute_shader_derivatives`
  are enabled (`Instance::IsFsr4Int8Supported`).
- Verified on RX 7800 XT: quality/ultraperf models are created; a preset
  change freezes for ~6.5 s (compilation). User report: the picture is
  sharper than FSR 3.1, but there is heavy ghosting on the character and
  weapon. Vectors verified with the debug view, they are correct: the
  character gets object vectors. In the pre-pass SPIR-V, depth is selected
  by minimum (as in our code), vectors are treated as "previous − current".
  For A/B in the menu: "FSR 4: auto-exposure", "FSR 4: inverted jitter sign".

### Performance (perf, GPU command thread)

- `SceneTargets::Eligible` asked the driver for format properties on every
  draw: ~13–15% of the GPU thread time. Now there is a per-format cache.
- `ObjectMotion::Attach`, the color snapshot and the reactive mask called
  `Scheduler::CommandBuffer()`. This moved recording of the entire rest of
  the submit (almost the whole G-buffer) onto the GPU thread. Now they go
  through `Scheduler::Record`. Two direct calls remain at the end of the
  frame (`TemporalUpscaler::Run`, presenter).
- Result: GPU thread ~74% instead of ~94% of one core. In game scenes
  61–98 FPS versus 53–87 before the fixes (scenes do not match one-to-one,
  this is a guideline).

### DWARF-stack profile (perf, GPU command thread, 09.30)

- `Motion::IndexedRange` (index scan and hash for object vectors) took ~10%
  of the GPU thread. Added `Motion::IndexRangeCache`: the result is reused
  and fully re-verified every 32 frames. In game ~98% of ranges come from
  the cache (260 entries).
- `SceneTargets`: flat table of format properties and memory of the last
  eight targets; together with Attachment/Get/View/Eligible ~4% instead of ~7%.
- After this the GPU thread is busy with work without noticeable waits. The
  Vulkan recording thread ~40% work and ~57% waiting. The GPU (RX 7800 XT)
  is ~65% busy on average. The frame is limited by the GPU command thread.
  The main entries are the video core base costs: FindView ~5.6%,
  BindTextures ~5.6%, memmove ~4.6%, SmallGuestCopy ~3.5%,
  CachedImageDescEntry ~3.2%, BindBuffers/BindVertexBuffers ~3% each.
  The next step is moving these computations to worker threads (step 2 of
  parallel_gpu.md).

### FSR 4: ghosting on the character and weapon (09.30, re-verification)

Video `video_2026-09-30_03-43-12.mp4`: FSR 4, Ultra Performance (640×360 → 1920×1080).
A dark imprint remains behind the moving saw disc on the revealed background.
Verified:

- vector debug view (FSR 4): the character and weapon get object vectors;
- the index range cache does not go stale (0 changes on re-verifications);
- the jitter sequence matches the provider (Halton 2/3, ceil(8·ratio²) phases);
- A/B in one run with the post-09.29 optimizations disabled (bits 4096, 8192,
  1<<30): trails are identical in both phases, so this is not a regression
  from them. Incidentally: these optimizations together give 84.4 versus
  70.8 FPS while running (+19%).

The v07 model determines revealed background by color (depth is used only for
vector dilation), and at a 640×360 input it has too little information.
FSR 3.1 discards such history by depth, so it has fewer trails on Ultra
Performance.
