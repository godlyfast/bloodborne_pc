# TAA and temporal upscaler input review — 2026-10-01

## Project state

bbport is a specialized Linux runtime for the original x86-64 Bloodborne
CUSA03173 1.09 code with GPU command translation to Vulkan based on shadPS4. This is an experimental
port: the loader, system call HLE, sound, input, saves, the in-game settings UI,
and temporal upscaling are already implemented. This working copy contains the sources, a built
library, a game dump, and a save. The project has no git metadata, so the change
history and working-tree cleanliness cannot be verified.

A full playthrough and portability to other drivers and the Steam Deck are not confirmed
by this review. The documentation still lists limitations: artificial occlusion queries,
incomplete predication, transparent effects without their own motion vectors, and races
in the FSR 4.1.1 model for some non-standard output sizes.

## Videos and causes

The source recording `video_2026-10-01_21-21-02.mp4`: 94.89 s, 2560×1080, 60 FPS.
It switches between TAA, FSR 4.1.1, FSR 4, and FSR 3.1. Temporal instability is visible
on architecture, thin outlines, and moving weapons. In-game motion blur is enabled in the menu;
its contribution cannot be attributed to TAA. The `video_fixed_taa.mp4` file has the same duration
but a different frame size (2560×1082); this recording by itself does not confirm a renderer fix.
Frames and sequences for review are in `out/dev/temporal-review/`.

Errors were found in the code, independently of the subjective assessment of the video:

1. **FP16 depth in TAA history.** The half step near 1 is about 0.000488.
   With near ≈ 0.05, distant surfaces become indistinguishable. The history check
   threshold was smaller than this step, so history could both be wrongly discarded
   and blended with another surface. History is now RGBA32F.
2. **Mismatched cameras.** The old check compared the previous frame's depth with the current
   frame's depth. Now the current point is transformed into the previous camera's frame,
   and the comparison is performed against the expected depth there. The tolerance scales
   with perspective depth.
3. **Zeroing of distant vectors.** `depth >= 0.99999` was treated as sky and given zero
   motion. For a projection with near ≈ 0.05, far 3000, this threshold affects geometry from about
   1875 units. Now only clear depth 1 is treated as infinite background; the background gets
   camera rotation motion without translation. Distant geometry gets regular reprojection.
4. **FP16 depth in object motion.** In RGBA16F, the depth used for the check of whether the vector
   is occluded by a later draw was lost. The buffer and the graphics pipeline format are now
   RGBA32F; the depth check no longer accepts another distant surface with a wide
   fixed tolerance. The final vectors for FSR remain RG16F.
5. **Mixed-depth check at edges.** TAA interpolated history depth between
   different surfaces. Now the four bilinear taps are checked independently, color is gathered
   only from consistent taps; with partial coverage the history weight is reduced.
6. **Too-weak accumulation at distance.** The previous depth-adaptive weight reduction to 0.8/0.5
   is replaced by a weight of 0.98…0.85 depending on motion when history is valid (the lower
   weight is reached at 8 px/frame). A diagnostic run with weight 0.94 showed
   residual color oscillation between jitter phases even with accepted history. History RGB
   is clamped to the current frame's neighborhood range.
7. **Depth jitter on slopes and thin details.** Depth is now carried to a
   stable pixel position along the local one-sided gradient, with protection against
   surface discontinuities. For motion/depth, the nearest surface in 3×3 is selected;
   color and the clipping range are taken around the original color pixel. This lets
   thin outlines keep history when foreground/background alternate under jitter.
8. **Unstable history addressing at near-zero motion — the main cause of the
   detected TAA shimmering.** Previously, the integer and fractional parts of the bilinear
   coordinate were computed after adding a large pixel number to a very small motion.
   On the GPU this produced inconsistent parts and selection of a neighboring texel. Now the motion
   itself is split first: `base = p + ivec2(floor(motion))`,
   `fraction = motion - floor(motion)`. A regression check at pixel x=2010
   with motion around −0.00003 px reproduces the old formula's error:
   color 0.250000 instead of the expected 0.739985. The fixed formula passes the check.

Fixes 3–4 concern the common inputs of TAA/FSR 3.1/FSR 4/FSR 4.1.1. AMD's algorithms and
ML assets were not changed. The shader/pipeline ABI check and the diagnostic object
motion dump were updated together with the resource format.

