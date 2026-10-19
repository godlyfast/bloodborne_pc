# Single black and grey frames: waiting for image readiness

The user observes isolated entirely grey or partly black frames in the game and menus.
Update after the 20:44 video: internal capture reproduced the same defect with FSR 4.1.1
and with the upscaler off after this fix. It did not eliminate the flicker;
see `Flicker_video_2026-10-17.md`.

## Error found

`Presenter::Present` adds waits in this order: swapchain image acquisition, then readiness
of the prepared frame. `Scheduler::QueueSubmit` assigned `ColorAttachmentOutput` to the
second wait. However, `Presenter::RecordPresent` reads the prepared frame via `blitImage`
at the Transfer stage; diagnostic copies also use Transfer. The previous wait did not
cover that stage, allowing the image to be read before its preparation finished.

According to [Vulkan VkSubmitInfo](https://docs.vulkan.org/refpages/latest/refpages/source/VkSubmitInfo.html),
`pWaitDstStageMask` limits the stages at which the semaphore wait applies.
Submission order alone does not replace the required dependency.

All four wait positions in `gpu/render/scheduler.cpp` now use `AllCommands`.
The first, third and fourth already used that mask; only the second changed.
This fix affects general frame presentation regardless of upscaler choice.

## Checks and limits

- GPU library built successfully.
- 131 Python tests and native `settings-test` and `cp-decoder-test` pass.
- `scene-resolution-test` passes on RX 7800 XT with packaged RADV 26.2.3:
  color, depth and stencil reads at several resolutions, including repeated changes
  and mip proxies.
- Initial graphics-test attempts with system drivers did not start: system Mesa/LLVM
  requires GLIBC_2.44; the build environment uses 2.42. The packaged driver is compatible;
  this is not a flicker-test result.

The running user's game, settings and saves were not changed. The new library will enter
the game on the next launch of the updated AppImage. Elimination of flicker and the fix's
FPS impact have not yet been measured. Performance regression and face corruption after
bes → deadinside remain separate unresolved questions.

Logs and pre-change source: `out/dev/present-wait-20261017/`.
Previous build: `dist/Bloodborne-bbport-x86_64-before-present-wait.AppImage`.
