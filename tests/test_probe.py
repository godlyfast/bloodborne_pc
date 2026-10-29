# SPDX-FileCopyrightText: Copyright 2026 bbport contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Boundary tests for the native loader; uses tiny synthetic x86-64 images."""
from paths import ROOT
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

EXE = ROOT / 'out/bb-probe'


def package(code, relocs=(), names=(), capabilities=None):
    image = code.ljust(4096, b'\0')
    header = struct.pack('<8sQQQQQ', b'BBPROBE1' if capabilities is None else b'BBPROBE2', len(image), 0, 1, len(relocs), len(names))
    if capabilities is not None:
        header += struct.pack('<Q', capabilities)
    segment = struct.pack('<QQQ', 0, len(image), 5)
    return (header + segment + b''.join(n.encode().ljust(128, b'\0') for n in names)
            + b''.join(struct.pack('<QQqq', *r) for r in relocs) + image)


def native_package(name='fixture-native', binding_address=4112, binding_kind=1,
                   lib_flags=5, init=b'\x31\xc0\xc3', native=b'\xc3', metadata=None):
    # Main calls an import then tail-jumps to the terminal diagnostic import.
    code = b'\x48\x83\xec\x08\xff\x15\x16\0\0\0\x48\x83\xc4\x08\xff\x25\x14\0\0\0'
    image = code.ljust(4096,b'\0') + init.ljust(16,b'\0') + native
    image = image.ljust(12288,b'\0')
    header=struct.pack('<8s6Q',b'BBPROBE3',len(image),0,3,2,2,1)
    meta=metadata or (4096,8192,4096,8192,32,4,1,256)
    return (header + struct.pack('<8Q',*meta) + struct.pack('<3Q',0,binding_address,binding_kind)
            + struct.pack('<9Q',0,4096,5,4096,4096,lib_flags,8192,4096,6)
            + name.encode().ljust(128,b'\0') + b'after-native'.ljust(128,b'\0')
            + struct.pack('<8Q',32,1,0,0,40,1,1,0) + image)