## Checks and limitations

`bbgpu`, `taa-shader-test`, `camera-motion-test` built via `shell.nix`.
18 cases of the production TAA shader passed on a Vulkan GPU: reset with NaN, unjitter, accumulation,
clipping, surface disocclusion, off-screen exit, NaN history, exact far depth,
rejection of another far surface, camera translation, edge with partially valid history,
sky and the sky/geometry boundary, sloped depth with both jitter signs, thin outline,
persistence reduction under motion, and very small negative motion at a large coordinate.
6 checks of the production camera-motion shader passed:
distant geometry, sky rotation, absence of sky translation, jitter exclusion,
valid and stale object vector. Log: `out/dev/temporal-review/tests.log`.
Additional unjitter check: `out/dev/temporal-review/taa-final-tests.log`.
Reproduction of the old formula regression and 18 successful checks of the new one:
`out/dev/temporal-review/regression-proof.log`.
Final in-game check: `out/dev/temporal-review/subpixel-validation.log`.
All 64 existing Python tests passed (`out/dev/temporal-review/python-tests.log`).

Live smoke: a save copy loaded in the Hunter's Dream. In a single process,
TAA → Off → FSR 3.1 → FSR 4 v07 → FSR 4.1.1 → TAA were verified, output 2560×1440,
six final frames per mode and camera movement between switches.
FSR runs with 1706×960 input; TAA with native 2560×1440. AMD contexts
are confirmed by the log; no substitution with FSR 3.1 occurred. The process exited normally;
after pipeline compilation it held the 60 FPS limit. Logs and raw frames:
`out/dev/temporal-review/subpixel-validation.log`, `out/dev/temporal-review/far-refined/`.
In-game motion blur and AA are disabled in the test configuration.

With a static camera on the distant tower section (x=2010…2099, y=400…779),
the mean absolute RGB change between six TAA frames dropped from 1.892 to
0.299 on the 0…255 scale, about 6.3×. After returning to TAA — 0.279.
In the final run, FSR 3.1: 0.328, FSR 4: 0.278, FSR 4.1.1: 0.364.
This is a result for the selected scene, not a universal quality assessment: FSR input
resolution differs from TAA, and the before/after here compares specifically the last
history-addressing fix. Data: `out/dev/temporal-review/far-refined/stability.json`;
previous run: `out/dev/temporal-review/final-validation.log`.

For diagnostics, `BB_TAA_DIAGNOSTICS=1` was added: the TAA output alpha contains the accepted
history weight instead of 1. It can be read in the `BB_DUMP_TRIGGER` raw RGBA16F. RGB is unchanged;
history alpha still contains depth. Normal mode keeps opaque output.
Additional modes 2 and 3 output the current color or the clamped history;
the diagnostic history image allows comparing a direct read with reprojection.
These comparisons revealed the addressing error even with accepted history and near-zero motion.

The sources and `out/gpu/libbbgpu.so` are updated.
`dist/Bloodborne-bbport-x86_64.AppImage` (832 MiB) was rebuilt; the packaged `--vulkan-info`
successfully detected the RX 7800 XT via RADV. Logs: `appimage-build.log` and
`appimage-vulkan.log` in `out/dev/temporal-review/`. The full game run above
was done with the local library; a separate full game run of the AppImage was not performed.

These tests confirm the specific fixes but do not prove the disappearance of all
flickering in the game. Object motion from vertex history, transparency, animated
materials, LOD selection, and sub-pixel geometry under heavy resolution downscaling
still require checks in separate scenes.

The cost of full precision: two TAA histories occupy 253 MiB instead of 127 MiB at 4K;
object motion — 127 MiB instead of 63 MiB at 4K render. This also increases
memory bandwidth consumption. A possible next optimization is a separate R32F depth
while keeping color and motion in FP16, with the same correctness tests.

For regressions:

```sh
nix-shell shell.nix --run 'ninja -C out/gpu taa-shader-test camera-motion-test && out/gpu/taa-shader-test && out/gpu/camera-motion-test'
```

The motion-for-all-input-pixels approach is consistent with the recommendations of
[AMD FSR 3.1 integration](https://gpuopen.com/presentations/2024/FidelityFX_Super_Resolution_3-1_Release-Overview_and_Integration.pdf).
