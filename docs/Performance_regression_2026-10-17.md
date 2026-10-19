# Slowdown after the SSR fix: live measurement, 2026-10-17

Investigating user process 34837, log `20261017_170617.log`.
The game was not restarted; no input was sent. At the investigator's request the user
disabled the upscaler in the same scene. Source and builds did not change during measurement.

Materials: `out/dev/live-load-20261017/`, script `out/dev/sample-live-load.py`.

## Measurements

RX 7800 XT / RADV, Ryzen 7 5700X3D, 2560×1080 output, Native AA,
SSR enabled, Bloom disabled. The process had already loaded several saves.

| Metric | FSR 4.1.1, 40 seconds | Upscaler off, 25 seconds |
| --- | ---: | ---: |
| FPS, average of game-log windows | 72.08 | 99.82 |
| Frame median, average of windows | 13.81 ms | 9.34 ms |
| GPU busy, sysfs | 99.88% | 95.76% |
| VRAM busy, sysfs | 25.15% | 26.48% |
| bb:DrawRec | 63.99% of a core | 84.58% of a core |
| bb:GpuComm | 48.33% of a core | 74.57% of a core |
| Main thread | 30.20% of a core | 39.99% of a core |
| bb:VkRecorder / 1 / 2 | 21.40 / 16.86 / 13.98% | 29.54 / 24.20 / 19.17% |

CPU percentages use each TID's utime+stime increments in `/proc`; 100% means one logical
core. All threads together in the first window use about 4.21 logical cores.
DrawPrep threads use about 13.8% each. Percentage estimates do not replace function
profiling or exclude short serial work sections.

GPU frequency in sysfs about 2.65 GHz, memory controller 1218 MHz;
power 189–195 W against a 236-W limit. Temperatures: edge 62°C, junction 81°C,
memory 70–71°C. No obvious clock drop in the measured window.
Throttle flags are saved in raw GPU metrics and are nonzero in some samples;
therefore this does not claim that every kind of throttling is excluded.

No compilations, bulk CPU buffer uploads or host-copy waits occur during the sustained
slowdown. Returning to the 100-FPS limit after disabling the upscaler narrows the issue
to GPU work in the upscaling path on top of current scene cost.
It proves neither the absence of a regression nor that FSR itself changed.

## Memory and bus

About 5.16 GiB VRAM and 4.73 GiB GTT occupied. In a neighboring steady CSV window,
the image-upload counter reports 9.44 MB/frame; CPU buffer uploads, guest_copy_mb and
read faults are zero. These count specific port operations, not all GPU traffic or PCIe.

`Buffer bindings: ~55 GB/frame in place` sums bound-range sizes; multiplying by FPS
does not yield bandwidth. Likewise `VRAM copies` in that line means selection of a
resource representation, not actual bytes copied.

This device has no sysfs `pcie_bw`; GPU metrics format 1.3 lacks PCIe byte counters.
Speed reports conflict: `current_link_speed` 16 GT/s, SMU metrics 8 GT/s,
both x16 wide. Exact PCIe and system DRAM traffic in GB/s was not measured.
VRAM busy is not the percentage of maximum bandwidth achieved.
Interface descriptions: https://kernel.org/doc/html/latest/gpu/amdgpu/thermal.html
and https://docs.kernel.org/6.2/gpu/amdgpu/driver-misc.html.

CPU perf recording was denied; `sudo -n` requires a password. System permissions
and sysctl were not changed, so no function-stack profile was obtained.

## Specific regression candidate

Comparing saved `baseline-new` and `startup-effects` captures from
`out/dev/corrupt-load-20261017/` identifies one common graphics pass whose
target size changed:

| VS / PS | Partial live SSR | Complete startup SSR |
| --- | --- | --- |
| `0b0acf50` / `86e96401` | RGBA16F, 960×540 | RGBA16F, 1920×1080 |

Fixing the incomplete SSR patch thus quadrupled that pass's pixel count.
Omitting the resize caused the incorrect live path; fixing the image was not
accompanied by a pass-timing comparison. Base scene cost may have risen enough
that, together with the previous FSR cost, it no longer fits in 10 ms.

Captures prove the fourfold target size, but neither fourfold time nor the exact
contribution to today's 13.8 ms was measured. Confirmation needs the same scene
with FSR 4.1.1 and SSR off/on. The startup SSR patch requires restarting.
GPU timestamps are not enabled in the current process; no calls were injected.

Inspecting cached SPIR-V `86e96401` with spirv-cross shows a simple pass with one
textureLod and an RGBA copy, without a reflection-tracing loop. Its increased size
alone therefore does not yet explain several milliseconds: the entire SSR path
and interaction with other passes need testing.
Decompilation saved in `out/dev/live-load-20261017/ssr-pass.frag`.
