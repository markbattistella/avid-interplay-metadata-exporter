#!/usr/bin/env python3
"""
Cross-platform build script for MediaCentral Explorer.
Run from inside the project venv after installing requirements + pyinstaller.

Icons are auto-generated from assets/icon.png if the target file is missing:
  - assets/icon.icns  (macOS — uses built-in sips + iconutil)
  - assets/icon.ico   (Windows / any — uses Pillow, auto-installed if absent)
"""

import subprocess
import sys
import shutil
import tempfile
import platform
from datetime import datetime
from pathlib import Path

HERE   = Path(__file__).parent
ASSETS = HERE / "assets"
BUILD  = HERE / "build"   # Windows version info written here

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
    """Convert a PNG to a multi-resolution .ico using Pillow."""
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
    """Convert a PNG to .icns using macOS built-in sips + iconutil."""
    if not IS_MAC:
        print("  .icns generation requires macOS — skipping")
        return
    tmp      = Path(tempfile.mkdtemp())
    iconset  = tmp / "icon.iconset"
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
    """Generate target icon from icon.png if the target is missing."""
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
# Windows version info file
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
# Assemble PyInstaller command
# ---------------------------------------------------------------------------

args = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "MCExplorer",
    "--collect-all", "customtkinter",
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
# Stamp version into _version.py so the app can read it at runtime
# ---------------------------------------------------------------------------

version_stamp = HERE / "_version.py"
version_stamp.write_text(f'__version__ = "{VERSION}"\n', encoding="utf-8")
print(f"\n  Stamped : _version.py ({VERSION})")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

print("\nRunning PyInstaller…\n")
result = subprocess.run(args, cwd=HERE)
sys.exit(result.returncode)