@unittest.skipUnless(EXE.exists(), 'build native probe first')
class LoaderTests(unittest.TestCase):
    def test_invalid_content_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'content.bin'
            for data in (b'BBCONT01',struct.pack('<8s5I',b'BBCONT01',2,0,0,0,0),
                         struct.pack('<8s5I',b'BBCONT01',3,0,0,0,0)+b'extra'):
                with self.subTest(data=data):
                    path.write_bytes(data)
                    r=self.run_image(package(b'\xc3'),'--content-profile',str(path))
                    self.assertEqual(r.returncode,1,r.stdout+r.stderr)
                    self.assertIn('content profile',r.stderr)

    def run_image(self, data, *options):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'boot.bin'
            path.write_bytes(data)
            return subprocess.run([str(EXE.resolve()), str(path), '--cpu-only', *options],
                                  capture_output=True, text=True, timeout=5)

    def test_original_instruction_reaches_named_import(self):
        # jmp [rip+2]; two padding bytes; relocated function pointer at +8
        r = self.run_image(package(b'\xff\x25\x02\0\0\0\x90\x90', [(8, 1, 0, 0)], ['fixture-import']))
        self.assertEqual(r.returncode, 20, r.stderr)
        self.assertIn('first unsupported PS4 import: fixture-import', r.stdout)

    def test_native_initializer_and_export_return(self):
        r=self.run_image(native_package())
        self.assertEqual(r.returncode,20,r.stdout+r.stderr)
        self.assertIn('Module 0 initializer returned 0',r.stdout)
        self.assertIn('first unsupported PS4 import: after-native',r.stdout)

    def test_host_contract_takes_priority_over_native_export(self):
        r=self.run_image(native_package(name='bzQExy189ZI#q#q',native=b'\x0f\x0b'))
        self.assertEqual(r.returncode,20,r.stdout+r.stderr)
        self.assertIn('_init_env returned',r.stdout)
        self.assertIn('first unsupported PS4 import: after-native',r.stdout)

    def test_strict_mode_skips_native_initialization_and_binding(self):
        r=self.run_image(native_package(init=b'\x0f\x0b'), '--strict-imports')
        self.assertEqual(r.returncode,20,r.stdout+r.stderr)
        self.assertIn('first unsupported PS4 import: fixture-native',r.stdout)
        self.assertNotIn('Starting native libc',r.stdout)

    def test_native_metadata_and_bindings_are_validated(self):
        for kwargs,message in [
            ({'binding_address':12288},'invalid native binding'),
            ({'binding_kind':2},'native export kind/range mismatch'),
            ({'lib_flags':4},'native function is not executable'),
            ({'metadata':(4096,8192,4096,8192,32,33,1,256)},'invalid linked module metadata'),
            ({'metadata':(4096,8192,4096,8192,32,4,1,12280)},'unmapped procparam'),
        ]:
            with self.subTest(kwargs=kwargs):
                r=self.run_image(native_package(**kwargs))
                self.assertEqual(r.returncode,1,r.stdout+r.stderr)
                self.assertIn(message,r.stderr)

    def test_failed_native_initializer_does_not_enter_game(self):
        r=self.run_image(native_package(init=b'\xb8\x01\0\0\0\xc3'))
        self.assertEqual(r.returncode,1,r.stdout+r.stderr)
        self.assertIn('module initializer failed',r.stderr)
        self.assertNotIn('Entering original',r.stdout)

    def test_base_relative_address_is_relocated(self):
        # jump via a relative relocation to code at +16, then to an import at +24
        code = b'\xff\x25\x02\0\0\0\x90\x90' + b'\0'*8 + b'\xff\x25\x02\0\0\0\x90\x90'
        r = self.run_image(package(code, [(8, 0, 16, 0), (24, 1, 0, 0)], ['after-relative-jump']))
        self.assertEqual(r.returncode, 20, r.stderr)
        self.assertIn('after-relative-jump', r.stdout)

    def test_out_of_bounds_relocation_is_rejected(self):
        r = self.run_image(package(b'\xc3', [(4092, 0, 0, 0)]))
        self.assertEqual(r.returncode, 1)
        self.assertIn('bad relocation', r.stderr)

    def test_truncated_image_is_rejected(self):
        r = self.run_image(package(b'\xc3')[:-1])
        self.assertEqual(r.returncode, 1)
        self.assertIn('incorrect memory image size', r.stderr)

    def test_illegal_instruction_reports_guest_offset(self):
        r = self.run_image(package(b'\x0f\x0b'))
        self.assertEqual(r.returncode, 132)
        self.assertIn('at guest offset 0x0,', r.stderr)

    def test_fatal_signal_reports_full_context(self):
        r = self.run_image(package(b'\x0f\x0b'))
        self.assertEqual(r.returncode, 132, r.stderr)
        for register in ('RAX', 'RBX', 'RCX', 'RDX', 'RSI', 'RDI', 'RBP', 'RSP',
                         'R8', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15',
                         'RIP', 'RFLAGS', 'ERR', 'TRAPNO'):
            self.assertRegex(r.stderr, rf'\b{register}=[0-9a-f]{{16}}\b')

    def test_guest_store_fault_preserves_addressing_registers(self):
        value = 0x1122334455667788
        # xor r12,r12; movabs r13,value; mov [r12+8],r13.
        code = b'\x4d\x31\xe4\x49\xbd' + struct.pack('<Q', value) + b'\x4d\x89\x6c\x24\x08'
        r = self.run_image(package(code))
        self.assertEqual(r.returncode, 139, r.stderr)
        self.assertIn('address 0x8', r.stderr)
        self.assertIn('R12=0000000000000000', r.stderr)
        self.assertIn(f'R13={value:016x}', r.stderr)
        self.assertIn('signal=000000000000000b', r.stderr)
        self.assertIn('address=0000000000000008', r.stderr)

    def test_runtime_returns_from_verified_init_env(self):
        # Align stack, call _init_env through +32, then tail-jump to unknown +40.
        code = b'\x48\x83\xec\x08\xff\x15\x16\0\0\0\x48\x83\xc4\x08\xff\x25\x14\0\0\0'
        data = package(code, [(32,1,0,0),(40,1,1,0)], ['bzQExy189ZI#q#q','after-init'], 1)
        r = self.run_image(data)
        self.assertEqual(r.returncode,20,r.stderr)
        self.assertIn('first unsupported PS4 import: after-init',r.stdout)
        self.assertIn('_init_env=1',r.stdout)
        strict = self.run_image(data,'--strict-imports')
        self.assertEqual(strict.returncode,20,strict.stderr)
        self.assertIn('first unsupported PS4 import: bzQExy189ZI#q#q',strict.stdout)

    def test_unverified_runtime_stays_disabled(self):
        r = self.run_image(package(b'\xff\x25\x02\0\0\0\x90\x90',[(8,1,0,0)],['bzQExy189ZI#q#q'],0))
        self.assertEqual(r.returncode,20,r.stderr)
        self.assertIn('_init_env=0',r.stdout)

    def test_unknown_capabilities_rejected(self):
        r = self.run_image(package(b'\xc3',capabilities=2))
        self.assertEqual(r.returncode,1)
        self.assertIn('unknown runtime capabilities',r.stderr)


