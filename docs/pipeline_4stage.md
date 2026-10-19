# Four-stage command pipeline: measurements and stages (2026-10-18)

Idea (user request): split the two-stage pipeline (`vk_draw_pipe.h`, stage A:
decoder, stage B: draw recording) into four stages:

1. Command-stream reception (decoder).
2. Parallel resource resolution on N threads.
3. Lightweight ordered barrier/state thread.
4. Parallel `VkCommandBuffer` recording.

Previous history: `docs/parallel_gpu.md`. Stage 4 already exists (command-buffer segments,
`BB_VK_RECORD_THREADS`, submission from recording threads). Part of stage 2 exists too:
speculative draw preparation on `bb:DrawPrep*` (pipelines, V#/T#/S#, vertex inputs;
used in ~97% of draws). Texture binding on a separate thread with fork/join every draw
gave no gain (data shuttles between cores).

## How to measure

CPU-bound: `~/.claude/jobs/9cdc30a2/tmp/run_cpu.sh`: route to Laurence, 860×360 output,
FSR 3.1 Ultra Performance (286×120 scene), unlimited FPS, Mailbox.
Weak CPU (like Steam Deck, 4 cores / 8 threads): `taskset -c 0-3,8-11`.
Stage profile: `BB_SECTIONS=1`. Run-to-run variation about ±10 FPS:
one run proves nothing; at least 3 alternating runs are needed.

Normal user settings (2560×1080, FSR 4.1.1 Native AA, RX 7800 XT) are GPU-bound:
154 FPS, stage B 55% busy, stage A waiting for GPU ~30% of the time.
Reworking the pipeline will not add FPS there.

## Baseline profile (CPU mode)

| | 16 threads | 8 threads |
|---|---|---|
| FPS | ~300 | ~230 |
| stage A, µs/packet | 3.6 | 4.4 |
| of which constant ring | 1.9 | 2.1 |
| stage A idle | 0% | 0.2% |
| stage B, µs/packet | 3.05 | 4.1 |
| stage B busy | 82% | 87% |

Stage B (16 threads, µs/packet): binding 0.78 (buffers 0.40, textures 0.25), vertices 0.35,
dispatch 0.41, tasks 0.35, begin render 0.19, dynamic 0.15, descriptors 0.14, kick 0.12.
Flat profile, no hotspot.

## Stage 1: constant-resolution workers (implemented, `BB_RESOLVE_WORKERS=n`, default 0)

Stage A no longer checks/copies small read-only buffers: it reserves `RingBinding`
with `RingPending` in the packet and marks bytes in `pending_resolve`.
`bb:ResolveN` workers take numbered packets (`DrawPipe::StartResolvers`, slot table),
check (`IsRegionGpuModified`, `PendingWriteOverlaps`, `LayerMirrored`), copy into their
own ring (`worker_rings`, tick marking still stage B), or mark `RingNotCopied` and
record the read in `pending_reads`. Stage B waits for the packet-ready flag.
CE dumps (`WaitForPendingReads`) first wait for `WaitResolved` for packets reading
their bytes. `PendingReads` tables are now atomic.

| | No workers | 1 worker | 2 workers |
|---|---|---|---|
| 16 threads | 300–303 | — | 298 |
| 8 threads | 228–232 | 230 | 217 |

Stage A: ring 2.1 → 0.48 µs, packet 4.4 → 3.3 µs, idle 20–25%.
FPS unchanged: on 16 threads the bottleneck moved to stage B (90%);
on 8 threads there are not enough cores.

## Oversubscription on 8 threads

Thread load (CPU mode, 8 threads, `/proc`): stage B 98%, stage A 84%, game main thread
84%, Vulkan recording 58% + 26%, `bb:DrawPrep` 4 × 22%, `bb:DrawScan` 15%, plus game
threads (GX, Havok, CSChr) ~150%. Almost 7 of 8 cores; some of our threads spin waiting.
On a weak CPU, less redundant work helps, not more parallel stages.

Knobs: `BB_PREP_WORKERS` (default half the threads), `BB_VK_RECORD_THREADS`
(2 on 8 threads), `BB_PIPE_SPIN_US` (50 µs below 12 threads).
Single runs: 1–2 preparation threads and 1 recording thread give +2…+9%,
but within variation; three-run series below.

## Stage 2 (not implemented)

Move buffer, vertex, index and texture lookup off stage B (~1.1 µs/packet).
Obstacle: `ObtainBuffer`/`LayerBind` are not pure lookup (Maintain, write traps, NoteUse,
VRAM promotion), and the texture cache changes state on image refresh.
Only pure lookups can move, with generation checks on stage B.
Expected +10–20% where stage B is the bottleneck (12+ threads).

## Three-run series (CPU mode) and new default

Speculative draw-preparation threads (`BB_PREP_WORKERS`):

| | Previous default | Better |
|---|---|---|
| 8 threads | 4 workers: 236, 239, 239 (238) | 1 worker: 250, 243, 246 (247, +3.7%) |
| 16 threads | 8 workers: 315, 317, 315 (316) | 4 workers: 333, 333, 331 (332, +5.3%) |

`DefaultWorkerCount` now uses a quarter of hardware threads from 12 up (16 → 4),
otherwise 1. New-build check: 8 threads 254 FPS, 16 threads 333 FPS.

Constant workers atop the new default (2 runs each): 16 threads 326/332 without,
324/323 with one; 8 threads 245/226 versus 240/240. No benefit;
`BB_RESOLVE_WORKERS` remains off. Stage B ~87% busy is the next limit;
without stage 2 the stages do not scale.
