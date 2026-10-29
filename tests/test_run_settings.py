# SPDX-FileCopyrightText: Copyright 2026 bbport contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise run.sh across a re-exec with lightweight preparation/probe stand-ins."""
from paths import ROOT
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest


class RestartResolutionTests(unittest.TestCase):
    def run_restarts(self, explicit=False, live=False, ini_extra='', caps=None, bare_path=False,
                     save_log=None, settings=None, overrides=None, hybrid=None, live_off=False):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            # Preparation is unrelated to this test; allow the real patch compiler to
            # validate writes against a single ELF load segment spanning the game image.
            out = data / 'out'
            out.mkdir()
            elf = bytearray(120)
            struct.pack_into('<Q', elf, 0x20, 64)
            struct.pack_into('<HH', elf, 0x36, 56, 1)
            struct.pack_into('<IIQQQQQQ', elf, 64, 1, 0, 0, 0, 0, 0, 0x6000000, 0)
            (out / 'eboot.elf').write_bytes(elf)
            (out / 'boot-linked.bin').write_bytes(b'fixture-boot-image')
            (data / 'eboot.bin').touch()
            config = data / 'bbport.ini'
            config.write_text('upscaler=fsr3\npreset=1\noutput_res=1280x720\n' + ini_extra)
            if caps is not None:  # the GPU check next to the probe (live_resolution=auto)
                tool = data / 'bb-gpu-capabilities'
                tool.write_text(f'#!/bin/sh\necho {caps}\n')
                tool.chmod(0o755)
            python = data / 'python'
            python.write_text(f'#!{sys.executable}\n' +
                'import subprocess, sys\n'
                'if sys.argv[1] in ("scripts/patches.py", "scripts/mods.py", "-c"):\n'
                '    sys.exit(subprocess.call([sys.executable, *sys.argv[1:]]))\n')
            python.chmod(0o755)
            probe = data / 'probe'
            probe.write_text(f'#!{sys.executable}\n' +
                'import json, os\n'
                'from pathlib import Path\n'
                'config=Path(os.environ["BB_CONFIG"])\n'
                'stage=int(os.environ.get("BB_TEST_STAGE", "0"))\n'
                'row={key:os.environ.get(key) for key in '
                '("BB_RENDER_RES", "BB_OUTPUT_RES", "BB_AUTO_RENDER_RES", "BB_LIVE_HYBRID", "BB_FREE_CHECK", '
                '"BB_WRITE_LOG", "BB_PRODUCER_CHECK", "BB_SAVE_LOG", "BB_FRAME_LOG", "BB_READBACK_LOG")}\n'
                'print(f"diagnostic-test-stage={stage}", flush=True)\n'
                'if os.environ.get("BB_TEST_CALLER_STREAM")=="1":\n'
                '    row["caller_stream"]=os.pread(3,4096,0).decode()\n'
                'with (config.parent/"environments").open("a") as f:\n'
                '    f.write(json.dumps(row)+"\\n")\n'
                'if stage<2:\n'
                '    config.write_text("upscaler=fsr3\\npreset=4\\noutput_res="+'
                '("1280x720" if stage==0 else "1920x1080")+"\\n")\n'
                '    os.environ["BB_TEST_STAGE"]=str(stage+1)\n'
                '    os.execlp("bash", "bash", "run.sh")\n')
            probe.chmod(0o755)
            env = dict(os.environ, BB_PREBUILT='1', BB_PROBE=str(probe), PYTHON=str(python),
                       BB_DATA_DIR=str(data), BB_CONFIG=str(config), BB_GAME_DIR=str(data),
                       BB_SAVE_LOG='1' if save_log else '0',
                       BB_TEST_CALLER_STREAM='1' if save_log else '0')
            env['XDG_CONFIG_HOME'] = str(data / 'xdg')
            if save_log is None:
                env.pop('BB_SAVE_LOG', None)
            for key in ('BB_FREE_CHECK', 'BB_WRITE_LOG', 'BB_PRODUCER_CHECK',
                        'BB_FRAME_LOG', 'BB_READBACK_LOG', 'BB_SESSION_LOG'):
                env.pop(key, None)
            if settings is not None:
                profile = data / 'xdg/bbport-launcher/settings.json'
                profile.parent.mkdir(parents=True)
                profile.write_text(settings if isinstance(settings, str) else json.dumps(settings))
            env.update(overrides or {})
            for key in ('BB_RENDER_RES', 'BB_OUTPUT_RES', 'BB_AUTO_RENDER_RES', 'BB_TEST_STAGE',
                        'BB_LIVE_HYBRID', 'BB_MONITOR_SIZE'):
                env.pop(key, None)
            if hybrid is not None:
                env['BB_LIVE_HYBRID'] = hybrid
            env.pop('BB_LIVE_RES', None)
            if explicit:
                env['BB_RENDER_RES'] = '800x450'
            if live:
                env['BB_LIVE_RES'] = '1'
            if live_off:
                env['BB_LIVE_RES'] = '0'
            if bare_path:  # the AppImage's PATH: coreutils and bash, no sed/grep
                tools = data / 'bin'
                tools.mkdir()
                for name in ('bash', 'dirname', 'mkdir', 'realpath'):
                    (tools / name).symlink_to(shutil.which(name))
                env['PATH'] = str(tools)
            command = [shutil.which('bash'), 'run.sh']
            if save_log:
                # A preloaded client (GameMode/D-Bus) can already own a low descriptor.
                stream = data / 'caller-stream'
                stream.write_text('caller-owned stream\n')
                command = [shutil.which('bash'), '-c',
                           'exec 3<"$1"; exec "$2" run.sh', 'caller',
                           str(stream), shutil.which('bash')]
            subprocess.run(command, cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30)
            self.saved_logs = [p.read_text() for p in (data / 'logs').glob('*.log')]
            self.probe_hash = hashlib.sha256(probe.read_bytes()).hexdigest()
            return [json.loads(line) for line in (data / 'environments').read_text().splitlines()]

    def test_outputs_patch_the_render_size_and_restarts_recompute_it(self):
        # Live presets over the startup patch by default: 720p Quality, 720p Ultra Performance
        # after a restart, then 1080p Ultra Performance (patched too); scenes a multiple of 8.
        rows = self.run_restarts()
        self.assertEqual([row['BB_RENDER_RES'] for row in rows], ['856x480', '424x240', '640x360'])
        self.assertEqual([row['BB_OUTPUT_RES'] for row in rows], ['1280x720', '1280x720', '1920x1080'])
        self.assertEqual([row['BB_AUTO_RENDER_RES'] for row in rows], ['1', '1', '1'])
        self.assertEqual([row['BB_LIVE_HYBRID'] for row in rows], ['1', '1', '1'])

    def test_startup_patch_without_live_changes(self):
        # BB_LIVE_RES=0 (tests only): the startup patch alone, at the preset's exact size.
        row = self.run_restarts(live_off=True)[0]
        self.assertEqual(row['BB_RENDER_RES'], '854x480')
        self.assertIsNone(row['BB_LIVE_HYBRID'])

    def test_proxies_only_keep_guest_sizes_native(self):
        rows = self.run_restarts(live=True, hybrid='0')
        self.assertTrue(all(row['BB_RENDER_RES'] is None for row in rows))
        self.assertTrue(all(row['BB_OUTPUT_RES'] is None for row in rows))
        self.assertTrue(all(row['BB_AUTO_RENDER_RES'] is None for row in rows))

    def test_old_live_resolution_key_is_ignored(self):
        # Live changes are always on (free over the startup patch): the launcher no longer has
        # the setting, an old bbport.ini's live_resolution=0/auto changes nothing.
        for extra, caps in (('live_resolution=0\n', 1), ('live_resolution=auto\n', 0), ('', None)):
            self.assertEqual(self.run_restarts(ini_extra=extra, caps=caps)[0]['BB_RENDER_RES'],
                             '856x480')

    def test_live_resolution_without_sed_or_grep(self):
        # A missing sed ended run.sh (exit 127) before the game in the AppImage on NixOS.
        self.assertEqual(self.run_restarts(ini_extra='live_resolution=0\n', caps=1,
                                           bare_path=True)[0]['BB_RENDER_RES'], '856x480')
        self.assertEqual(self.run_restarts(live_off=True, bare_path=True)[0]['BB_RENDER_RES'],
                         '854x480')

    def test_explicit_render_override_survives_restart(self):
        rows = self.run_restarts(explicit=True)
        self.assertEqual([row['BB_RENDER_RES'] for row in rows], ['800x450'] * 3)
        self.assertTrue(all(row['BB_AUTO_RENDER_RES'] is None for row in rows))

    def test_saved_logging_preserves_an_inherited_stream(self):
        rows = self.run_restarts(save_log=True)
        self.assertEqual(rows[0]['caller_stream'], 'caller-owned stream\n')

    def test_saved_provenance_hashes_and_restart_logs_survive(self):
        rows = self.run_restarts(save_log=True)
        self.assertEqual(len(self.saved_logs), 3)
        for text in self.saved_logs:
            records = [json.loads(line.removeprefix('Launch provenance: '))
                       for line in text.splitlines() if line.startswith('Launch provenance: ')]
            self.assertTrue(records, text)
            files = records[0]['files']
            self.assertEqual(files['selected_probe']['sha256'], self.probe_hash)
            self.assertEqual(files['boot']['sha256'],
                             hashlib.sha256(b'fixture-boot-image').hexdigest())
        for stage in range(3):
            self.assertTrue(any(f'diagnostic-test-stage={stage}' in text
                                for text in self.saved_logs))
        for key in ('BB_FRAME_LOG', 'BB_READBACK_LOG'):
            self.assertEqual(len({row[key] for row in rows}), 3)

    def test_cli_uses_saved_diagnostics_without_overriding_callers(self):
        rows = self.run_restarts(settings={'crash_diag': True, 'save_log': True})
        for row in rows:
            for key in ('BB_FREE_CHECK', 'BB_WRITE_LOG', 'BB_PRODUCER_CHECK', 'BB_SAVE_LOG'):
                self.assertEqual(row[key], '1')
        rows = self.run_restarts(settings={'crash_diag': True, 'save_log': True},
                                 overrides={'BB_FREE_CHECK': '0', 'BB_WRITE_LOG': '2',
                                            'BB_PRODUCER_CHECK': '0', 'BB_SAVE_LOG': '0'})
        for row in rows:
            self.assertEqual([row[key] for key in ('BB_FREE_CHECK', 'BB_WRITE_LOG',
                                                   'BB_PRODUCER_CHECK', 'BB_SAVE_LOG')],
                             ['0', '2', '0', '0'])

    def test_custom_statistics_paths_survive_restart(self):
        rows = self.run_restarts(save_log=True,
                                 overrides={'BB_FRAME_LOG': '/caller/frames.csv',
                                            'BB_READBACK_LOG': '/caller/readbacks.csv'})
        for row in rows:
            self.assertEqual(row['BB_FRAME_LOG'], '/caller/frames.csv')
            self.assertEqual(row['BB_READBACK_LOG'], '/caller/readbacks.csv')

    def test_cli_rejects_invalid_diagnostic_settings_before_probe(self):
        for settings in ('{"crash_diag":', [], {'crash_diag': 'true'}, {'save_log': 1}):
            with self.subTest(settings=settings), self.assertRaises(subprocess.CalledProcessError) as error:
                self.run_restarts(settings=settings)
            self.assertEqual(error.exception.returncode, 1)
            self.assertIn(b'Crash diagnostic settings', error.exception.stderr)
