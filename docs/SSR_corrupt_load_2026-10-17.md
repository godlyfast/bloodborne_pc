# Scene corruption on first load: SSR — 2026-10-17

User screenshots: `image_2026-10-17_19-34-43.png` (save menu) and
`image_2026-10-17_19-35-22.png` (scene with colored blocks).
The user confirmed the failure occurs on the process's very first load:
colored blocks without Bloom, a white frame with Bloom.

## Cause validation

Diagnostics ran on separate copies of a Hunter's Dream save. User settings and saves
were unchanged. No commands controlled window size, position, monitor or fullscreen
mode. Images came from internal render dumps.

Materials: `out/dev/corrupt-load-20261017/`; script
`out/dev/diagnose-corrupt-load.py`.

| Case | Result |
| --- | --- |
| `baseline-new`: New, live effects, SSR on, Bloom off | Colored blocks already at FSR input |
| `old`: Old, same SSR/Bloom | Colored blocks already at FSR input |
| `startup-effects`: New, `BB_HOT_EFFECTS=0`, SSR on, Bloom off | Normal scene |
| `live-no-ssr-bloom`: New, live effects, SSR off, Bloom on | Normal scene |
| `fixed-ssr-bloom`: fix, New, SSR on, Bloom on | Normal scene |
| `appimage-ssr-bloom`: new AppImage, New, SSR on, Bloom on | Normal FSR input and presented frame; closed after control dumps |

All cases used FSR 4.1.1, Native AA, 2560×1080 output, RX 7800 XT / RADV.
Camera positions may differ between launches; this checks image corruption, not
pixel-by-pixel equality or FPS.

## Defect

The live SSR implementation carried over the community patch's code and constants,
deliberately skipping `0x22c428d`: replacing `shr esi,1; shr edx,1` with a four-byte NOP.
That changes the constructor's resource size. Skipping it left a half-sized target
with altered SSR passes. The observations require neither changing saves nor
a hypothesis about FSR or only the new memory model.

SSR also occupied several `hot_code` entries, but normal settings application marked
the common effect index applied after the first entry. Remaining entries could be
skipped on toggle. Removing the partial live path eliminates this SSR inconsistency.

## Fix

- `scripts/patches.py` again selects the complete startup SSR patch, including size.
- Partial live SSR entries removed from `hot_code`.
- Overlay and built-in menu indicate SSR requires restart; Bloom remains live.
- Added checks for all ten SSR writes, including the four bytes at `0x22c428d`,
  and the SSR/Bloom menu classification.

131 Python tests passed after linking completed. Native settings, effect-flags and
fx-init-clear passed. bbgpu and AppImage builds successful; third-party FSR ODR warnings
remain unchanged.

Previous main AppImage saved as
`dist/Bloodborne-bbport-x86_64-before-ssr-fix.AppImage`.
Main `dist/Bloodborne-bbport-x86_64.AppImage` rebuilt with the fix.
SHA-256: `ed514586521d6452031e8a708f3cc61661b761c7f074ff0391c0a10dc844d6b6`.

The control AppImage loaded the character in the clinic; its frame is not compared
pixel-by-pixel with exterior frames from the original build. No diagnostic processes
remained afterwards.

Save-menu portraits were not investigated separately: a screenshot shows one corrupted
character portrait but does not establish a connection to current scene rendering.
Long sessions, repeated save changes and NVIDIA are not covered by these short control runs.
