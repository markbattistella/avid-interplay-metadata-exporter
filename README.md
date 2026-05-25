# Interplay Project Explorer

A cross-platform desktop app (and CLI tool) for browsing an Avid Interplay workgroup, loading project contents, and exporting formatted asset metadata — ready to paste into an email or save as a text file.

---

## Features

- Connect to any Avid Interplay Web Services endpoint
- Browse and filter projects at a given Interplay path
- Load a project and see all bins, sequences, and masterclips with metadata
- Asset type labels: `MC` (masterclip), `SEQ` (sequence), `SUB` (subclip), etc.
- Configurable output fields (duration, status, created/modified dates, and more)
- Copy to clipboard, save as `.txt`, or open directly in your email client
- Credentials saved to Windows Credential Manager / macOS Keychain
- Connection settings persisted across sessions

---

## Requirements

- Python 3.13
- On macOS: `brew install python-tk@3.13`
- Dependencies: `pip install requests keyring`

---

## Running without building

### GUI

```bash
python3.13 app/interplay_explorer.py
```

Opens the full desktop app. No build step required.

### CLI

Pass `--server` and the app runs headless — useful for testing connectivity or scripting.

**List all projects at a path:**

```bash
python3.13 app/interplay_explorer.py \
  --server 192.168.1.10 \
  --user jsmith \
  --password secret \
  --path "interplay://AvidWorkgroup/Projects/2026"
```

Output:

```
Listing: interplay://AvidWorkgroup/Projects/2026
  2026001 ALPHA
    interplay://AvidWorkgroup/Projects/2026/2026001 ALPHA
  2026002 BRAVO
    interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO
  2026003 CHARLIE
    interplay://AvidWorkgroup/Projects/2026/2026003 CHARLIE

3 project(s) found.
```

**Load a specific project (substring match):**

```bash
python3.13 app/interplay_explorer.py \
  --server 192.168.1.10 \
  --user jsmith \
  --password secret \
  --path "interplay://AvidWorkgroup/Projects/2026" \
  --project "BRAVO"
```

Output:

```
PROJECT: 2026002 BRAVO
Date:    25 May 2026  04:13 PM
────────────────────────────────────────────────────────────────────────

RAW AUDIO RECORDINGS 22-01-2026
────────────────────────────────
  MC   Interview A                00:07:39:18   Online
    Created: jsmith 22/01/2026   |   Modified: jsmith 25/05/2026
  MC   Interview B                00:03:12:04   Online
    Created: jsmith 22/01/2026   |   Modified: jsmith 25/05/2026

SEQUENCES 22-01-2026
────────────────────
  SEQ  Assembly Edit              00:12:45:00   Online
    Created: jsmith 22/01/2026   |   Modified: jeditor 24/05/2026
```

**Windows (cmd or PowerShell):**

```bat
python app\interplay_explorer.py ^
  --server 192.168.1.10 ^
  --user jsmith ^
  --password secret ^
  --path "interplay://AvidWorkgroup/Projects/2026" ^
  --project "BRAVO"
```

---

## CLI reference

| Flag | Required | Description |
|---|---|---|
| `--server` | Yes | Interplay server address (IP or hostname) |
| `--user` | Yes | Interplay username |
| `--password` | Yes | Interplay password |
| `--path` | Yes | Interplay URI to search, e.g. `interplay://WorkgroupName/Projects/2026` |
| `--project` | No | Project name to load (substring match). Omit to list only. |

---

## Building a standalone executable

Binaries are built automatically via GitHub Actions on every release.

### macOS

```bash
sh app/build_mac.sh
# Output: app/dist/InterplayExplorer
```

Requires `brew install python-tk@3.13`.

### Windows

```bat
app\build_windows.bat
```

Output: `app\dist\InterplayExplorer.exe`

> **Note:** Windows may show a SmartScreen prompt on first run. Right-click → Properties → Unblock, or run `Unblock-File -Path InterplayExplorer.exe` in PowerShell.

---

## Output fields

The default output includes duration, media status, and created/modified dates. Additional fields can be toggled in the GUI via **Fields…**, or saved as new defaults.

Available field groups:

| Group | Fields |
|---|---|
| Core | Duration, Media Status |
| Dates | Created By, Creation Date, Modified By, Modified Date |
| Timecode | Start Timecode, End Timecode |
| Technical | Tracks, Format, Resolution, Tape / Reel, Original Project |
| Production | Comments, Scene, Take, Camera, Camera Roll, Shoot Date |
