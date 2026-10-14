# Motion vectors: rework after the 2026-09-26 video

Source material: `video_2026-09-26_04-19-53.mp4`, FSR 3.1 Performance,
render 960×540 → output 1920×1080, and `out/dev/t71.log`.
This describes the current working-tree changes, not a confirmation of in-game quality.

A common pass for all G-buffer draws turned out too expensive: Performance ran at about
49 FPS with it and 77–78 FPS without it. Object vectors are now enabled by default only
for shaders with a pose/bone buffer (size 640–16384 bytes, excluding the common 864-byte
scene buffer; 16-byte step). In a trial run with a narrower 1024-byte threshold,
this cut the number of processed draws to about 140 per frame, eliminated history
overflow, and gave about 81–87 FPS. The remaining draws keep cheap camera vectors.
`BB_OBJECT_MOTION=0` disables the whole feature; `BB_OBJECT_MOTION_ALL=1` brings back the common
pass for A/B. The auxiliary target's alpha channel stores depth: if a later regular
draw occluded the object, its vector is not used. Character and weapon quality in motion
after sampling still needs a visual check.

## Findings

- At the end of the source log over 600 frames: 257400 G-buffer draws, 256200 declared
  moving, only 30000 received previous positions (~11.7% of all draws).
  This is draw coverage, not a percentage of pixels. The old counter did not distinguish
  the reason for each skip.
- History reserved the size of the whole vertex buffer multiplied by the instance
  count **including firstInstance**. For submeshes of shared buffers these are extra
  positions; the budget was 2097152 positions per frame.
- History had no separate barrier between vertex shader writes/reads;
  reuse of the host-parameter ring did not wait for the GPU.
- Disabled all-vertex writes were directed into a single scratch element.
- `CameraMotion::OnDisplayPass` reset Depth() before computing jitter phases:
  Performance got 8 phases instead of 32. Position reconstruction from depth
  also did not account for the viewport offset.

## Changes

- The history range is determined by min/max of the actual indices, accounting for baseVertex
  and primitive restart. FirstInstance is subtracted in the shader instead of consuming memory.
- All suitable direct G-buffer draws are saved, starting from their first appearance.
  The constant-change heuristic was removed: it considered almost all draws moving
  and missed the start of motion. Reading is possible only on a match with the previous frame.
- The key includes all vertex stream descriptions, the shader, the address and content hash
  of the indices, the vertex range, instances, and the ordinal among identical draws.
  A topology change or a skipped frame resets the corresponding history.
- Budget — 4194304 positions/frame; the two arrays together occupy 128 MiB instead of 64 MiB.
  On memory shortage, camera vectors remain. The log separately shows saves,
  matches, missing history, memory shortage, and invalid ranges.
- Added vertex-to-vertex barriers, a GPU wait before host-parameter reuse,
  coherent host memory, and independent tracking of the motion image layout.
  Re-reading the image does not erase the vector-presence flag.
- Disabled accesses are bypassed with branching. For repeated invocations of one
  indexed vertex, atomic writes of position components are used.
  Positions behind the camera and non-numeric/infinite vectors are not used.
- Performance gets 32 jitter phases after FSR context creation. Camera vectors
  are reconstructed from unjittered coordinates; object vectors were already taken
  from clip positions before the viewport shift.

## Checks

Build and CPU tests:

```bash
cd native_probe
nix-shell shell.nix --run 'bash build.sh && ninja -C out/gpu motion-history-test motion-shader-test && out/gpu/motion-history-test && out/gpu/motion-shader-test out/motion-shaders'
```

`test_motion_history.cpp` checks u16/u32 ranges, restart, negative baseVertex,
firstInstance, repeated draws, topology change, a skipped frame, budget exhaustion,
overflow, and the phase count. A run with AddressSanitizer/UBSan also passed.

`test_motion_shaders.cpp` uses the real SPIR-V backend and creates VS/PS with
and without vectors. All four results passed `spirv-val --target-env vulkan1.3`.
To repeat, you need `spirv-val` from SPIRV-Tools:

```bash
for shader in out/motion-shaders/*.spv; do
    spirv-val --target-env vulkan1.3 "$shader" || exit
done
```

Build/test logs: `out/dev/motion-validation.log`. The test environment
has no access to `/dev/dri`: quality on the RX 7800 XT, FPS, and the coverage percentage
after the changes are not yet verified. Successful SPIR-V validation does not prove
picture correctness.

## Next in-game run

From `game_files`:

```bash
BB_FRAME_STATS=1 BB_TOGGLE_FILE=out/dev/motion-toggles bash native_probe/run.sh 2>&1 | tee native_probe/out/dev/motion-run.log
```

Bit 29 in the temporary toggle file disables only history writes. For a correct
performance comparison, the game must be run with `BB_OBJECT_MOTION=0` and without it:
pipeline selection and the additional target are set at process start.
After switching, give FSR several frames to refresh history.
Compare one scene: character/weapon while running, a camera turn, combat, static camera.
After ~600 frames, check `Object motion:`: `with history`, `capacity skips`, `unmatched`.

Remaining limitations: identical meshes are matched by draw order, which
can change when objects are culled; a change of dynamic vertex buffer addresses
loses the match. Indirect draws, tessellation/geometry shaders, MSAA, and passes
outside the G-buffer remain on camera vectors. Transparency/particles, blurry UI, and moving
scaling to the renderer level are not solved by this change. The cost of index scanning
and atomic writes must be measured in a real run.

## September 29: weapons and small skeletons (whirligig saw ghosting)

Video `video_2026-09-29_23-08-26.mp4`: the character stands still, the saw disc spins and leaves
a trail. The `BB_MOTION_SELECT_LOG=1` log showed the cause: the vertex shader's second buffer is
the bone palette at 48 bytes each (3x4), and for weapons/props it is 96–384 bytes (2–8 bones).
The "640 bytes and up" rule did not include such draws; the disc got only camera vectors,
i.e. it was static for FSR.

Changes:

- `Motion::ClassifyBuffer` (`motion_history.h`): 864 — scene, ≥640 — character skeleton,
  96..639 divisible by 48 — small skeleton. Pipelines with any skeleton get the
  vector variant.
- There are about a thousand small skeletons per frame, most of them static map parts.
  So they are "gated": the palette hash is compared with the previous frame using a cheap
  key (`History::Moving`) before index scanning. If it matches — the camera vector is accurate,
  nothing is written. If it changed — positions are saved, and the object vector applies
  from the next frame. The hash with the 416-byte buffer is not suitable: it changes with
  the camera for almost all of them (verified: history overflow and FPS drop to ~40).
- Menu: "Show motion vectors (debug)". Red/green — |x|/|y|, blue —
  the pixel received an object vector. `BB_MOTION_SELECT_LOG=1` prints G-buffer shaders
  with buffer sizes and the decision.

Measurement `out/motion-gated.log`: ~225 saved draws and ~600 "static" per frame,
no overflow, 58–80 FPS in game scenes. Visual disappearance of the trail
on the saw still needs to be confirmed.
