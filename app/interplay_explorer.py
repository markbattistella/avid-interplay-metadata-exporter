#!/usr/bin/env python3
"""Avid MediaCentral Metadata Exporter"""

import webview
import requests
import xml.etree.ElementTree as ET
import html as html_lib
import json
import re
import sys
import os
import subprocess
import tempfile
import webbrowser
import urllib.parse
import atexit
import hashlib
from pathlib import Path
from datetime import datetime

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

try:
    from _version import __version__
except ImportError:
    __version__ = "dev"

# ---------------------------------------------------------------------------
# Field definitions
# (group, attr_name, display_label, default_on, category)
# category="" means always fetched / not shown as a user toggle
# ---------------------------------------------------------------------------

FIELD_DEFS = [
    # Always fetched, not shown in dialog
    ("Asset",  "Name",          "Name",             True,  ""),
    ("User",   "Display Name",  "Clip Name",        True,  ""),
    ("Asset",  "Type",          "Node Type",        True,  ""),
    ("System", "Type",          "Node Type (sys)",  True,  ""),
    # Core — shown on the main clip line
    ("System", "Duration",      "Duration",         True,  "Core"),
    ("System", "Media Status",  "Media Status",     True,  "Core"),
    # Dates — shown as an indented sub-line
    ("System", "Created By",       "Created By",       True,  "Dates"),
    ("System", "Creation Date",    "Creation Date",    True,  "Dates"),
    ("System", "Modified By",      "Modified By",      True,  "Dates"),
    ("System", "Modified Date",    "Modified Date",    True,  "Dates"),
    # Timecode — shown as extras
    ("System", "Start",            "Start Timecode",   False, "Timecode"),
    ("System", "End",              "End Timecode",     False, "Timecode"),
    # Technical — shown as extras
    ("System", "Tracks",           "Tracks",           False, "Technical"),
    ("System", "Format",           "Format",           False, "Technical"),
    ("System", "Tape",             "Tape / Reel",      False, "Technical"),
    ("System", "Original Project", "Original Project", False, "Technical"),
    # Production — shown as extras
    ("User",   "Comments",         "Comments",         False, "Production"),
    ("User",   "Scene",            "Scene",            False, "Production"),
    ("User",   "Take",             "Take",             False, "Production"),
    ("User",   "Camera",           "Camera",           False, "Production"),
    ("User",   "Camroll",          "Camera Roll",      False, "Production"),
    ("System", "Shoot Date",       "Shoot Date",       False, "Production"),
    # Markers — requires a separate GetUMIDLocators call per clip
    ("Markers", "Locators",        "Markers",          False, "Markers"),
]

_ALWAYS_ON = frozenset(
    (g, n) for g, n, _, _, cat in FIELD_DEFS if cat == "")

DEFAULT_FIELDS = frozenset(
    (g, n) for g, n, _, default, cat in FIELD_DEFS if default and cat != "")

RETURN_ATTRS = [(g, n) for g, n, _, _, cat in FIELD_DEFS if cat != "Markers"]

_MAIN_LINE = {("System", "Duration"), ("System", "Media Status")}
_DATE_LINE = {("System", "Created By"), ("System", "Creation Date"),
              ("System", "Modified By"), ("System", "Modified Date")}
_EXTRAS    = {(g, n) for g, n, _, _, cat in FIELD_DEFS
              if cat not in ("", "Core", "Dates")}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOAP_NS    = "http://schemas.xmlsoap.org/soap/envelope/"
TYPES_NS   = "http://avid.com/interplay/ws/assets/types"
APP_NAME   = "MCExplorer"
LINE_WIDTH = 72

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

GITHUB_OWNER = "markbattistella"
GITHUB_REPO  = "avid-interplay-metadata-exporter"
DEFAULT_PROJECT_LOAD_DEPTH = 4
MAILTO_MAX_URL_LENGTH = 8000

_HERE   = Path(__file__).parent
_ASSETS = _HERE / "assets"

