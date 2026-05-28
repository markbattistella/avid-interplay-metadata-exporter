#!/usr/bin/env python3
# Avid MediaCentral Metadata Exporter — build script
# Copyright (C) 2026  Mark Battistella
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
Cross-platform build script for MediaCentral Explorer.

macOS  : dist/MCExplorer.app  →  dist/MCExplorer.dmg
Windows: dist/MCExplorer/     →  dist/MCExplorer-Setup.exe
"""

import os
import subprocess
import sys
import shutil
import tempfile
import plistlib
import platform
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows (default console codepage is cp1252)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE   = Path(__file__).parent
ASSETS = HERE / "assets"
BUILD  = HERE / "build"

def _parse_version(v: str):
    v = v.lstrip("v").strip()
    parts = v.split(".")
    if len(parts) in (3, 4) and all(p.isdigit() for p in parts):
        build = int(parts[3]) if len(parts) == 4 else 0
        return v, int(parts[0]), int(parts[1]), int(parts[2]), build
    return None, None, None, None, None

_env_tag = os.environ.get("RELEASE_VERSION", "")
_tag_ver, _tag_y, _tag_m, _tag_d, _tag_build = _parse_version(_env_tag)

if _tag_ver:
    VERSION   = _tag_ver
    YEAR      = _tag_y
    VER_TUPLE = (_tag_y, _tag_m, _tag_d, _tag_build)
else:
    VERSION   = datetime.now().strftime("%Y.%m.%d")
    YEAR      = datetime.now().year
    VER_TUPLE = (datetime.now().year, datetime.now().month, datetime.now().day, 0)

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

print("=" * 60)
print(" MediaCentral Explorer — Build")
print("=" * 60)
print(f" Platform  : {platform.system()}")
print(f" Version   : {VERSION}")
print(f" Copyright : © 2010-{YEAR} Mark Battistella")
print("=" * 60)

# ---------------------------------------------------------------------------
# Icon generation
# ---------------------------------------------------------------------------

def _ensure_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("  Installing Pillow for icon generation…")
        subprocess.run([sys.executable, "-m", "pip", "install", "pillow"],
                       check=True, capture_output=True)

def make_ico(src: Path, out: Path):
    _ensure_pillow()
    from PIL import Image
    img   = Image.open(src).convert("RGBA")
    sizes = [16, 32, 48, 64, 128, 256]
    icons = [img.resize((s, s), Image.LANCZOS) for s in sizes]
    icons[0].save(out, format="ICO",
                  sizes=[(s, s) for s in sizes],
                  append_images=icons[1:])
    print(f"  Created : {out.name}")

def make_icns(src: Path, out: Path):
    if not IS_MAC:
        print("  .icns generation requires macOS — skipping")
        return
    tmp     = Path(tempfile.mkdtemp())
    iconset = tmp / "icon.iconset"
    iconset.mkdir()
    sizes = [
        (16,   "icon_16x16.png"),
        (32,   "icon_16x16@2x.png"),
        (32,   "icon_32x32.png"),
        (64,   "icon_32x32@2x.png"),
        (128,  "icon_128x128.png"),
        (256,  "icon_128x128@2x.png"),
        (256,  "icon_256x256.png"),
        (512,  "icon_256x256@2x.png"),
        (512,  "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, name in sizes:
        subprocess.run(
            ["sips", "-z", str(size), str(size), str(src),
             "--out", str(iconset / name)],
            check=True, capture_output=True)
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
        check=True)
    shutil.rmtree(tmp)
    print(f"  Created : {out.name}")

def _auto_icon(target: Path):
    if target.exists():
        print(f"  Icon    : {target.name} (existing)")
        return
    png = ASSETS / "icon.png"
    if not png.exists():
        print(f"  Icon    : not found ({target.name} and icon.png both missing)")
        return
    print(f"  Generating {target.name} from icon.png…")
    if target.suffix == ".icns":
        make_icns(png, target)
    elif target.suffix == ".ico":
        make_ico(png, target)

# ---------------------------------------------------------------------------
# Windows version info file (for PyInstaller)
# ---------------------------------------------------------------------------

def _make_win_version(out: Path):
    major, minor, patch, build = VER_TUPLE
    text = (
        "# UTF-8\n"
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers=({major}, {minor}, {patch}, {build}),\n"
        f"    prodvers=({major}, {minor}, {patch}, {build}),\n"
        "    mask=0x3f, flags=0x0, OS=0x40004,\n"
        "    fileType=0x1, subtype=0x0, date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([StringTable(u'040904B0', [\n"
        "      StringStruct(u'CompanyName',      u'Mark Battistella'),\n"
        "      StringStruct(u'FileDescription',  u'Avid MediaCentral Explorer'),\n"
        f"      StringStruct(u'FileVersion',      u'{VERSION}'),\n"
        "      StringStruct(u'InternalName',     u'MCExplorer'),\n"
        f"      StringStruct(u'LegalCopyright',   u'\\xa9 2010-{YEAR} Mark Battistella. markbattistella.com'),\n"
        "      StringStruct(u'OriginalFilename', u'MCExplorer.exe'),\n"
        "      StringStruct(u'ProductName',      u'MediaCentral Explorer'),\n"
        f"      StringStruct(u'ProductVersion',   u'{VERSION}'),\n"
        "    ])]),\n"
        "    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"  Generated: {out.name}")

# ---------------------------------------------------------------------------
# macOS: patch Info.plist inside .app after PyInstaller runs
# ---------------------------------------------------------------------------

def _patch_info_plist(app_path: Path):
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        print(f"  Warning : Info.plist not found at {plist_path}")
        return
    with open(plist_path, "rb") as f:
        data = plistlib.load(f)
    data.update({
        "CFBundleName":               "MediaCentral Explorer",
        "CFBundleDisplayName":        "MediaCentral Explorer",
        "CFBundleVersion":            VERSION,
        "CFBundleShortVersionString": VERSION,
        "NSHumanReadableCopyright":   f"Copyright © 2010-{YEAR} Mark Battistella. markbattistella.com",
        "NSHighResolutionCapable":    True,
        "LSMinimumSystemVersion":     "11.0",
    })
    with open(plist_path, "wb") as f:
        plistlib.dump(data, f)
    print(f"  Patched : Info.plist ({VERSION})")

# ---------------------------------------------------------------------------
# macOS: create DMG
# ---------------------------------------------------------------------------

def _make_dmg(app_path: Path, out: Path):
    tmp = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(str(app_path), str(tmp / app_path.name))
        subprocess.run([
            "hdiutil", "create",
            "-volname", "MediaCentral Explorer",
            "-srcfolder", str(tmp),
            "-ov", "-format", "UDZO",
            str(out),
        ], check=True, capture_output=True)
        print(f"  Created : {out.name}")
    finally:
        shutil.rmtree(tmp)

# ---------------------------------------------------------------------------
# Windows: generate Inno Setup script and run ISCC
# ---------------------------------------------------------------------------

def _make_inno_script(out: Path) -> Path:
    major, minor, patch, _ = VER_TUPLE
    dist_src  = str(HERE / "dist" / "MCExplorer") + ("\\*" if IS_WIN else "/*")
    dist_out  = str(HERE / "dist")
    icon_path = str(ASSETS / "icon.ico")
    has_icon  = (ASSETS / "icon.ico").exists()

    icon_line = f'SetupIconFile={icon_path}\n' if has_icon else ""

    script = (
        "[Setup]\n"
        "AppName=MediaCentral Explorer\n"
        f"AppVersion={VERSION}\n"
        "AppPublisher=Mark Battistella\n"
        "AppPublisherURL=https://markbattistella.com\n"
        "AppSupportURL=https://markbattistella.com\n"
        f"AppCopyright=Copyright (C) 2010-{YEAR} Mark Battistella\n"
        "DefaultDirName={autopf}\\MCExplorer\n"
        "DefaultGroupName=MediaCentral Explorer\n"
        f"OutputDir={dist_out}\n"
        "OutputBaseFilename=MCExplorer-Setup\n"
        f"{icon_line}"
        "Compression=lzma\n"
        "SolidCompression=yes\n"
        "WizardStyle=modern\n"
        "PrivilegesRequired=admin\n"
        f"VersionInfoVersion={major}.{minor}.{patch}.0\n"
        "VersionInfoCompany=Mark Battistella\n"
        "VersionInfoDescription=MediaCentral Explorer Installer\n"
        f"VersionInfoCopyright=Copyright (C) 2010-{YEAR} Mark Battistella\n"
        "\n"
        "[Languages]\n"
        'Name: "english"; MessagesFile: "compiler:Default.isl"\n'
        "\n"
        "[Tasks]\n"
        'Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; '
        'GroupDescription: "{cm:AdditionalIcons}"\n'
        "\n"
        "[Files]\n"
        f'Source: "{dist_src}"; DestDir: "{{app}}"; '
        "Flags: ignoreversion recursesubdirs createallsubdirs\n"
        "\n"
        "[Icons]\n"
        'Name: "{group}\\MediaCentral Explorer"; Filename: "{app}\\MCExplorer.exe"\n'
        'Name: "{group}\\{cm:UninstallProgram,MediaCentral Explorer}"; Filename: "{uninstallexe}"\n'
        'Name: "{commondesktop}\\MediaCentral Explorer"; Filename: "{app}\\MCExplorer.exe"; '
        'Tasks: desktopicon\n'
        "\n"
        "[Run]\n"
        'Filename: "{app}\\MCExplorer.exe"; '
        'Description: "{cm:LaunchProgram,MediaCentral Explorer}"; '
        "Flags: nowait postinstall skipifsilent\n"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(script, encoding="utf-8")
    print(f"  Generated: {out.name}")
    return out

def _run_inno(iss_path: Path):
    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if not iscc:
        for candidate in [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ]:
            if Path(candidate).exists():
                iscc = candidate
                break
    if not iscc:
        print("  Inno Setup not found — skipping installer.")
        print("  Install it: choco install innosetup  or  https://jrsoftware.org/isinfo.php")
        return
    print("  Running ISCC…")
    subprocess.run([iscc, str(iss_path)], check=True, cwd=HERE)
    print("  Installer: dist/MCExplorer-Setup.exe")

# ---------------------------------------------------------------------------
# Stamp version
# ---------------------------------------------------------------------------

(HERE / "_version.py").write_text(f'__version__ = "{VERSION}"\n', encoding="utf-8")
print(f"\n  Stamped : _version.py ({VERSION})")

# ---------------------------------------------------------------------------
# Assemble PyInstaller args
# ---------------------------------------------------------------------------

UI_DIR = HERE / "ui"

_sep = ";" if IS_WIN else ":"

args = [
    sys.executable, "-m", "PyInstaller",
    "--onedir",
    "--windowed",
    "--name", "MCExplorer",
    "--collect-all", "webview",
    "--add-data", f"{UI_DIR}{_sep}ui",
    "--noconfirm",
]

if IS_WIN:
    args += [
        "--hidden-import", "keyring.backends.Windows",
        "--hidden-import", "keyring.backends.fail",
    ]
    ver_file = BUILD / "win_version_info.txt"
    _make_win_version(ver_file)
    args += ["--version-file", str(ver_file)]
    icon = ASSETS / "icon.ico"

elif IS_MAC:
    args += ["--osx-bundle-identifier", "com.markbattistella.mcexplorer"]
    icon = ASSETS / "icon.icns"

else:
    icon = ASSETS / "icon.png"

print()
_auto_icon(icon)
if icon.exists():
    args += ["--icon", str(icon)]

args.append(str(HERE / "interplay_explorer.py"))

# ---------------------------------------------------------------------------
# Run PyInstaller
# ---------------------------------------------------------------------------

print("\nRunning PyInstaller…\n")
result = subprocess.run(args, cwd=HERE)
if result.returncode != 0:
    sys.exit(result.returncode)

# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

print()
if IS_MAC:
    app_path = HERE / "dist" / "MCExplorer.app"
    if app_path.exists():
        _patch_info_plist(app_path)
        _make_dmg(app_path, HERE / "dist" / "MCExplorer.dmg")
        print("\nDone.")
        print(f"  App : dist/MCExplorer.app")
        print(f"  DMG : dist/MCExplorer.dmg  ← distribute this")
    else:
        print(f"Warning: {app_path} not found.")
        sys.exit(1)

elif IS_WIN:
    dist_dir = HERE / "dist" / "MCExplorer"
    if dist_dir.exists():
        iss = _make_inno_script(BUILD / "installer.iss")
        _run_inno(iss)
        print("\nDone.")
        print(f"  Folder   : dist/MCExplorer/")
        print(f"  Installer: dist/MCExplorer-Setup.exe  ← distribute this")
    else:
        print(f"Warning: {dist_dir} not found.")
        sys.exit(1)