class FaultContextTests(unittest.TestCase):
    def test_essential_registers_precede_optional_gpu_diagnostics(self):
        # Exercise the production handler; the optional diagnostic deliberately cannot finish.
        source = r'''
#define main probe_program_main
#include "src/probe.c"
#undef main
__thread sigjmp_buf *runtime_fault_recover;
void runtime_re_watch_report(void) {}
int bbgpu_handle_fault(void *context, void *address) {
    (void)context; (void)address; return 0;
}
void bbgpu_dump_guest_writes(void *context) {
    (void)context;
    const char marker[] = "optional GPU diagnostic failed\n";
    ssize_t n = write(2, marker, sizeof(marker)-1); (void)n;
    _exit(99);
}
static void deliver(int sig, siginfo_t *info, void *context) {
    ucontext_t *uc = context;
    for (int i=0; i<NGREG; ++i) uc->uc_mcontext.gregs[i] = 0x1000+i;
    gpu_enabled = 1;
    fault(sig, info, context);
}
int main(void) {
    struct sigaction action = {0};
    action.sa_sigaction = deliver; action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask); sigaction(SIGILL, &action, NULL);
    raise(SIGILL);
    return 1;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fault.c'
            path.write_text(source)
            exe = Path(tmp) / 'fault'
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2',
                            '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
                            '-I', str(ROOT), '-I', str(ROOT / 'src'), str(path),
                            '-pthread', '-ldl', '-o', str(exe)], check=True,
                           capture_output=True, text=True)
            r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
        self.assertEqual(r.returncode, 99, r.stderr)
        registers = ('R8', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15',
                     'RDI', 'RSI', 'RBP', 'RBX', 'RDX', 'RAX', 'RCX', 'RSP',
                     'RIP', 'RFLAGS')
        essential = r.stderr.split('optional GPU diagnostic failed')[0]
        self.assertIn('signal=0000000000000004', essential)
        for field in ('si_code', 'address', 'image'):
            self.assertRegex(essential, rf'\b{field}=[0-9a-f]{{16}}\b')
        for index, register in enumerate(registers):
            self.assertIn(f'{register}={0x1000 + index:016x}', essential)
        self.assertIn('ERR=0000000000001013', essential)
        self.assertIn('TRAPNO=0000000000001014', essential)


if __name__ == '__main__':
    unittest.main()
