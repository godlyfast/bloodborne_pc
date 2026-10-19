# Flicker: the 20:44 video and internal capture

Recording `video_2026-10-17_20-44-16.mp4`: AV1, 2560×1080, 60 FPS, 64.8865 s.
Among 3890 decoded frames, two isolated bright flashes were found: frame 908 at
15.150016 s and frame 965 at 16.100009 s (zero-based). The sharp scene is shifted/cropped
into the upper-left quarter; the rest is bright and blurry. Following frames are normal.
FPS counter stays intact. Camera cuts at 13.55, 20.78, 29.60 and 37.32 s were inspected
separately and not classified as flicker.

Session `20261017_174326.log` identifies package
`/nix/store/vpj7ggb7gcwl1yc8g4niixwls1fc2kqm-bbport-0.1`.
Its GPU library's `.text` matches the 20:42 build after the semaphore-wait fix:
SHA256 `abfe97958a5b80061167942e7a2d462bddd69bac3ce6be95eb388484d02c6ffb`.
Packaging strips debug information, so whole files differ.

The same defect pattern reproduced on separate save copies:

| Run | Internal-frame sample | Isolated bright frames |
| --- | --- | --- |
| `flicker-fsr411-1`, FSR 4.1.1, 2560×1080 | 894 | `f665_final` |
| `flicker-fsr411-2`, FSR 4.1.1, 2560×1080 | 1225 | `f108_final`, `f434_final` |
| `flicker-off-1`, upscaler off, 2560×1080 | 1324 | `f294_final` |
| `flicker-off-native1080`, upscaler off, 1920×1080 | 1342 | No isolated bright flashes found |
| `flicker-off-no-halfres`, upscaler off, 2560×1080, half-resolution proxies disabled | 1339 | No isolated bright/dark flashes found |
| `flicker-off-startup`, upscaler off, 2560×1080, `BB_LIVE_RES=0` | 1342 | No isolated bright/dark flashes found |
| `flicker-fsr411-no-halfres`, FSR 4.1.1, 2560×1080 | 3239 | No isolated bright/dark flashes found; see change below |
| `flicker-fsr411-startup`, FSR 4.1.1, 2560×1080, `BB_LIVE_RES=0` | 1313 | Bright `f1177`, `f1293`; dark `f146`, `f160`, `f764` |
| `flicker-fsr411-startup-display-read`, after LOAD fix | 1251 | Bright `f734`, `f811`, `f1059`, `f1065`, `f1096`, `f1204` |
| `flicker-fsr411-startup-old-memory`, same fix, `BB_PC_MODEL=0` | 1319 | No isolated bright/dark flashes found |

Internal capture reads the prepared frame before `RecordPresent`. The defect reproduced
before final blit, desktop recording and video codec. With upscaling off, the game's HUD
also remains intact above the corrupted scene. FSR is not a necessary condition.
The 1920×1080 control warrants investigating resolution scaling; one clean launch is
insufficient to declare it the proven cause or fix.

In the last run, half-resolution proxies were disabled through capture 2194 inclusive,
then enabled in the same process via the diagnostic-toggle file. The remaining sample
also has no flashes, so this control **does not yet prove** half-resolution proxies are
responsible. Transition recorded in `halfres-enable-transition.json`.
Comparison used a physically smaller window; internal scene resolution remained
2560×1080. Capture count is sample size, not the number of all rendered frames.

The FSR 4.1.1 control **disproved disabling live_resolution as a workaround**:
the defect also occurs with startup resolution patching. Live scaling and half-resolution
proxies are therefore not necessary conditions for every case found.
`live_resolution=0` cannot be recommended as a fix. Dark frame `f146` retains the
upper-left quarter of the scene and game HUD; the rest is black. Internal capture
reproduced the original report's symptoms, including this variant. User setting unchanged.

The semaphore-wait mask error is fixed but did not eliminate this defect.
The earlier pass producing it is not identified. Scene offset, target sizes,
intermediate textures and command state need comparison.
This analysis also does not explain FPS regression or face corruption.

## Vulkan synchronization validation

`flicker-validation` uses `BB_VK_VALIDATION=1` and `BB_VK_VALIDATION_SYNC=1`,
Khronos layer 1.4.357.0. Already in the menu, `SYNC-HAZARD-READ-AFTER-WRITE`
is confirmed: `vkCmdBeginRendering` reads a redirected output target through
`loadOp=LOAD`, but the post-layout-change barrier permits only
`COLOR_ATTACHMENT_WRITE`. The message repeats for three output targets.

`COLOR_ATTACHMENT_READ` was added to `dstAccessMask` in `TemporalUpscaler::RedirectColor`.
This follows [Vulkan's LOAD semantics](https://docs.vulkan.org/refpages/latest/refpages/source/VkAttachmentLoadOp.html).
It fixes a specific confirmed API error; whether isolated corrupted frames disappear
is checked separately. Pre-change source:
`out/dev/flicker-video-20261017/vk_temporal_upscaler.before.cpp`.

Repeat run `flicker-validation-display-read` completed its game control without
`SYNC-HAZARD`: the original message disappeared. Other validator errors below remain,
so this is not clean validation of the entire renderer.
An ordinary control without validation reproduced flashes again (6 bright frames
in a sample of 1251). The LOAD fix **did not eliminate flicker**.
It is built into the main AppImage, SHA256
`485e5d705e79669bb2f6a1fbb65d1254ea45175150d177e4d5d38256fd62ac60`.
Previous build: `Bloodborne-bbport-x86_64-before-display-read.AppImage`.

The validator also reports input-component-limit violations in some fragment shaders
and incompatible storage usage of some sRGB views. Not changed in this fix;
neither is independently proven to cause flicker.

Materials: `out/dev/flicker-video-20261017/` (contact sheet, neighboring frames,
FFmpeg statistics, reproduction JSON and PNG). Script: `out/dev/flicker-laurence.py`;
data: `out/dev/laurence-compare/flicker-*`.
User saves and settings unchanged. Capture rate is script-limited; absence of a flash
from the sample alone does not prove absence from all rendered frames.
After analysis ordinary RAW frames were deleted: anomalies with two neighbors on
each side, first/last frames and every 200th frame were retained. JSON counts were
made before deletion; reanalysis of remaining files will not reproduce the original
sample. User video retained in full.
