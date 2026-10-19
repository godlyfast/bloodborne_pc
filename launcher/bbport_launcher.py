#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bloodborne launcher for the native port (GTK4 / libadwaita).

Picks the game folder, edits the port's settings (bbport.ini: upscaler, preset, ...) and the
start-up tweaks passed as environment variables to run.sh, starts and stops the game and shows
its output. Launcher settings live in ~/.config/bbport-launcher/settings.json.
"""

import json
import math
import shutil
import os
import re
import signal
import subprocess
import threading
import sys
import time
from pathlib import Path
from bbport_assets import fsr411_problem

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

PORT_DIR = Path(__file__).resolve().parent.parent  # native_probe (or the package's copy)
sys.path.insert(0, str(PORT_DIR / 'scripts'))
from mods import discover as discover_mods  # noqa: E402
import game_check  # noqa: E402
import online  # noqa: E402  (the online module: addresses and the connection test)
from patches import external_patches  # noqa: E402
# Packaged (AppImage): generated files, saves and bbport.ini live in BB_DATA_DIR.
PACKAGED = bool(os.environ.get("BB_PREBUILT"))
DATA_DIR = Path(os.environ.get("BB_DATA_DIR", PORT_DIR))
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "bbport-launcher"
CONFIG_FILE = CONFIG_DIR / "settings.json"
MAX_LOG_LINES = 5000
# The memory model (run.sh: BB_PC_MODEL): "auto" is the new one on every GPU (0.6), or either by
# hand. The new one goes through the layer's memory module on
# every GPU (no sparse binding of the game's memory; BB_LAYER_MEMORY=0: AMD's sparse arena).
PC_MODEL_SUBTITLE = ("The new one: the GPU works with the game's memory directly, as in a PC game, and graphics "
                     "commands are translated rather than emulated. The old one: the memory model of 0.3 with all "
                     "the fixes. If the driver fails the startup check, the old one")
MEMORY_MODELS = [("Auto: new on every GPU", "auto"), ("New", "new"),
                 ("Old (as in 0.3)", "old")]
# FSR 4.1.1 assets built from the user's AMD DLL (tools/fsr4cap, also in the package).
FSR4CAP_DIR = PORT_DIR / "tools" / "fsr4cap"
sys.path.insert(0, str(FSR4CAP_DIR))
# The package's own environment (its Mesa, libraries, GTK modules) must not reach Proton's
# container: Proton runs the DLL on the system's drivers.
PACKAGE_ONLY_ENV = (
    "LD_LIBRARY_PATH", "VK_DRIVER_FILES", "VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES",
    "VK_LAYER_PATH", "VK_ADD_LAYER_PATH", "__EGL_VENDOR_LIBRARY_DIRS", "GDK_PIXBUF_MODULE_FILE",
    "GIO_EXTRA_MODULES", "GI_TYPELIB_PATH", "FONTCONFIG_FILE", "GSETTINGS_SCHEMA_DIR", "PYTHONPATH",
    "PYTHONHOME",
)
# build_assets.sh exit statuses (see there).
FSR411_BUILD_ERRORS = {
    2: "The DLL does not fit: details in the log",
    3: ("No suitable Proton found: install GE-Proton 10 or newer (ProtonUp-Qt), or Proton Experimental / "
        "Proton-CachyOS in Steam. If you have them, start any game with that Proton in Steam so that Steam "
        "installs its runtime"),
    4: "Tools for the build are missing: the list is in the log",
    5: ("No Proton started this DLL's FSR 4.1. Either they are too old (GE-Proton 10+, Proton Experimental, "
        "Proton-CachyOS 11 work), or the DLL does not enable FSR 4.1 on this GPU (Steam Deck?): then build on a "
        "PC with a Radeon RX 7000/9000 and copy the fsr4_411 folder. Details in the log"),
    6: ("The recorded passes do not match what bbport replays (another DLL version, or a new GPU?): details in "
        "the log"),
    7: "No FidelityFX loader 2.x found",
    8: ("On NixOS the recording runs on the system itself (systemd --user) with umu-launcher from nix-shell, and "
        "neither was found: install umu-launcher or Nix. Details in the log"),
}

# Choices: (label, value). The first entry is the default.
UPSCALERS = [("FSR 4", "fsr4"), ("FSR 4.1.1", "fsr411"), ("FSR 3", "fsr3"),
             ("DLSS (NVIDIA RTX)", "dlss"),
             ("TAA (native anti-aliasing)", "taa"), ("Off", "off")]
PRESETS = [("Native AA", 0), ("Quality (x1.5)", 1), ("Balanced (x1.7)", 2),
           ("Performance (x2)", 3), ("Ultra Performance (x3)", 4)]
# Output aspect ratios and their resolutions (gpu/shim/bbport_settings.cpp, the same lists): the
# game keeps its 1920x1080 frame; for another aspect ratio its camera sees more to the sides (above
# and below) and the UI keeps to the screen edges, changed live. Auto: the monitor's group.
ASPECTS = ["auto", "4:3", "16:10", "16:9", "21:9", "32:9"]
ASPECT_RATIOS = {"4:3": 4 / 3, "16:10": 16 / 10, "16:9": 16 / 9, "21:9": 64 / 27, "32:9": 32 / 9}
OUTPUTS = {
    "4:3": [(640, 480), (800, 600), (1024, 768), (1280, 960), (1440, 1080), (1600, 1200), (2048, 1536),
            (2880, 2160)],
    "16:10": [(640, 400), (960, 600), (1280, 800), (1440, 900), (1680, 1050), (1920, 1200), (2560, 1600),
              (3840, 2400)],
    "16:9": [(640, 360), (854, 480), (960, 540), (1280, 720), (1600, 900), (1920, 1080), (2560, 1440),
             (3200, 1800), (3840, 2160)],
    "21:9": [(860, 360), (1280, 540), (1720, 720), (2560, 1080), (3440, 1440), (3840, 1600), (5120, 2160)],
    "32:9": [(1280, 360), (1920, 540), (2560, 720), (3840, 1080), (5120, 1440), (7680, 2160)],
}


def resolved_aspect(aspect, monitor):
    """The aspect ratio group: Auto is the one nearest the monitor's (16:9 when unknown)."""
    if aspect in OUTPUTS:
        return aspect
    if not monitor:
        return "16:9"
    ratio = monitor[0] / monitor[1]
    return min(OUTPUTS, key=lambda a: abs(math.log(ratio / ASPECT_RATIOS[a])))


def output_sizes(aspect, monitor):
    """The resolutions of an aspect ratio; Auto adds the monitor's own size."""
    sizes = list(OUTPUTS[resolved_aspect(aspect, monitor)])
    if (aspect == "auto" and monitor and monitor not in sizes and 640 <= monitor[0] <= 7680
            and 360 <= monitor[1] <= 4320):
        sizes = sorted(sizes + [monitor], key=lambda size: (size[1], size[0]))
    return sizes


def nearest_output(sizes, size):
    """The size itself if listed, else the one nearest in height (another aspect ratio keeps it)."""
    return size if size in sizes else min(sizes, key=lambda s: abs(s[1] - size[1]))


def parse_size(text, default=(1920, 1080)):
    try:
        w, h = (int(v) for v in text.lower().split("x"))
        return (w, h) if w > 0 and h > 0 else default
    except ValueError:
        return default
# Game effects (patches applied at start): bbport.ini key, title, default.
EFFECTS = [
    ("effect_chromatic_aberration", "Chromatic aberration", True),
    ("effect_dof", "Depth of field (DoF)", True),
    ("effect_motion_blur", "Motion blur", True),
    ("effect_ssao", "SSAO", True),
    ("effect_game_aa", "The game's own anti-aliasing", True),
    ("effect_dynamic_shadows", "Dynamic light shadows", True),
    ("effect_ssr", "SSR reflections (not in the original game)", False),
    ("effect_bloom", "Bloom", True),
    ("skip_intro", "Skip the intro videos", False),
    ("debug_camera", "Free camera (Cross + L3 / F + Ctrl)", False),
    ("debug_menu", "Debug menu (left touchpad / G; needs fonts)", False),
]
MODEL_LOD = [("As in the game", "0"), ("Highest (-2)", "-2"), ("Lower (1)", "1"),
             ("Lowest (2)", "2")]
FPS_MODES = [("Unlocked", "uncap"), ("60", "60"), ("90", "90"),
             ("30 (as on PS4)", "30")]
PRESENT_MODES = [("Mailbox", "Mailbox"), ("FIFO (VSync)", "Fifo"),
                 ("FIFO Relaxed", "FifoRelaxed"), ("Immediate", "Immediate")]
# A third element is a note shown under the row's title while that choice is selected: the
# choice labels stay short, so the selected one is shown in full.
DRAW_PIPE = [("Auto", "", "On with 8 or more CPU threads"), ("On", "1"),
             ("Off", "0", "More stable, but slower")]
# The game's text languages (dvdroot_ps4/msg) by the PS4 system language code (#249).
LANGUAGES = [("English", "1"), ("English (United Kingdom)", "18"), ("Russian", "8"),
             ("Japanese", "0"), ("French", "2"), ("Spanish", "3"),
             ("Spanish (Latin America)", "20"), ("German", "4"), ("Italian", "5"),
             ("Dutch", "6"), ("Portuguese", "7"), ("Portuguese (Brazil)", "17"),
             ("Polish", "16"), ("Turkish", "19"), ("Korean", "9"),
             ("Chinese (Simplified)", "11"), ("Chinese (Traditional)", "10"),
             ("Finnish", "12"), ("Swedish", "13"), ("Danish", "14"), ("Norwegian", "15")]
LIVE_RESOLUTION = [("Auto (by GPU)", "auto"), ("Off (faster)", "0"), ("On", "1")]
READBACKS = [("Relaxed", "", "Default"), ("Off", "0"), ("Precise", "2")]
# Background pre-upload of the game's GPU memory into VRAM (BB_PREUPLOAD): auto = on with a discrete GPU.
PREUPLOAD = [("Normal", "", "No extra VRAM"), ("Full", "2", "About 3 GB more VRAM"),
             ("Off", "0")]

DEFAULTS = {
    "game_dir": "" if PACKAGED else str(PORT_DIR.parent / "CUSA03173"),
    "user_dir": "",
    "mods_dir": "",
    "mods_enabled": True,
    "patches_dir": "",
    "language": "1",
    "fullscreen": False,
    "hdr": False,
    "present_mode": "Mailbox",
    "gamepad": "",
    "gamepad_name": "",
    "display": "",
    # The GPU by its Vulkan name ("" = the port's choice: a discrete one first).
    "gpu": "",
    "skip_network_choice": True,
    "fps_mode": "uncap",
    "fps_limit": 0,
    "draw_pipe": "",
    "readbacks": "",
    "preupload": "",
    "mangohud": False,
    "frame_stats": False,
    "save_log": False,
    "crash_diag": False,
    "memory_model": "auto",
    "as_0_3": False,
    "gpu_profile": False,
    "vk_validation": False,
    "extra_env": "",
    # Online play (Online page, the online module gpu/bbnet): off by default; Seamless Hunt's
    # servers (BBSC's: shadNet, its WebAPI and the game server).
    "online": False,
    # BBSC, Bloodborne seamless co-op (seamlesshunt.com): needs a server running its
    # game server next to shadNet (Seamless Hunt's does).
    "online_bbsc": True,
    "online_community": online.COMMUNITY_SERVER,
    "online_server": online.SHADNET_SERVER,
    "online_webapi": online.WEBAPI_SERVER,
    "online_npid": "",
    "online_password": "",
    "online_upnp": True,
    # The pool: "seamless" (BBSC, the shadp2p module gpu/bbnet), "shadnet" (shadPS4 0.20's shadNet client,
    # gpu/bbnet20) or "huntersdream" (The Hunter's Dream, bbhost's protocol, gpu/bbnet20; the account
    # comes from the Discord sign-in).
    "online_pool": "seamless",
    "thd_server": "",
    "thd_online_id": "",
    "thd_token": "",
}

