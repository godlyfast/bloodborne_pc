# NVIDIA / hybrid laptop: submitted-log analysis, 2026-10-17

This investigation is separate from PM4/23 during save loading and allocation error 9
in Laurence's cinematic. No renderer changes have yet been made for these reports:
the null call and loading stop require different checks.

## Confirmed cases

| Case | Evidence | Conclusion |
| --- | --- | --- |
| Low FPS | `20261016_225412.log`: NVIDIA ICD failed to load, Intel RPL-S selected; scene 7.4 FPS, GPU wait about 90% | NVIDIA setting could not select a device absent from Vulkan's list. Not an RTX 4060 performance measurement. |
| Startup crash | `crashlogs.log`, `20261017_033953.log`: NVIDIA 4060 selected, then SIGSEGV, RIP/address nil, before presenter-ready message | Failure before game-frame startup. BB_ASYNC_SUBMIT is the last message, not by itself evidence of the culprit. |
| Crash inside NVIDIA | `bbport-gdb.txt:264–269`: return address 0x7f18257b181c; eglcore mapping starts 0x7f1824c00000, segment offset matches address | Null call returns into `libnvidia-eglcore.so.615.78.08`, file offset 0xbb181c. Dump lacks called function name and null-pointer cause. |
| Game-independent reproducer | `bbport-coredump.txt`: vulkaninfo --summary SIGSEGV, RIP 0 | Game code unnecessary to reproduce one failure. Author reports host vkcube works; priority is AppImage/host environment differences. |
| Hang after Core.Res.TaskManager | `bbport-20261017_032608.log`, `20261017_034314.log`, `log.txt`: submitted=decoded=18, waiting=commands=0, label 0x1041400030 reached 0x11 | Decoder queue not stuck on these commands. Need main-thread execution/wait location. Reported CPU usage does not prove a particular busy-wait. |

`20261017_033348.log` also stops after Core.Res.TaskManager with submitted=decoded=18.
Presenter-ready confirms creation, not that the first frame was presented.

## EGL and packaging

`bbport-vulkan-info (copy 1).txt` sets only
`__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json`.
The loader opened NVIDIA ICD but did not obtain `vkCreateInstance` through
`vk_icdGetInstanceProcAddr`, leaving Intel. Another report with both vendor JSONs
makes NVIDIA available but encounters a different failure. Substituting NVIDIA JSON
thus explains the behavioral change, not a verified crash fix.

`launcher/bbport_vulkan.py` preserves an explicitly user-set EGL list; if absent,
adds host vendor JSONs. Separately sets NVIDIA ICD and a symlink directory for host
NVIDIA libraries ahead of bundled glvnd/X11/Xext. GDB indeed shows host NVIDIA and
bundled glvnd, Wayland, GBM, libc. This mixture needs dependency checking but does
not itself prove incompatibility.

Diagnostics list EGL Wayland/GBM/X11 libraries as `not loaded` although symlinks exist.
Currently this means no `calling init` in LD_DEBUG trace, not proven file absence.
Possible causes: missing transitive dependency, load error, or process termination before
initialization. Full linker trace is needed to distinguish them.
The author already tried hiding external platforms without success; these libraries
cannot be treated as the sole cause.

NVIDIA EGL external-platform descriptions: https://github.com/NVIDIA/eglexternalplatform
and https://github.com/NVIDIA/egl-wayland2 .

## Why bb-probe produces no core

`src/probe.c` installs a SIGSEGV handler that prints Fault and calls `_exit(128 + sig)`.
That is ordinary exit 139 after intercepting the signal, not necessarily core creation.
`No coredumps found` is expected on this path. Standalone vulkaninfo has no such
handler; the supplied core belongs to it. GDB can stop bb-probe on SIGSEGV before
delivering the signal to its handler.

## Next targeted checks on the reporter's machine

