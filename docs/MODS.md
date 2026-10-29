# File-based mods

The launcher now has a **Mods** group: folder selection, a master toggle,
per-mod enabling, and load-order arrows. Changes take effect on the
next launch. The lower enabled mod has higher priority; when files
overlap, the log shows which mod replaced the previous one.

By default `bbport/mods/` is used, and in the AppImage —
`~/.local/share/bbport/mods/`. Unpack a downloaded mod like this:

```text
mods/
  Mod name/
    dvdroot_ps4/
      chr/...
      param/...
      menu/...
```

Also accepted:

- `Mod name/app0/dvdroot_ps4/...` and `Mod name/CUSA03173/dvdroot_ps4/...`;
- an extra wrapper folder, as after unpacking an archive into a folder with its name:
  `Mod name/Mod name v1.2/dvdroot_ps4/...` (readme/pictures may sit alongside);
- a mod without `dvdroot_ps4` where the game folders lie directly: `Mod name/chr/...`,
  `Mod name/parts/...` (`chr`, `parts`, `map`, `menu`, `msg`, `param`, `sfx`,
  `sound`, `font` and other `dvdroot_ps4` folders).

File name case in a mod does not matter: `DVDROOT_PS4/Chr/C0000.chrbnd.dcx` from a mod built
on Windows replaces the game's `dvdroot_ps4/chr/c0000.chrbnd.dcx`. Previously such a file
was added next to it under its own name, and the game did not see it. The launch log shows how many
game files the mod replaced and how many it added: `Mods: 12 game files replaced, 0 added`.
If a mod should replace files but logs `0 game files replaced`, check the paths inside the mod.
ZIP/7z archives must be unpacked first. Ready-made `dvdroot_ps4`
file replacements are supported: textures, models, parameters, interface, sound, and fonts.
The manager does not merge the contents of two identical `.dcx`/`.bnd` files: the last
replacement wins in full.

For an already prepared shadPS4 folder, the sibling directory
`CUSA03173-mods/dvdroot_ps4/...` next to `CUSA03173/` works. It is connected automatically
before the mods from the list. The master toggle disables it too. You can also select
a folder directly containing `dvdroot_ps4` as the mods folder; such a folder
is connected as a whole, without a list of individual mods.
The `-mods` convention was verified against the
[shadPS4 sources](https://github.com/shadps4-emu/shadPS4/blob/main/src/core/file_sys/fs.cpp).

The original game files are not overwritten. For the duration of a launch, a separate
merged tree of links is created in the data directory `out/mod-game-*`; reads, stat, and
directory listings see the selected replacements and the rest of the original files.
The game `/app0` and `/hostapp` are read-only. Saves stay
in their usual folder and remain writable. On normal exit or when stopped by the
launcher, the temporary tree is deleted. After SIGKILL/a power failure it
may remain; such directories are not used on the next launch.

Mods that replace `eboot.bin`, `sce_module`, or `sce_sys`, DLL injectors, and script
plugins are not supported by this loader. Executable code patches remain
in the existing `patches/` / `BB_PATCHES` system. Symbolic links inside a mod
are not accepted. Compatibility of a specific mod with CUSA03173 1.09 is determined
by its author.

To launch from a terminal:

```sh
BB_GAME_DIR=/path/to/CUSA03173 BB_MODS_DIR=/path/to/mods bash run.sh
BB_GAME_DIR=/path/to/CUSA03173 BB_MODS_ENABLED=0 bash run.sh
```

Order and disables are saved in the data directory in `mods.json`:

```json
{"order": ["First", "Second"], "disabled": ["First"]}
```

New folders are enabled automatically and appended at the end in alphabetical order.
`BB_MODS_CONFIG` changes the profile path. `BB_MOD_TRACE=1` with `BB_MODS_DIR` prints
the first reads of the actually connected files for diagnostics.

# Texture packs

Packs with enlarged map textures do not fit in the game's graphics heaps, which are sized for
the PS4 (2287 and 886 MiB). When a heap is full, the game's GPU memory allocations fail:
textures flicker, then the game crashes (code 139 in Iosefka's Clinic, behind which the
Forbidden Woods is streamed in, #240). Launching detects such a pack by itself, both one
connected from the mods folder and one already written into the game folder: a map texture
larger than 4096 pixels on a side (retail 1.09 has none). Then the `Increased Graphics Heap Sizes`
patch is applied (heaps of 3952 and 2560 MiB, as with the patches for resolutions above 1080p)
and 9152 MiB of direct memory, roughly 3.3 GB more RAM. In the log:
`Graphics heaps: larger (a texture pack: dvdroot_ps4/map/m24/m24_0000.tpfbhd has 8192-pixel textures, ...)`.

The first check reads about 8600 entries of the map texture archives (a fraction of a second on
an SSD); the answer is kept in `out/texture-pack.json` until the texture files change.
`BB_LARGE_HEAPS=1` always enables the large heaps (for a pack the check does not recognise: for
example, one that enlarged textures to no more than 4096), `BB_LARGE_HEAPS=0` disables them.

# Third-party patches (shadPS4 XML)

The `patches/` folder in the data directory (in the AppImage — `~/.local/share/bbport/patches/`; in the launcher,
the **Third-party patches** group, where another folder can also be selected). Patch XML files in
shadPS4/GoldHEN format are accepted: `Metadata` for `AppVer="01.09"` and `eboot.bin` is taken; files with
other games' `TitleID` are skipped. Default enabling comes from the file's `isEnabled`; the launcher
choice is saved in `patches.json` in the data directory:

```json
{"enabled": ["file.xml/Patch name"], "disabled": ["file.xml/Other patch"]}
```

The `bytes`, `bytes16/32/64`, `float32/64`, `utf8`, `utf16` strings are supported.
A patch with `mask` strings (pattern search) or with an address outside eboot is skipped entirely,
with a message in the log. Third-party patches are applied after the built-in ones
(`patches/Bloodborne.xml`): on overlap, the third-party one wins. From a terminal:
`BB_PATCHES_DIR=/path BB_PATCHES_CONFIG=/path/patches.json bash run.sh`.

Patches that replace pointers in tables (like `60 FPS++` and `90 FPS++`) are relocated by the
loader to the real image address. Previously such patches stopped the launch with the
error `patch overlaps a relocation`.

# TAA sharpness

The `sharpen` and `sharpness` settings now work for TAA as well, in the launcher and
the in-game menu. Range — **0…1**; at 0 or with the toggle off there is no additional
pass. RCAS is applied to the finished scene before the HUD. TAA history stores the
color before sharpening so that it is not amplified during repeated accumulation.
Flat areas keep their original color, including HDR; no additional buffer is needed.
