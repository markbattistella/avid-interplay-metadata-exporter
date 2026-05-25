#!/usr/bin/env python3
"""Avid Interplay Project Explorer"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import requests
import xml.etree.ElementTree as ET
import threading
import html as html_lib
import json
import re
import sys
import os
import webbrowser
import urllib.parse
from pathlib import Path
from datetime import datetime

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

# ---------------------------------------------------------------------------
# Field definitions
# (group, attr_name, display_label, default_on, category)
# category="" means always fetched / not shown as a user toggle
# ---------------------------------------------------------------------------

FIELD_DEFS = [
    # Always fetched, not shown in dialog
    ("Asset",  "Name",             "Name",             True,  ""),
    ("Asset",  "Type",             "Node Type",        True,  ""),
    # Core — shown on the main clip line
    ("System", "Duration",         "Duration",         True,  "Core"),
    ("System", "Media Status",     "Media Status",     True,  "Core"),
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
    ("System", "Type",             "Asset Type",       False, "Technical"),
    ("System", "Format",           "Format",           False, "Technical"),
    ("System", "Resolution",       "Resolution",       False, "Technical"),
    ("System", "Tape",             "Tape / Reel",      False, "Technical"),
    ("System", "Original Project", "Original Project", False, "Technical"),
    # Production — shown as extras
    ("User",   "Comments",         "Comments",         False, "Production"),
    ("User",   "Scene",            "Scene",            False, "Production"),
    ("User",   "Take",             "Take",             False, "Production"),
    ("User",   "Camera",           "Camera",           False, "Production"),
    ("User",   "Camroll",          "Camera Roll",      False, "Production"),
    ("User",   "Shoot Date",       "Shoot Date",       False, "Production"),
]

# Fields always shown — not user-toggleable
_ALWAYS_ON = frozenset(
    (g, n) for g, n, _, _, cat in FIELD_DEFS if cat == "")

# Default active set (toggleable fields that are on by default)
DEFAULT_FIELDS = frozenset(
    (g, n) for g, n, _, default, cat in FIELD_DEFS if default and cat != "")

# All attributes to request from the API in one go
RETURN_ATTRS = [(g, n) for g, n, _, _, _ in FIELD_DEFS]

# Rendering buckets
_MAIN_LINE   = {("System", "Duration"), ("System", "Media Status")}
_DATE_LINE   = {("System", "Created By"), ("System", "Creation Date"),
                ("System", "Modified By"), ("System", "Modified Date")}
_EXTRAS      = {(g, n) for g, n, _, _, cat in FIELD_DEFS
                if cat not in ("", "Core", "Dates")}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOAP_NS    = "http://schemas.xmlsoap.org/soap/envelope/"
TYPES_NS   = "http://avid.com/interplay/ws/assets/types"
APP_NAME   = "InterplayExplorer"
LINE_WIDTH = 72

# Short labels shown in the type column of the output
_TYPE_LABEL = {
    "masterclip":  "MC ",
    "sequence":    "SEQ",
    "subclip":     "SUB",
    "effect":      "FX ",
    "group":       "GRP",
    "folder":      "DIR",
    "bin":         "BIN",
}

# ---------------------------------------------------------------------------
# Config  (server / path / username / saved field defaults)
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
# Credentials  (Windows Credential Manager / macOS Keychain via keyring)
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
# Natural sort  (1 2 10  not  1 10 2)
# ---------------------------------------------------------------------------

def natural_key(s: str) -> list:
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", s or "")]

# ---------------------------------------------------------------------------
# Interplay SOAP client
# ---------------------------------------------------------------------------

class InterplayClient:
    def __init__(self, server: str, username: str, password: str):
        self.username = username
        self.password = password
        if not server.startswith(("http://", "https://")):
            server = f"http://{server}"
        self.assets_url = server.rstrip("/") + "/services/Assets"

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
            # Collect ALL attributes returned — store keyed as "Group.Name"
            attrs: dict[str, str] = {}
            for attr in desc.findall(f".//{{{TYPES_NS}}}Attribute"):
                key = f"{attr.get('Group','')}.{attr.get('Name','')}"
                attrs[key] = (attr.text or "").strip()
            display_name = attrs.get("Asset.Name") or uri.rstrip("/").rsplit("/", 1)[-1]
            asset_type   = attrs.get("Asset.Type", "").lower()
            assets.append({
                "uri":   uri,
                "name":  display_name,
                "type":  asset_type,
                "attrs": attrs,
            })
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

# ---------------------------------------------------------------------------
# Asset helpers
# ---------------------------------------------------------------------------

def is_folder(asset: dict) -> bool:
    t = asset.get("type", "")
    return "folder" in t or "bin" in t

# ---------------------------------------------------------------------------
# Project loading (recursive)
# ---------------------------------------------------------------------------

def load_project_data(client: InterplayClient, uri: str,
                      status_fn=None) -> list[dict]:
    """
    Returns list of sections:
        [{"name": str, "items": [{"name", "attrs"}, ...]}, ...]
    """
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
            _collect_items(client, folder["uri"], items, depth=0)
            sections.append({"name": folder["name"], "items": items})
        except Exception as e:
            sections.append({"name": folder["name"], "items": [], "error": str(e)})

    return sections

def _uri_variants(uri: str):
    yield uri
    yield (uri.rstrip("/") if uri.endswith("/") else uri + "/")

def _collect_items(client, uri: str, acc: list, depth: int):
    if depth > 4:
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
        _collect_items(client, folder["uri"], acc, depth + 1)

# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_project(project_name: str,
                   sections: list[dict],
                   active: frozenset) -> str:
    lines: list[str] = []

    lines.append(f"PROJECT: {project_name}")
    lines.append(f"Date:    {datetime.now().strftime('%d %B %Y  %I:%M %p')}")
    lines.append("─" * LINE_WIDTH)
    lines.append("")

    for section in sections:
        heading = section["name"].upper()
        lines.append(heading)
        lines.append("─" * min(len(heading), LINE_WIDTH))

        items = section["items"]
        if not items:
            err = section.get("error", "")
            lines.append(f"  [Error: {err}]" if err else "  (empty)")
            lines.append("")
            continue

        # Calculate name column width (capped so lines stay reasonable)
        name_w = min(max(len(i["name"]) for i in items), 44)

        for item in items:
            attrs = item["attrs"]
            name  = item["name"]
            tcode = _TYPE_LABEL.get(item.get("type", "").lower(), "   ")

            # ── Main line: Type   Name   Duration   Status ────────────────────
            dur    = attrs.get("System.Duration",    "") if ("System", "Duration")     in active else ""
            status = attrs.get("System.Media Status","") if ("System", "Media Status") in active else ""

            name_col = name[:name_w].ljust(name_w)
            main_parts = [f"  {tcode}  {name_col}"]
            if dur:
                main_parts.append(dur.ljust(12))
            if status:
                main_parts.append(status)
            lines.append("   ".join(main_parts).rstrip())

            # ── Date sub-line ─────────────────────────────────────────────────
            date_parts: list[str] = []
            cb = attrs.get("System.Created By",    "")
            cd = attrs.get("System.Creation Date", "")
            mb = attrs.get("System.Modified By",   "")
            md = attrs.get("System.Modified Date", "")

            show_created  = ("System", "Created By")    in active or ("System", "Creation Date")  in active
            show_modified = ("System", "Modified By")   in active or ("System", "Modified Date") in active

            if show_created and (cb or cd):
                date_parts.append(f"Created: {' '.join(filter(None, [cb, cd]))}")
            if show_modified and (mb or md):
                date_parts.append(f"Modified: {' '.join(filter(None, [mb, md]))}")
            if date_parts:
                lines.append("    " + "   |   ".join(date_parts))

            # ── Extras sub-line ───────────────────────────────────────────────
            extra_parts: list[str] = []
            for g, n, label, _, cat in FIELD_DEFS:
                if cat in ("", "Core", "Dates"):
                    continue
                if (g, n) not in active:
                    continue
                val = attrs.get(f"{g}.{n}", "")
                if val:
                    extra_parts.append(f"{label}: {val}")
            if extra_parts:
                # Wrap into ~LINE_WIDTH chunks
                line = "    "
                for part in extra_parts:
                    if len(line) + len(part) + 3 > LINE_WIDTH and line.strip():
                        lines.append(line.rstrip())
                        line = "    " + part + "   "
                    else:
                        line += part + "   "
                if line.strip():
                    lines.append(line.rstrip())

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

# ---------------------------------------------------------------------------
# Fields dialog
# ---------------------------------------------------------------------------

class FieldsDialog(tk.Toplevel):
    """
    Let the user pick which fields appear in the output.
    Does NOT auto-save — user must click 'Save as Defaults' to persist.
    """

    def __init__(self, parent, current: frozenset, on_apply):
        super().__init__(parent)
        self.title("Configure Output Fields")
        self.resizable(False, False)
        self.grab_set()                      # modal
        self._on_apply = on_apply
        self._vars: dict[tuple, tk.BooleanVar] = {}

        self._build(current)
        self.transient(parent)
        self.wait_visibility()
        self.focus_set()

    def _build(self, current: frozenset):
        pad = {"padx": 10, "pady": 4}

        # Group fields by category
        cats: dict[str, list] = {}
        for g, n, label, _, cat in FIELD_DEFS:
            if not cat:
                continue
            cats.setdefault(cat, []).append((g, n, label))

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        # Two-column layout of category frames
        cat_order = ["Core", "Dates", "Timecode", "Technical", "Production"]
        col = 0
        for cat in cat_order:
            if cat not in cats:
                continue
            frame = ttk.LabelFrame(outer, text=cat, padding=8)
            frame.grid(row=0, column=col, sticky="nw", padx=6, pady=4)
            for i, (g, n, label) in enumerate(cats[cat]):
                var = tk.BooleanVar(value=(g, n) in current)
                self._vars[(g, n)] = var
                ttk.Checkbutton(frame, text=label, variable=var).grid(
                    row=i, column=0, sticky="w")
            col += 1

        # Buttons
        btn_row = ttk.Frame(outer)
        btn_row.grid(row=1, column=0, columnspan=col, sticky="ew", pady=(12, 0))
        btn_row.columnconfigure(1, weight=1)

        ttk.Button(btn_row, text="Reset to Defaults",
                   command=self._reset).grid(row=0, column=0, sticky="w")
        ttk.Button(btn_row, text="Save as Defaults",
                   command=self._save_defaults).grid(row=0, column=2, padx=(4, 0))
        ttk.Button(btn_row, text="Apply",
                   command=self._apply).grid(row=0, column=3, padx=(4, 0))

    def _current_selection(self) -> frozenset:
        return frozenset(k for k, v in self._vars.items() if v.get())

    def _reset(self):
        for (g, n), var in self._vars.items():
            var.set((g, n) in DEFAULT_FIELDS)

    def _save_defaults(self):
        sel = self._current_selection()
        # Persist as list-of-lists in config
        cfg = load_config()
        cfg["default_fields"] = [[g, n] for g, n in sel]
        save_config(cfg)
        self._on_apply(sel)
        self.destroy()

    def _apply(self):
        self._on_apply(self._current_selection())
        self.destroy()

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Interplay Project Explorer")
        self.geometry("1100x700")
        self.minsize(800, 520)

        self._cfg           = load_config()
        self._all_projects: list[dict] = []
        self._uri_map:      dict[str, str] = {}
        self._sort_reverse  = False
        self._last_output   = ""
        self._last_sections: list[dict] = []
        self._last_project  = ""

        # Load field selection: saved defaults → fall back to built-in defaults
        saved = self._cfg.get("default_fields")
        if saved:
            self._active_fields = frozenset(tuple(x) for x in saved)
        else:
            self._active_fields = DEFAULT_FIELDS

        self._build_ui()
        self._load_saved()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Connection bar ────────────────────────────────────────────────────
        conn = ttk.LabelFrame(self, text="Connection", padding=8)
        conn.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        conn.columnconfigure(3, weight=1)

        ttk.Label(conn, text="Username:").grid(row=0, column=0, sticky="w")
        self.v_user = tk.StringVar()
        user_e = ttk.Entry(conn, textvariable=self.v_user, width=20)
        user_e.grid(row=0, column=1, sticky="w", padx=(4, 20))

        ttk.Label(conn, text="Password:").grid(row=0, column=2, sticky="w")
        self.v_pass = tk.StringVar()
        pass_e = ttk.Entry(conn, textvariable=self.v_pass, width=20, show="•")
        pass_e.grid(row=0, column=3, sticky="w", padx=(4, 0))

        ttk.Label(conn, text="Server:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.v_server = tk.StringVar()
        server_e = ttk.Entry(conn, textvariable=self.v_server, width=28)
        server_e.grid(row=1, column=1, sticky="w", padx=(4, 20), pady=(6, 0))

        ttk.Label(conn, text="Path:").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.v_path = tk.StringVar(value="interplay://AvidWorkgroup/Projects/")
        path_e = ttk.Entry(conn, textvariable=self.v_path)
        path_e.grid(row=1, column=3, sticky="ew", padx=(4, 8), pady=(6, 0))

        self.btn_search = ttk.Button(conn, text="Search", command=self._on_search)
        self.btn_search.grid(row=1, column=4, pady=(6, 0))

        for w in (user_e, pass_e, server_e, path_e):
            w.bind("<Return>", lambda _: self._on_search())
        user_e.bind("<FocusOut>", lambda _: self._autofill_password())

        # ── Resizable split ───────────────────────────────────────────────────
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        left  = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left,  weight=1)
        paned.add(right, weight=3)

        # ── Left: filter + project tree ───────────────────────────────────────
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        filter_row = ttk.Frame(left)
        filter_row.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        filter_row.columnconfigure(1, weight=1)
        ttk.Label(filter_row, text="Filter:").grid(row=0, column=0, sticky="w")
        self.v_filter = tk.StringVar()
        ttk.Entry(filter_row, textvariable=self.v_filter).grid(
            row=0, column=1, sticky="ew", padx=(4, 0))
        self.v_filter.trace_add("write", lambda *_: self._apply_filter())

        tree_wrap = ttk.Frame(left)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_wrap, columns=("name",),
                                 show="headings", selectmode="browse")
        self.tree.heading("name", text="Project  ▲", anchor="w",
                          command=self._toggle_sort)
        self.tree.column("name", stretch=True)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", lambda _: self._on_load())
        self.tree.bind("<Return>",   lambda _: self._on_load())

        self.btn_load = ttk.Button(left, text="Load Project",
                                   state=tk.DISABLED, command=self._on_load)
        self.btn_load.grid(row=2, column=0, sticky="e", pady=(6, 0))

        # ── Right: output ─────────────────────────────────────────────────────
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        top_bar = ttk.Frame(right)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        top_bar.columnconfigure(1, weight=1)

        ttk.Label(top_bar, text="Project:").grid(row=0, column=0, sticky="w")
        self.lbl_project = ttk.Label(top_bar, text="", foreground="#555")
        self.lbl_project.grid(row=0, column=1, sticky="w", padx=(4, 0))

        self.btn_fields = ttk.Button(top_bar, text="Fields…",
                                     command=self._open_fields_dialog)
        self.btn_email  = ttk.Button(top_bar, text="Email",
                                     state=tk.DISABLED, command=self._email)
        self.btn_copy   = ttk.Button(top_bar, text="Copy",
                                     state=tk.DISABLED, command=self._copy)
        self.btn_export = ttk.Button(top_bar, text="Save as txt…",
                                     state=tk.DISABLED, command=self._export)
        self.btn_fields.grid(row=0, column=2, padx=(4, 0))
        self.btn_email.grid( row=0, column=3, padx=(4, 0))
        self.btn_copy.grid(  row=0, column=4, padx=(4, 0))
        self.btn_export.grid(row=0, column=5, padx=(4, 0))

        self.output = scrolledtext.ScrolledText(
            right, font=("Courier New", 10), state=tk.DISABLED, wrap=tk.NONE)
        self.output.grid(row=1, column=0, sticky="nsew")
        hbar = ttk.Scrollbar(right, orient="horizontal", command=self.output.xview)
        self.output.configure(xscrollcommand=hbar.set)
        hbar.grid(row=2, column=0, sticky="ew")

        # ── Status bar ────────────────────────────────────────────────────────
        self.v_status = tk.StringVar(
            value="Enter connection details and click Search.")
        ttk.Label(self, textvariable=self.v_status,
                  relief="sunken", anchor="w", padding=(6, 2)
                  ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 6))

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_saved(self):
        cfg = self._cfg
        self.v_server.set(cfg.get("server", ""))
        self.v_path.set(cfg.get("path", "interplay://AvidWorkgroup/Projects/"))
        username = cfg.get("username", "")
        self.v_user.set(username)
        if username:
            pw = load_password(username)
            if pw:
                self.v_pass.set(pw)

    def _save_settings(self):
        username = self.v_user.get().strip()
        save_config({
            **self._cfg,                       # keep saved field defaults
            "server":   self.v_server.get().strip(),
            "path":     self.v_path.get().strip(),
            "username": username,
        })
        save_password(username, self.v_pass.get())

    def _autofill_password(self):
        username = self.v_user.get().strip()
        if username and not self.v_pass.get():
            pw = load_password(username)
            if pw:
                self.v_pass.set(pw)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _status(self, msg: str):
        self.v_status.set(msg)
        self.update_idletasks()

    def _set_output(self, text: str):
        self.output.configure(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        if text:
            self.output.insert(tk.END, text)
        self.output.configure(state=tk.DISABLED)
        self._last_output = text

    def _make_client(self) -> InterplayClient:
        server = self.v_server.get().strip()
        user   = self.v_user.get().strip()
        pw     = self.v_pass.get()
        if not server:
            raise ValueError("Server address is required.")
        if not user:
            raise ValueError("Username is required.")
        return InterplayClient(server, user, pw)

    def _set_output_btns(self, enabled: bool):
        st = tk.NORMAL if enabled else tk.DISABLED
        for b in (self.btn_email, self.btn_copy, self.btn_export):
            b.configure(state=st)

    def _rerender(self):
        """Re-render from cached data with current field selection."""
        if self._last_sections and self._last_project:
            text = format_project(self._last_project,
                                  self._last_sections,
                                  self._active_fields)
            self._set_output(text)

    # ── Fields dialog ─────────────────────────────────────────────────────────

    def _open_fields_dialog(self):
        def on_apply(sel: frozenset):
            self._active_fields = sel
            self._rerender()
            count = len(sel)
            self._status(f"Output fields updated ({count} selected).")

        FieldsDialog(self, self._active_fields, on_apply)

    # ── Project list ──────────────────────────────────────────────────────────

    def _populate_tree(self, projects: list[dict]):
        self._all_projects = sorted(projects, key=lambda a: natural_key(a["name"]))
        self._sort_reverse = False
        self.tree.heading("name", text="Project  ▲")
        self._apply_filter()

    def _apply_filter(self):
        q = self.v_filter.get().lower()
        self.tree.delete(*self.tree.get_children())
        self._uri_map = {}
        for i, p in enumerate(self._all_projects):
            if q in p["name"].lower():
                iid = str(i)
                self.tree.insert("", tk.END, values=(p["name"],), iid=iid)
                self._uri_map[iid] = p["uri"]

    def _toggle_sort(self):
        self._sort_reverse = not self._sort_reverse
        arrow = "▼" if self._sort_reverse else "▲"
        self.tree.heading("name", text=f"Project  {arrow}")
        self._all_projects.sort(key=lambda a: natural_key(a["name"]),
                                reverse=self._sort_reverse)
        self._apply_filter()

    # ── Search ────────────────────────────────────────────────────────────────

    def _on_search(self):
        try:
            client = self._make_client()
        except ValueError as e:
            messagebox.showwarning("Missing fields", str(e))
            return
        path = self.v_path.get().strip()
        if not path:
            messagebox.showwarning("Missing path", "Enter an Interplay path.")
            return

        self._save_settings()
        self.btn_search.configure(state=tk.DISABLED)
        self._status("Connecting…")

        def work():
            try:
                assets = client.get_children(path, folders=True, files=False, mobs=False)
                self.after(0, lambda a=assets: self._search_done(a))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._search_error(e))

        threading.Thread(target=work, daemon=True).start()

    def _search_done(self, assets: list[dict]):
        self._populate_tree(assets)
        self.btn_search.configure(state=tk.NORMAL)
        self._status(
            f"Found {len(assets)} project(s). "
            "Select one and click Load Project (or double-click).")

    def _search_error(self, msg: str):
        self.btn_search.configure(state=tk.NORMAL)
        self._status(f"Search failed: {msg}")
        messagebox.showerror("Search Error", msg)

    # ── Tree selection ────────────────────────────────────────────────────────

    def _on_tree_select(self, _=None):
        self.btn_load.configure(
            state=tk.NORMAL if self.tree.selection() else tk.DISABLED)

    # ── Load project ──────────────────────────────────────────────────────────

    def _on_load(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        uri = self._uri_map.get(iid, "")
        if not uri:
            return
        project_name = self.tree.item(iid)["values"][0]

        try:
            client = self._make_client()
        except ValueError as e:
            messagebox.showwarning("Error", str(e))
            return

        self.btn_load.configure(state=tk.DISABLED)
        self._set_output_btns(False)
        self.lbl_project.configure(text=project_name)
        self._set_output("")
        self._status(f"Loading '{project_name}'…")

        def work():
            try:
                def sf(msg): self.after(0, lambda m=msg: self._status(m))
                sections = load_project_data(client, uri, status_fn=sf)
                output   = format_project(project_name, sections, self._active_fields)
                self.after(0, lambda o=output, n=project_name, s=sections:
                           self._load_done(o, n, s))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._load_error(e))

        threading.Thread(target=work, daemon=True).start()

    def _load_done(self, output: str, name: str, sections: list[dict]):
        self._last_sections = sections
        self._last_project  = name
        self._set_output(output)
        self.btn_load.configure(state=tk.NORMAL)
        self._set_output_btns(True)
        total = output.count("\n  ")
        self._status(f"Loaded '{name}' — {total} item(s).")

    def _load_error(self, msg: str):
        self.btn_load.configure(state=tk.NORMAL)
        self._status(f"Load failed: {msg}")
        messagebox.showerror("Load Error", msg)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._last_output)
        self._status("Copied to clipboard.")

    def _export(self):
        if not self._last_output.strip():
            return
        project = self.lbl_project.cget("text")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"{project}.txt" if project else "export.txt",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._last_output)
            self._status(f"Saved → {path}")

    def _email(self):
        project = self.lbl_project.cget("text")
        subject = urllib.parse.quote(f"Interplay Project: {project}")
        body    = urllib.parse.quote(self._last_output)
        webbrowser.open(f"mailto:?subject={subject}&body={body}")
        self._status("Opening email client…")


# ---------------------------------------------------------------------------
# CLI entry point  (no GUI — useful for testing connectivity)
# ---------------------------------------------------------------------------

def _cli():
    import argparse
    parser = argparse.ArgumentParser(
        description="Interplay Project Explorer — CLI mode")
    parser.add_argument("--server",   required=True, help="Server address")
    parser.add_argument("--user",     required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--path",     required=True,
                        help='Interplay path, e.g. interplay://AvidWorkgroup/Projects/2026')
    parser.add_argument("--project",
                        help="Project name to load (substring match). "
                             "Omit to list projects only.")
    parser.add_argument("--fields",   nargs="*",
                        help="Override active fields as Group.Name pairs, "
                             "e.g. System.Duration System.Media\\ Status")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw asset type/URI info for each item "
                             "(useful for diagnosing empty sections)")
    parser.add_argument("--raw-xml", action="store_true",
                        help="Dump the raw SOAP XML response for the first bin "
                             "and exit — used to diagnose attribute parsing")
    args = parser.parse_args()

    client = InterplayClient(args.server, args.user, args.password)

    if not args.project:
        # ── List projects ────────────────────────────────────────────────────
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
            if args.debug:
                print(f"    type : {p.get('type', '(empty)')}")
                print(f"    uri  : {p['uri']}")
        print(f"\n{len(projects)} project(s) found.")
        return

    # ── Load a project ───────────────────────────────────────────────────────
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
        print("Available projects:")
        for p in sorted(projects, key=lambda x: natural_key(x["name"])):
            print(f"  {p['name']}")
        sys.exit(1)

    proj = matches[0]
    if len(matches) > 1:
        print(f"Multiple matches — using: {proj['name']}")

    # Resolve active fields
    if args.fields:
        active = frozenset(tuple(f.split(".", 1)) for f in args.fields if "." in f)
    else:
        active = DEFAULT_FIELDS

    # ── Raw XML dump mode ────────────────────────────────────────────────────
    if getattr(args, "raw_xml", False):
        import xml.dom.minidom
        print(f"Fetching children of project URI: {proj['uri']}")
        # Dump the raw SOAP response for the first bin found
        try:
            bins = client.get_children(proj["uri"], folders=True, files=False, mobs=False)
        except Exception as e:
            print(f"ERROR listing bins: {e}", file=sys.stderr)
            sys.exit(1)
        if not bins:
            print("No bins found in project.")
            sys.exit(0)
        target = bins[0]
        print(f"\nFirst bin: {target['name']}")
        print(f"Bin URI:   {target['uri']}\n")
        print("── Raw SOAP response for GetChildren on that bin ──")
        ra = "".join(
            f'<types:Attribute Group="{g}" Name="{n}"/>'
            for g, n in RETURN_ATTRS)
        uri = target["uri"]
        body = (f"<types:GetChildren>"
                f"<types:InterplayURI>{html_lib.escape(uri)}</types:InterplayURI>"
                f"<types:IncludeFolders>false</types:IncludeFolders>"
                f"<types:IncludeFiles>true</types:IncludeFiles>"
                f"<types:IncludeMOBs>true</types:IncludeMOBs>"
                f"<types:ReturnAttributes>{ra}</types:ReturnAttributes>"
                f"</types:GetChildren>")
        envelope = client._envelope(body)
        raw = client._post(envelope)
        try:
            pretty = xml.dom.minidom.parseString(raw).toprettyxml(indent="  ")
        except Exception:
            pretty = raw
        print(pretty)
        sys.exit(0)

    print(f"Loading: {proj['name']} …\n")
    try:
        sections = load_project_data(
            client, proj["uri"],
            status_fn=lambda m: print(f"  {m}", flush=True))
    except Exception as e:
        print(f"ERROR loading project: {e}", file=sys.stderr)
        sys.exit(1)

    if args.debug:
        print("\n── DEBUG: raw section data ──")
        for sec in sections:
            print(f"\n  [{sec['name']}]  ({len(sec['items'])} item(s))")
            if sec.get("error"):
                print(f"    ERROR: {sec['error']}")
            for item in sec["items"][:5]:
                print(f"    --- item ---")
                print(f"    name : {item['name']}")
                print(f"    type : {item.get('type', '(empty)')}")
                print(f"    uri  : {item['uri']}")
                print(f"    attrs returned ({len(item['attrs'])}):")
                for k, v in sorted(item["attrs"].items()):
                    print(f"      {k} = {v!r}")
        print("\n── END DEBUG ──\n")

    print(format_project(proj["name"], sections, active))


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    # If any recognised CLI flags are present, skip the GUI entirely
    if len(sys.argv) > 1:
        _cli()
    else:
        app = App()
        app.mainloop()