1. For the hang, obtain the built-in watchdog dump of all threads:

   ```sh
   BB_TIMEOUT=25 ./Bloodborne-bbport-x86_64-test-1016.AppImage --play > bbport-startup-watchdog.log 2>&1
   ```

   Expected exit 25 seconds after watchdog installation, with
   `STOP: watchdog timeout; thread stacks`. Unlike the supplied GPU-stall dump this
   includes main thread, registers, pointed-to data and stack words. The test deliberately
   terminates this launch. The command does not change saves/settings; the game may
   perform normal startup writes.

2. For the null call, save the complete linker trace including child vulkaninfo:

   ```sh
   LD_DEBUG=libs,files __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json:/usr/share/glvnd/egl_vendor.d/50_mesa.json ./Bloodborne-bbport-x86_64-test-1016.AppImage --vulkan-info > bbport-nvidia-linker.log 2>&1
   ```

   This reproducer does not launch the game. Need unresolved-symbol/dependency messages
   immediately before SIGSEGV. Repeating already excluded DLSS/async submit/memory model
   switches without new evidence will not localize this failure.

The local machine has no proprietary NVIDIA ICD. It cannot confirm this driver-path
fix or establish that the issue is solved.

## Addendum: bb-loop.txt, bb-vals.txt and bb-hung.txt

New files substantially narrow the windowless hang specifically.
It is not the same case as the null call from NVIDIA EGL core:

- Main thread is in the ordinary frame limiter, `+0x2034af0…+0x2034b6f`, calling
  gettimeofday. Two samples five seconds apart show both current time and frame start
  `[r12+0x20]` changing; wait target about 0.033333 s. Frequent profiler hits here
  are explained by busy-waiting between updates, not proof of stalled clocks.
- Zero system calls on that thread is compatible with vDSO gettimeofday;
  it does not mean time stopped updating.
- Chain `+0x1e4a6f5 ← +0x2018e27 ← +0x2034b35` corresponds respectively to outer
  game loop, one application update, and limiter.
- Watchdog shows GPU completed all 18 initial commands, queue empty, label at `0x11`.
  This excludes waiting for those commands specifically, not faults in the entire
  subsequent presentation path.
- Sleeping-worker waits alone do not establish a lost wakeup: workers also sleep
  when the main loop gives them no tasks.

### Findings in guest code

Addresses below are offsets from image base `0x800000000`.

| Point | Diagnostic meaning |
| --- | --- |
| `+0x2018d20` | Main-loop update |
| `+0x2018e27` | Limiter return, before handing frame to dispatcher |
| `+0x20512a0` → `+0xf88c60` → `+0xf88c70` | Game-task update path |
| Global pointer `+0x54b2e30` | Dispatcher object |
| `dispatcher+0x38` | Nonzero on entry makes dispatcher return immediately; temporarily 1 during normal root-task call |
| `dispatcher+0x40` | Root task; nonzero pointer calls virtual method `vtable+0x30` |
| Global pointer `+0x5540518` | Table of 76 registered game tasks after vtable pointer |

Next sample must therefore be at a frame boundary, avoiding mistaking the transient
execution flag for a failure. Old `bbport-startup-watchdog.log` contains RIP/RDI and
frame chains but not these objects. `bb-vals.txt` contains the limiter object, not
dispatcher. Submitted files still cannot identify the specific loading-stop condition.

This build's `SprjWindow` poll method calls `+0xfe3960` at the end and returns true.
Runtime system status is also always foreground. No direct dependence of this game-loop
portion on SDL-window focus was found; there is no basis to fake focus or force-show a window.

### Targeted sampling without rebuilding AppImage

Added `scripts/diagnose_boot.gdb`. Attaches to the already hung process, checks guest-code
signature, places a temporary breakpoint at `+0x2018e27`, captures three states
eight updates apart, and detaches. Captures dispatcher, root task with update method,
task table and state objects. Calls no guest functions, changes no flags, skips no
initialization. Brief all-thread debugger stops temporarily affect timing.

Launch normally, wait for the hang, and from project root in another terminal run
with the main bb-probe process PID:

