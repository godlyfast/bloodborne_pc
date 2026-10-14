# The original GPU copy and portable labels

Snapshot 2026-10-09. Verification scope: `BB_PC_MODEL=1 BB_LAYER_MEMORY=1`; the new model, without evaluating the old memory model.

## The original copy shader

With the game's memory in place, shader `fefebf9f` is now translated to SPIR-V by default and executed on the GPU. The shader itself reads its copy list at execution time; the CPU does not replace it with a list of Vulkan copies. `BB_COPY_SHADER_NATIVE=0` keeps the HLE for comparison. Experiment 2 still inverts the choice.

For large bindings the BDA table holds two representations: the first half has the current addresses (mirror or game memory), the second half has the game-memory addresses. The existing addressing of the first half is kept for DMA/ReadConst. The binding description carries a write-through flag and the offset of the second table.

The original copy shader writes the result to the current GPU address and to game memory. So CPU consumers see the result after synchronization, and GPU consumers do not read a stale mirror. When both writes address game memory, they produce the same result. The other compute shaders keep their accounting of GPU ownership of the mirrors. Write-through stores do not mark the whole mirror of a huge binding as needing a copy back; the GPU writes accumulated before that stay in the accounting.

The range check prevents `offset + size` overflow; a rejected access does not index an arbitrary page of the table. The shader binary cache version was raised to 9. The cache profile now carries the binary/meta/pipeline versions: when they change, the whole cache is rebuilt before the modules load. Old metadata and SPIR-V with matching variation-index names do not mix with the new ones.

`run.sh` sets `BB_GPU_USER_DIR` before the process starts, from `BB_USER_DIR` or `$BB_DATA_DIR/user`. The GPU directories are created at library load, so setting this value inside `bbgpu_init` was too late. This picks the right cache for the AppImage and for separate save profiles; an explicit `BB_GPU_USER_DIR` is kept.

## EOP/EOS and RELEASE_MEM

If `VK_AMD_buffer_marker` is available, the fast AMD path is kept. Without the extension the label is written by the GPU through the standard `vkCmdUpdateBuffer`. `BB_GPU_LABELS_PORTABLE=1` forces this path and allows checking it on AMD. `BB_GPU_LABELS=0` keeps the former CPU callback after the GPU finishes.

The portable path ends the current render pass, publishes the preceding GPU writes for the CPU, writes the upper half of the 64-bit label, sets a dependency and writes the lower half. The next dependency makes the label visible to the GPU and the CPU. The scheduler notification and the WAIT_REG_MEM handling are kept. Unsuitable addresses and interrupted labels keep their respective fallback paths.

The standard command is allowed outside a render pass: [vkCmdUpdateBuffer](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdUpdateBuffer.html). The stage and access masks follow the [Vulkan synchronization rules](https://docs.vulkan.org/spec/latest/chapters/synchronization.html). Ending passes and inserting barriers has a cost; the forced portable path is not the default on AMD.

While checking, two dependencies of neighboring paths were also fixed: update/inline data are accounted at the CLEAR stage, and the index-buffer range is accounted after the draw, so that a later upload into the mirror waits for the index reads.

## Checks

`translation-memory-test` executes the production backend's SPIR-V and the production portable-label function on a Vulkan GPU. It checks reading the current source, writing to the mirror and to game memory, the page boundary, unmapped/out-of-range store, disabled write-through, 32/64-bit labels, the order of the halves, visibility of a preceding GPU result under CPU polling, a later GPU consumer and a zero value. The AMD diagnostic breadcrumbs are disabled so the test does not write AMD markers.

```sh
nix-shell shell.nix --run 'ninja -C out/gpu translation-memory-test'
# VK_LAYER_PATH may point at the directory of the installed Khronos validation layer.
BB_VK_VALIDATION_SYNC=1 out/gpu/translation-memory-test out/translation-shaders
spirv-val --target-env vulkan1.3 out/translation-shaders/paged-copy.spv
```

The PM4 self-test measures the positive occlusion interval across several submissions. A large separate submission could contain only compute/state and give a false FAIL. The positive-samples, valid-bits, zero-interval and predication requirements are kept.

Hardware verification was done on an RX 7800 XT / RADV. The portable path was force-checked on AMD; running on a real NVIDIA, importing its host memory and a long game session require a separate hardware run.

Local logs, source copies before the changes, measurements and screenshots: `out/dev/translation-fixes-20261009/`. The game checks use copies of saves and settings. The original saves and settings are not replaced. Logs and game data are not included in the release.
