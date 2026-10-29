# Bloodborne CPU-binary analysis and initial static recompilation

Analysis date: 2026-10-09. Targets: Linux x86-64 and Linux ARM64 (AArch64).
This stage produced reproducible analysis and an AOT prototype for individual functions.
Full-game recompilation and an ARM64 launcher are not implemented yet.

## Main result

Existing `bbport` already executes original CPU code directly on x86-64:
`src/probe.c` maps the game image and calls its entry point;
`src/runtime_*.c` substitute PS4 system APIs. CPU recompilation is not required for
this variant. A separate ARM64 build needs behavior-preserving translation of all
executable game regions and used PS4 libraries.

Created `recompiler/` pipeline: plaintext SELF → validated ELF → unwind ranges and
control-flow graph → selected integer functions → LLVM IR → native x86-64 and AArch64
objects. Executing these AOT functions uses no instruction decoder, interpreter or JIT.
QEMU is used only in ARM64 tests.

## Exact binary analyzed

- Source: `game_files/CUSA03173/eboot.bin`.
- Edition: `CUSA03173`, APP_VER `01.09`.
- Original SELF SHA-256: `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9`.
- Loadable-image SHA-256: `071df19c8880086d97182dbc057bc8cb37badaca57d9112683836b24a0444c0a`.
- File size: 93,825,704 bytes; image: 91,042,036 bytes.
- ELF64 little-endian, x86-64, type `0xfe10`, FreeBSD OSABI.
- Entry point: `0xa0`; no ordinary ELF section headers.
- Plaintext SELF read; no decryption performed.

Image hash matches supported 1.09 in `scripts/game_check.py`.
Original game files are read; extracted images and recompiled code go to `out/recompiler/`.

## Recovered structure

| Measurement | Result |
|---|---:|
| FDE ranges from `.eh_frame_hdr` | 162,959 |
| Total size of those ranges | 41,719,719 bytes |
| RX segment size, including data and unwind | 84,776,668 bytes |
| Overlapping FDE ranges | 0 |
| FDE with LSDA pointer | 38 |
| Relocations | 235,000 |
| Imported symbols | 701 |
| Main-binary exported symbols | 0 |
| Relative relocations to known FDE starts | 149,926 |

An FDE gives an unwind range, not a proven boundary of every original C++ function.
RX segment contains constants and metadata; its size is not code size.
Dynamic names are PS4 NIDs with library/module IDs. The binary itself does not
provide names for all 162,959 ranges.

Relocation types: 7: 661, 8: 231,478, 1: 2,838, 6: 23.
Many code pointers live in data: ARM recompilation must do more than translate
direct `call`; vtables, callbacks and function pointers need a consistent representation.

## Instruction and control-flow traversal

Zydis decodes from known entries. Both conditional-branch arms are traversed within
the range. Direct calls are recorded as edges; indirect calls are not resolved;
an indirect jump ends the current branch. No search for isolated `E8`/`E9` bytes.

Additionally analyzed 606 direct-call entries without FDE, including 604 imported
PLT thunks. Their RIP-relative slots are matched to actual relocations and complete
import IDs. Nonreturning `exit`, `abort`, `__stack_chk_fail` are handled.
First pass mistakenly entered inline tables after these calls; fixing it reduced
undecodable addresses from 843 to 22.

Final counts below cover FDE traversal without adding the PLT pass:

| Measurement | Result |
|---|---:|
| Decoded instructions | 9,358,972 |
| Decoded bytes | 38,345,547 |
| Direct calls | 407,756 |
| Indirect calls | 158,095 |
| Indirect jumps | 15,073 |
| FS/GS accesses | 16,733 |
| LOCK instructions | 11,946 |
| CPU-flag-reading instructions | 820,619 |
| Calls to known noreturn thunks | 32,482 |
| Undecodable addresses | 22 |
| Instruction-boundary conflicts | 3 |
| Branches reaching FDE end without termination | 5,635 |

Incomplete CFG recovery. Indirect jump tables, some entries without unwind,
exception landing pads and continuations beyond FDE boundaries need separate analysis.
All remaining issues are in `cfg-issues.json`: graph-recovery issues, not proof
of game corruption.

Zydis classification by ISA extension:

| ISA extension | Instructions |
|---|---:|
| AVX | 852,131 |
| BASE | 8,452,210 |
| BMI1 | 3,910 |
| LONGMODE | 46,441 |
| LZCNT | 325 |
| MOVBE | 868 |
| PAUSE | 1,570 |
| RDTSCP | 1 |
| SSE | 1,338 |
| SSE2 | 60 |
| SSE4 | 118 |

Visible SIMD registers: XMM 844,157, YMM 8,427, ZMM 0 instructions.
AVX code is not necessarily 256-bit: VEX instructions also use 128-bit XMM.
Important for ARM NEON porting. Classification covers recovered main-binary code.

## Validated AOT prototype

Of 26,651 preliminary candidates the strict lifter accepted 9,613.
The test corpus selects 140 functions with distinct instruction sequences.

