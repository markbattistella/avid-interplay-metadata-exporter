# Icons

Place your icon files here before building:

| File | Used by |
|---|---|
| `icon.icns` | macOS build |
| `icon.ico` | Windows build |

If either file is missing the build still completes — just without a custom icon.

---

## Converting a PNG to .icns (macOS)

You need a square PNG, ideally 1024×1024.

```bash
# 1. Create an iconset folder
mkdir icon.iconset

# 2. Generate all required sizes
sips -z 16   16   source.png --out icon.iconset/icon_16x16.png
sips -z 32   32   source.png --out icon.iconset/icon_16x16@2x.png
sips -z 32   32   source.png --out icon.iconset/icon_32x32.png
sips -z 64   64   source.png --out icon.iconset/icon_32x32@2x.png
sips -z 128  128  source.png --out icon.iconset/icon_128x128.png
sips -z 256  256  source.png --out icon.iconset/icon_128x128@2x.png
sips -z 256  256  source.png --out icon.iconset/icon_256x256.png
sips -z 512  512  source.png --out icon.iconset/icon_256x256@2x.png
sips -z 512  512  source.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 source.png --out icon.iconset/icon_512x512@2x.png

# 3. Convert to .icns
iconutil -c icns icon.iconset -o icon.icns

# 4. Clean up
rm -rf icon.iconset
```

---

## Converting a PNG to .ico (Windows / cross-platform)

**On macOS using ImageMagick** (`brew install imagemagick`):

```bash
magick source.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
```

**On Windows using ImageMagick:**

```bat
magick source.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
```

**Online:** [icoconvert.com](https://icoconvert.com) or [convertico.com](https://convertico.com) — upload your PNG, download the `.ico`.