```sh
gdb -nx -q -batch -ex 'set auto-solib-add off' -p PID \
    -x scripts/diagnose_boot.gdb > bb-boot-state.txt 2>&1
```

If attach reports `ptrace: Operation not permitted`, repeat with `sudo gdb`:
Yama may forbid attaching to a sibling process owned by the same user.
No need to disable the system restriction globally.

Complete sampling is marked `BOOT DIAGNOSIS COMPLETE`. If the debugger never reaches
the frame boundary, interrupt with Ctrl+C and retain output; on exit the script removes
its breakpoint and detaches. Need `bb-boot-state.txt` specifically to compare task
state with a working launch. Already tested GPU, memory-model, FPS, audio and TZ
switches need not be repeated for this sample.

Local script validation on a working launch with separate save copies completed:
all three snapshots captured, all have `dispatcher+0x38=0`, root task exists,
update method `+0xf8a370`. Reference:
`out/dev/boot-hang/reference-v2/bb-boot-state.txt`; full log beside it, `game.log`.
This validates the diagnostic tool on the current AMD build, not reproduction
of the reporter's hang or a fix.

## Local reproduction attempts

At the user's request the old `dist/Bloodborne-bbport-x86_64-test-1016.AppImage`
specifically was checked, not only current build. Local file SHA-256:
`9d5139e98f219cd227921b3fc642b5baf4bcb039bf32d686f148022bf2cd61b5`.
Hash equality with the reporter's file was not checked.

Machine: Ryzen 7 5700X3D, Radeon RX 7800 XT, NixOS, kernel `7.2.10-cachyos`,
Hyprland 0.56.2. Each launch used a separate profile; main user settings and saves
unchanged. Common parameters: 1920×1080, TAA, 30 FPS, DLSS off, SDL dummy audio,
new memory model. Runs were terminated sequentially by the script after about 36 seconds.

| Check | Window appeared | Frame-stat lines | Result |
| --- | --- | --- | --- |
| test-1016, Wayland | Yes | 840 | Boot hang and Fault not reproduced |
| test-1016, Wayland, single-CPU affinity | Yes | 881 | Boot hang and Fault not reproduced |
| test-1016, X11 via Xwayland | Yes | 880 | Boot hang and Fault not reproduced |
| test-1016, Wayland, empty profile | Yes | 880 | Boot hang and Fault not reproduced |
| test-1016, Wayland, empty profile, only Intel Black Tonemap Fix | Yes | 880 | Boot hang and Fault not reproduced |

First three runs used a save copy and five disabled graphics effects; Sprint Fix
also came from the shared folder. Fourth removed effect settings but still picked up
Sprint Fix. Fifth excluded external patches via a separate empty directory; log
confirms exactly one patch write:
`FPS preset 30; 1 writes from ['Intel Black Tonemap Fix']`.

All five created Core.Res.TaskManager, queue advanced beyond initial compute,
window appeared in Hyprland's mapped-client list, and frames continued until test stop.
Direct process-memory reads also confirmed dispatcher, root task, and zero in_update
at the last sample. Not reproduction of the intermittent error or proof of no race.

Results and full logs:
`out/dev/boot-hang/local-matrix/summary.json`,
`out/dev/boot-hang/local-clean/summary.json`,
`out/dev/boot-hang/local-native/summary.json`.
AMD cannot check the null call inside proprietary NVIDIA EGL core. A similar loading
hang could in principle be sought locally because the reporter also sees it on Intel,
but these variants did not reproduce it.

GitHub review found another similar report:
[#216](https://github.com/deadinside28/bloodborne_pc/issues/216), RX 5500 XT,
log also ends after Core.Res.TaskManager. It uses the old renderer and lacks a main-thread
snapshot, so no common cause established. PR #193's low thread addresses are already
implemented in the current line; Windows boot-fix in PR #138's comment concerns a separate
Windows-branch error. Details and other current PRs:
[GitHub review](GitHub_review_2026-10-17.md).