# bbport.ini keys the launcher edits; the rest of the file is kept.
INI_DEFAULTS = {
    "upscaler": "fsr4",
    "preset": "4",
    "sharpen": "1",
    "sharpness": "0.50",
    "object_motion": "1",
    "show_fps": "1",
    "output_res": "1920x1080",
    "model_lod": "0",
    "live_resolution": "0",
    "mouse_look": "1",
    "mouse_sensitivity": "1.00",
    "mouse_invert_y": "0",
    **{key: "1" if default else "0" for key, _, default in EFFECTS},
}


def load_settings():
    settings = dict(DEFAULTS)
    try:
        settings.update(json.loads(CONFIG_FILE.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    # Addresses saved as the old defaults (shadPS4's public shadNet, which accepts only shadPS4's
    # own builds since 2026-10-12, and The Hunter's Dream) become the new ones.
    for key, old_values in online.OLD_DEFAULTS.items():
        if str(settings.get(key, '')).strip() in old_values:
            settings[key] = DEFAULTS[key]
    return settings


def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.touch(mode=0o600)
    CONFIG_FILE.chmod(0o600)  # it holds the shadNet password
    CONFIG_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def ini_path():
    return Path(os.environ.get("BB_CONFIG", DATA_DIR / "bbport.ini"))


def load_ini():
    values = dict(INI_DEFAULTS)
    lines = []
    try:
        lines = ini_path().read_text(encoding='utf-8').splitlines()
    except OSError:
        pass
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values, lines


def save_ini(values, lines):
    """Rewrites the edited keys in place, appends missing ones, keeps comments and others; a key
    whose value is None is removed (a control binding back to its default)."""
    written = set()
    out = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in values:
                if values[key] is not None:
                    out.append(f"{key}={values[key]}")
                written.add(key)
                continue
        out.append(line)
    if not lines:
        out.append("# bbport settings (in-game menu: Insert / L3+R3)")
    for key, value in values.items():
        if key not in written and value is not None:
            out.append(f"{key}={value}")
    ini_path().write_text("\n".join(out) + "\n", encoding="utf-8")


def patches_dir(settings):
    return Path(settings.get("patches_dir") or DATA_DIR / "patches").expanduser()


# DLSS (vk_dlss.cpp): the bridge (libbbport_dlss.so) and NVIDIA's runtime library
# libnvidia-ngx-dlss.so.<version>, beside bb-probe (the package, a build with DLSS_SDK_ROOT) or the
# player's own in <user>/dlss, which the game prefers. Linux needs the .so from NVIDIA's DLSS SDK
# (github.com/NVIDIA/DLSS, lib/Linux_x86_64/rel); a game's nvngx_dlss.dll is Windows-only.
NGX_PREFIX = "libnvidia-ngx-dlss.so."
DLSS_SDK_URL = "https://github.com/NVIDIA/DLSS/tree/main/lib/Linux_x86_64/rel"


def binaries_dir():
    return PORT_DIR / ("bin" if PACKAGED else "out")


def ngx_libraries(directory):
    """NVIDIA's DLSS runtime libraries in directory, newest version last."""
    def version(path):
        return tuple(int(p) if p.isdigit() else 0 for p in path.name[len(NGX_PREFIX):].split("."))
    try:
        return sorted((p for p in Path(directory).iterdir() if p.name.startswith(NGX_PREFIX)), key=version)
    except OSError:
        return []


def fsr411_dir():
    """Where the FSR 4.1.1 assets are looked up, as run.sh does."""
    if os.environ.get("BB_FSR411_DIR"):
        return Path(os.environ["BB_FSR411_DIR"])
    return PORT_DIR / "fsr4_411" if (PORT_DIR / "fsr4_411").is_dir() else DATA_DIR / "fsr4_411"


def fsr411_build_command(upscaler, loader=None):
    """tools/fsr4cap/build_assets.sh for the user's DLL: command and environment. The package
    writes into the data directory (it is read-only itself) and removes the work folder after."""
    env = dict(os.environ)
    if PACKAGED:
        for key in PACKAGE_ONLY_ENV:
            env.pop(key, None)
        env["BB_FSR4CAP_WORK"] = str(DATA_DIR / "fsr4cap")
        env["BB_FSR4CAP_CLEAN"] = "1"
    tools = FSR4CAP_DIR / "bin"
    if (tools / "dxil-spirv").is_file() and (tools / "fsr4cap.exe").is_file():
        env["BB_FSR4CAP_TOOLS"] = str(tools)
    env["BB_FSR411_OUT"] = os.environ.get("BB_FSR411_DIR") or str(
        (DATA_DIR if PACKAGED else PORT_DIR) / "fsr4_411")
    command = ["bash", str(FSR4CAP_DIR / "build_assets.sh"), str(upscaler)]
    return command + ([str(loader)] if loader else []), env


def online_module(pool="seamless"):
    """The online module beside the GPU library (gpu/bbnet, or gpu/bbnet20 for the shadNet and The
    Hunter's Dream pools; a build without its libraries has none)."""
    name = "libbbnet20.so"
    return (PORT_DIR / ("bin" if PACKAGED else "out") / "gpu" / name).is_file()


def game_environment(s):
    """Environment for run.sh from the launcher settings."""
    env = dict(os.environ)
    env["BB_GAME_DIR"] = str(Path(s["game_dir"]).expanduser())
    if s["user_dir"]:
        env["BB_USER_DIR"] = s["user_dir"]
    env["BB_MODS_DIR"] = str(Path(s.get("mods_dir") or DATA_DIR / "mods").expanduser())
    env["BB_MODS_CONFIG"] = str(DATA_DIR / "mods.json")
    env["BB_MODS_ENABLED"] = "1" if s.get("mods_enabled", True) else "0"
    env["BB_PATCHES_DIR"] = str(patches_dir(s))
    env["BB_PATCHES_CONFIG"] = str(DATA_DIR / "patches.json")
    env["BB_LANGUAGE"] = s["language"]
    env["BB_FULLSCREEN"] = "1" if s["fullscreen"] else "0"
    env["BB_PRESENT_MODE"] = s["present_mode"]
    if s.get("gamepad"):
        env["BB_GAMEPAD"] = s["gamepad"]
    if s.get("display"):
        env["BB_DISPLAY"] = s["display"]
    env["BB_SKIP_NETWORK_CHOICE"] = "1" if s.get("skip_network_choice", True) else "0"
    if s["hdr"]:
        env["BB_HDR"] = "1"
    env["BB_FPS"] = s["fps_mode"]
    if s["fps_limit"] > 0:
        env["BB_FPS_LIMIT"] = str(s["fps_limit"])
    if s["draw_pipe"]:
        env["BB_DRAW_PIPE"] = s["draw_pipe"]
    if s["readbacks"]:
        env["BB_READBACKS"] = s["readbacks"]
    if s.get("preupload"):
        env["BB_PREUPLOAD"] = s["preupload"]
    if s["mangohud"]:
        env["MANGOHUD"] = "1"
    if s["frame_stats"]:
        env["BB_FRAME_STATS"] = "1"
    if s.get("save_log"):
        env["BB_SAVE_LOG"] = "1"
    # The memory model: "auto" is run.sh's choice (the new one on every GPU). "pc_model", "pc_memory", "old_memory_model", "new_memory_model" and
    # "legacy_memory_model" of older settings are ignored (0.5: auto for everyone).
    # BB_PC_MODEL from the shell (or the extra variables) still wins over "auto".
    model = s.get("memory_model", "auto")
    if model in ("new", "old"):
        env["BB_PC_MODEL"] = "1" if model == "new" else "0"
    # The GPU chosen by name: its index in Vulkan's order now (BB_GPU_ID). One not found (taken
    # out, renamed by a driver update) leaves the choice to the port. BB_GPU_ID from the shell
    # wins.
    if s.get("gpu") and "BB_GPU_ID" not in os.environ:
        index = next((index for index, _vendor, _kind, name, _best in connected_gpus()
                      if name == s["gpu"]), None)
        if index is not None:
            env["BB_GPU_ID"] = str(index)
    # Synchronisation and memory as released in 0.3 (run.sh: BB_AS_0_3), for comparisons.
    if s.get("as_0_3"):
        env["BB_AS_0_3"] = "1"
    if s.get("crash_diag"):
        env["BB_FREE_CHECK"] = "1"
        env["BB_WRITE_LOG"] = "1"
        env["BB_PRODUCER_CHECK"] = "1"
    if s["gpu_profile"]:
        env["BB_GPU_PROFILE"] = "1"
    if s["vk_validation"]:
        env["BB_VK_VALIDATION"] = "1"
    pool = "huntersdream" if s.get("online_pool") == "huntersdream" else "seamless"
    if s.get("online") and online_module(pool):
        server = s["online_server"].strip() or online.SHADNET_SERVER
        community = online.community_address(s["online_community"])
        env["BB_ONLINE"] = "1"
        env["BB_SHADNET_SERVER"] = server
        env["BB_SHADNET_WEBAPI"] = online.webapi_setting(s["online_webapi"], server, community)
        env["BB_SHADNET_NPID"] = s["online_npid"].strip()
        env["BB_SHADNET_PASSWORD"] = s["online_password"]
        env["BB_UPNP"] = "1" if s["online_upnp"] else "0"
        env["BB_COMMUNITY_SERVER"] = community
        env["BB_NET_GEN"] = "20"
        if pool == "seamless" and s.get("online_bbsc"):
            env["BB_BBSC"] = "1"
        if pool == "huntersdream":
            # run.sh turns these into the backend's addresses and the host overrides.
            env["BB_NET_BACKEND"] = "thd"
            env["BB_COMMUNITY_SERVER"] = online.thd_base(s.get("thd_server", ""))
            env["BB_THD_ONLINE_ID"] = s.get("thd_online_id", "")
            env["BB_THD_TOKEN"] = s.get("thd_token", "")
    for item in s["extra_env"].split():
        if "=" in item:
            key, value = item.split("=", 1)
            env[key] = value
    return env


def open_url(url):
    """Opens url in the user's browser: GIO, then Python's webbrowser (xdg-open and the like);
    True when one of them took it."""
    try:
        if Gio.AppInfo.launch_default_for_uri(url, None):
            return True
    except GLib.Error:
        pass
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:
        return False


def flat_button(icon, tooltip, handler):
    button = Gtk.Button(icon_name=icon, valign=Gtk.Align.CENTER, tooltip_text=tooltip)
    button.add_css_class("flat")
    button.connect("clicked", handler)
    return button


def open_folder(window, path):
    """Opens `path` in the file manager (created first, so that a new saves folder opens)."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    Gtk.FileLauncher.new(Gio.File.new_for_path(str(path))).launch(window, None, None)


def combo_row(title, subtitle, choices, current):
    model = Gtk.StringList.new([choice[0] for choice in choices])
    row = Adw.ComboRow(title=title, model=model)
    values = [choice[1] for choice in choices]
    notes = [choice[2] if len(choice) > 2 else None for choice in choices]

    def show_note(*_):
        lines = [line for line in (subtitle, notes[row.get_selected()]) if line]
        row.set_subtitle("\n".join(lines))

    row.set_selected(values.index(current) if current in values else 0)
    show_note()
    row.connect("notify::selected", show_note)
    row.values = values
    return row


def combo_value(row):
    return row.values[row.get_selected()]


# Controls (runtime_pad.c): input, label, default keyboard keys (Dark Souls III-like; a chord
# is "Left Shift+Mouse Left"), default gamepad buttons (SDL names).
# bbport.ini key.<input>= / pad.<input>= replace a default; no line keeps it. Mouse buttons and the
# wheel are keys ("Mouse Left", "Wheel Down"); they act while the game holds the mouse.
CONTROLS = [
    ("cross", "Cross (interact)", "F, Return", "a"),
    ("circle", "Circle (dodge, sprint; keyboard: Space and Shift below)", "", "b"),
    ("dodge", "Dodge (tap Circle; Shift+Space to jump)", "Space", None),
    ("sprint", "Sprint (hold Circle)", "Left Shift", None),
    ("square", "Square (quick item)", "Tab, R", "x"),
    ("triangle", "Triangle (blood vial)", "Q", "y"),
    ("l1", "L1 (transform weapon)", "E, Mouse X2", "leftshoulder"),
    ("r1", "R1 (attack)", "Mouse Left", "rightshoulder"),
    ("l2", "L2 (shoot)", "Mouse Right", "lefttrigger"),
    ("r2", "R2 (strong attack)", "Left Shift+Mouse Left, Mouse X1", "righttrigger"),
    ("l3", "L3", "Left Ctrl", "leftstick"),
    ("r3", "R3 (lock on)", "C, Mouse Middle", "rightstick"),
    ("options", "Options (menu; Escape goes back in game menus, like Circle)", "Escape", "start"),
    ("touchpad", "Touchpad, left half (gestures)", "G", "back, touchpad"),
    ("touchpad_right", "Touchpad, right half (key items)", "Backspace", ""),
    ("up", "D-pad up", "3, Up, Wheel Up", "dpup"),
    ("down", "D-pad down", "4, Down, Wheel Down", "dpdown"),
    ("left", "D-pad left (left-hand weapon)", "1, Left", "dpleft"),
    ("right", "D-pad right (right-hand weapon)", "2, Right", "dpright"),
    ("move_up", "Move forward", "W", None),
    ("move_down", "Move back", "S", None),
    ("move_left", "Move left", "A", None),
    ("move_right", "Move right", "D", None),
    ("look_up", "Camera up", "I", None),
    ("look_down", "Camera down", "K", None),
    ("look_left", "Camera left", "J", None),
    ("look_right", "Camera right", "L", None),
]


def connected_gamepads():
    """(GUID, name) of the connected gamepads (bb-gpu-capabilities --gamepads), [] if unknown."""
    tool = PORT_DIR / ("bin" if PACKAGED else "out") / "bb-gpu-capabilities"
    try:
        run = subprocess.run([str(tool), "--gamepads"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    return [tuple(line.split("\t", 1)) for line in run.stdout.splitlines() if "\t" in line]


def connected_displays():
    """(BB_DISPLAY value, label, (w, h) or None, primary) of the monitors (bb-gpu-capabilities
    --displays), [] if unknown. The value is the monitor's name, or its number when two monitors
    share a name."""
    tool = PORT_DIR / ("bin" if PACKAGED else "out") / "bb-gpu-capabilities"
    try:
        run = subprocess.run([str(tool), "--displays"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    rows = [line.split("\t") for line in run.stdout.splitlines() if line.count("\t") == 2]
    names = [name for name, _, _ in rows]
    return [(name if names.count(name) == 1 else str(number),
             f"{number}: {name} ({size})" + (", primary" if primary == "1" else ""),
             parse_size(size, None), primary == "1")
            for number, (name, size, primary) in enumerate(rows, 1)]



def connected_gpus():
    """(index, vendor ID, type, name, the port's own choice) of the GPUs in Vulkan's order
    (bb-gpu-capabilities --gpus; BB_GPU_ID is the index), [] if unknown."""
    tool = PORT_DIR / ("bin" if PACKAGED else "out") / "bb-gpu-capabilities"
    env = {key: value for key, value in os.environ.items() if key != "BB_GPU_ID"}
    try:
        run = subprocess.run([str(tool), "--gpus"], capture_output=True, text=True, timeout=10,
                             env=env)
    except (OSError, subprocess.SubprocessError):
        return []
    rows = [line.split("\t") for line in run.stdout.splitlines() if line.count("\t") == 4]
    return [(int(index), vendor, kind, name, best == "1")
            for index, vendor, kind, name, best in rows if index.isdigit()]


class FolderList:
    """A preferences group with a folder row and one switch row per item below it."""

    def __init__(self, group):
        self.group = group
        self.rows = []

    def clear(self):
        for _, row in self.rows:
            self.group.remove(row)
        self.rows = []

    def add(self, key, row):
        self.group.add(row)
        self.rows.append((key, row))


class LauncherWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Bloodborne")
        self.set_default_size(760, 820)
        self.settings = load_settings()
        self.ini, self.ini_lines = load_ini()
        self.process = None
        self.stream = None
        self.fsr411_build = None  # tools/fsr4cap/build_assets.sh while it runs
        self.build()
        self.connect("close-request", self.on_close)

    def build(self):
        """(Re)creates the window's content."""
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        self.launch_button = Gtk.Button()
        self.launch_button.connect("clicked", self.on_launch)
        header.pack_end(self.launch_button)
        toolbar.add_top_bar(header)

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.stack)
        toolbar.set_content(self.toasts)
        self.set_content(toolbar)

        log_text = self.log_text() if hasattr(self, "log_view") else ""
        self.stack.add_titled_with_icon(self.build_settings_page(), "settings", "Settings",
                                        "preferences-system-symbolic")
        self.stack.add_titled_with_icon(self.build_online_page(), "online", "Online",
                                        "network-workgroup-symbolic")
        self.stack.add_titled_with_icon(self.build_log_page(), "log", "Log",
                                        "utilities-terminal-symbolic")
        self.log_view.get_buffer().set_text(log_text)
        self.update_launch_button()
        self.update_game_status()
        self.update_user_status()
        self.update_upscaler_status()

    def update_launch_button(self):
        running = self.process is not None
        self.launch_button.set_label("Stop" if running else "Play")
        self.launch_button.remove_css_class("destructive-action" if not running else "suggested-action")
        self.launch_button.add_css_class("destructive-action" if running else "suggested-action")
        # The game and an FSR 4.1.1 build do not run together (both want the GPU, the build
        # replaces the assets the game reads).
        self.launch_button.set_sensitive(self.fsr411_build is None)
        if hasattr(self, "fsr411_button"):
            self.fsr411_button.set_sensitive(not running)

    # --- settings page -------------------------------------------------------------------

    def build_settings_page(self):
        page = Adw.PreferencesPage()

        game = Adw.PreferencesGroup(title="Game")
        self.game_row = Adw.ActionRow(title="Game folder (CUSA03173)")
        self.game_status = Gtk.Image()
        self.game_row.add_suffix(self.game_status)
        self.game_row.add_suffix(flat_button("folder-open-symbolic", "Choose the folder with eboot.bin",
                                             self.on_choose_game))
        self.game_row.add_suffix(flat_button("system-file-manager-symbolic",
                                             "Open in the file manager",
                                             lambda _b: open_folder(self, self.game_dir())))
        game.add(self.game_row)
        # Saves and the shader cache: user/ in the data directory unless chosen.
        self.user_row = Adw.ActionRow(title="Saves folder")
        self.user_status = Gtk.Image()
        self.user_row.add_suffix(self.user_status)
        self.user_row.add_suffix(flat_button("folder-open-symbolic", "Choose the saves folder",
                                             self.on_choose_user))
        self.user_row.add_suffix(flat_button("system-file-manager-symbolic",
                                             "Open in the file manager",
                                             lambda _b: open_folder(self, self.user_dir())))
        self.user_reset = flat_button("edit-undo-symbolic", "Back to the default folder",
                                      self.on_reset_user)
        self.user_row.add_suffix(self.user_reset)
        game.add(self.user_row)
        self.language_row = combo_row("Game language", None, LANGUAGES, self.settings["language"])
        game.add(self.language_row)
        page.add(game)

        # Auto: the new memory model on every GPU; or either by hand.
        mode = Adw.PreferencesGroup(title="Mode")
        self.memory_model_row = combo_row("Memory and translation model", PC_MODEL_SUBTITLE,
                                          MEMORY_MODELS, self.settings.get("memory_model", "auto"))
        mode.add(self.memory_model_row)
        # The GPU the game runs on, as in shadPS4 (laptops with two GPUs).
        self.gpu_row = Adw.ComboRow(title="GPU")
        self.gpu_row.add_suffix(flat_button("view-refresh-symbolic", "Refresh the list",
                                            lambda _button: self.fill_gpus()))
        self.fill_gpus()
        mode.add(self.gpu_row)
        page.add(mode)

        self.mods_group = Adw.PreferencesGroup(
            title="Mods", description=("Extract each mod into its own folder (with dvdroot_ps4, or chr/, "
                                               "parts/, ... directly). When files collide, the mod lower in the "
                                               "list wins. Applied at start."))
        self.mods_enabled_row = Adw.SwitchRow(title="Load mods",
                                               active=self.settings["mods_enabled"])
        self.mods_group.add(self.mods_enabled_row)
        self.mods_folder_row = Adw.ActionRow(title="Mods folder")
        self.mods_folder_row.add_suffix(flat_button("folder-open-symbolic", "Choose the mods folder",
                                                    self.on_choose_mods))
        self.mods_folder_row.add_suffix(flat_button("system-file-manager-symbolic", "Open the mods folder",
                                                    lambda _b: open_folder(self, self.mods_dir())))
        self.mods_folder_row.add_suffix(flat_button("view-refresh-symbolic", "Refresh the list",
                                                    self.on_refresh_mods))
        self.mods_group.add(self.mods_folder_row)
        self.mod_list = FolderList(self.mods_group)
        self.refresh_mods()
        page.add(self.mods_group)

        self.patches_group = Adw.PreferencesGroup(
            title="Third-party patches",
            description="shadPS4-format XML patches for version 01.09 from the patches folder. Applied at start.")
        self.patches_folder_row = Adw.ActionRow(title="Patches folder")
        self.patches_folder_row.add_suffix(flat_button("folder-open-symbolic", "Choose the patches folder",
                                                       self.on_choose_patches))
        self.patches_folder_row.add_suffix(flat_button(
            "system-file-manager-symbolic", "Open the patches folder",
            lambda _b: open_folder(self, patches_dir(self.settings))))
        self.patches_folder_row.add_suffix(flat_button("view-refresh-symbolic", "Refresh the list",
                                                       self.on_refresh_patches))
        self.patches_group.add(self.patches_folder_row)
        self.patch_list = FolderList(self.patches_group)
        self.refresh_patches()
        page.add(self.patches_group)

        screen = Adw.PreferencesGroup(title="Display")
        # The aspect ratio, then its resolutions (rebuilt when it changes, the height kept).
        self.aspect_row = Adw.ComboRow(title="Aspect ratio", subtitle=(
            "Wider than 16:9 shows more to the sides, taller shows more above and below; UI stays at the edges"))
        self.aspect_row.values = ASPECTS
        self.output_row = Adw.ComboRow(title="Output resolution",
                                       subtitle="The upscaler fills the frame; Steam Deck: 1280×800 (16:10)")
        self.output_row.values = []
        screen.add(self.aspect_row)
        screen.add(self.output_row)
        self.live_row = combo_row("Live resolution changes",
                                  "No restart needed, but slower on the Steam Deck and older GPUs",
                                  LIVE_RESOLUTION, self.ini.get("live_resolution", "0"))
        screen.add(self.live_row)
        self.fullscreen_row = Adw.SwitchRow(title="Fullscreen",
                                            active=self.settings["fullscreen"])
        screen.add(self.fullscreen_row)
        # Issue #69: the window (and fullscreen) went to the monitor SDL calls primary.
        self.display_row = Adw.ComboRow(title="Monitor")
        self.display_row.add_suffix(flat_button("view-refresh-symbolic", "Refresh the list",
                                                lambda _button: self.fill_displays()))
        self.fill_displays()
        screen.add(self.display_row)
        aspect = self.ini.get("aspect_ratio", "auto")
        self.fill_aspects(aspect if aspect in ASPECTS else "auto")
        self.fill_outputs(parse_size(self.ini.get("output_res", "1920x1080")))
        self.aspect_row.connect("notify::selected",
                                lambda *_: self.fill_outputs(parse_size(combo_value(self.output_row))))
        self.display_row.connect("notify::selected", lambda *_: self.on_display_changed())
        self.present_row = combo_row("Present mode", None, PRESENT_MODES,
                                     self.settings["present_mode"])
        screen.add(self.present_row)
        self.hdr_row = Adw.SwitchRow(title="Allow HDR", active=self.settings["hdr"])
        screen.add(self.hdr_row)
        page.add(screen)

        # Issue #15: the first gamepad SDL found was taken (wheels and other controllers too).
        controls = Adw.PreferencesGroup(title="Controls")
        self.gamepad_row = Adw.ComboRow(title="Controller")
        # Controller names are long: the selected one is shown in full under the title.
        self.gamepad_row.connect("notify::selected", lambda *_: self.show_gamepad())
        self.gamepad_row.add_suffix(flat_button("view-refresh-symbolic", "Refresh the list",
                                                lambda _button: self.fill_gamepads()))
        self.fill_gamepads()
        controls.add(self.gamepad_row)
        # Bindings: "Assign" waits for a key or button (bb-gpu-capabilities --read-input).
        self.control_rows = {}
        for kind, title, icon in (("key", "Keyboard and mouse", "input-keyboard-symbolic"),
                                  ("pad", "Gamepad", "input-gaming-symbolic")):
            expander = Adw.ExpanderRow(title=title,
                                       subtitle="Button assignments; applied when the game starts")
            for name, label, key_default, pad_default in CONTROLS:
                default = key_default if kind == "key" else pad_default
                if default is None:
                    continue
                row = Adw.ActionRow(title=label)
                row.add_suffix(flat_button(icon, "Assign",
                                           lambda _b, k=kind, n=name: self.assign_control(k, n)))
                row.add_suffix(flat_button("edit-undo-symbolic", "Reset",
                                           lambda _b, k=kind, n=name: self.set_control(k, n, None)))
                expander.add_row(row)
                self.control_rows[(kind, name)] = (row, default)
                self.show_control(kind, name)
            controls.add(expander)
        # Mouse look (runtime_pad.c): a click in the game takes the mouse, F1 lets it go; the mouse
        # turns the game camera itself (gpu/shim/bbport_guest_hooks.cpp, BB_NATIVE_MOUSE).
        self.mouse_look_row = Adw.SwitchRow(
            title="Mouse look",
            subtitle="A click in the game window takes the mouse, F1 releases it",
            active=self.ini.get("mouse_look", "1") == "1")
        controls.add(self.mouse_look_row)
        self.mouse_sensitivity_row = Adw.SpinRow.new_with_range(0.1, 10.0, 0.05)
        self.mouse_sensitivity_row.set_title("Mouse sensitivity")
        self.mouse_sensitivity_row.set_digits(2)
        self.mouse_sensitivity_row.set_value(float(self.ini.get("mouse_sensitivity", "1.0")))
        controls.add(self.mouse_sensitivity_row)
        self.mouse_invert_row = Adw.SwitchRow(title="Invert mouse Y axis",
                                              active=self.ini.get("mouse_invert_y") == "1")
        controls.add(self.mouse_invert_row)
        def mouse_rows_sensitive(*_):
            for row in (self.mouse_sensitivity_row, self.mouse_invert_row):
                row.set_sensitive(self.mouse_look_row.get_active())
        self.mouse_look_row.connect("notify::active", mouse_rows_sensitive)
        mouse_rows_sensitive()
        page.add(controls)

        upscaler = Adw.PreferencesGroup(
            title="Upscaler",
            description="Stored in bbport.ini; in game, change it in the menu (Insert or L3+R3)")
        self.upscaler_row = combo_row("Upscaler", None, UPSCALERS, self.ini["upscaler"])
        self.upscaler_row.connect("notify::selected", lambda *_: self.update_upscaler_status())
        upscaler.add(self.upscaler_row)
        # FSR 4.1.1 is built from the user's own AMD DLL (nothing of AMD's is shipped).
        self.fsr411_row = Adw.ActionRow(title="FSR 4.1.1 from your own AMD DLL")
        self.fsr411_button = Gtk.Button(valign=Gtk.Align.CENTER)
        self.fsr411_button.connect("clicked", self.on_fsr411_button)
        self.fsr411_row.add_suffix(self.fsr411_button)
        self.fsr411_row.set_visible((FSR4CAP_DIR / "build_assets.sh").is_file())
        upscaler.add(self.fsr411_row)
        self.update_fsr411_row()
        # DLSS: NVIDIA's library, chosen like the FSR 4.1.1 DLL (the package may bring one).
        self.dlss_row = Adw.ActionRow(title="DLSS: NVIDIA's library")
        self.dlss_row.add_suffix(flat_button("document-open-symbolic", "Choose a file…",
                                             lambda _b: self.choose_ngx()))
        self.dlss_reset_button = flat_button("edit-undo-symbolic", "Remove the chosen one",
                                             lambda _b: self.reset_ngx())
        self.dlss_row.add_suffix(self.dlss_reset_button)
        upscaler.add(self.dlss_row)
        self.update_dlss_row()
        self.preset_row = combo_row("Preset", None, PRESETS, int(self.ini.get("preset", "4")))
        self.preset_row.connect("notify::selected", lambda *_: self.update_upscaler_status())
        self.output_row.connect("notify::selected", lambda *_: self.update_upscaler_status())
        upscaler.add(self.preset_row)
        self.sharpen_row = Adw.SwitchRow(title="Sharpening (RCAS)",
                                         active=self.ini.get("sharpen") == "1")
        upscaler.add(self.sharpen_row)
        self.sharpness_row = Adw.SpinRow.new_with_range(0.0, 2.0, 0.05)
        self.sharpness_row.set_title("Sharpness")
        self.sharpness_row.set_digits(2)
        self.sharpness_row.set_value(float(self.ini.get("sharpness", "0.5")))
        upscaler.add(self.sharpness_row)
        self.motion_row = Adw.SwitchRow(
            title="Object motion vectors",
            subtitle="Less ghosting on characters; costs about 10% FPS",
            active=self.ini.get("object_motion") == "1")
        upscaler.add(self.motion_row)
        self.show_fps_row = Adw.SwitchRow(title="Show FPS",
                                          active=self.ini.get("show_fps") == "1")
        upscaler.add(self.show_fps_row)
        page.add(upscaler)

        effects = Adw.PreferencesGroup(title="Game effects",
                                       description="Game patches, applied at start")
        self.lod_row = combo_row("Model detail", None, MODEL_LOD,
                                 self.ini.get("model_lod", "0"))
        effects.add(self.lod_row)
        self.effect_rows = {}
        for key, title, default in EFFECTS:
            row = Adw.SwitchRow(title=title,
                                active=self.ini.get(key, "1" if default else "0") == "1")
            if key == "debug_menu":
                row.set_subtitle(("Needs the adhoc folder from Nexus mod #253 (fonts in adhoc/font), in the game's "
                                  "dvdroot_ps4 or as a mod; without it the patch is not applied"))
            self.effect_rows[key] = row
            effects.add(row)
        # The title's "play online / play offline": the port has no PSN.
        self.skip_network_row = Adw.SwitchRow(
            title="Skip the “play online / offline” choice",
            subtitle="The game opens the main menu offline at once (a game patch)",
            active=self.settings.get("skip_network_choice", True))
        effects.add(self.skip_network_row)
        page.add(effects)

        frames = Adw.PreferencesGroup(title="Frame rate")
        self.fps_row = combo_row("Mode", "Which frame rate patch to apply to the game",
                                 FPS_MODES, self.settings["fps_mode"])
        frames.add(self.fps_row)
        self.limit_row = Adw.SpinRow.new_with_range(0, 480, 1)
        self.limit_row.set_title("FPS limit")
        self.limit_row.set_subtitle("0: no limit; set a number to cap the frame rate")
        self.limit_row.set_value(self.settings["fps_limit"])
        frames.add(self.limit_row)
        page.add(frames)

        perf = Adw.PreferencesGroup(title="Performance")
        self.pipe_row = combo_row(
            "Two-stage GPU pipeline",
            "20–30% faster; turn off if unstable", DRAW_PIPE,
            self.settings["draw_pipe"])
        perf.add(self.pipe_row)
        self.readbacks_row = combo_row("GPU data readbacks by the CPU", None, READBACKS,
                                       self.settings["readbacks"])
        perf.add(self.readbacks_row)
        self.preupload_row = combo_row(
            "Background pre-upload into VRAM",
            "Fewer hitches when areas stream in", PREUPLOAD,
            self.settings.get("preupload", ""))
        perf.add(self.preupload_row)
        page.add(perf)

        dev = Adw.PreferencesGroup(title="Developer")
        self.mangohud_row = Adw.SwitchRow(title="MangoHud", active=self.settings["mangohud"])
        dev.add(self.mangohud_row)
        self.save_log_row = Adw.SwitchRow(
            title="Save the log and statistics to a file",
            subtitle="Into the logs folder of the data directory: to look into stutters and crashes",
            active=self.settings.get("save_log", False))
        dev.add(self.save_log_row)
        self.crash_diag_row = Adw.SwitchRow(
            title="Crash diagnostics",
            subtitle="Checks the game's heap and logs writes into its memory; a little slower",
            active=self.settings.get("crash_diag", False))
        dev.add(self.crash_diag_row)
        self.as_0_3_row = Adw.SwitchRow(
            title="Synchronisation as in 0.3",
            subtitle="For finding regressions: the old memory model and copy waits as released in 0.3",
            active=self.settings.get("as_0_3", False))
        dev.add(self.as_0_3_row)
        self.stats_row = Adw.SwitchRow(title="Frame statistics in the log",
                                       subtitle="BB_FRAME_STATS",
                                       active=self.settings["frame_stats"])
        dev.add(self.stats_row)
        self.profile_row = Adw.SwitchRow(title="GPU profile in the log",
                                         subtitle="BB_GPU_PROFILE",
                                         active=self.settings["gpu_profile"])
        dev.add(self.profile_row)
        self.validation_row = Adw.SwitchRow(title="Vulkan validation layers",
                                            subtitle="Much slower",
                                            active=self.settings["vk_validation"])
        dev.add(self.validation_row)
        self.extra_row = Adw.EntryRow(title="Extra variables (NAME=value, space-separated)",
                                      text=self.settings["extra_env"])
        dev.add(self.extra_row)
        page.add(dev)
        return page

    def game_dir(self):
        return Path(self.settings["game_dir"]).expanduser()

    def user_dir(self):
        return Path(self.settings["user_dir"]).expanduser() if self.settings["user_dir"] \
            else DATA_DIR / "user"

    def update_user_status(self):
        path = self.user_dir()
        custom = bool(self.settings["user_dir"])
        self.user_row.set_subtitle(str(path) if custom else "Default: {}".format(path))
        saves = path / "savedata"
        found = saves.is_dir() and any(saves.iterdir())
        self.user_status.set_from_icon_name("object-select-symbolic" if found else "document-new-symbolic")
        self.user_status.set_tooltip_text("Saves found" if found
                                          else "No saves yet: the game will create them here")
        self.user_reset.set_sensitive(custom)

    def choose_folder(self, title, current, done):
        dialog = Gtk.FileDialog(title=title)
        if Path(current).is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(str(current)))

        def finish(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return
            if folder:
                done(folder.get_path())
        dialog.select_folder(self, None, finish)

    def on_choose_user(self, _button):
        def chosen(path):
            self.settings["user_dir"] = path
            self.update_user_status()
            self.store()
        self.choose_folder("Saves folder", self.user_dir(), chosen)

    def on_reset_user(self, _button):
        self.settings["user_dir"] = ""
        self.update_user_status()
        self.store()

    def update_upscaler_status(self):
        value = combo_value(self.upscaler_row)
        if value == "fsr4":
            ok = (PORT_DIR / "fsr4_shaders").is_dir()
            hint = "Assets found" if ok else "No assets: tools/fetch_fsr4_assets.sh"
        elif value == "fsr411":
            directory = fsr411_dir()
            problem = fsr411_problem(directory, combo_value(self.output_row),
                                     int(combo_value(self.preset_row)))
            hint = "Assets for the selected mode found" if not problem else (
                "{}. Build FSR 4.1.1 from your own DLL with the “Choose DLL…” button below".format(problem))
        elif value == "dlss":
            # The game looks for the bridge and NVIDIA's library next to bb-probe (vk_dlss.cpp); the
            # AppImage has neither (NVIDIA's DLSS SDK is not bundled): DLSS then falls back to FSR 3.1.
            binaries = PORT_DIR / ("bin" if PACKAGED else "out")
            found = (binaries / "libbbport_dlss.so").is_file() and bool(
                ngx_libraries(self.user_dir() / "dlss") or ngx_libraries(binaries))
            hint = "DLSS found (needs an NVIDIA RTX GPU)" if found else (
                "DLSS not found: choose NVIDIA's library below (a build with the DLSS bridge is needed too). "
                "The game will use FSR 3.1")
        else:
            hint = "Anti-aliasing at the output resolution, no FSR model" if value == "taa" else None
        self.preset_row.set_sensitive(value not in ("taa", "off"))
        self.sharpen_row.set_sensitive(value != "off")
        self.sharpness_row.set_sensitive(value != "off")
        self.upscaler_row.set_subtitle(hint or "")

    def game_problem(self, path):
        """game_check.problem for the folder, kept until its eboot.bin or param.sfo changes (the
        image hash reads ~90 MB)."""
        try:
            key = (str(path),) + tuple(
                (f.stat().st_size, f.stat().st_mtime_ns) for f in (path / "eboot.bin", path / "sce_sys/param.sfo"))
        except OSError:
            key = (str(path),)
        if getattr(self, "_game_problem_key", None) != key:
            self._game_problem_key = key
            self._game_problem = game_check.problem(path)
        return self._game_problem

    def update_game_status(self):
        path = self.game_dir()
        ok = bool(self.settings["game_dir"]) and (path / "eboot.bin").is_file()
        self.game_row.set_subtitle(str(path) if self.settings["game_dir"] else "not chosen")
        # Other versions of the game start and then crash in its code (issues #7, #13, #14).
        problem = self.game_problem(path) if ok else None
        if not ok:
            tooltip = "No eboot.bin in the folder"
        elif problem:
            kind, title, version = problem
            tooltip = {
                "missing_update": ("The 1.09 update is needed: copy the dumped 1.09 update into the game folder, "
                                   "replacing files (found version {})").format(version),
                "wrong_eboot": ("eboot.bin is not from 1.09: copy eboot.bin from the dumped 1.09 update into the "
                                "game folder, replacing it"),
                "patched_eboot": ("This eboot.bin has Lance McDonald's 60 fps patch baked in, which crashes the "
                                  "game in the gestures menu: copy a clean eboot.bin from the dumped 1.09 update "
                                  "into the game folder, replacing it"),
                "other_title": ("Not a retail release of Bloodborne (found {}): Bloodborne from any region with "
                                "update 1.09 is needed").format(title),
                "unreadable": "eboot.bin cannot be read as a decrypted PS4 executable: dump the game again",
                "damaged_files": ("The game files were damaged when extracted: the shaders do not unpack and the "
                                  "game would hang while loading. Extract the game and the 1.09 update again with "
                                  "a fixed tool (issue #81)"),
            }[kind]
            self.game_row.set_subtitle(f"{path}\n{tooltip}")
        else:
            tooltip = "Bloodborne CUSA03173, version 1.09"
        self.game_status.set_from_icon_name("object-select-symbolic" if ok and not problem else "dialog-warning-symbolic")
        self.game_status.set_tooltip_text(tooltip)
        self.launch_button.set_sensitive(ok or self.process is not None)

    def on_choose_game(self, _button):
        def chosen(path):
            self.settings["game_dir"] = path
            self.update_game_status()
            self.store()
        self.choose_folder("Game folder (with eboot.bin)", self.game_dir(), chosen)

    def show_control(self, kind, name):
        row, default = self.control_rows[(kind, name)]
        value = self.ini.get(f"{kind}.{name}")
        if value is None:
            row.set_subtitle("{} (default)".format(default) if default else "not assigned")
        else:
            row.set_subtitle(value or "not assigned")

    def set_control(self, kind, name, value):
        """value: the binding, or None for the default."""
        self.ini[f"{kind}.{name}"] = value
        self.show_control(kind, name)
        self.store()

    def assign_control(self, kind, name):
        tool = PORT_DIR / ("bin" if PACKAGED else "out") / "bb-gpu-capabilities"
        try:
            process = Gio.Subprocess.new([str(tool), "--read-input", kind],
                                         Gio.SubprocessFlags.STDOUT_PIPE)
        except GLib.Error as error:
            self.toasts.add_toast(Adw.Toast(title="Could not start: {}".format(error.message)))
            return
        row, _default = self.control_rows[(kind, name)]
        row.set_subtitle("Press a key or a button… (Esc cancels)")

        def done(proc, result):
            try:
                _ok, out, _err = proc.communicate_utf8_finish(result)
            except GLib.Error:
                out = ""
            words = (out or "").strip().split(" ", 1)
            if len(words) == 2 and words[0] == kind:
                self.set_control(kind, name, words[1])
            else:
                self.show_control(kind, name)
        process.communicate_utf8_async(None, None, done)

    def fill_gamepads(self):
        """The controller choices: the first connected one, the connected ones, and the saved
        choice while it is not connected."""
        current = self.settings.get("gamepad", "")
        choices = [("Auto", "", "First connected")]
        choices += [(name, guid, name) for guid, name in connected_gamepads()]
        if current and current not in [guid for _, guid, _ in choices]:
            name = self.settings.get("gamepad_name") or current
            choices.append(("{} (not connected)".format(name), current, name))
        self.gamepad_row.set_model(Gtk.StringList.new([label for label, _, _ in choices]))
        self.gamepad_row.values = [guid for _, guid, _ in choices]
        self.gamepad_row.names = [name for _, _, name in choices]
        self.gamepad_row.set_selected(self.gamepad_row.values.index(current) if current in self.gamepad_row.values else 0)
        self.show_gamepad()

    def monitor_size(self):
        """The size of the monitor chosen for the game (Auto's aspect ratio), None if unknown."""
        value = combo_value(self.display_row) if self.display_row.values else ""
        sizes = getattr(self, "display_sizes", {})
        return sizes.get(value) or sizes.get("")

    def fill_aspects(self, current):
        labels = ["Auto" + f" ({resolved_aspect('auto', self.monitor_size())})"] + ASPECTS[1:]
        self.aspect_row.set_model(Gtk.StringList.new(labels))
        self.aspect_row.set_selected(ASPECTS.index(current))

    def fill_outputs(self, keep):
        """The chosen aspect ratio's resolutions; the one of `keep`'s height selected."""
        sizes = output_sizes(combo_value(self.aspect_row), self.monitor_size())
        chosen = nearest_output(sizes, keep)
        self.output_row.values = [f"{w}x{h}" for w, h in sizes]
        self.output_row.set_model(Gtk.StringList.new(
            [f"{w}×{h}" + (" (Steam Deck)" if (w, h) == (1280, 800) else "") for w, h in sizes]))
        self.output_row.set_selected(sizes.index(chosen))

    def on_display_changed(self):
        aspect, output = combo_value(self.aspect_row), parse_size(combo_value(self.output_row))
        self.fill_aspects(aspect)
        self.fill_outputs(output)

    def fill_displays(self):
        """The monitor choices: the primary one, the connected ones, and the saved choice while it
        is not connected."""
        current = self.settings.get("display", "")
        displays = connected_displays()
        self.display_sizes = {value: size for value, _label, size, _primary in displays}
        primary = [size for _value, _label, size, is_primary in displays if is_primary]
        if primary:
            self.display_sizes[""] = primary[0]
        choices = [("Primary", "")] + [(label, value) for value, label, _size, _primary in displays]
        if current and current not in [value for _, value in choices]:
            choices.append(("{} (not connected)".format(current), current))
        self.display_row.set_model(Gtk.StringList.new([label for label, _ in choices]))
        self.display_row.values = [value for _, value in choices]
        self.display_row.set_selected(self.display_row.values.index(current) if current in self.display_row.values else 0)

    def fill_gpus(self):
        """The GPU choices: the port's own (named), the GPUs found, and the saved one while it is
        not found."""
        current = self.settings.get("gpu", "")
        gpus = connected_gpus()
        best = [name for _index, _vendor, _kind, name, is_best in gpus if is_best]
        auto = "Auto" + (f" ({best[0]})" if best else "")
        choices = [(auto, "")]
        for _index, _vendor, kind, name, _best in gpus:
            note = {"integrated": "integrated", "cpu": "software, very slow"}.get(kind)
            choices.append((f"{name} ({note})" if note else name, name))
        if current and current not in [value for _, value in choices]:
            choices.append(("{} (not found)".format(current), current))
        self.gpu_row.set_model(Gtk.StringList.new([label for label, _ in choices]))
        self.gpu_row.values = [value for _, value in choices]
        self.gpu_row.set_selected(self.gpu_row.values.index(current) if current in self.gpu_row.values else 0)
        self.gpu_row.set_subtitle("On a laptop with two GPUs, choose the discrete one; applies at game startup")

    def show_gamepad(self):
        names = getattr(self.gamepad_row, "names", None)
        selected = names[self.gamepad_row.get_selected()] if names else ""
        self.gamepad_row.set_subtitle("\n".join(
            line for line in (selected, "The chosen one is used as soon as it connects") if line))

    def store(self):
        s = self.settings
        s["gamepad"] = combo_value(self.gamepad_row)
        s["gamepad_name"] = self.gamepad_row.names[self.gamepad_row.get_selected()]
        s["display"] = combo_value(self.display_row)
        s["gpu"] = combo_value(self.gpu_row)
        s["skip_network_choice"] = self.skip_network_row.get_active()
        s["language"] = combo_value(self.language_row)
        s["fullscreen"] = self.fullscreen_row.get_active()
        s["present_mode"] = combo_value(self.present_row)
        s["hdr"] = self.hdr_row.get_active()
        s["fps_mode"] = combo_value(self.fps_row)
        s["fps_limit"] = int(self.limit_row.get_value())
        s["draw_pipe"] = combo_value(self.pipe_row)
        s["readbacks"] = combo_value(self.readbacks_row)
        s["preupload"] = combo_value(self.preupload_row)
        s["mangohud"] = self.mangohud_row.get_active()
        s["frame_stats"] = self.stats_row.get_active()
        s["save_log"] = self.save_log_row.get_active()
        s["crash_diag"] = self.crash_diag_row.get_active()
        s["memory_model"] = combo_value(self.memory_model_row)
        s["as_0_3"] = self.as_0_3_row.get_active()
        s["gpu_profile"] = self.profile_row.get_active()
        s["vk_validation"] = self.validation_row.get_active()
        s["extra_env"] = self.extra_row.get_text().strip()
        s["mods_enabled"] = self.mods_enabled_row.get_active()
        s["online"] = self.online_row.get_active()
        s["online_bbsc"] = self.bbsc_row.get_active()
        s["online_community"] = self.community_row.get_text().strip()
        s["online_server"] = self.server_row.get_text().strip()
        s["online_webapi"] = self.webapi_row.get_text().strip()
        s["online_npid"] = self.npid_row.get_text().strip()
        s["online_password"] = self.password_row.get_text()
        s["online_upnp"] = self.upnp_row.get_active()
        s["online_pool"] = self.online_pool()
        s["thd_server"] = self.thd_server_row.get_text().strip()
        s["thd_online_id"], s["thd_token"] = self.thd_id, self.thd_token
        self.save_mod_profile()
        self.save_patch_profile()
        save_settings(s)
        self.ini.update({
            "upscaler": combo_value(self.upscaler_row),
            "preset": str(combo_value(self.preset_row)),
            "sharpen": "1" if self.sharpen_row.get_active() else "0",
            "sharpness": f"{self.sharpness_row.get_value():.2f}",
            "object_motion": "1" if self.motion_row.get_active() else "0",
            "show_fps": "1" if self.show_fps_row.get_active() else "0",
            "aspect_ratio": combo_value(self.aspect_row),
            "output_res": combo_value(self.output_row),
            "model_lod": combo_value(self.lod_row),
            "live_resolution": combo_value(self.live_row),
            "mouse_look": "1" if self.mouse_look_row.get_active() else "0",
            "mouse_sensitivity": f"{self.mouse_sensitivity_row.get_value():.2f}",
            "mouse_invert_y": "1" if self.mouse_invert_row.get_active() else "0",
            **{key: "1" if row.get_active() else "0" for key, row in self.effect_rows.items()},
        })
        save_ini(self.ini, self.ini_lines)
        self.ini, self.ini_lines = load_ini()

    def environment(self):
        return game_environment(self.settings)

    # --- mods ----------------------------------------------------------------------------

    def mods_dir(self):
        return Path(self.settings.get("mods_dir") or DATA_DIR / "mods").expanduser()

    def save_mod_profile(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        rows = self.mod_list.rows
        profile = {"order": [name for name, _ in rows],
                   "disabled": [name for name, row in rows if not row.get_active()]}
        (DATA_DIR / "mods.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def refresh_mods(self):
        self.mod_list.clear()
        self.mods_folder_row.set_subtitle(str(self.mods_dir()))
        try:
            profile = json.loads((DATA_DIR / "mods.json").read_text(encoding='utf-8'))
        except (OSError, ValueError):
            profile = {}
        available = discover_mods(self.mods_dir())
        order = list(dict.fromkeys(n for n in [*profile.get("order", []), *available] if n in available))
        for name in order:
            row = Adw.SwitchRow(title=name, active=name not in profile.get("disabled", []))
            row.add_suffix(flat_button("go-up-symbolic", "Load earlier",
                                        lambda _b, n=name: self.move_mod(n, -1)))
            row.add_suffix(flat_button("go-down-symbolic", "Load later",
                                        lambda _b, n=name: self.move_mod(n, 1)))
            self.mod_list.add(name, row)
        if not order:
            self.mods_folder_row.set_subtitle(f"{self.mods_dir()} — {'No mods'}")

    def move_mod(self, name, direction):
        rows = self.mod_list.rows
        index = next(i for i, (n, _) in enumerate(rows) if n == name)
        target = index + direction
        if 0 <= target < len(rows):
            rows[index], rows[target] = rows[target], rows[index]
            self.save_mod_profile()
            self.refresh_mods()

    def on_refresh_mods(self, _button):
        self.save_mod_profile()
        self.refresh_mods()

    def on_choose_mods(self, _button):
        self.save_mod_profile()

        def chosen(path):
            self.settings["mods_dir"] = path
            self.refresh_mods()
            self.store()
        self.choose_folder("Mods folder", self.mods_dir(), chosen)

    # --- third-party patches -------------------------------------------------------------

    def save_patch_profile(self):
        """patches.json: the switches that differ from each file's isEnabled."""
        enabled, disabled = [], []
        for key, row in self.patch_list.rows:
            if row.get_active() != row.default:
                (enabled if row.get_active() else disabled).append(key)
        path = DATA_DIR / "patches.json"
        try:
            profile = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            profile = {}
        # Patches of files not listed now (another folder) keep their choice.
        shown = {key for key, _ in self.patch_list.rows}
        profile = {"enabled": sorted({k for k in profile.get("enabled", []) if k not in shown} | set(enabled)),
                   "disabled": sorted({k for k in profile.get("disabled", []) if k not in shown} | set(disabled))}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def refresh_patches(self):
        self.patch_list.clear()
        directory = patches_dir(self.settings)
        try:
            profile = json.loads((DATA_DIR / "patches.json").read_text(encoding='utf-8'))
        except (OSError, ValueError):
            profile = {}
        found = external_patches(directory)
        for key, _path, meta in found:
            default = meta.get("isEnabled", "false").lower() == "true"
            active = key in profile.get("enabled", []) or (default and key not in profile.get("disabled", []))
            subtitle = key.split("/", 1)[0]
            if meta.get("Author"):
                subtitle += " · " + "Author: {}".format(meta.get("Author"))
            row = Adw.SwitchRow(title=GLib.markup_escape_text(meta.get("Name") or key),
                                subtitle=GLib.markup_escape_text(subtitle), active=active)
            if meta.get("Note"):
                row.set_tooltip_text(meta.get("Note").replace("\\n", "\n"))
            row.default = default
            self.patch_list.add(key, row)
        self.patches_folder_row.set_subtitle(
            str(directory) if found else f"{directory} — {'No patches'}")

    def on_refresh_patches(self, _button):
        self.save_patch_profile()
        self.refresh_patches()

    def on_choose_patches(self, _button):
        self.save_patch_profile()

        def chosen(path):
            self.settings["patches_dir"] = path
            self.refresh_patches()
            self.store()
        self.choose_folder("Patches folder", patches_dir(self.settings), chosen)

    # --- log page ------------------------------------------------------------------------

    # --- online page ---------------------------------------------------------------------

    def build_online_page(self):
        s = self.settings
        page = Adw.PreferencesPage()
        play = Adw.PreferencesGroup(description=(
            "Messages, bloodstains and ghosts come from the game server; bells and summons "
            "go through a shadNet server. Both default to Seamless Hunt (BBSC's server). "
            "Online play works with the Windows version: everyone needs game version 1.09 and the same server"))
        self.online_row = Adw.SwitchRow(title="Play online",
                                        subtitle="Off: the game stays offline, as before",
                                        active=s["online"])
        play.add(self.online_row)
        if not online_module():
            self.online_row.set_sensitive(False)
            self.online_row.set_subtitle("This build has no online module (libbbnet20.so): offline play only")
        self.pool_row = combo_row("Pool", "Who to play with: everyone in a session needs the same pool", [
            ("Seamless Hunt (seamlesshunt.com)", "seamless",
             "BBSC server: seamless co-op, bells and summons; create an account on the website"),
            ("The Hunter's Dream (thehuntersdream.com)", "huntersdream",
             "Co-op with bbhost players through The Hunter's Dream; sign in with Discord"),
        ], "huntersdream" if s.get("online_pool") == "huntersdream" else "seamless")
        play.add(self.pool_row)
        page.add(play)

        game = Adw.PreferencesGroup(title="Game server (messages, bloodstains, ghosts)")
        self.game_group = game
        self.community_row = Adw.EntryRow(title="Game server", text=s["online_community"])
        game.add(self.community_row)
        page.add(game)

        coop = None
        coop = Adw.PreferencesGroup(
            title="Co-op server (bells and summons)",
            description=("play.seamlesshunt.com:31313 is the Seamless Hunt (BBSC) server. "
                         "shadPS4's public server accepts only shadPS4 builds. For a private server, "
                         "enter host:port from its owner. WebAPI: leave it empty to use the server "
                         "address with port 31315"))
        self.server_row = Adw.EntryRow(title="Server address", text=s["online_server"])
        self.webapi_row = Adw.EntryRow(title="WebAPI address", text=s["online_webapi"])
        coop.add(self.server_row)
        coop.add(self.webapi_row)
        self.bbsc_row = Adw.SwitchRow(
            title="Seamless co-op (BBSC)",
            subtitle=("Sessions survive deaths, lamps, area changes and bosses; up to 5 hunters. "
                      "Needs a server running BBSC's game server, enabled by every player"),
            active=s.get("online_bbsc", False))
        coop.add(self.bbsc_row)
        self.coop_group = coop
        page.add(coop)

        account = Adw.PreferencesGroup(
            title="Account",
            description=("Your shadNet account name, not your email. Register at seamlesshunt.com "
                         "or ask the owner of a private server. The password is saved on this computer "
                         "with the launcher settings"))
        self.npid_row = Adw.EntryRow(title="Online ID (NPID)", text=s["online_npid"])
        self.password_row = Adw.PasswordEntryRow(title="Password", text=s["online_password"])
        account.add(self.npid_row)
        account.add(self.password_row)
        self.account_group = account
        page.add(account)

        thd = Adw.PreferencesGroup(
            title="The Hunter's Dream",
            description=("Sign in through Discord, as in bbhost: confirm a code on the website. No password "
                         "needed; the token is saved on this computer with the launcher settings"))
        self.thd_server_row = Adw.EntryRow(title="Server address", text=s.get("thd_server", ""))
        self.thd_server_row.set_tooltip_text(online.HUNTERS_DREAM_SERVER)
        thd.add(self.thd_server_row)
        self.thd_account_row = Adw.ActionRow()
        self.thd_sign_button = Gtk.Button(valign=Gtk.Align.CENTER)
        self.thd_sign_button.connect("clicked", self.on_thd_sign)
        self.thd_account_row.add_suffix(self.thd_sign_button)
        thd.add(self.thd_account_row)
        self.thd_group = thd
        self.thd_id, self.thd_token = s.get("thd_online_id", ""), s.get("thd_token", "")
        self.thd_signing = False
        self.thd_cancel = False
        self.show_thd_account()
        page.add(thd)

        connection = Adw.PreferencesGroup(
            title="Connection",
            description=("Everyone in a session needs the same game version (1.09) and the same server. Cheats "
                         "change the game for the other players too: turn them off when you play together"))
        self.upnp_row = Adw.SwitchRow(title="UPnP (open a port on the router automatically)",
                                      subtitle="Turn it off with Tailscale or another VPN",
                                      active=s["online_upnp"])
        connection.add(self.upnp_row)
        test = Adw.ActionRow(title="Test the connection")
        self.test_button = Gtk.Button(label="Test", valign=Gtk.Align.CENTER)
        self.test_button.connect("clicked", self.on_test_connection)
        test.add_suffix(self.test_button)
        connection.add(test)
        self.test_rows = []
        self.connection_group = connection
        page.add(connection)
        self.pool_row.connect("notify::selected", self.on_pool_changed)
        self.on_pool_changed()
        return page

    def online_pool(self):
        return combo_value(self.pool_row)

    def on_pool_changed(self, *_):
        pool = self.online_pool()
        legacy, thd = pool == "seamless", pool == "huntersdream"
        self.game_group.set_visible(not thd)
        self.coop_group.set_visible(not thd)
        self.account_group.set_visible(not thd)
        self.bbsc_row.set_visible(legacy)
        self.thd_group.set_visible(thd)
        if not online_module(pool):
            self.pool_row.set_subtitle("This build has no module for this pool (libbbnet20.so)")

    def show_thd_account(self):
        link = getattr(self, "thd_link", None)
        if link is not None:
            self.thd_account_row.remove(link)
            self.thd_link = None
        if self.thd_id and self.thd_token:
            self.thd_account_row.set_title("Signed in as {}".format(GLib.markup_escape_text(self.thd_id)))
            self.thd_account_row.set_subtitle("")
            self.thd_sign_button.set_label("Sign out")
        else:
            self.thd_account_row.set_title("Not signed in")
            self.thd_account_row.set_subtitle("A Discord account linked to The Hunter's Dream is required")
            self.thd_sign_button.set_label("Sign in with Discord")
        if self.thd_signing:
            self.thd_sign_button.set_label("Cancel")
        self.thd_sign_button.set_sensitive(True)

    def on_thd_sign(self, _button):
        if self.thd_signing:
            self.thd_cancel = True  # the waiting thread stops; done() resets the row
            return
        self.thd_cancel = False
        if self.thd_id and self.thd_token:
            self.thd_id = self.thd_token = ""
            self.show_thd_account()
            return
        self.thd_signing = True
        self.show_thd_account()
        server = self.thd_server_row.get_text().strip()

        def show_code(page, code):
            def show():
                self.thd_account_row.set_title("Sign-in code: {}".format(code))
                self.thd_account_row.set_subtitle(GLib.markup_escape_text((
                    "On {}: 1) click “Sign in with Discord to link” and sign in; "
                    "2) return to the page and enter the code in the code field (not “Sign in with a code from the game”). "
                    "The code has been copied to the clipboard").format(page)))
                # The code goes to the clipboard; the page opens by whatever works in this environment
                # (an AppImage may have no default handler for the GIO call), else a button does it.
                try:
                    self.thd_account_row.get_clipboard().set(code)
                except Exception:
                    pass
                if not open_url(page):
                    link = Gtk.LinkButton(uri=page, label="Open page", valign=Gtk.Align.CENTER)
                    self.thd_account_row.add_prefix(link)
                    self.thd_link = link
                return False
            GLib.idle_add(show)

        def done(name, token, error):
            self.thd_signing = False
            if error:
                self.show_thd_account()
                if error != "cancelled":
                    self.thd_account_row.set_subtitle(GLib.markup_escape_text(error))
            else:
                self.thd_id, self.thd_token = name, token
                self.settings["thd_online_id"], self.settings["thd_token"] = name, token
                save_settings(self.settings)
                self.show_thd_account()
            return False

        def work():
            try:
                name, token = online.thd_sign_in(server, show_code, device="bbport on Linux",
                                                  cancelled=lambda: self.thd_cancel)
            except ValueError as error:
                GLib.idle_add(done, "", "", str(error))
                return
            GLib.idle_add(done, name, token, "")
        threading.Thread(target=work, daemon=True).start()

    def online_addresses(self):
        server = self.server_row.get_text().strip() or online.SHADNET_SERVER
        community = online.community_address(self.community_row.get_text())
        webapi = online.webapi_setting(self.webapi_row.get_text(), server, community)
        return server, webapi, community

    def on_test_connection(self, _button):
        if self.online_pool() == "huntersdream":
            self.test_thd_connection()
            return
        server, webapi, community = self.online_addresses()
        names = {"game": "Game server", "shadnet": "shadNet server", "webapi": "WebAPI"}
        for row in self.test_rows:
            self.connection_group.remove(row)
        self.test_rows = []
        self.test_button.set_sensitive(False)
        self.test_button.set_label("Checking…")

        def show(results):
            for name, address, ok, detail in results:
                # Plain text: an error such as "<urlopen error ...>" is not Pango markup.
                row = Adw.ActionRow(title=GLib.markup_escape_text(f"{names[name]}: {address}"),
                                    subtitle=GLib.markup_escape_text(
                                        "reachable" if ok else f"{'not reachable'} ({detail})"))
                row.add_prefix(Gtk.Image(icon_name="object-select-symbolic" if ok else "dialog-warning-symbolic"))
                self.connection_group.add(row)
                self.test_rows.append(row)
            self.test_button.set_sensitive(True)
            self.test_button.set_label("Test")
            return False

        def work():
            results = online.check(server, webapi, community)
            GLib.idle_add(show, results)
        threading.Thread(target=work, daemon=True).start()

    def test_thd_connection(self):
        names = {"game": "Game server", "service": "Co-op service"}
        server = self.thd_server_row.get_text().strip()
        for row in self.test_rows:
            self.connection_group.remove(row)
        self.test_rows = []
        self.test_button.set_sensitive(False)
        self.test_button.set_label("Checking…")

        def show(results):
            for name, address, ok, detail in results:
                row = Adw.ActionRow(title=GLib.markup_escape_text(f"{names[name]}: {address}"),
                                    subtitle=GLib.markup_escape_text(
                                        "reachable" if ok else f"not reachable ({detail})"))
                row.add_prefix(Gtk.Image(icon_name="object-select-symbolic" if ok else "dialog-warning-symbolic"))
                self.connection_group.add(row)
                self.test_rows.append(row)
            self.test_button.set_sensitive(True)
            self.test_button.set_label("Test")
            return False

        threading.Thread(target=lambda: GLib.idle_add(show, online.check_thd(server)), daemon=True).start()

    def build_log_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.log_view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False,
                                     wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.log_view.set_top_margin(8)
        self.log_view.set_left_margin(8)
        self.log_view.set_right_margin(8)
        scroller = Gtk.ScrolledWindow(vexpand=True, child=self.log_view)
        self.log_scroller = scroller
        box.append(scroller)
        bar = Gtk.ActionBar()
        self.export_log_button = Gtk.Button(label="Export log…")
        self.export_log_button.connect("clicked", self.on_export_log)
        bar.pack_end(self.export_log_button)
        self.copy_log_button = Gtk.Button(label="Copy")
        self.copy_log_button.connect("clicked", self.on_copy_log)
        bar.pack_end(self.copy_log_button)
        box.append(bar)
        buffer = self.log_view.get_buffer()
        buffer.connect("changed", self.on_log_changed)
        self.on_log_changed(buffer)
        return box

    def on_log_changed(self, buffer):
        has_text = buffer.get_char_count() > 0
        self.copy_log_button.set_sensitive(has_text)
        self.export_log_button.set_sensitive(has_text)

    def log_text(self):
        buffer = self.log_view.get_buffer()
        return buffer.get_text(*buffer.get_bounds(), False)

    def on_copy_log(self, _button):
        self.get_clipboard().set(self.log_text())
        self.toasts.add_toast(Adw.Toast(title="Log copied"))

    def on_export_log(self, _button):
        text = self.log_text()
        dialog = Gtk.FileDialog(title="Export log")
        dialog.set_initial_name(f"bbport-{time.strftime('%Y%m%d_%H%M%S')}.log")

        def finish(dialog, result):
            try:
                chosen = dialog.save_finish(result)
            except GLib.Error:
                return
            if not chosen or not chosen.get_path():
                return
            try:
                Path(chosen.get_path()).write_text(text, encoding="utf-8")
            except OSError as error:
                self.toasts.add_toast(Adw.Toast(
                    title="Could not save the log: {}".format(error.strerror or error)))
                return
            self.toasts.add_toast(Adw.Toast(title="Log saved: {}".format(chosen.get_path())))
        dialog.save(self, None, finish)

    def append_log(self, text):
        buffer = self.log_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), text)
        extra = buffer.get_line_count() - MAX_LOG_LINES
        if extra > 0:
            buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_line(extra)[1])
        adj = self.log_scroller.get_vadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper()) and False)

    # --- process -------------------------------------------------------------------------

    def on_launch(self, _button):
        if self.process:
            self.stop_game()
            return
        npid = self.npid_row.get_text().strip()
        if online_module() and not self.online_row.get_active() and npid and hasattr(Adw, "AlertDialog"):
            dialog = Adw.AlertDialog(heading="Bloodborne", body=("An online account is filled in, but “Play "
                                                                 "online” is off"))
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("offline", "Play offline")
            dialog.add_response("online", "Play online")
            dialog.set_response_appearance("online", Adw.ResponseAppearance.SUGGESTED)

            def on_response(_dialog, response):
                if response != "cancel":
                    self.online_row.set_active(response == "online")
                    self.start_game()
            dialog.connect("response", on_response)
            dialog.present(self)
            return
        self.start_game()

    def start_game(self):
        if self.online_row.get_active() and "@" in self.npid_row.get_text():
            self.alert("Bloodborne", ("The Online ID is the account name (NPID) you registered on the server, not "
                                      "your email address"))
            self.stack.set_visible_child_name("online")
            return
        self.store()
        self.log_view.get_buffer().set_text("")
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
        launcher.set_environ([f"{k}={v}" for k, v in self.environment().items()])
        launcher.set_cwd(str(PORT_DIR))
        try:
            # setsid: the game and its helpers form one process group, stopped together.
            self.process = launcher.spawnv(["setsid", "bash", str(PORT_DIR / "run.sh")])
        except GLib.Error as error:
            self.toasts.add_toast(Adw.Toast(title="Could not start: {}".format(error.message)))
            return
        self.stream = Gio.DataInputStream.new(self.process.get_stdout_pipe())
        self.read_line()
        self.process.wait_async(None, self.on_exit)
        self.update_launch_button()
        self.stack.set_visible_child_name("log")

    def read_line(self):
        self.stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self.on_line)

    def on_line(self, stream, result):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            return
        if line is None:
            return
        self.append_log(line + "\n")
        self.read_line()

    def stop_game(self):
        if not self.process:
            return
        pid = int(self.process.get_identifier())
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            self.process.force_exit()
        GLib.timeout_add_seconds(3, self.kill_if_running, pid)

    def kill_if_running(self, pid):
        if self.process:
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                pass
        return False

    def on_exit(self, process, result):
        try:
            process.wait_finish(result)
        except GLib.Error:
            pass
        status = process.get_exit_status() if process.get_if_exited() else -1
        self.process = None
        self.update_launch_button()
        self.update_game_status()
        self.append_log("\n— the game exited (code {}) —\n".format(status))

    def on_close(self, _window):
        self.store()
        if self.process:
            self.stop_game()
        if self.fsr411_build:
            self.stop_fsr411_build()
        return False

    # --- FSR 4.1.1 from the user's DLL -----------------------------------------------------

    def update_fsr411_row(self, progress=None):
        building = self.fsr411_build is not None
        self.fsr411_button.set_label("Cancel" if building else "Choose DLL…")
        if progress:
            self.fsr411_row.set_subtitle(progress)
        elif not building:
            self.fsr411_row.set_subtitle(("Build FSR 4.1.1 from amd_fidelityfx_upscaler_dx12.dll 4.1.x "
                                          "(OptiScaler: the FSR4_LATEST folder, or from a game with FSR 4.1). "
                                          "Needs GE-Proton 10+, Proton Experimental or Proton-CachyOS; 2–5 minutes "
                                          "(RDNA4: twice as long, with the FP8 variant)"))

    def alert(self, heading, body):
        if hasattr(Adw, "AlertDialog"):
            dialog = Adw.AlertDialog(heading=heading, body=body)
            dialog.add_response("ok", "OK")
            dialog.present(self)
        else:
            self.toasts.add_toast(Adw.Toast(title=f"{heading}: {body}", timeout=10))

    def update_dlss_row(self):
        own = ngx_libraries(self.user_dir() / "dlss")
        bundled = ngx_libraries(binaries_dir())
        bridge = (binaries_dir() / "libbbport_dlss.so").is_file()
        if own:
            text = "Your own: {}".format(own[-1].name[len(NGX_PREFIX):])
        elif bundled:
            text = "From this build: {}".format(bundled[-1].name[len(NGX_PREFIX):])
        else:
            text = "None: choose libnvidia-ngx-dlss.so.* from NVIDIA's DLSS SDK ({})".format(DLSS_SDK_URL)
        if not bridge:
            text += "\n" + "This build has no DLSS bridge (libbbport_dlss.so): DLSS will not work"
        self.dlss_row.set_subtitle(text)
        self.dlss_reset_button.set_sensitive(bool(own))
        if hasattr(self, "sharpness_row"):  # built after this row
            self.update_upscaler_status()

    def choose_ngx(self):
        dialog = Gtk.FileDialog(title="NVIDIA's DLSS library (libnvidia-ngx-dlss.so.*)")
        files = Gtk.FileFilter()
        files.set_name("libnvidia-ngx-dlss.so.*, nvngx_dlss.dll")
        for pattern in ("libnvidia-ngx-dlss.so*", "*.dll", "*.DLL"):
            files.add_pattern(pattern)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(files)
        dialog.set_filters(filters)
        dialog.set_default_filter(files)

        def finish(dialog, result):
            try:
                chosen = dialog.open_finish(result)
            except GLib.Error:
                return
            if chosen and chosen.get_path():
                self.install_ngx(Path(chosen.get_path()))
        dialog.open(self, None, finish)

    def install_ngx(self, path):
        if path.suffix.lower() == ".dll":
            self.alert("A Linux library is needed",
                       "{} is the Windows DLSS library; NVIDIA's Linux driver does not load it. "
                       "libnvidia-ngx-dlss.so.<version> from NVIDIA's DLSS SDK is needed: {}".format(
                           path.name, DLSS_SDK_URL))
            return
        try:
            with open(path, "rb") as f:
                elf = f.read(4) == b"\x7fELF"
        except OSError as error:
            self.alert("Could not read the file", str(error))
            return
        if not path.name.startswith(NGX_PREFIX) or not elf:
            self.alert("This is not the DLSS library",
                       "libnvidia-ngx-dlss.so.<version> from NVIDIA's DLSS SDK is needed: {}".format(
                           DLSS_SDK_URL))
            return
        target = self.user_dir() / "dlss"
        try:
            target.mkdir(parents=True, exist_ok=True)
            for old in ngx_libraries(target):
                old.unlink()
            shutil.copy2(path, target / path.name)
        except OSError as error:
            self.alert("Could not copy the library", str(error))
            return
        self.toasts.add_toast(Adw.Toast(title="DLSS {}: ready".format(path.name[len(NGX_PREFIX):])))
        self.update_dlss_row()

    def reset_ngx(self):
        for old in ngx_libraries(self.user_dir() / "dlss"):
            try:
                old.unlink()
            except OSError:
                pass
        self.update_dlss_row()

    def choose_dll(self, title, done):
        dialog = Gtk.FileDialog(title=title)
        dll = Gtk.FileFilter()
        dll.set_name("DLL")
        dll.add_pattern("*.dll")
        dll.add_pattern("*.DLL")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(dll)
        dialog.set_filters(filters)
        dialog.set_default_filter(dll)
        folder = self.settings.get("fsr411_dll_dir", "")
        if folder and Path(folder).is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(folder))

        def finish(dialog, result):
            try:
                chosen = dialog.open_finish(result)
            except GLib.Error:
                return
            if chosen and chosen.get_path():
                done(chosen.get_path())
        dialog.open(self, None, finish)

    def on_fsr411_button(self, _button):
        if self.fsr411_build:
            self.stop_fsr411_build()
            return
        self.choose_dll("AMD upscaler DLL (amd_fidelityfx_upscaler_dx12.dll)",
                        self.on_fsr411_dll)

    def on_fsr411_dll(self, upscaler, loader=None):
        import dll_info
        self.settings["fsr411_dll_dir"] = str(Path(upscaler).parent)
        status, problem, details = dll_info.inspect(upscaler, loader)
        kind = details.get("kind")
        version = details.get("version", "?")
        if status == dll_info.UNSUPPORTED:
            if kind == "fsr4_0":
                body = ("{}: FSR {}. This is AMD's official FSR 4.0.x: it is enabled on RDNA4 GPUs (RX 9000) "
                        "only and does not start under Proton on other GPUs, so it cannot be recorded.\n\n"
                        "FSR 4.1.x is needed: for example FSR4_LATEST from OptiScaler, or the DLL of a game "
                        "with FSR 4.1.").format(Path(upscaler).name, version)
            elif kind == "not_fsr4":
                body = ("{}: this DLL has no FSR 4 inside. amd_fidelityfx_upscaler_dx12.dll version 4.1.x is "
                        "needed.").format(Path(upscaler).name)
            else:
                models = ", ".join(details.get("models", [])) or "none"
                body = ("{}: version {}, FSR 4 models: {}.\n\n"
                        "bbport replays AMD's official FSR 4.1.x only (model v07_fp8_no_scale): for example "
                        "FSR4_LATEST from OptiScaler, or amd_fidelityfx_upscaler_dx12.dll from a game with "
                        "FSR 4.1. Community builds (4.0.2b and the like) are laid out differently and are not "
                        "supported yet.").format(Path(upscaler).name, version, models)
            self.alert("This DLL does not fit", body)
            return
        if status == dll_info.NO_LOADER:
            if kind == "loader_is_upscaler":
                self.alert("This is not the loader",
                           "{} is the upscaler DLL. The loader is called amd_fidelityfx_loader_dx12.dll "
                           "(amd_fidelityfx_dx12.dll in OptiScaler) and lies in the same game folder as the "
                           "upscaler DLL.".format(Path(loader).name))
                return
            if loader:
                self.alert("The loader does not fit",
                           "{}: version {}. A FidelityFX loader 2.x is needed, from the same game as the "
                           "upscaler DLL.".format(Path(loader).name,
                                                  details.get("loader_version", "?")))
                return
            # A DLL without the FidelityFX API exports (AMD's own export it: no loader needed), and no
            # loader next to it or one folder up: ask for it.
            self.toasts.add_toast(Adw.Toast(title=("No loader next to the DLL: choose "
                                                   "amd_fidelityfx_loader_dx12.dll from the game's folder"),
                timeout=8))
            self.choose_dll("FidelityFX loader (amd_fidelityfx_loader_dx12.dll or amd_fidelityfx_dx12.dll)",
                            lambda path: self.on_fsr411_dll(upscaler, path))
            return
        self.start_fsr411_build(upscaler, details.get("loader"))

    def start_fsr411_build(self, upscaler, loader):
        command, env = fsr411_build_command(upscaler, loader)
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
        launcher.set_environ([f"{k}={v}" for k, v in env.items()])
        launcher.set_cwd(str(PORT_DIR))
        try:
            # setsid: Proton and its helpers form one process group, cancelled together.
            self.fsr411_build = launcher.spawnv(["setsid", *command])
        except GLib.Error as error:
            self.toasts.add_toast(Adw.Toast(title="Could not start: {}".format(error.message)))
            return
        self.append_log("\n— building FSR 4.1.1 from {} —\n".format(upscaler))
        stream = Gio.DataInputStream.new(self.fsr411_build.get_stdout_pipe())
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self.on_fsr411_line)
        self.fsr411_build.wait_async(None, self.on_fsr411_built)
        self.update_fsr411_row("Preparing…")
        self.update_launch_button()

    def on_fsr411_line(self, stream, result):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            return
        if line is None:
            return
        self.append_log(line + "\n")
        if self.fsr411_build:
            step = re.match(r"\[\s*(\d+)/(\d+)\]", line)
            if step:
                self.update_fsr411_row("Recording the DLL's passes under Proton: {} of {}".format(*step.groups()))
            elif line.startswith("Translating"):
                self.update_fsr411_row("Translating the passes to SPIR-V…")
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self.on_fsr411_line)

    def stop_fsr411_build(self):
        pid = int(self.fsr411_build.get_identifier())
        self.fsr411_cancelled = True
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            self.fsr411_build.force_exit()

    def on_fsr411_built(self, process, result):
        try:
            process.wait_finish(result)
        except GLib.Error:
            pass
        status = process.get_exit_status() if process.get_if_exited() else -1
        cancelled = getattr(self, "fsr411_cancelled", False)
        self.fsr411_cancelled = False
        self.fsr411_build = None
        self.update_fsr411_row()
        self.update_launch_button()
        self.append_log("— FSR 4.1.1 build finished (code {}) —\n".format(status))
        if status == 0:
            for index, (_label, value) in enumerate(UPSCALERS):
                if value == "fsr411":
                    self.upscaler_row.set_selected(index)
            self.update_upscaler_status()
            self.store()
            self.toasts.add_toast(Adw.Toast(title="FSR 4.1.1 built and selected"))
        elif cancelled:
            self.toasts.add_toast(Adw.Toast(title="FSR 4.1.1 build cancelled"))
        else:
            message = FSR411_BUILD_ERRORS.get(status, "The build failed (code {}): details in the log")
            self.alert("FSR 4.1.1 was not built", message.format(status))


class LauncherApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.bbport.Launcher",
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        window = self.get_active_window() or LauncherWindow(self)
        window.present()


def play():
    """--play: the game with the saved settings, no window (Steam Deck game mode)."""
    settings = load_settings()
    if not (Path(settings["game_dir"]).expanduser() / "eboot.bin").is_file():
        print("bbport: choose the game folder in the launcher first", file=sys.stderr)
        return 1
    os.chdir(PORT_DIR)
    os.execvpe("bash", ["bash", str(PORT_DIR / "run.sh")], game_environment(settings))


def build_fsr411(arguments):
    """--build-fsr411 <upscaler DLL> [loader DLL]: the launcher's FSR 4.1.1 build, without a window."""
    if not 1 <= len(arguments) <= 2:
        print("usage: --build-fsr411 <amd_fidelityfx_upscaler_dx12.dll> [loader DLL]", file=sys.stderr)
        return 1
    command, env = fsr411_build_command(*arguments)
    return subprocess.call(command, env=env, cwd=PORT_DIR)


if __name__ == "__main__":
    if "--play" in sys.argv[1:]:
        sys.exit(play())
    if "--build-fsr411" in sys.argv[1:]:
        sys.exit(build_fsr411(sys.argv[sys.argv.index("--build-fsr411") + 1:]))
    sys.exit(LauncherApp().run(sys.argv))
