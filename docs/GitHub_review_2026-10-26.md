# GitHub: review of 26 October 2026

Snapshot via the GitHub REST API (read-only) on 26.10 ~17:30: **136 open issues, 24 open
PRs**, 65 closed since 17.10 (mostly at the 0.6 release), 185 new comments. Raw data is in
the session `scratchpad` (issues/PRs/comments in JSON). The "locally" status is from session
logs and memory: changes made after 0.6, not yet published.

Nothing has been closed or commented on — this is a release list.

## Pull requests (24)

### Already merged locally — close at the release with thanks and attribution (Co-authored-by)

| PR | Author | What | State |
|---|---|---|---|
| [#343](https://github.com/deadinside28/bloodborne_pc/pull/343) | whp199 | GX occlusion query guard (crash 0x2169edc, issue #336) | merged 22.10 (now `games/bloodborne/hooks_gx.cpp`) |
| [#342](https://github.com/deadinside28/bloodborne_pc/pull/342) | whp199 | BBSC: hunter's kit, Kin Bell, summons | merged 22.10 **partially**: without his memory.h/glue (we have our own solution, #282), the sign/summon zone patches taken |
| [#346](https://github.com/deadinside28/bloodborne_pc/pull/346) | DominickCobb-rs | BBSC off → restore the vanilla bells | merged 22.10 (+ a printf fix for Windows) |
| [#339](https://github.com/deadinside28/bloodborne_pc/pull/339) | maiconjsv | test_online with a module path | merged 22.10; after the old module was removed the test checks only libbbnet20 |
| [#293](https://github.com/deadinside28/bloodborne_pc/pull/293) | iannitram | FSR 3.1 not in protected memory (issue #85, ROG Ally) | merged overnight 19.10 |
| [#260](https://github.com/deadinside28/bloodborne_pc/pull/260) | adds39939 | DLSS Frame Generation + Reflex | merged overnight 19.10 (+ AMD Anti-Lag 2 on top) |
| [#225](https://github.com/deadinside28/bloodborne_pc/pull/225) | AndiMajore | present mode FifoRelaxed | merged overnight 19.10 |
| [#157](https://github.com/deadinside28/bloodborne_pc/pull/157) | Qiming-Liu | Chinese launcher translation | merged overnight 19.10 |

### Outdated (0.51 code / `gpu/shadps4`, which no longer exists) — close with an explanation

| PR | What | Why |
|---|---|---|
| [#226](https://github.com/deadinside28/bloodborne_pc/pull/226) | liverpool coroutine frame leak | the author himself writes: 0.51 only, in 0.6 the command processor is different |
| [#223](https://github.com/deadinside28/bloodborne_pc/pull/223) | RTAO (ray-traced AO) | on `gpu/shadps4`; the author (AndiMajore) ported it to 0.6 but has not opened the PR yet — wait for a new PR |
| [#167](https://github.com/deadinside28/bloodborne_pc/pull/167) | shader replacement by hash (shader patches) | on the old pipeline cache; the idea can be carried over if needed |
| [#138](https://github.com/deadinside28/bloodborne_pc/pull/138) | Windows port on 0.51 (Ifjy) | we have our own Windows build on the new memory model |
| [#127](https://github.com/deadinside28/bloodborne_pc/pull/127) | "Trophies" (a huge Windows branch) | trophies are already taken from guutol's commit; the PR itself is an old 301-file branch |
| [#24](https://github.com/deadinside28/bloodborne_pc/pull/24) | mouse and keymap (draft) | native mouse look and the keymap already exist |
| [#6](https://github.com/deadinside28/bloodborne_pc/pull/6) | Windows port (yumlevi) | see #138 |
| [#50](https://github.com/deadinside28/bloodborne_pc/pull/50) | "Thhee" | no description, a copy of the old tree |

### Needs a decision

| PR | Author | What | Comment |
|---|---|---|---|
| [#364](https://github.com/deadinside28/bloodborne_pc/pull/364) | AndiMajore | trophies: per-user storage, in-game notifications with names and icons (needs the player's trophy key) | **overlaps** with our guutol trophy port (`runtime_trophy.c`, `trophies.jsonl`); decide whose storage to keep and take the notifications/icons |
| [#360](https://github.com/deadinside28/bloodborne_pc/pull/360) | wheat32 | large graphics heaps for texture packs (auto-detect the pack, `BB_DMEM_MB=9152`) | closes #240 and #283 (the same author confirmed the workaround); check whether it conflicts with our on-demand GraphicsPrivate heap growth |
| [#296](https://github.com/deadinside28/bloodborne_pc/pull/296) | whp199 | bbnet20: clear login messages, no passwords in logs, UPnP lease | not merged; useful (passwords in logs that people attach to issues); check for conflicts with the 25.10 BBSC 0.0.2 port |
| [#347](https://github.com/deadinside28/bloodborne_pc/pull/347) | Sarxzer | French launcher translation | simple; conflicts only with the i18n edits |
| [#156](https://github.com/deadinside28/bloodborne_pc/pull/156) | AyrtonSanabio | Portuguese (Brazilian) launcher translation | same |
| [#165](https://github.com/deadinside28/bloodborne_pc/pull/165) | AndiMajore | `BB_FAULT_WAIT=1` — the process waits for gdb on a crash | small; file paths are from 0.51 (`gpu/shim/common/assert.cpp`), port by hand |
| [#79](https://github.com/deadinside28/bloodborne_pc/pull/79) | Convez | build via nix flake | optional |
| [#8](https://github.com/deadinside28/bloodborne_pc/pull/8) | yogesh1239 | FSR 4.1.1 FP8 on RDNA4 | we already have an FP8 variant for RDNA4 (done separately) — likely close, noting this |

## Issues: fixed locally after 0.6 (close at the release, ask people to re-check)

| Issue | What | What was done |
|---|---|---|
| [#307](https://github.com/deadinside28/bloodborne_pc/issues/307) | version number in the launcher | VERSION file (0.7-dev), launcher/run.sh/run.py/Windows |
| [#304](https://github.com/deadinside28/bloodborne_pc/issues/304), [#334](https://github.com/deadinside28/bloodborne_pc/issues/334) | the L3+R3 overlay menu triggers in combat | opens only when L3+R3 is held for 0.8 s (#334 also asks for a disable/remap — partially) |
| [#290](https://github.com/deadinside28/bloodborne_pc/issues/290) | key descriptions not in English | 15 strings filled in |
| [#299](https://github.com/deadinside28/bloodborne_pc/issues/299), [#366](https://github.com/deadinside28/bloodborne_pc/issues/366) | button icon choice | `button_prompts=auto/playstation/xbox/keyboard` in bbport.ini and the launcher (#366 — wrong icons before the first press; forcing a choice works around it) |
| [#291](https://github.com/deadinside28/bloodborne_pc/issues/291) | borders on the Deck at 1280×800 | fullscreen mode forced under gamescope |
| [#269](https://github.com/deadinside28/bloodborne_pc/issues/269), [#321](https://github.com/deadinside28/bloodborne_pc/issues/321) | Chinese text, Japanese voice, languages tied to region | per-region language tables found; `game_text_language`/`game_voice_language` (Japanese voice not checked by ear) |
| [#234](https://github.com/deadinside28/bloodborne_pc/issues/234), [#328](https://github.com/deadinside28/bloodborne_pc/issues/328) | blur on Wayland at 200% | SDL high pixel density + `SDL_VIDEO_WAYLAND_SCALE_TO_DISPLAY=1` by default |
| [#282](https://github.com/deadinside28/bloodborne_pc/issues/282), [#313](https://github.com/deadinside28/bloodborne_pc/issues/313) | BBSC on Linux: no bell set, `?GoodsName?` | reading the game image for BBSC (our own low-range table) + PR #342/#346; you confirmed "the connection appeared" on 22.10 |
| [#336](https://github.com/deadinside28/bloodborne_pc/issues/336) | crash 0x2169edc (GX query) | PR #343 |
| [#213](https://github.com/deadinside28/bloodborne_pc/issues/213) | hang when selecting the upscaler in the menu (Deck) | FSR 4/4.1.1 contexts are created in the background |
| [#85](https://github.com/deadinside28/bloodborne_pc/issues/85) | FSR 3.1 garbage on the ROG Ally | PR #293 |
| [#289](https://github.com/deadinside28/bloodborne_pc/issues/289) | crash with mako FG | the Anti-Lag layer on Linux only with `BB_ANTI_LAG=1` (marked #289 in the code) |
| [#212](https://github.com/deadinside28/bloodborne_pc/issues/212) | mods do not roll back | mod-state backup (`mods.last`) |
| [#358](https://github.com/deadinside28/bloodborne_pc/issues/358) | Deck: mouse/gamepad switching jerks the camera | keyboard/mouse events from Steam Input are dropped while the overlay is closed (23.10) — probably this |
| [#345](https://github.com/deadinside28/bloodborne_pc/issues/345) | FSR 4.1.2 / driver DLLs for RDNA2 | INT8 RDNA2 / Lite models from `amdxcffx64.dll` (23.10, not checked by you) |
| [#368](https://github.com/deadinside28/bloodborne_pc/issues/368), [#253](https://github.com/deadinside28/bloodborne_pc/issues/253) | "vertex explosion" after returning to the Dream | bindings across the chunk boundary of the growing heap read a stale copy; fixed 25.10 (`LayerStitch`), not checked |

## Issues: probably already fixed, needs re-checking with the authors

- Gestures do not open: [#241](https://github.com/deadinside28/bloodborne_pc/issues/241), [#188](https://github.com/deadinside28/bloodborne_pc/issues/188), [#180](https://github.com/deadinside28/bloodborne_pc/issues/180), [#196](https://github.com/deadinside28/bloodborne_pc/issues/196) — work in the current build (touchpad left / Back).
- Startup crash on NVIDIA, RIP=0: [#181](https://github.com/deadinside28/bloodborne_pc/issues/181), [#219](https://github.com/deadinside28/bloodborne_pc/issues/219), [#229](https://github.com/deadinside28/bloodborne_pc/issues/229) — fix via `GBM_BACKENDS_PATH` (19.10), not checked on NVIDIA; new comments 21–23.10 still on 0.6.
- [#238](https://github.com/deadinside28/bloodborne_pc/issues/238) Hemwick: objects stop loading — render resource cache (fixed 19.10).
- [#155](https://github.com/deadinside28/bloodborne_pc/issues/155) FPS drop after creating a character (= save switch, fixed).
- [#227](https://github.com/deadinside28/bloodborne_pc/issues/227) copy shader 1.65 ms — no longer in the top.
- [#231](https://github.com/deadinside28/bloodborne_pc/issues/231) Vulkan in `bbport_dlss` — fixed.
- [#92](https://github.com/deadinside28/bloodborne_pc/issues/92) Ludwig's blade flicker (0.4) — gone with the new model, which is now the default.
- [#88](https://github.com/deadinside28/bloodborne_pc/issues/88) VK_KHR_surface (0.4) = #172, closed.
- [#143](https://github.com/deadinside28/bloodborne_pc/issues/143) DoF and sky flicker (0.4) — the ConstRam race was fixed on 07.10.
- [#11](https://github.com/deadinside28/bloodborne_pc/issues/11) item icons flicker (0.3).
- Old versions 0.2–0.51 with no new messages: [#41](https://github.com/deadinside28/bloodborne_pc/issues/41), [#42](https://github.com/deadinside28/bloodborne_pc/issues/42), [#47](https://github.com/deadinside28/bloodborne_pc/issues/47), [#40](https://github.com/deadinside28/bloodborne_pc/issues/40), [#61](https://github.com/deadinside28/bloodborne_pc/issues/61), [#4](https://github.com/deadinside28/bloodborne_pc/issues/4), [#56](https://github.com/deadinside28/bloodborne_pc/issues/56), [#98](https://github.com/deadinside28/bloodborne_pc/issues/98), [#97](https://github.com/deadinside28/bloodborne_pc/issues/97), [#28](https://github.com/deadinside28/bloodborne_pc/issues/28), [#111](https://github.com/deadinside28/bloodborne_pc/issues/111), [#169](https://github.com/deadinside28/bloodborne_pc/issues/169), [#139](https://github.com/deadinside28/bloodborne_pc/issues/139), [#118](https://github.com/deadinside28/bloodborne_pc/issues/118), [#200](https://github.com/deadinside28/bloodborne_pc/issues/200), [#20](https://github.com/deadinside28/bloodborne_pc/issues/20), [#7](https://github.com/deadinside28/bloodborne_pc/issues/7) — close with a request to reopen on the new version.

## Issues: open, needs work

**Crashes and hangs**
- [#32](https://github.com/deadinside28/bloodborne_pc/issues/32) **the main open crash**: 0x263b8e7, address 0x5300000000 (pool corruption, all reports on AMD, including the Deck). A new lead (rcopra, 21.10): the whole session the texture cache is above the critical mark, 241–1032 evictions right before the crash → the GC eviction path. Two-hour runs on the Deck did not catch it.
- [#369](https://github.com/deadinside28/bloodborne_pc/issues/369) **new (25.10)**: assert "flip interrupt out of order [videoout.cpp:394]" about ~1 s after an autosave (RTX 2080 SUPER, 0.6, DLSS, 60 FPS, Hyprland, second monitor). Detailed report.
- [#355](https://github.com/deadinside28/bloodborne_pc/issues/355) 0.6 crash (log only; the log has `m27_9999.tpf.dcx not found`, as in #240).
- [#340](https://github.com/deadinside28/bloodborne_pc/issues/340), [#341](https://github.com/deadinside28/bloodborne_pc/issues/341), [#359](https://github.com/deadinside28/bloodborne_pc/issues/359) Intel UHD 620 / laptops without a discrete card: device lost at submit, code 23.
- [#262](https://github.com/deadinside28/bloodborne_pc/issues/262) crash in `ucrtbase.dll` (bb-probe.exe, 18.10) — this is the Windows fork; a new comment on 25.10 with an Intel 12700K is also about Windows.
- [#261](https://github.com/deadinside28/bloodborne_pc/issues/261) crash at startup (NVIDIA 595 CreateDevice).
- [#184](https://github.com/deadinside28/bloodborne_pc/issues/184) NVIDIA Xid 109 in Gaol/Yharnam only with DoF + motion blur (new confirmation on 0.6, 25.10).
- [#344](https://github.com/deadinside28/bloodborne_pc/issues/344) dead enemies fall through the ground — exists in the original too, but happens more often for us (physics at high FPS?).

**Memory and performance**
- [#335](https://github.com/deadinside28/bloodborne_pc/issues/335) VRAM "leak" over an hour on the RTX 5060 Ti 8 GB.
- [#332](https://github.com/deadinside28/bloodborne_pc/issues/332) RX 580: bad frame pacing from texture eviction (player workaround: `BB_GUEST_GPU_MEMORY=0`).
- [#315](https://github.com/deadinside28/bloodborne_pc/issues/315) one core at 100%, GPU at 50% (Gascoigne, Amelia, Hemwick) — bottlenecked on stage A/B on the CPU.
- [#240](https://github.com/deadinside28/bloodborne_pc/issues/240), [#283](https://github.com/deadinside28/bloodborne_pc/issues/283) crash/flicker in Iosefka's clinic with texture packs → PR #360.
- Polaris (RX 570/580): [#131](https://github.com/deadinside28/bloodborne_pc/issues/131), [#105](https://github.com/deadinside28/bloodborne_pc/issues/105) — the old model was removed, only the new one remains.

**Graphics**
- [#308](https://github.com/deadinside28/bloodborne_pc/issues/308) world blur after spawning — reproduced 25.10: the game's own motion blur with the wrong previous camera; hypothesis — a stale VRAM mirror of the constant buffer. Not fixed.
- [#365](https://github.com/deadinside28/bloodborne_pc/issues/365) Boom Hammer smoke artifacts (FSR 4.1.1, Deck) — possibly the reactive mask (fix 25.10, not checked).
- [#237](https://github.com/deadinside28/bloodborne_pc/issues/237) edge flicker with DLSS FG.
- [#194](https://github.com/deadinside28/bloodborne_pc/issues/194) red/yellow screen in the Forbidden Woods.
- [#182](https://github.com/deadinside28/bloodborne_pc/issues/182) AMD BC-250: orange fringe, gray squares.
- [#18](https://github.com/deadinside28/bloodborne_pc/issues/18) ghosting (collecting locations).

**Controls and the rest**
- [#361](https://github.com/deadinside28/bloodborne_pc/issues/361) Deck back buttons and touchpads — only via Steam Input.
- [#325](https://github.com/deadinside28/bloodborne_pc/issues/325) camera on an Xbox gamepad at 90+ FPS — not reproduced; the author needs `BB_PAD_TRACE=2 BB_CAMLOG=1`.
- [#208](https://github.com/deadinside28/bloodborne_pc/issues/208) vertical camera speed higher than horizontal — that is how the game itself is (338°/s vs 159°/s); X/Y speeds already exist in the launcher → reply.
- [#354](https://github.com/deadinside28/bloodborne_pc/issues/354) THD: reconnecting from the main menu does not work.
- [#356](https://github.com/deadinside28/bloodborne_pc/issues/356) character presets are not saved, the model freezes.
- [#362](https://github.com/deadinside28/bloodborne_pc/issues/362) no .desktop when building the AppImage from source via `packaging/appimage.sh` (per the 21.10 log our AppImage has it — check this exact build path); older ones: [#287](https://github.com/deadinside28/bloodborne_pc/issues/287), [#132](https://github.com/deadinside28/bloodborne_pc/issues/132), [#133](https://github.com/deadinside28/bloodborne_pc/issues/133).
- Steam overlay / MangoHud in the AppImage: [#217](https://github.com/deadinside28/bloodborne_pc/issues/217), [#77](https://github.com/deadinside28/bloodborne_pc/issues/77), [#66](https://github.com/deadinside28/bloodborne_pc/issues/66) — disabled on purpose (needs the host's libGL).
- [#350](https://github.com/deadinside28/bloodborne_pc/issues/350) "failed to start the embedded python interpreter" — according to the author, the launcher got corrupted by an update during play; looks like someone else's build.

## Feature requests

[#363](https://github.com/deadinside28/bloodborne_pc/issues/363) launcher on RmlUi · [#357](https://github.com/deadinside28/bloodborne_pc/issues/357) a mod from the Izz glitch · [#319](https://github.com/deadinside28/bloodborne_pc/issues/319) DS3 icons · [#298](https://github.com/deadinside28/bloodborne_pc/issues/298) 16:10 (already works, answered in the comments) · [#233](https://github.com/deadinside28/bloodborne_pc/issues/233) shader precompilation (done: recipes) · [#220](https://github.com/deadinside28/bloodborne_pc/issues/220), [#201](https://github.com/deadinside28/bloodborne_pc/issues/201) cheat menu (was in the fork) · [#198](https://github.com/deadinside28/bloodborne_pc/issues/198) DLC on CUSA00900 · [#176](https://github.com/deadinside28/bloodborne_pc/issues/176), [#148](https://github.com/deadinside28/bloodborne_pc/issues/148) launching without the launcher (`--play`) · [#168](https://github.com/deadinside28/bloodborne_pc/issues/168) GTAO (VBAO done) · [#160](https://github.com/deadinside28/bloodborne_pc/issues/160) repository description · [#150](https://github.com/deadinside28/bloodborne_pc/issues/150) trophy key (PR #364) · [#94](https://github.com/deadinside28/bloodborne_pc/issues/94) DLSS/FSR (done) · [#73](https://github.com/deadinside28/bloodborne_pc/issues/73) button combinations · [#72](https://github.com/deadinside28/bloodborne_pc/issues/72) macOS (there is a fork) · [#46](https://github.com/deadinside28/bloodborne_pc/issues/46) LSFG-VK (in the comments: works via `LSFGVK_PROFILE`) · [#37](https://github.com/deadinside28/bloodborne_pc/issues/37), [#21](https://github.com/deadinside28/bloodborne_pc/issues/21) Windows and other platforms (a Windows build is being prepared) · [#25](https://github.com/deadinside28/bloodborne_pc/issues/25) build system · [#16](https://github.com/deadinside28/bloodborne_pc/issues/16) a game speed map for motion vectors · [#255](https://github.com/deadinside28/bloodborne_pc/issues/255), [#58](https://github.com/deadinside28/bloodborne_pc/issues/58) physics at FPS above 30/60 (the game engine).

## Not about this project / meta

- Forks: [#250](https://github.com/deadinside28/bloodborne_pc/issues/250) (Jgamrot), [#242](https://github.com/deadinside28/bloodborne_pc/issues/242), [#114](https://github.com/deadinside28/bloodborne_pc/issues/114) (Windows forks), [#262](https://github.com/deadinside28/bloodborne_pc/issues/262).
- Unsupported CPUs without BMI1/MOVBE: [#221](https://github.com/deadinside28/bloodborne_pc/issues/221), [#26](https://github.com/deadinside28/bloodborne_pc/issues/26), [#230](https://github.com/deadinside28/bloodborne_pc/issues/230) (Xeon/i7-3770; #26 has a probe.c patch from players).
- Support: [#329](https://github.com/deadinside28/bloodborne_pc/issues/329) (libcuda, answered: #135), [#82](https://github.com/deadinside28/bloodborne_pc/issues/82), [#87](https://github.com/deadinside28/bloodborne_pc/issues/87), [#107](https://github.com/deadinside28/bloodborne_pc/issues/107), [#187](https://github.com/deadinside28/bloodborne_pc/issues/187), [#189](https://github.com/deadinside28/bloodborne_pc/issues/189), [#216](https://github.com/deadinside28/bloodborne_pc/issues/216) (not reproduced).
- Meta and questions: [#222](https://github.com/deadinside28/bloodborne_pc/issues/222) (your announcement — pin it?), [#300](https://github.com/deadinside28/bloodborne_pc/issues/300) (PR attribution — do it on push), [#65](https://github.com/deadinside28/bloodborne_pc/issues/65), [#23](https://github.com/deadinside28/bloodborne_pc/issues/23), [#5](https://github.com/deadinside28/bloodborne_pc/issues/5).

## What to take on (suggestion)

1. [#369](https://github.com/deadinside28/bloodborne_pc/issues/369) — the flip-interrupt-order assert after an autosave: fresh, reproducible, with a full report.
2. [#32](https://github.com/deadinside28/bloodborne_pc/issues/32) — pool corruption: check the GC eviction lead (the cache above the critical mark the whole session).
3. [#308](https://github.com/deadinside28/bloodborne_pc/issues/308) — blur after a teleport: check the stale constant-buffer mirror hypothesis.
4. PRs [#360](https://github.com/deadinside28/bloodborne_pc/pull/360) and [#296](https://github.com/deadinside28/bloodborne_pc/pull/296) — review and merge if they do not conflict.
5. PR [#364](https://github.com/deadinside28/bloodborne_pc/pull/364) — decide about trophies (their notifications on top of our storage?).
