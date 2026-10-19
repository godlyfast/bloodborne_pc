# White scene after changing saves — 2026-10-17

**Evening update, 17 October:** colored blocks without Bloom also reproduced on first load.
A separate partial-live-SSR-patch regression was found; the complete startup patch gives
a normal scene with Bloom enabled too. See `SSR_corrupt_load_2026-10-17.md`.
Original observations follow; the cache-coherency defect found did not by itself prove
the cause of the white image.

The user loaded a save, exited and loaded another in the same process.
On the second save the scene is almost entirely white; HUD visible.

## Observations

- Process 160872, log `20261017_124103.log`. Validation not loaded.
- First section ran at about 96–99 FPS. After the save change, intervals at 9–12 FPS
  with ~500–600-ms stalls occurred, later about 77 FPS. These are different scenes,
  so the steady-FPS difference cannot all be attributed to a loading regression.
  The cause of the temporary large stalls is not yet established.
- The user disabled the upscaler in the menu and confirmed the whiteness remained.
  The failure is not confined to FSR output.
- Only read-only window and process-memory snapshots were taken. The window was not
  moved, resized or switched modes; no input sent, process not stopped.
- `contexts.json` records addresses, flags, signatures and SSAO pointers for known
  contexts. Most old objects were already reused; signature validation excludes them.
  This snapshot alone does not establish the white-frame cause.

Materials: `out/dev/white-after-save-20261017/`.

## Defect found and change

`FxInitClear` submits private PM4 WRITE_DATA for three FX-history helper targets.
In New, `Rasterizer::WriteDataOnGpu` updated the game-memory buffer but did not notify
the texture cache of changed bytes. Unlike the CPU path through `NoteCommandWrite`,
an existing Vulkan texture could retain old content. On first load the texture may not
yet be cached; reloading and address reuse expose the defect.

GPU writes larger than 8 bytes now call existing
`TextureCache::InvalidateMemoryFromGPU`: an image at the same start address, fully
covered by the write, gets `GpuDirty` and refreshes from memory on next use.
The `guest_size <= max_size` check prevents uploading an entire GPU image from stale
memory after a partial write. Scalar fence/label writes retain the previous fast path.
This change does not expand handling of arbitrary partial writes inside an image:
the existing API considers images with matching starts.

This fixes a real cache-coherency violation, but its connection to this observed white
frame is not confirmed. Large frame stalls also require remeasurement after the fix.

## Validation and limits

bbgpu build and native fx-init-clear, cp-decoder and effect-flags tests passed.
They check clear commands, decoder and the previous SSAO fix; they do not replace
testing Vulkan-texture reuse in the game. Initial validation log: `build-test.log`;
final build after image-size restriction: `build-test-final.log`.

Separate test AppImage:
`dist/Bloodborne-bbport-x86_64-white-reload-test.AppImage`.
This test does not replace the main AppImage. The game was not launched automatically.
The same two-save sequence needs manual testing in a new process. The already running
process continues using the old library. Additional dumps can be obtained on the next
launch with `BB_IMAGE_SYNC_LOG=1`, `BB_DUMP_TRIGGER`, `BB_DUMP_DIR`, `BB_DUMP_FRAMES=1`.
