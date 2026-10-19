# Issues and PRs: what changed on 17–18 October 2026

Continuation of `GitHub_review_2026-10-17.md`. Evening API snapshot on 18 October:
151 open items (28 PRs), 40 updated since 17 October, 29 new comments.
Nothing was posted or closed on GitHub. Data: `~/.claude/jobs/9cdc30a2/tmp/gh/`.

## Main points

1. **The releases page marks 0.51 "latest", with two known failures fixed only
   in 0.6-pre1/locally:**
   - NVIDIA: `vkCreateDevice` → `ErrorInitializationFailed` (#247 RTX 4060 Ti,
     #252 RTX 4060 Laptop, probably #236). The driver advertises NGX DLSS extensions
     but device creation with them fails. 0.51 has no retry without DLSS; 0.6-pre1
     does (`gpu/vulkan/instance.cpp`, #135/#147). 0.51 workaround: `BB_DLSS=0`.
     #252's author says 0.4 works on the same machine (0.4 had no DLSS).
   - Online: PR #235 says shadNet has disconnected clients without a client version
     since 12 October; 0.51 does not report it. Local `bbnet20` reports
     `BB_CLIENT_VERSION`.
   Conclusion: users need a new release (0.6-pre2 or stable 0.6), not 0.51 patches.

2. **Port PR #206** (wait for deferred texture deletions before "VRAM is full",
   #163, #173): new report, RTX 3050 4 GB, 2 hours without a crash where Yharnam
   previously crashed. PR targets the old structure (`gpu/shadps4/video_core/...`);
   absent from the local tree.

3. **Quick fix: game text languages** (#249, Polish). The game has 27 text languages
   (`dvdroot_ps4/msg`: polpl, nldnl, porpt, porbr, turtr, korkr, zhocn, zhotw, dandk,
   finfi, norno, swese, enggb, spaar…), launcher only 7 (`LANGUAGES` in
   `bbport_launcher.py`). Add PS4 system-language codes: 6 Dutch, 7 Portuguese,
   9 Korean, 10/11 Traditional/Simplified Chinese, 12 Finnish, 13 Swedish, 14 Danish,
   15 Norwegian, 16 Polish, 17 Portuguese (Brazil), 18 English (UK), 19 Turkish,
   20 Spanish (Latin America); labels in the three `bbport_i18n.py` tables.

## New items (by number)

| # | What | Assessment |
|---|---|---|
| #255 | Above-30-FPS bugs: beard does not change in creator, messenger and Doll animations | Game logic tied to FPS (like Laurence hang). Workaround: 30-FPS limit (F3). Reply with known sites. |
| #254 (PR) | Steam Deck 16:10, 1280×800 | Targets `master`. 0.6-pre1 already has 16:10 and 1280×800. Reply that it is in 0.6. |
| #253 | RTX 3060 Ti: stretched face polygons with any upscaler | Resembles known face corruption (`Performance_regression_2026-10-17`, `Present_wait`). Need log/version. |
| #252, #247 | NVIDIA, `ErrorInitializationFailed` | See point 1: `BB_DLSS=0` or 0.6-pre1. |
| #251 | BB PC Remaster mod (Nexus #45) breaks graphics; mouse X speed depends on Y pitch | Mod replaces game files and targets shadPS4 (DMem +5000M, LOD −2, larger heaps). Check separately. Mouse resembles a real mouse-look bug (yaw depends on pitch). |
| #250 | RTX 4060 Laptop, Windows: `TranslateProgram` + `MarkReadConstBufferSharpSources` assert | Jgamrot Windows fork, not ours. |
| #249 | No Polish language | See point 3. |
| #248 | Crash after 15 s–1 min at the beginning | No logs; already requested. |
| #242 | Crash by two trolls, `bb-probe.exe` | Windows fork, not ours (already answered). |

## Fresh comments on older topics

- **#32** (RX 6600, RADV): two more guest faults 0x263b8e7 @ 0x5300000000; a third
  with the two-stage pipeline off, on the main thread; common stack prefix.
  The memcpy fix (4 October) did not fully close this case.
- **#222**: RX 580, new memory model crashes on startup (Polaris; compare #203, GPU labels).
- **#173**: "code 23" crash with VRAM 2.2/4 GB, log attached: not only memory exhaustion.
- **#178**: confirmation, RTX 3060 Laptop creator preview fixed in 0.6-pre1.
- **#186**: AUR Proton-GE installs to `/usr/share/steam/compatibilitytools.d/`;
  launcher misses it (only works via symlink in `~/.local/share/Steam/...`).
  Add system path to Proton search for FSR 4.1.1.
- **#46**: LSFG-VK fails with our build, works with ayozetr/bloodborne_linux.
- **#161**: users launch via ayozetr fork (Ubuntu 26.04).
- **#208**: vertical sensitivity higher than horizontal (DualSense, Xbox, Steam Controller).
- **#100**: BB PC Remaster mod crash on first werewolf hit (Windows fork).

## Not ours

#250, #242, #100 are Windows forks. Replies already exist in #222
("report forks to their authors").