Limited contract: six raw integer inputs RDI/RSI/RDX/RCX/R8/R9, defined RAX result,
no memory accesses, calls or branches. A validated frame prologue/epilogue pair is
allowed. Implemented integer operations, partial registers, zero/sign extension,
shift-count masking, LEA from input registers, CMP/TEST, SETcc/CMOVcc and necessary flags.
Undefined inputs, unsupported semantics and unknown flags are rejected.
Original function names/signatures were neither recovered nor guessed.

| Check | Result |
|---|---|
| Original x86-64 bytes versus AOT x86-64 | 308,420 comparisons; 0 mismatches |
| AOT AArch64 versus original x86-64 results | 46,340 comparisons; 0 mismatches in QEMU; physical ARM untested |
| Object format | ELF64 x86-64 / ELF64 AArch64 |
| Undefined symbols in AOT objects | 0 |

Vectors include 8/16/32/64-bit integer boundaries, shift counts, zero inputs and
random 64-bit arguments; seed `0xbb109`. Compared RAX; full registers, FP state
and full-game ABI not checked. ARM64 test is a freestanding Linux ELF without libc
or dynamic interpreter. No physical ARM-processor checks.

Artifacts: `leaves.ll`, `leaves-x86_64.o`, `leaves-aarch64.o`, `leaves-x86_64.so`,
`arm-check`, `lift.json`, `verification.json`, disassembly of both objects.
They contain code derived from the local dump and remain in `out/`.

## Requirements for two full-game launch variants

1. Finish CFG recovery: resolve 22 decode failures, 3 conflicts, 5,635 exits beyond
   range boundaries; resolve switch tables, callbacks and exception landing pads.
   Build tests for new function classes against original x86-64.
2. Add full memory, stack, branch, SSE/AVX/BMI and FP lifter. Preserve x86 flags,
   MXCSR/FP rounding, NaN behavior, memory ordering and LOCK. On ARM, ordinary C
   writes cannot replace x86 atomics and TSO.
3. Introduce consistent mapping of guest code addresses to AOT entry points.
   Direct calls, vtables, stored callbacks, thread creation and runtime callbacks
   must share one model. Data addresses and PS4 layout preserved.
4. Translate or replace used PS4 PRX. `bbport` currently links `libc.prx` and
   `libSceFios2.prx` as original x86 code; ARM needs them too:

   | Module | RX bytes | FDE | Imports |
   |---|---:|---:|---:|
   | libc.prx | 751,908 | 2,164 | 79 |
   | libSceFios2.prx | 309,956 | 650 | 83 |

5. Port architecture-specific runtime parts: ARM prohibition in `src/probe.c`,
   x86 entry/import-trampoline asm, FS→GS/`arch_prctl` in `runtime_thread.c`,
   `REG_RIP`/`ucontext` handlers, guest `setjmp`/unwind and SysV→AAPCS64 bridges.
   Check GPU-core architectural dependencies: SIMD headers, trap handlers,
   Xbyak in `flatten_extended_userdata_pass.cpp`: its non-x86 branch currently calls
   `UNREACHABLE_MSG` without implementing the pass. Vulkan renderer remains necessary.
6. Produce separate ARM64 executable and sequential smoke checks:
   entry → initialization → title screen → save loading → gameplay/audio/saving.
   Only afterwards add CPU-architecture selection and packaging for two builds.

Prototype confirms practical translation of specific functions to both ISAs.
It does not confirm automatic whole-game porting or equal performance.
x86-64 direct execution can remain the working variant and reference for ARM64 verification.

## Reproduction

From `bbport/`:

```bash
nix-shell recompiler/shell.nix --run 'bash recompiler/run.sh ../game_files/CUSA03173'
```

Requires GCC, CMake, Ninja, Python 3, Zydis 4, LLVM 21, LLD and QEMU user-mode.
Current run: GCC 15.3, Zydis 4.1.1, LLVM 21.1.8, LLD 22.0 (ROCm), QEMU 11.1.1.
Can also run `bash recompiler/run.sh GAME_DIR` in a prepared environment.
`BB_RECOMP_OUT` sets artifact directory; `BB_LLVM_BIN`, `BB_LLD`,
`BB_QEMU_AARCH64` select installed tools. Pipeline checks source binary hash
and does not launch the game.

## Sources for the next stage

[Remill](https://github.com/lifting-bits/remill) was considered for lifter expansion:
a machine-instruction semantics and LLVM IR lifting library, including amd64.
It does not automatically solve PS4 runtime/CFG and is not integrated into the prototype.
[McSema limitations](https://github.com/lifting-bits/mcsema/blob/master/docs/Limitations.md)
separately cover code/data recovery, self-modifying code and exceptions;
it cannot be treated as a ready whole-game converter.

ARM call bridge must follow
[AAPCS64](https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst);
exception porting needs separate analysis of the
[C++ Exception Handling ABI](https://itanium-cxx-abi.github.io/cxx-abi/abi-eh.html).
All numerical results above came from local tools applied to the specified SELF.
