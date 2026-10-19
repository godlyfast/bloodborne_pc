# Laurence's cinematic: video, 2026-10-17

Recording: `video_2026-10-17_07-33-43.mp4`, AV1, 2560x1080, SAR 1:1, 60 FPS,
48.9265 seconds. This analyzes visual symptoms; the original allocation error 9
is not yet confirmed fixed.

Frames and contact sheet: `out/dev/cutscene-video/`.

- At 5 seconds the game frame is normal and full-width.
- At about 8 seconds the transition/fade begins.
- At 12–16 seconds large stretched triangles appear; at 15 seconds geometry covers
  the entire picture. Real geometry corruption, not compression blocks or ordinary
  FSR blur.
- From 20 seconds the scene is readable again. Frames at 28 and 42 seconds show
  Laurence, not a process crash. The cinematic continues at the recording's end;
  the video does not prove completion.
- During the cinematic the central region is about 1920x1080, with 320 black pixels
  on either side. Side bars alone do not prove distorted proportions.

Latest log `~/.local/share/bbport/logs/20261017_043323.log` matches launch time and
includes the enabled FX initialization context race fix. The loading PM4/23 crash
and this geometry-preparation issue are different paths.

In the log:

1. Line 10: FPS uncap, `Model LOD -2 (Highest)` enabled.
2. Line 257: camera aspect 2.370, output 2560x1080.
3. Lines 537–624: resource allocation failures and job-slot returns with error=9,
   counter exceeds 4096. Printed bytes=0 cannot be treated as a proven zero-size
   request: JobProbeWord does not read stack/image through the runtime memory map.
4. Lines 625–642: SRT walker reads absent tables at 0x0, 0x4 and other low addresses,
   returning zero for inaccessible values.
5. Then vertex-attribute warnings with format=0; inaccessible SRT reads reach at least 65536.

This sequence is consistent with missing geometry data/descriptors after resource
preparation failed. The complete causal chain is not yet proven. Null-descriptor
protection and returning leaked slots let the game continue; they do not create missing
geometry. Geometry cannot be declared fixed merely because SIGSEGV no longer occurs.

High FPS and forced highest LOD are control-run parameters, not proven causes.
Separate comparisons with 30 FPS and normal LOD are needed.
An earlier user confirmation in the project says a 30-FPS limit eliminated this
cinematic's hang; absence of today's artifacts with it is not yet checked.

For visual "squeezing" there is a testable hypothesis: InstallCameraAspectHooks always
replaces the active camera aspect with output aspect. If a cinematic camera receives
2560/1080 and the game then displays it in a central 1920/1080 region, horizontal
compression is (16/9)/(64/27)=0.75. Establishing this in a specific frame needs camera
parameters and viewport reads; the video alone does not prove it.
A 1920x1080/16:9 control separates this from geometry corruption. Disabling the
ultrawide hook for the whole game is not a final solution without identifying cinematic mode.

## Control runs and fixes

`out/dev/compare-laurence.py` uses a save copy before Laurence, separate settings,
and identical forward movement. Test writes do not alter user saves.
Per-case logs/images: `out/dev/laurence-compare/<name>/`.
fps is the actual game-pacer limit, not the post-VSync counter. Original video:
limit 480, monitor showed 100.

| Run | Cinematic-start result |
| --- | --- |
| `baseline-30-high`, 30 FPS, LOD -2 | No allocation error 9 or inaccessible SRT reads; output stays 16:9 |
| `baseline-100-high-1`, 100 FPS, LOD -2 | No allocation error 9 or inaccessible SRT reads; output stays 16:9 |
| `baseline-480-high`, 480 FPS, LOD -2 | Reproduced error 9, exploding vertices and inaccessible SRT reads |
| `baseline-480-normal`, 480 FPS, LOD 0 | Same: normal LOD does not eliminate failure |
| `fixed-480-large-heaps`, general Increased Graphics Heap Sizes + DMEM 9152 | Same: overall budget does not change the required separate heap |
| `fixed-480-high`, output fixed, 160-MiB cache | Proportions fixed; resource failures remain |
| `fixed-480-cache320`, separate 320-MiB cache | Fewer failures but still present, including 4-MiB requests; candidate rejected |
| `fixed-480-cache512`, separate 512-MiB cache | Until window closure: no error 9, SRT faults or Bad PM4; 21:9 output |
| `appimage-final-480`, new AppImage, 480 FPS, LOD -2 | Until window closure after 45s image: no error 9, SRT faults or Bad PM4; 21:9 output |

Two independent fixes implemented.

**Output without HUD.** Native camera accessor and `bbgpu_frame_aspect` read through
`/proc/<pid>/mem`, without calling code inside the game. In baseline-480-high camera
aspect is 2.370370, displayed frame 1.777778. In fixed-480-high both are 2.370370;
FOV/near/far match. The camera already showed a wide view, but absence of a
Scaleform/HUD pass left the native 16:9 display buffer.
`TemporalUpscaler::OnDisplayPassStart` now finishes the ready LDR scene at output
size before resetting camera and depth. Normal UI-frame path preserved.
With upscaler off/failed, the finished scene is copied.
`BB_SCENE_WITHOUT_UI=0` restores old behavior for comparison.

**Resource cache.** JobProbeWord diagnostics fixed: stack locals and image vtables
read via safe process_vm_readv; heap+0xd0 labeled reported_free.
Actual 18–41-KB requests and allocate_fn=0x216af40 are now confirmed.
Native heap 0x10282a2060, capacity 160 MiB, retained only tens of KB after collection,
with largest free span smaller than the request. This is a separate backing allocation
from creation parameters +0x54, read both before allocation and before range setup
at 0x26a9b50. A checked-code hook at 0x216b20e increases this exact parameter from
160 to 512 MiB before both reads. Other original sizes unchanged.
`BB_RENDER_RESOURCE_CACHE_MB=160` disables enlargement for control;
allowed range 160–512 MiB. Lowering FPS is not the implemented fix.

After peak loading with a 512-MiB cache, 283–387 live ranges and about 489–500 million
free bytes were observed. This confirms release after the peak in the tested section,
not a long-term leak test.

Build/checks passed: ui-composition-test, fx-init-clear-test, cp-decoder-test,
srt-walker-fault-test (517 deliberately triggered and handled SIGSEGV).
Log: `out/dev/laurence-final-build-tests.log`. AppImage rebuilt:
`dist/Bloodborne-bbport-x86_64.AppImage`, log `out/dev/laurence-appimage-build.log`.
Full completion confirmed in `appimage-final-fsr411`: AppImage, FSR 4.1.1,
pacer limit 480 FPS, LOD -2, 2560x1080. Observed 115 seconds after load, without
allocation error 9, inaccessible SRT, Bad PM4 or host faults. `90s.png` already shows
the Laurence fight and health bar; `105s.png` confirms continued operation.
Test terminated its own process after the observation period.
Initially FSR reports the common FSR 3.1 backend available, then confirms actual
`FSR 4.1.1 replay, INT8 t2160_m0 output 2560x1080`.

Final run's `*.state.json` records cache capacity 536870912 bytes, hundreds of live
ranges after loading, hundreds of MiB free, and matching camera/display aspect
2.370370. `60s.png` is fullscreen 2560x1080 without side bars.
The user confirmed earlier `Window: closed (close button)` endings were manual closures,
not cinematic failures.

Frame-toggle comparison: `docs/Laurence_compare.html` (self-contained HTML,
embedded images). AppImage built 2026-10-17 14:29:35 MSK, 613206560 bytes.
This validates Laurence's cinematic on RX 7800 XT, not the separate NVIDIA
AppImage-startup driver failure.
