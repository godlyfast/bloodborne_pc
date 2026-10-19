# bloodborne_pc issues and pull requests: review, 17 October 2026

Main conclusion: investigating specific failure mechanisms and porting small fixes
to 0.6 matters more now than grouping all "code 23 / 139" reports or accepting every
open PR. Some proposals are already in `testing`, some target only the old renderer,
and others concern third-party Windows builds.

## Reviewed material

GitHub API snapshot: **182 issues, 109 open and 73 closed**; **47 PRs, 28 open and
19 closed**; **385 ordinary issue/PR comments**. Snapshot counts, not unique failures.
Inline review comments and CI results were not separately downloaded.
All lists/discussions saved in `out/dev/github-review-20261017/`.

Descriptions, related reports and changed files of open PRs reviewed; deeper code
comparison for the priority cases below. Not a line-by-line audit of every large-port
change. For #6 and #127, whose file lists exceeded an API page, full diffs downloaded too.

Branches at review time:

- [`master`, 3c57da4](https://github.com/deadinside28/bloodborne_pc/tree/3c57da4198ad62039f63f33bfd205b9916518acf): 0.51 line, old renderer.
- [`testing`, 72e5c8c](https://github.com/deadinside28/bloodborne_pc/tree/72e5c8ce22ec0fa39481bc81aefbb761869d0691): 0.6-pre1, new renderer.
- Local worktree contains changes beyond `testing`, including our loading/cinematic
  fixes. It is not an exact copy of published GitHub code.

Nothing published, closed or merged on GitHub. This review did not change executable code.

## Connection to current investigations

### Hang before first frame: a similar AMD report exists

[Issue #216](https://github.com/deadinside28/bloodborne_pc/issues/216) includes
an [RX 5500 XT log](https://github.com/user-attachments/files/33536475/bbport-20261016_120626.log).
I downloaded it: Vulkan presenter created, Core.Res threads start, then after TaskManager
only the image-write-trap message remains. Author sees no menu; memory-model switching
does not help.

Useful similarity to the submitted laptop hang: an NVIDIA-specific cause alone is
no longer sufficient. But #216 uses the previous renderer line and lacks a main-thread
snapshot. A common cause with our case is **not proven**. Comparison needs task-dispatcher
states now captured by `scripts/diagnose_boot.gdb`.

Two similarly named fixes must not be mistaken for ready solutions:

- [PR #193](https://github.com/deadinside28/bloodborne_pc/pull/193) attributes lamp-travel
  hangs to truncating thread pointers to 40 bits. `testing` and local code already have
  `low_record()` with low-memory allocation. Also, its main thread slept on a lock;
  ours continues the limiter loop. Rare unresolved edge: on low-allocation failure
  code falls back to `calloc`, losing the pointer contract. Without an allocation-failure
  message there is no basis to link it to the current hang.
- [PR #138 comment](https://github.com/deadinside28/bloodborne_pc/pull/138#issuecomment-6107606220)
  does analyze a black window, but from file-descriptor leakage after a bad conflict
  resolution in the author's Windows branch, hitting UCRT's limit.
  Author explicitly said upstream needs no fix. Different cause.

### NVIDIA RIP=0: several failures share one signature

| Family | Links | Distinguish |
| --- | --- | --- |
| NVIDIA ICD/dependencies missing, Intel selected | [#107](https://github.com/deadinside28/bloodborne_pc/issues/107), [#205](https://github.com/deadinside28/bloodborne_pc/issues/205) | Driver selection/loading error; low iGPU FPS is a consequence |
| Device creation fails with DLSS | [#135](https://github.com/deadinside28/bloodborne_pc/issues/135), [#147](https://github.com/deadinside28/bloodborne_pc/issues/147), [PR #137](https://github.com/deadinside28/bloodborne_pc/pull/137), [PR #140](https://github.com/deadinside28/bloodborne_pc/pull/140) | libcuda/optional extensions; principal measures already in `testing` |
| Null Vulkan-extension pointer in recorder | [#161](https://github.com/deadinside28/bloodborne_pc/issues/161), [#177](https://github.com/deadinside28/bloodborne_pc/issues/177) | Check exact call and dispatch-function loading |
| RIP=0 at bb-probe startup in new reports | [#181](https://github.com/deadinside28/bloodborne_pc/issues/181), [#219](https://github.com/deadinside28/bloodborne_pc/issues/219), [#229](https://github.com/deadinside28/bloodborne_pc/issues/229) | Priority unresolved cluster; identical RIP does not imply identical caller |
| DLSS bridge build lacks headers | [#231](https://github.com/deadinside28/bloodborne_pc/issues/231) | Source-build failure, not proof of packaged-AppImage crash cause |

#229 still fails with `BB_DLSS=0`, old model and breadcrumbs disabled.
The libcuda fix does not establish that the whole cluster is solved.
Our separate dump, where the null call comes from NVIDIA eglcore and even vulkaninfo
crashes, also requires independent AppImage/host environment comparison.

For #231, `gpu/dlss_bridge/CMakeLists.txt` indeed lacks its own `find_package(Vulkan)`;
includes are supplied manually. The bridge receives Vulkan proc-address functions
through its initialization API. The report directly proves a missing header.
Testing a CMake dependency on Debian outside nix-shell is reasonable, but connection
to runtime RIP=0 remains the commenter's hypothesis, not established fact.

### Intermittent game/cinematic crashes

Well-linked cluster: [#162](https://github.com/deadinside28/bloodborne_pc/issues/162),
[#169](https://github.com/deadinside28/bloodborne_pc/issues/169),
[#192](https://github.com/deadinside28/bloodborne_pc/issues/192).
One variant writes NULL+8 at `+0x2199310`, another passes NULL to memcpy from
`+0x21d5b40`. Discussion links both to one exhausted GX allocator.

[PR #224](https://github.com/deadinside28/bloodborne_pc/pull/224) enlarges each of
two command buffers from 256 KiB to 1 MiB. I checked both immediates locally in the
guest image: still 262144. A current small change to test early; adds headroom
but does not itself explain buffer exhaustion.

This is a **different heap** from our Laurence resource cache, formerly 160 MiB,
locally now 512 MiB. Enlarging one does not replace the other.
Our loading PM4 private-clear fix is another distinct path. Matching exit 23 or 139
does not unify these causes.

[PR #214](https://github.com/deadinside28/bloodborne_pc/pull/214) exposed another
real gap: old memory model never installs guest hooks. Confirmed by
`GuestInPlace() && game && game->install_hooks` in both `testing` and local code.
Not only memory-dependent hooks are lost, but GX-heap protection, aspect ratio and
mouse controls too. Port must retain model-dependency separation and our new cinematic hooks.

Separately, [#207](https://github.com/deadinside28/bloodborne_pc/issues/207#issuecomment-6202536610)
analyzes exit 23 in Yebis motion blur: caller permits two samples, callee requires
at least three. Author has not determined why two were selected: corrupted tables
or pass index not covered by techniques. Motion blur off is a proposed workaround;
merely suppressing the assert without checking tables may hide primary corruption.

No direct Laurence report found in downloaded issues/comments.
[#180](https://github.com/deadinside28/bloodborne_pc/issues/180) has corrupted
textures in Amelia's introduction: candidate for write/allocator comparison,
not confirmation of one cause.

## Fix priorities

| Priority | What | Why / checks |
| --- | --- | --- |
| P1 | #224 and #214 | GX crashes, missing protective hooks in Old; transitions/cinematics in both models |
| P1 | [#211](https://github.com/deadinside28/bloodborne_pc/pull/211) | resize/HDR `swapchain.Recreate` lacks common submit_mutex; author has queue-concurrency validation error and comparative tests |
| P1 | #219/#229 cluster + our eglcore dump | Broken startup; retain distinct caller signatures, check packaging/dispatch |
| P1 | #216 + our startup hang | Capture tasks/boot transition; no ready confirmed PR fix found |
| P2 | [#206](https://github.com/deadinside28/bloodborne_pc/pull/206) | Area-change VRAM exhaustion; port from 0.51 and test low VRAM |
| P2 | [#210](https://github.com/deadinside28/bloodborne_pc/pull/210) | Faster tiler writes into host memory; local variant exists, absent in published `testing` |
| P2 | #207 | Reproduce Yebis assert with table dump, separate from memory exhaustion |
| P2 | [#165](https://github.com/deadinside28/bloodborne_pc/pull/165) | Retain crashed process for debugging; supplement existing local dumps |
| P3 | [#225](https://github.com/deadinside28/bloodborne_pc/pull/225) | Launcher offers FifoRelaxed but parser does not recognize it; small independent fix |

#206 details: description emphasizes retry after resource release, but current diff
also adds VRAM-block reclamation, combined unbind and BDA-table update.
Review is broader than one allocation retry. Discussion has a positive
[two-hour RTX 3050 4-GB report](https://github.com/deadinside28/bloodborne_pc/pull/206#issuecomment-6230825407):
one participant's validation, not all GPUs. 0.6 file paths and logic already differ.

#210's 36 → 117 FPS is the author's RTX 5090 result, not ours.
Local `gpu/textures/detiler.cpp` already uses VRAM staging and one copy for eligible
host destinations; GitHub `testing` still writes directly. Treat it as a local change
to compare/publish, not a PR to apply blindly again.

## All 28 open PRs

"Already present" means the idea is implemented, not that the PR was merged.
Local/published statuses distinguished where different.

| PR | Assessment / next step |
| --- | --- |
| [#226](https://github.com/deadinside28/bloodborne_pc/pull/226) | Fixes coroutine-frame leak in renderer 0.51. Useful for `master`; irrelevant to iterative 0.6 decoder. |
| [#225](https://github.com/deadinside28/bloodborne_pc/pull/225) | Current small FifoRelaxed/fallback fix. Check available X11/Wayland modes. |
| [#224](https://github.com/deadinside28/bloodborne_pc/pull/224) | Current, P1; test with #214. |
| [#223](https://github.com/deadinside28/bloodborne_pc/pull/223) | Experimental RTAO on 0.51 renderer. Defer until stable; author explicitly proposes 0.6 port. Tested only RDNA4 so far. |
| [#214](https://github.com/deadinside28/bloodborne_pc/pull/214) | Current locally and in `testing`: common hooks incorrectly depend on GuestInPlace. |
| [#211](https://github.com/deadinside28/bloodborne_pc/pull/211) | Current locally and in `testing`: common resize/HDR mutex missing. Not a startup RIP=0 fix. |
| [#210](https://github.com/deadinside28/bloodborne_pc/pull/210) | Absent from published `testing`, locally adapted. Needs comparative measurements/image integrity. |
| [#206](https://github.com/deadinside28/bloodborne_pc/pull/206) | Current VRAM issue, but old-renderer PR broader than short description. Port separately. |
| [#193](https://github.com/deadinside28/bloodborne_pc/pull/193) | Low thread-record addresses already implemented via pool in `testing` and locally. Check rare calloc fallback, then decide PR disposition. |
| [#191](https://github.com/deadinside28/bloodborne_pc/pull/191) | macOS/Rosetta/MoltenVK separate port. Assess platform support/common changes independently of Linux stabilization. |
| [#167](https://github.com/deadinside28/bloodborne_pc/pull/167) | Shader packs/hot reload useful, but IsPatchShaders() currently returns false; needs 0.6 renderer port and pipeline/module lifetime checks. |
| [#166](https://github.com/deadinside28/bloodborne_pc/pull/166) | Idea already in `testing`, migrated `gpu/gcn/formats.h`: invalid SnormNz descriptor no longer asserts. Does not solve every exit 23. |
| [#165](https://github.com/deadinside28/bloodborne_pc/pull/165) | BB_FAULT_WAIT absent from current probe. Changelog has related diagnostics, not full PR integration. Retaining process worth porting. |
| [#157](https://github.com/deadinside28/bloodborne_pc/pull/157) | Chinese translation incomplete; rebase current keys/placeholders. |
| [#156](https://github.com/deadinside28/bloodborne_pc/pull/156) | Portuguese translation incomplete; independent small slice after rebase. |
| [#154](https://github.com/deadinside28/bloodborne_pc/pull/154) | `testing` already has menu_language_chosen. Check saved-language persistence/migration; do not merge again without comparison. |
| [#153](https://github.com/deadinside28/bloodborne_pc/pull/153) | `testing` play() already calls set_language. Link existing fix. |
| [#140](https://github.com/deadinside28/bloodborne_pc/pull/140) | Device-creation retry without optional DLSS extensions already in new `gpu/vulkan/instance.cpp`. |
| [#138](https://github.com/deadinside28/bloodborne_pc/pull/138) | Windows-port sync to 0.51. Extract shared fixes separately; comment's Windows boot-fix irrelevant to Linux. |
| [#137](https://github.com/deadinside28/bloodborne_pc/pull/137) | libcuda already searched in `testing`. Broader Debian neighboring-directory search exists locally, not published yet. |
| [#130](https://github.com/deadinside28/bloodborne_pc/pull/130) | WIP LAN/plugin architecture differs from existing 0.6 BBSC/shadNet. Not a mandatory missing co-op fix. |
| [#127](https://github.com/deadinside28/bloodborne_pc/pull/127) | Trophies: full diff touches 301 files including Windows/renderer. Rebase/extract feature first; title understates scope. |
| [#79](https://github.com/deadinside28/bloodborne_pc/pull/79) | Flake build improves reproducibility, not game-crash cause. Check devshell/packaging separately. |
| [#50](https://github.com/deadinside28/bloodborne_pc/pull/50) | No substantive description, 89 files. Request precise goal/update; cannot assess as small fix by title. |
| [#43](https://github.com/deadinside28/bloodborne_pc/pull/43) | Correct clone URL already in local README; only PR disposition needs comparison. |
| [#10](https://github.com/deadinside28/bloodborne_pc/pull/10) | Labeled pt-BR but touches 89 old-branch files. Translation exists; take current missing strings from narrow #156. |
| [#8](https://github.com/deadinside28/bloodborne_pc/pull/8) | FP8 FSR 4.1.1 already announced/implemented in current line; compare remaining differences, do not reapply whole PR. |
| [#6](https://github.com/deadinside28/bloodborne_pc/pull/6) | Early Windows port, 140-file full diff. Infrastructure partly exists; source presence is not official Windows-build support. |

Static dictionary check of published `testing`: EN 271 keys; pt_BR misses 110 EN keys,
zh_CN 42. Counts missing fallback keys, not visible UI errors or translation quality.

## Organizing issues

1. Separate crash signatures: stage, thread, RIP/guest offset, final assert,
   memory model, renderer version. Exit code alone is unsuitable:
   #111, #144, #173 and #207 terminate by different mechanisms.
2. Form clusters with a primary technical report: GX heap (#162/#169/#192),
   VRAM (#142/#163/#173/#200), startup RIP=0, startup without first frame,
   Yebis (#207). Link others while preserving signature differences.
3. For already included PR ideas, identify commit/branch/first build.
   All 19 closed PRs in the snapshot have merged_at=null: no GitHub merge;
   this alone says nothing about manually porting their ideas.
4. Mark third-party Windows builds and legacy CPU separately:
   [#232](https://github.com/deadinside28/bloodborne_pc/issues/232) and
   [#230](https://github.com/deadinside28/bloodborne_pc/issues/230) cannot prove
   an official Linux AppImage regression. Windows dump in #162 still helps confirm
   the common GX allocator.
5. Include latest disproofs. In
   [#182](https://github.com/deadinside28/bloodborne_pc/issues/182#issuecomment-6180049311)
   author withdrew the earlier theory, linking artifacts to RADV/HTILE on a specific
   Oberon APU. Do not fix texture cache based on the old hypothesis or apply its
   nohiz workaround to all GPUs.
6. After checking the current build, revisit obsolete ultrawide, DLC, FSR-asset,
   language and --play requests. Feature presence does not prove every related problem
   solved; close only confirmed cases.

Practical order: stability/diagnostics first (#224/#214/#211, startup, #206/#207),
performance next (#210/#227), then new graphics features/large platform PRs.
None reviewed is a confirmed ready solution for the submitted Hyprland/Intel/NVIDIA hang.

Full number/status/date index:
[GitHub_inventory_2026-10-17.md](GitHub_inventory_2026-10-17.md).