_TYPE_LABEL = {
    "masterclip": "MC ",
    "sequence":   "SEQ",
    "subclip":    "SUB",
    "effect":     "FX ",
    "group":      "GRP",
    "folder":     "DIR",
    "bin":        "BIN",
}

def _ui_dir() -> Path:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "ui")

        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / "ui",
            exe_dir / "_internal" / "ui",
            exe_dir.parent / "Resources" / "ui",
        ])
    else:
        candidates.append(_HERE / "ui")

    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate

    checked = "\n".join(str(p) for p in candidates)
    raise RuntimeError("Could not find UI assets. Checked:\n" + checked)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / "Library" / "Application Support"
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"

def load_config() -> dict:
    p = _config_path()
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}

def save_config(cfg: dict):
    try:
        _config_path().write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def save_password(username: str, password: str):
    if HAS_KEYRING and username and password:
        try:
            keyring.set_password(APP_NAME, username, password)
        except Exception:
            pass

def load_password(username: str) -> str:
    if HAS_KEYRING and username:
        try:
            return keyring.get_password(APP_NAME, username) or ""
        except Exception:
            pass
    return ""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def natural_key(s: str) -> list:
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", s or "")]

def fmt_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        try:
            dt = datetime.strptime(iso[:10], "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return iso

# ---------------------------------------------------------------------------
# Interplay SOAP client
# ---------------------------------------------------------------------------

def normalize_server_url(server: str) -> str:
    server = server.strip()
    if "://" not in server:
        server = f"http://{server}"

    parsed = urllib.parse.urlsplit(server)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Server must use http:// or https://.")
    if not parsed.hostname:
        raise ValueError("Server address is missing a host.")
    if parsed.username or parsed.password:
        raise ValueError("Enter credentials in the username and password fields.")
    if parsed.query or parsed.fragment:
        raise ValueError("Server address cannot include a query string or fragment.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Server port must be a number.") from exc

    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    base_path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit(
        (parsed.scheme, f"{host}:{port}", base_path, "", "")
    )

class InterplayClient:
    def __init__(self, server: str, username: str, password: str):
        self.username = username
        self.password = password
        server = normalize_server_url(server)
        self.assets_url = server + "/services/Assets"

    def _creds(self) -> str:
        u = html_lib.escape(self.username)
        p = html_lib.escape(self.password)
        return (f'<types:UserCredentials xmlns:types="{TYPES_NS}">'
                f"<types:Username>{u}</types:Username>"
                f"<types:Password>{p}</types:Password>"
                f"</types:UserCredentials>")

    def _envelope(self, body: str) -> str:
        return (f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" xmlns:types="{TYPES_NS}">'
                f"<soapenv:Header>{self._creds()}</soapenv:Header>"
                f"<soapenv:Body>{body}</soapenv:Body>"
                f"</soapenv:Envelope>")

    def _post(self, envelope: str) -> str:
        headers = {"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": '""'}
        resp = requests.post(self.assets_url, data=envelope.encode("utf-8"),
                             headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _check_errors(root: ET.Element):
        fault = root.find(f".//{{{SOAP_NS}}}Fault")
        if fault is not None:
            fs = fault.find("faultstring")
            raise RuntimeError(f"SOAP Fault: {fs.text if fs is not None else 'Unknown'}")
        errors = root.findall(f".//{{{TYPES_NS}}}Error")
        if errors:
            msgs = [e.findtext(f"{{{TYPES_NS}}}Message") or "" for e in errors]
            raise RuntimeError("Interplay error: " + "; ".join(m for m in msgs if m))

    @staticmethod
    def _parse(xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        InterplayClient._check_errors(root)
        assets = []
        for desc in root.iter(f"{{{TYPES_NS}}}AssetDescription"):
            uri_el = desc.find(f"{{{TYPES_NS}}}InterplayURI")
            uri = (uri_el.text or "").strip() if uri_el is not None else ""
            attrs: dict[str, str] = {}
            for attr in desc.findall(f".//{{{TYPES_NS}}}Attribute"):
                group = attr.get("Group", "").strip().title()
                name  = attr.get("Name",  "").strip()
                attrs[f"{group}.{name}"] = (attr.text or "").strip()
            display_name = (attrs.get("Asset.Name")
                            or attrs.get("User.Display Name")
                            or uri.rstrip("/").rsplit("/", 1)[-1])
            asset_type = (attrs.get("Asset.Type") or attrs.get("System.Type", "")).lower()
            assets.append({"uri": uri, "name": display_name,
                           "type": asset_type, "attrs": attrs})
        return assets

    def get_children(self, uri: str,
                     folders: bool = True,
                     files:   bool = True,
                     mobs:    bool = True) -> list[dict]:
        ra = "".join(
            f'<types:Attribute Group="{g}" Name="{n}"/>'
            for g, n in RETURN_ATTRS)
        body = (f"<types:GetChildren>"
                f"<types:InterplayURI>{html_lib.escape(uri)}</types:InterplayURI>"
                f"<types:IncludeFolders>{'true' if folders else 'false'}</types:IncludeFolders>"
                f"<types:IncludeFiles>{'true' if files else 'false'}</types:IncludeFiles>"
                f"<types:IncludeMOBs>{'true' if mobs else 'false'}</types:IncludeMOBs>"
                f"<types:ReturnAttributes>{ra}</types:ReturnAttributes>"
                f"</types:GetChildren>")
        return self._parse(self._post(self._envelope(body)))

    def get_locators(self, uri: str) -> list[dict]:
        body = (f"<types:GetUMIDLocators>"
                f"<types:InterplayURI>{html_lib.escape(uri)}</types:InterplayURI>"
                f"</types:GetUMIDLocators>")
        root = ET.fromstring(self._post(self._envelope(body)))
        self._check_errors(root)
        locators = []
        for loc in root.iter(f"{{{TYPES_NS}}}Locator"):
            locators.append({
                "timecode": (loc.findtext(f"{{{TYPES_NS}}}Timecode")  or "").strip(),
                "comment":  (loc.findtext(f"{{{TYPES_NS}}}Comment")   or "").strip(),
                "username": (loc.findtext(f"{{{TYPES_NS}}}Username")  or "").strip(),
                "color":    (loc.findtext(f"{{{TYPES_NS}}}Color")     or "").strip(),
            })
        return locators

# ---------------------------------------------------------------------------
# Project loading
# ---------------------------------------------------------------------------

def _uri_variants(uri: str):
    yield uri
    yield (uri.rstrip("/") if uri.endswith("/") else uri + "/")

def _collect_items(client, uri: str, acc: list, depth: int,
                   max_depth: int = DEFAULT_PROJECT_LOAD_DEPTH):
    if max_depth and depth > max_depth:
        return
    sub_folders = items = None
    for try_uri in _uri_variants(uri):
        try:
            sub_folders = client.get_children(try_uri, folders=True,  files=False, mobs=False)
            items       = client.get_children(try_uri, folders=False, files=True,  mobs=True)
            break
        except RuntimeError as e:
            if "not found" in str(e).lower():
                sub_folders = items = None
                continue
            raise
    if sub_folders is None:
        raise RuntimeError(f"Path not found: {uri}")
    acc.extend(items or [])
    for folder in sub_folders:
        _collect_items(client, folder["uri"], acc, depth + 1, max_depth)

def load_project_data(client: InterplayClient, uri: str,
                      status_fn=None,
                      max_depth: int = DEFAULT_PROJECT_LOAD_DEPTH) -> list[dict]:
    tried: list[str] = []
    folders = loose = None

    for try_uri in _uri_variants(uri):
        tried.append(try_uri)
        try:
            folders = client.get_children(try_uri, folders=True,  files=False, mobs=False)
            loose   = client.get_children(try_uri, folders=False, files=True,  mobs=True)
            break
        except RuntimeError as e:
            if "not found" in str(e).lower():
                folders = loose = None
                continue
            raise

    if folders is None:
        raise RuntimeError("Project not found. Tried:\n" + "\n".join(tried))

    folders = sorted(folders, key=lambda a: natural_key(a["name"]))

    sections: list[dict] = []
    if loose:
        sections.append({"name": "(Project root)", "items": loose})

    for folder in folders:
        if status_fn:
            status_fn(f"Loading: {folder['name']}…")
        try:
            items: list[dict] = []
            _collect_items(client, folder["uri"], items, depth=0, max_depth=max_depth)
            sections.append({"name": folder["name"], "items": items})
        except Exception as e:
            sections.append({"name": folder["name"], "items": [], "error": str(e)})

    return sections

# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_project(project_name: str,
                   sections: list[dict],
                   active: frozenset) -> str:
    lines: list[str] = []

    lines.append(f"PROJECT: {project_name}")
    lines.append(f"Date:    {datetime.now().strftime('%Y-%m-%d  %H:%M')}")
    lines.append("─" * LINE_WIDTH)
    lines.append("")

    n_sec = len(sections)
    for si, section in enumerate(sections):
        sec_last = (si == n_sec - 1)
        s_branch = "└── " if sec_last else "├── "
        i_cont   = "    " if sec_last else "│   "

        items   = section["items"]
        n_items = len(items)
        count   = f"  [{n_items} item{'s' if n_items != 1 else ''}]"
        lines.append(f"{s_branch}{section['name'].upper()}{count}")

        if section.get("error"):
            lines.append(f"{i_cont}└── [Error: {section['error']}]")
        elif not items:
            lines.append(f"{i_cont}└── (empty)")
        else:
            name_w = min(max(len(i["name"]) for i in items), 44)

            for ji, item in enumerate(items):
                item_last = (ji == n_items - 1)
                i_branch  = "└── " if item_last else "├── "
                sub_cont  = "    " if item_last else "│   "

                attrs = item["attrs"]
                name  = item["name"]
                tcode = _TYPE_LABEL.get(item.get("type", "").lower(), "   ")

                dur    = attrs.get("System.Duration",     "") if ("System", "Duration")     in active else ""
                status = attrs.get("System.Media Status", "").capitalize() if ("System", "Media Status") in active else ""

                name_col   = name[:name_w].ljust(name_w)
                main_parts = [f"{i_cont}{i_branch}{name_col}"]
                if dur:
                    main_parts.append(dur.ljust(12))
                if status:
                    main_parts.append(status)
                if tcode.strip():
                    main_parts.append(tcode.strip())
                lines.append("   ".join(main_parts).rstrip())

                cb = attrs.get("System.Created By",    "")
                cd = fmt_date(attrs.get("System.Creation Date", ""))
                mb = attrs.get("System.Modified By",   "")
                md = fmt_date(attrs.get("System.Modified Date", ""))

                show_created  = ("System", "Created By")  in active or ("System", "Creation Date")  in active
                show_modified = ("System", "Modified By") in active or ("System", "Modified Date")  in active

                date_parts: list[str] = []
                if show_created and (cb or cd):
                    date_parts.append(f"Created: {' '.join(filter(None, [cb, cd]))}")
                if show_modified and (mb or md):
                    date_parts.append(f"Modified: {' '.join(filter(None, [mb, md]))}")
                if date_parts:
                    lines.append(f"{i_cont}{sub_cont}" + "   |   ".join(date_parts))

                extra_parts: list[str] = []
                for g, n, label, _, cat in FIELD_DEFS:
                    if cat in ("", "Core", "Dates", "Markers"):
                        continue
                    if (g, n) not in active:
                        continue
                    val = attrs.get(f"{g}.{n}", "")
                    if val:
                        extra_parts.append(f"{label}: {val}")
                if extra_parts:
                    pfx  = f"{i_cont}{sub_cont}"
                    line = pfx
                    for part in extra_parts:
                        if len(line) + len(part) + 3 > LINE_WIDTH and line.strip():
                            lines.append(line.rstrip())
                            line = pfx + part + "   "
                        else:
                            line += part + "   "
                    if line.strip():
                        lines.append(line.rstrip())

                if ("Markers", "Locators") in active:
                    markers = item.get("markers") or []
                    if markers:
                        pfx = f"{i_cont}{sub_cont}"
                        lines.append(f"{pfx}Markers ({len(markers)}):")
                        for m in markers:
                            tc    = m.get("timecode", "").ljust(12)
                            color = m.get("color",    "").upper().ljust(7)
                            user  = m.get("username", "")
                            note  = m.get("comment",  "")
                            row   = f"{pfx}  {tc}  {color}"
                            if user:
                                row += f"  {user}"
                                if note:
                                    row += f": {note}"
                            elif note:
                                row += f"  {note}"
                            lines.append(row)

                if not item_last:
                    lines.append(i_cont.rstrip())

        if not sec_last:
            lines.append("│")
            lines.append("│")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------

def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "10022" in msg or "invalid argument was supplied" in low:
        return ("Could not connect — Windows Firewall may be blocking the app. "
                "Go to Windows Defender Firewall → Allow an app, find MCExplorer and allow it.")
    if "10061" in msg or "connection refused" in low:
        return "Connection refused — is the Avid WS service running on that server?"
    if "timed out" in low or "timeout" in low:
        return "Connection timed out — check the server address and network."
    if "max retries exceeded" in low or "newconnectionerror" in low:
        return "Could not reach server — check the address and that the server is online."
    if "401" in msg or "unauthorized" in low:
        return "Authentication failed — check username and password."
    if "soap fault" in low or "interplay error" in low:
        return msg
    if "Caused by" in msg:
        inner = msg.split("Caused by")[-1].strip().strip("()")
        return inner[:200] + ("…" if len(inner) > 200 else "")
    return msg[:200] + ("…" if len(msg) > 200 else "")

# ---------------------------------------------------------------------------
# Updater
# ---------------------------------------------------------------------------

class Updater:
    def __init__(self):
        self._pending: Path | None = None
        self._available: dict | None = None

    @property
    def pending_path(self) -> Path | None:
        return self._pending

    def set_pending(self, path: Path):
        self._pending = path

    def check_for_update(self) -> dict:
        """Synchronous check — call from a background thread or API handler."""
        if __version__ == "dev":
            return {"available": False, "current": __version__}
        try:
            resp  = requests.get(
                f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
                timeout=10)
            resp.raise_for_status()
            data   = resp.json()
            tag    = data.get("tag_name", "").lstrip("v")
            assets = data.get("assets", [])
            if self._newer_than_current(tag):
                asset = self._asset(assets)
                url = asset.get("browser_download_url", "") if asset else ""
                if url:
                    digest = asset.get("digest", "")
                    sha256 = digest.removeprefix("sha256:") if digest.startswith("sha256:") else ""
                    self._validate_download_url(url)
                    self._available = {"tag": tag, "url": url, "sha256": sha256}
                    return {"available": True, "tag": tag, "current": __version__,
                            "notes": data.get("body", "") or ""}
        except Exception:
            pass
        self._available = None
        return {"available": False, "current": __version__}

    @staticmethod
    def _newer_than_current(tag: str) -> bool:
        try:
            remote = tuple(int(x) for x in tag.split(".")[:3])
            local  = tuple(int(x) for x in __version__.split(".")[:3])
            return remote > local
        except Exception:
            return False

    @staticmethod
    def _asset(assets: list) -> dict | None:
        want = "MCExplorer-Setup.exe" if IS_WIN else "MCExplorer.dmg"
        for a in assets:
            if a.get("name") == want:
                return a
        return None

    @staticmethod
    def _validate_download_url(url: str):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise RuntimeError("Update download URL is not a trusted GitHub release URL.")
        expected_prefix = f"/{GITHUB_OWNER}/{GITHUB_REPO}/releases/download/".lower()
        if not parsed.path.lower().startswith(expected_prefix):
            raise RuntimeError("Update download URL does not match this app's release repo.")

    def download_available(self) -> Path:
        if not self._available:
            raise RuntimeError("No checked update is available.")
        return self.download(self._available["url"], self._available.get("sha256") or "")

    def download(self, url: str, expected_sha256: str = "") -> Path:
        self._validate_download_url(url)
        suffix = ".exe" if IS_WIN else ".dmg"
        fd, tmp_str = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        tmp = Path(tmp_str)
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        digest = hashlib.sha256()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    digest.update(chunk)
        if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
            try:
                tmp.unlink()
            except Exception:
                pass
            raise RuntimeError("Downloaded update did not match the release checksum.")
        return tmp

    def launch_installer(self, path: Path):
        if IS_WIN:
            subprocess.Popen([str(path), "/SILENT"])
        elif IS_MAC:
            self._mac_install(path)

    @staticmethod
    def _mac_install(dmg: Path):
        fd, mount_str = tempfile.mkstemp(suffix="_mount")
        os.close(fd)
        os.unlink(mount_str)
        mount_pt = mount_str

        if getattr(sys, "frozen", False):
            app_dest    = str(Path(sys.executable).parent.parent.parent)
            install_dir = str(Path(app_dest).parent)
        else:
            app_dest    = "/Applications/MCExplorer.app"
            install_dir = "/Applications"

        fd2, script_str = tempfile.mkstemp(suffix=".sh")
        os.close(fd2)
        script = (
            "#!/usr/bin/env bash\n"
            "sleep 1\n"
            f'hdiutil attach "{dmg}" -nobrowse -mountpoint "{mount_pt}" -quiet || exit 1\n'
            f'rm -rf "{app_dest}"\n'
            f'cp -R "{mount_pt}/MCExplorer.app" "{install_dir}/"\n'
            f'hdiutil detach "{mount_pt}" -quiet\n'
            f'open "{install_dir}/MCExplorer.app"\n'
            'rm -- "$0"\n'
        )
        Path(script_str).write_text(script, encoding="utf-8")
        Path(script_str).chmod(0o755)
        subprocess.Popen(["bash", script_str], close_fds=True, start_new_session=True)

# ---------------------------------------------------------------------------
# JavaScript API (exposed to the webview frontend)
# ---------------------------------------------------------------------------

class Api:
    def __init__(self):
        self._window: webview.Window | None = None
        self._client: InterplayClient | None = None
        self._cfg    = load_config()
        self._updater = Updater()

    def _set_window(self, window: webview.Window):
        self._window = window

    def _push_status(self, msg: str):
        if self._window:
            safe = json.dumps(msg)
            self._window.evaluate_js(f"window._onStatus && window._onStatus({safe})")

    # ── Config / credentials ──────────────────────────────────────────────────

    def get_version(self) -> str:
        return __version__

    def get_config(self) -> dict:
        username = self._cfg.get("username", "")
        saved = self._cfg.get("default_fields")
        active = frozenset(tuple(x) for x in saved) if saved else DEFAULT_FIELDS
        return {
            "server":         self._cfg.get("server", ""),
            "workgroup":      self._cfg.get("workgroup", "AvidWorkgroup"),
            "username":       username,
            "has_password":   bool(load_password(username)) if username else False,
            "start_path":     self._cfg.get("start_path", ""),
            "max_depth":      self._cfg.get("max_depth", 0),
            "default_fields": [list(f) for f in active],
        }

    def get_root_uri(self) -> str:
        wg = self._cfg.get("workgroup", "AvidWorkgroup")
        return f"interplay://{wg}/"

    def save_settings(self, server: str, workgroup: str,
                      username: str, password: str,
                      start_path: str = "", max_depth: int = 0,
                      default_fields=None) -> dict:
        server     = server.strip()
        workgroup  = workgroup.strip() or "AvidWorkgroup"
        username   = username.strip()
        start_path = start_path.strip()
        if not server or not username:
            return {"ok": False, "error": "Server and username are required."}
        try:
            max_depth = max(0, min(20, int(max_depth)))
        except Exception:
            max_depth = 0
        try:
            server = normalize_server_url(server)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        password = password or load_password(username)
        client = InterplayClient(server, username, password)
        if default_fields is not None:
            fields_to_save = [list(x) for x in
                              frozenset(tuple(x) for x in default_fields if len(x) == 2)]
        else:
            fields_to_save = self._cfg.get("default_fields")
        new_cfg = {**self._cfg, "server": server, "workgroup": workgroup,
                   "username": username, "start_path": start_path,
                   "max_depth": max_depth, "default_fields": fields_to_save}
        save_config(new_cfg)
        save_password(username, password)
        self._cfg    = new_cfg
        self._client = client
        return {"ok": True}

    # ── Connection / browsing ─────────────────────────────────────────────────

    def test_connection(self, server: str, workgroup: str,
                        username: str, password: str) -> dict:
        try:
            username = username.strip()
            password = password or load_password(username)
            client = InterplayClient(server.strip(), username, password)
            wg = workgroup.strip() or "AvidWorkgroup"
            client.get_children(f"interplay://{wg}/",
                                folders=True, files=False, mobs=False)
            return {"ok": True, "message": "Connected successfully."}
        except Exception as e:
            return {"ok": False, "message": _friendly_error(e)}

    def get_children(self, uri: str) -> list | dict:
        if not self._client:
            return {"error": "Not connected. Open Settings and save your credentials."}
        try:
            items = self._client.get_children(
                uri, folders=True, files=False, mobs=False)
            return [{"name": i["name"], "uri": i["uri"]}
                    for i in sorted(items, key=lambda a: natural_key(a["name"]))]
        except Exception as e:
            return {"error": _friendly_error(e)}

    def load_project(self, name: str, uri: str) -> dict:
        if not self._client:
            return {"error": "Not connected."}
        try:
            def sf(msg):
                self._push_status(msg)
            sections = load_project_data(self._client, uri, status_fn=sf)
            saved = self._cfg.get("default_fields")
            active = frozenset(tuple(x) for x in saved) if saved else DEFAULT_FIELDS

            if ("Markers", "Locators") in active:
                clip_types = {"masterclip", "sequence", "subclip"}
                clips = [(s, i) for s in sections for i in s["items"]
                         if i.get("type", "") in clip_types]
                total = len(clips)
                for idx, (_, item) in enumerate(clips):
                    if total > 5 and idx % 5 == 0:
                        self._push_status(f"Fetching markers… {idx}/{total}")
                    try:
                        item["markers"] = self._client.get_locators(item["uri"])
                    except Exception:
                        item["markers"] = []

            text = format_project(name, sections, active)
            n = sum(len(s["items"]) for s in sections)
            return {"text": text, "summary": f"{n} item{'s' if n != 1 else ''} loaded."}
        except Exception as e:
            return {"error": _friendly_error(e)}

    def save_fields(self, default_fields) -> dict:
        try:
            fields = [list(x) for x in
                      frozenset(tuple(x) for x in default_fields if len(x) == 2)]
            new_cfg = {**self._cfg, "default_fields": fields}
            save_config(new_cfg)
            self._cfg = new_cfg
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── File / export actions ─────────────────────────────────────────────────

    def save_to_file(self, filename: str, text: str) -> dict:
        if not self._window:
            return {"ok": False}
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=filename,
            file_types=("Text files (*.txt)",))
        if not result:
            return {"ok": False}
        path = result[0] if isinstance(result, (list, tuple)) else result
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_email(self, project_name: str, text: str) -> dict:
        subject = urllib.parse.quote(f"Interplay Project: {project_name}")
        body    = urllib.parse.quote(text)
        url = f"mailto:?subject={subject}&body={body}"
        if len(url) > MAILTO_MAX_URL_LENGTH:
            return {"ok": False, "error": "Email draft is too large. Use Copy or Save instead."}
        webbrowser.open(url)
        return {"ok": True}

    # ── Updates ───────────────────────────────────────────────────────────────

    def check_updates(self) -> dict:
        return self._updater.check_for_update()

    def install_update_now(self) -> dict:
        try:
            path = self._updater.download_available()
            self._updater.launch_installer(path)
            if self._window:
                import threading
                def _quit():
                    import time; time.sleep(1.5)
                    self._window.destroy()
                threading.Thread(target=_quit, daemon=True).start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def queue_update(self) -> dict:
        try:
            path = self._updater.download_available()
            self._updater.set_pending(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

# ---------------------------------------------------------------------------
# CLI entry point (unchanged)
# ---------------------------------------------------------------------------

def _cli():
    import argparse
    parser = argparse.ArgumentParser(
        description="MediaCentral Explorer — CLI mode")
    parser.add_argument("--server",   required=True, help="Server address")
    parser.add_argument("--user",     required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--path",     required=True,
                        help="Interplay path, e.g. interplay://AvidWorkgroup/Projects/2026")
    parser.add_argument("--project",
                        help="Project name to load (substring match). "
                             "Omit to list projects only.")
    parser.add_argument("--fields", nargs="*",
                        help="Override active fields as Group.Name pairs")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw asset info for each item")
    args = parser.parse_args()

    client = InterplayClient(args.server, args.user, args.password)

    if not args.project:
        print(f"Listing: {args.path}")
        try:
            projects = client.get_children(
                args.path, folders=True, files=False, mobs=False)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        if not projects:
            print("  (no projects found)")
            return
        for p in sorted(projects, key=lambda x: natural_key(x["name"])):
            print(f"  {p['name']}")
        print(f"\n{len(projects)} project(s) found.")
        return

    print(f"Searching for '{args.project}' in {args.path} …")
    try:
        projects = client.get_children(
            args.path, folders=True, files=False, mobs=False)
    except Exception as e:
        print(f"ERROR listing projects: {e}", file=sys.stderr)
        sys.exit(1)

    matches = [p for p in projects if args.project.lower() in p["name"].lower()]
    if not matches:
        print(f"No project matching '{args.project}'.")
        sys.exit(1)

    proj = matches[0]
    active = (frozenset(tuple(f.split(".", 1)) for f in args.fields if "." in f)
              if args.fields else DEFAULT_FIELDS)

    print(f"Loading: {proj['name']} …\n")
    try:
        sections = load_project_data(
            client, proj["uri"],
            status_fn=lambda m: print(f"  {m}", flush=True))
    except Exception as e:
        print(f"ERROR loading project: {e}", file=sys.stderr)
        sys.exit(1)

    if args.debug:
        print(json.dumps(sections, indent=2), file=sys.stderr)

    print(format_project(proj["name"], sections, active))

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli()
    else:
        ui_dir = _ui_dir()

        api = Api()

        # Pre-connect if we have saved credentials
        cfg = load_config()
        if cfg.get("server") and cfg.get("username"):
            pw = load_password(cfg["username"])
            try:
                api._client = InterplayClient(cfg["server"], cfg["username"], pw)
            except Exception:
                pass

        window = webview.create_window(
            title="Avid MediaCentral Metadata Exporter",
            url=str(ui_dir / "index.html"),
            js_api=api,
            width=1100,
            height=700,
            min_size=(800, 520),
        )
        api._set_window(window)

        # Run pending installer (if any) on exit
        atexit.register(lambda: (
            api._updater.launch_installer(api._updater.pending_path)
            if api._updater.pending_path and api._updater.pending_path.exists()
            else None
        ))

        webview.start()
