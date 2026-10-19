# Crash after selecting an item — 2026-10-17

Log: `~/.local/share/bbport/logs/20261017_123530.log`; copy and analysis results:
`out/dev/crash-20261017-123530/`.
The user opened the inventory and probably clicked an item.

## Established from the log and game code

- SIGSEGV on `GXWorker:2`, guest offset `0x22a3f07`, NULL address, RAX=0.
- `mov rcx,[rax]` executes immediately after a call to `0xe669a0` with argument
  `r13+0x10d0`. This getter returns one of two pointers, `+0x68` or `+0xc0`;
  the second is selected when both flags `+0x1b8` and `+0x189`, relative to
  the argument, are nonzero.
- This branch runs with SSAO enabled: byte `[r13+0x2968] != 0`.
- At `0x22c4cb3` the game explicitly clears this byte if `[r13+0x48]` lacks bit 3.
  The neighboring branch with that bit creates resource `+0x10d0`.
- Our `ApplyHotEffects` previously wrote the user's `effect_ssao=1` to every known
  context on each application, including contexts where the game had cleared the flag.
  This is a real defect: the setting could enable a path without its resource.
- The saved log has no snapshot of R13 or that object's fields. Linking this particular
  crash to forced enabling is therefore a justified hypothesis, not a confirmed reproduction.
- Before the crash the game ran at about 93 FPS. No Bad PM4, Job allocation or Vulkan
  Device Lost messages precede it.

## Change

The local SSAO setting now permits enabling only with the support bit and a nonzero
selected resource, using the same selection rule as the game's getter. The user's SSAO-off
setting is preserved. Constructor/helper contexts without a resource remain off;
an eligible context can use SSAO again once the resource exists.
The SIGSEGV handler is unchanged; faulting instructions are not skipped.

The new native test checks missing support, primary resource present, both alternate-resource
selection flags, selected resource absent while the other exists, resource removal,
the off setting, and a short input buffer. The existing settings-test also runs and
bbgpu is built. Command results are recorded in `build-test.log`.

The game was not launched automatically for testing; it was neither closed nor its window
controlled. Confirming the crash fix requires repeating the item action in an updated build.
SSAO in other contexts also needs visual in-game validation.
