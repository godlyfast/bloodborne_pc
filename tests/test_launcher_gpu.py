"""The launcher's runtime choices: GPU, monitor, aspect ratio, game language and online pool."""
from paths import ROOT
import importlib.util
import os
import subprocess
import tempfile
import sys
import types
import unittest
from unittest import mock
from pathlib import Path

# The launcher's window needs GTK; these tests use its functions only.
gi = types.ModuleType("gi")
gi.require_version = lambda *_args: None
gi.repository = mock.MagicMock()
sys.modules.setdefault("gi", gi)
sys.modules.setdefault("gi.repository", gi.repository)
sys.path.insert(0, str(ROOT / "launcher"))
spec = importlib.util.spec_from_file_location("bbport_launcher", ROOT / "launcher/bbport_launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

GPUS = ("0\t0x8086\tintegrated\tIntel(R) UHD Graphics 630\t0\n"
        "1\t0x10de\tdiscrete\tNVIDIA GeForce RTX 4060 Laptop GPU\t1\n"
        "2\t0x10005\tcpu\tllvmpipe (LLVM 21.1.8, 256 bits)\t0\n")


class LauncherGpuTests(unittest.TestCase):
    def setUp(self):
        run = mock.patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 0, stdout=GPUS, stderr=""))
        self.run = run.start()
        self.addCleanup(run.stop)
        self.settings = dict(launcher.DEFAULTS, game_dir="/games/CUSA03173", user_dir="")

    def test_gpus_listed_in_vulkans_order(self):
        gpus = launcher.connected_gpus()
        self.assertEqual([(index, name, best) for index, _vendor, _kind, name, best in gpus],
                         [(0, "Intel(R) UHD Graphics 630", False),
                          (1, "NVIDIA GeForce RTX 4060 Laptop GPU", True),
                          (2, "llvmpipe (LLVM 21.1.8, 256 bits)", False)])
        self.assertEqual(self.run.call_args.args[0][1:], ["--gpus"])

    def test_chosen_gpu_passed_by_index(self):
        self.settings["gpu"] = "Intel(R) UHD Graphics 630"
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BB_GPU_ID", None)
            self.assertEqual(launcher.game_environment(self.settings).get("BB_GPU_ID"), "0")

    def test_auto_and_missing_gpu_leave_the_choice_to_the_port(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BB_GPU_ID", None)
            self.assertNotIn("BB_GPU_ID", launcher.game_environment(self.settings))
            self.settings["gpu"] = "AMD Radeon RX 580"
            self.assertNotIn("BB_GPU_ID", launcher.game_environment(self.settings))

    def test_shell_gpu_id_wins(self):
        self.settings["gpu"] = "Intel(R) UHD Graphics 630"
        with mock.patch.dict(os.environ, {"BB_GPU_ID": "1"}):
            self.assertEqual(launcher.game_environment(self.settings)["BB_GPU_ID"], "1")

    def test_displays_keep_resolution_and_primary_with_duplicate_names(self):
        self.run.return_value.stdout = ("DP-1\t1920x1080\t1\nDP-1\t3440x1440\t0\n"
                                       "HDMI-1\tunknown\t0\nmalformed\n")
        displays = launcher.connected_displays()
        self.assertEqual([(value, size, primary) for value, _label, size, primary in displays],
                         [("1", (1920, 1080), True), ("2", (3440, 1440), False),
                          ("HDMI-1", None, False)])

    def test_auto_output_includes_monitor_and_aspect_change_keeps_nearest_height(self):
        sizes = launcher.output_sizes("auto", (2560, 1600))
        self.assertIn((2560, 1600), sizes)
        self.assertEqual(launcher.resolved_aspect("auto", (2560, 1600)), "16:10")
        self.assertEqual(launcher.resolved_aspect("auto", None), "16:9")
        self.assertEqual(launcher.nearest_output(launcher.output_sizes("21:9", None), (1920, 1080)),
                         (2560, 1080))
        self.assertEqual(launcher.nearest_output(launcher.output_sizes("16:9", None), (3440, 1440)),
                         (2560, 1440))

    def test_game_language_reaches_runtime_independently_of_system_locale(self):
        expected = {str(code) for code in range(21)}
        selected = set()
        with mock.patch.dict(os.environ, {"LANG": "ru_RU.UTF-8", "LC_ALL": "zh_CN.UTF-8"}):
            for _label, code in launcher.LANGUAGES:
                self.settings["language"] = code
                selected.add(launcher.game_environment(self.settings)["BB_LANGUAGE"])
        self.assertEqual(selected, expected)

    def test_headless_play_keeps_game_language_under_non_english_locale(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "eboot.bin").touch()
            settings = dict(self.settings, game_dir=tmp, language="8")
            with mock.patch.object(launcher, "load_settings", return_value=settings), \
                    mock.patch.object(launcher.os, "chdir"), \
                    mock.patch.object(launcher.os, "execvpe") as launch, \
                    mock.patch.dict(os.environ, {"LANG": "ru_RU.UTF-8"}, clear=True):
                launcher.play()
            executable, command, env = launch.call_args.args
            self.assertEqual(executable, "bash")
            self.assertEqual(command, ["bash", str(launcher.PORT_DIR / "run.sh")])
            self.assertEqual(env["BB_LANGUAGE"], "8")

    def test_online_pool_selects_backend_and_keeps_credentials(self):
        self.settings.update(online=True, online_bbsc=True, online_npid="hunter",
                             online_password="password", thd_online_id="discord-hunter",
                             thd_token="token", thd_server="https://hunters.example")
        with mock.patch.object(launcher, "online_module", return_value=True), \
                mock.patch.dict(os.environ, {}, clear=True):
            env = launcher.game_environment(self.settings)
            self.assertEqual((env["BB_ONLINE"], env["BB_NET_GEN"], env["BB_BBSC"]), ("1", "20", "1"))
            self.assertEqual((env["BB_SHADNET_NPID"], env["BB_SHADNET_PASSWORD"]), ("hunter", "password"))
            self.settings["online_pool"] = "huntersdream"
            env = launcher.game_environment(self.settings)
            self.assertEqual(env["BB_NET_BACKEND"], "thd")
            self.assertEqual(env["BB_COMMUNITY_SERVER"], "https://hunters.example")
            self.assertEqual((env["BB_THD_ONLINE_ID"], env["BB_THD_TOKEN"]), ("discord-hunter", "token"))
            self.assertNotIn("BB_BBSC", env)


if __name__ == "__main__":
    unittest.main()
