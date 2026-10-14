# The layer's memory module: PS4 GPU addresses without sparse (plan, 2026-10-09)

## Why

The new memory model keeps the game's memory in one sparse arena and moves blocks between the
game's memory and VRAM by rebinding (`vkQueueBindSparse`). On NVIDIA (Linux, drivers ≥ 555) the
bind time grows with the number of already bound pages, and the call holds a global lock: every
move to VRAM cost seconds, freezing the game and the desktop (GTX 1660 Ti, 615.71). Without moves
(`BB_FIXED_ARENA=1`) — 48.6 FPS against ~205 on an RX 7800 XT. What is needed is a model that
works the same on AMD, NVIDIA and Intel and is not tied to shadPS4's buffer cache: it is part of
the future PS4-game launch layer.

## The idea

The PS4 GPU has its own virtual memory (GPUVM) over the shared memory; every V#, T# and pointer in
user data is a virtual address. On a PC we do the same with Vulkan 1.2 (BDA) means:

- **Memory sources** — ordinary (non-sparse) Vulkan buffers:
  - pieces of the game's memory: dma-buf (AMD) or host-memory import (NVIDIA, Intel), one piece
    per direct game-memory allocation (allocations are mapped whole — a range inside one mapping
    is always contiguous within one piece);
  - VRAM mirrors: segments aligned to the game's addresses (game page X lies in the segment at
    the same offset), allocated when the segment gets its first page in VRAM.
- **Page table** (a buffer on the GPU): a page of a PS4 address → the device address (BDA) of its
  current source. Changed by a copy in the command stream — in order with the draws, without
  semaphores.
- **Direct path**: a V# range lies wholly in one source (almost all bindings) → an ordinary
  descriptor (source buffer, offset, size). The shader translator is unchanged.
- **Paged path**: a mixed range (≈85 huge bindings a frame: shaders bound to the whole memory) →
  the descriptor points at a {PS4 address, size} record, and the shader translates every address
  through the table. A pipeline variant only for such bindings (a specialization key).
- **Vertices, indices, indirect arguments, copies, texture uploads**: the direct path; otherwise
  assembly into a contiguous temporary buffer (read-only) or per-page copies (the CPU knows the
  table).
- **Moving to VRAM and back** — the policy of the current new model (data whose writes we know:
  uploaders, the GPU; unknown writers stay in place), but the execution is a copy + a table write
  + the source choice at binding. Bindings recorded before a move read the old source — it is
  still correct; the VRAM is freed once the GPU has passed those commands.

## Work plan

1. **The module core** (`gpu/layer/`, no shadPS4 dependencies): sources, pages, the table,
   `Resolve(address, size)` → a direct source or "mixed", iteration over sources for copies.
   The command-writing interface is abstract (copy, table write) so as not to drag in the
   scheduler.
2. **Hook-up without VRAM**: the new model hands over the in-place ranges through the piece
   buffers instead of the arena; the sparse arena is not created in the new model. Expectation:
   ~48 FPS on AMD (as with `BB_FIXED_ARENA`), no `vkQueueBindSparse` at all. A picture check,
   then a build for NVIDIA.
3. **VRAM mirrors + moving**: the policy from `BufferCache`, the page table, the paged path in
   the shaders for mixed bindings. The goal is parity with the sparse arena on AMD (~205 FPS).
4. **NVIDIA/Intel**: a test build, a tester's log; then remove sparse from the new model
   entirely.

Measurements — RX 7800 XT, standing still (`tools/bench.sh`), `BB_PC_MODEL=1`; diagnostics
`BB_RESIDENCY_MIX=1`.

## State (2026-10-09, morning)

- Steps 1–3 are done. On an RX 7800 XT, standing still: the module ~205 FPS, the sparse arena
  ~205–238, the old model ~220 (at the lamp in the Hunter's Nightmare); elsewhere (1170 draw
  calls) — 167.5 / 164.5 / 146. `vkQueueBindSparse` is never called in module mode (a counter in
  the `Layer memory:` line).
- Mixed bindings were solved without the paged path: "volatile" blocks (`layer_volatile`) — a
  block with unknown bytes (the edge of a range, a gap between images) is placed into the mirror
  together with the rest of the range, updated from the game's memory before every binding, and
  what the dispatch wrote into it is copied back after the dispatch (`LayerAfterBindings`). The
  paged path remains for bindings of 64 MiB and up. `BB_LAYER_VOLATILE=0` turns it off (for
  comparison).
- By default: AMD — the sparse arena, the other GPUs — the module (`BB_LAYER_MEMORY=1/0` — by
  hand). Step 4 (NVIDIA): a tester's log is needed; the host-memory import path cannot be checked
  on AMD (RADV does not import memfd).

## Addendum: the original copy and portable labels (2026-10-09)

In the new module the paged path of the original copy shader was fixed: writes update the game's
memory and the current mirror; the native shader is now chosen by default. A standard Vulkan path
without AMD buffer marker was added for the GPU labels. The implementation, switches and
verification boundaries are described in
[TRANSLATION_GPU_COPY_LABELS.md](TRANSLATION_GPU_COPY_LABELS.md). This closes the label-writing
dependency on the AMD extension but does not replace NVIDIA hardware verification.
