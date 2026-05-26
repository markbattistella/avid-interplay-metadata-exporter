# MediaCentral Explorer

A cross-platform desktop app (and CLI tool) for browsing an Avid MediaCentral workgroup, loading project contents, and exporting formatted asset metadata — ready to paste into an email or save as a text file.

---

## Features

- Connect to any Avid MediaCentral Web Services endpoint
- Browse and filter projects at a given path
- Load a project and see all bins, sequences, and master clips with metadata
- Asset type labels: `MC` (master clip), `SEQ` (sequence), `SUB` (sub-clip), etc.
- Configurable output fields (duration, status, created/modified dates, and more)
- Copy to clipboard, save as `.txt`, or open directly in your email client
- Credentials saved to Windows Credential Manager / macOS Keychain
- Connection settings persisted across sessions

---

## Requirements

### macOS

1. Install Python 3.13 — [python.org](https://www.python.org/downloads/) or `brew install python@3.13`
2. Install dependencies:

   ```bash
   python3.13 -m pip install -r app/requirements.txt
   ```

### Windows

1. Install Python 3.13 from [python.org](https://www.python.org/downloads/)
   - On the installer's first screen, check **"Add python.exe to PATH"** before clicking Install
2. Open **Command Prompt** or **PowerShell** and install dependencies:

   ```bat
   pip install -r app\requirements.txt
   ```

3. Verify Python is available:

   ```bat
   python --version
   ```

   If `python` is not recognised, restart your terminal after installing. If it still fails, use the full path: `C:\Users\<you>\AppData\Local\Programs\Python\Python313\python.exe`

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

```text
Listing: interplay://AvidWorkgroup/Projects/2026
  2026001 ALPHA
  2026002 BRAVO
  2026003 CHARLIE

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

```text
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
| --- | --- | --- |
| `--server` | Yes | MediaCentral server address (IP or hostname) |
| `--user` | Yes | Username |
| `--password` | Yes | Password |
| `--path` | Yes | Interplay URI to search, e.g. `interplay://WorkgroupName/Projects/2026` |
| `--project` | No | Project name to load (substring match). Omit to list only. |
| `--fields` | No | Override active output fields as quoted `Group.Name` pairs, e.g. `"System.Duration" "System.Media Status"` |

Server addresses are normalised before connecting:

- `192.168.0.1` → `http://192.168.0.1:80`
- `https://192.168.0.1` → `https://192.168.0.1:443`
- `192.168.0.1:12345` → `http://192.168.0.1:12345`
- `https://192.168.0.1:12345` → `https://192.168.0.1:12345`

---

## Building a standalone executable

Binaries are built automatically via GitHub Actions on every release.

### Build on macOS

```bash
sh app/build_mac.sh
```

Outputs:

- `app/dist/MCExplorer.app` — the app bundle
- `app/dist/MCExplorer.dmg` — distribute this

Requires Python 3.13 and the dependencies in `app/requirements.txt`.

### Build on Windows

Requires [Inno Setup](https://jrsoftware.org/isinfo.php) (or `choco install innosetup`).

```bat
app\build_windows.bat
```

Outputs:

- `app\dist\MCExplorer\` — the app folder
- `app\dist\MCExplorer-Setup.exe` — distribute this; installs to `Program Files`, creates Start Menu entry

---

## Output fields

The default output includes duration, media status, and created/modified dates. Additional fields are available through the CLI `--fields` option or saved defaults in the app configuration.

Available field groups:

| Group | Fields |
| --- | --- |
| Core | Duration, Media Status |
| Dates | Created By, Creation Date, Modified By, Modified Date |
| Timecode | Start Timecode, End Timecode |
| Technical | Tracks, Format, Tape / Reel, Original Project |
| Production | Comments, Scene, Take, Camera, Camera Roll, Shoot Date |
