#!/usr/bin/env python3
"""Avid MediaCentral Explorer"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
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

try:
    from _version import __version__
except ImportError:
    __version__ = "dev"

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

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
]

_ALWAYS_ON = frozenset(
    (g, n) for g, n, _, _, cat in FIELD_DEFS if cat == "")

DEFAULT_FIELDS = frozenset(
    (g, n) for g, n, _, default, cat in FIELD_DEFS if default and cat != "")

RETURN_ATTRS = [(g, n) for g, n, _, _, _ in FIELD_DEFS]

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

_TYPE_LABEL = {
    "masterclip": "MC ",
    "sequence":   "SEQ",
    "subclip":    "SUB",
    "effect":     "FX ",
    "group":      "GRP",
    "folder":     "DIR",
    "bin":        "BIN",
}

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
    except Exception:
        try:
            dt = datetime.strptime(iso[:10], "%Y-%m-%d")
        except Exception:
            return iso
    return f"{dt.day} {dt.strftime('%b')} {dt.year}"

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

# ---------------------------------------------------------------------------
# Project loading
# ---------------------------------------------------------------------------

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

def load_project_data(client: InterplayClient, uri: str,
                      status_fn=None) -> list[dict]:
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
                    if cat in ("", "Core", "Dates"):
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

                if not item_last:
                    lines.append(i_cont.rstrip())

        if not sec_last:
            lines.append("│")
            lines.append("│")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

# ---------------------------------------------------------------------------
# UI — Fields dialog
# ---------------------------------------------------------------------------

class FieldsDialog(ctk.CTkToplevel):
    def __init__(self, parent, current: frozenset, on_apply):
        super().__init__(parent)
        self.title("Output Fields")
        self.resizable(False, False)
        self._on_apply = on_apply
        self._vars: dict[tuple, tk.BooleanVar] = {}
        self._build(current)
        self.after(50,  self.lift)
        self.after(100, self.grab_set)

    def _build(self, current: frozenset):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        cats: dict[str, list] = {}
        for g, n, label, _, cat in FIELD_DEFS:
            if not cat:
                continue
            cats.setdefault(cat, []).append((g, n, label))

        cat_order = ["Core", "Dates", "Timecode", "Technical", "Production"]
        col = 0
        for cat in cat_order:
            if cat not in cats:
                continue
            frame = ctk.CTkFrame(outer)
            frame.grid(row=0, column=col, sticky="nw", padx=6, pady=4)
            ctk.CTkLabel(frame, text=cat,
                         font=ctk.CTkFont(weight="bold")).pack(
                anchor="w", padx=10, pady=(10, 4))
            for g, n, label in cats[cat]:
                var = tk.BooleanVar(value=(g, n) in current)
                self._vars[(g, n)] = var
                ctk.CTkCheckBox(frame, text=label, variable=var,
                                onvalue=True, offvalue=False).pack(
                    anchor="w", padx=10, pady=2)
            ctk.CTkFrame(frame, height=10, fg_color="transparent").pack()
            col += 1

        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.grid(row=1, column=0, columnspan=col, sticky="ew", pady=(12, 0))

        ctk.CTkButton(btn_row, text="Reset to Defaults", width=140,
                      fg_color="transparent", border_width=1,
                      command=self._reset).pack(side="left")
        ctk.CTkButton(btn_row, text="Apply", width=90,
                      command=self._apply).pack(side="right")
        ctk.CTkButton(btn_row, text="Save as Defaults", width=140,
                      command=self._save_defaults).pack(side="right", padx=(0, 6))

    def _current_selection(self) -> frozenset:
        return frozenset(k for k, v in self._vars.items() if v.get())

    def _reset(self):
        for (g, n), var in self._vars.items():
            var.set((g, n) in DEFAULT_FIELDS)

    def _save_defaults(self):
        sel = self._current_selection()
        cfg = load_config()
        cfg["default_fields"] = [[g, n] for g, n in sel]
        save_config(cfg)
        self._on_apply(sel)
        self.destroy()

    def _apply(self):
        self._on_apply(self._current_selection())
        self.destroy()

# ---------------------------------------------------------------------------
# UI — Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, cfg: dict, on_save):
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self._cfg    = cfg
        self._on_save = on_save
        self._build()
        self.after(50,  self.lift)
        self.after(100, self.grab_set)

    def _build(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=28, pady=28)

        ctk.CTkLabel(outer, text="Connection Settings",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", pady=(0, 20))

        def labeled_entry(label, default="", show=""):
            ctk.CTkLabel(outer, text=label, anchor="w").pack(fill="x")
            var = tk.StringVar(value=default)
            ctk.CTkEntry(outer, textvariable=var, width=340, show=show).pack(
                fill="x", pady=(2, 12))
            return var

        self.v_server    = labeled_entry("Server (IP or hostname)",
                                         self._cfg.get("server", ""))
        self.v_workgroup = labeled_entry("Workgroup name",
                                         self._cfg.get("workgroup", "AvidWorkgroup"))
        self.v_user      = labeled_entry("Username", self._cfg.get("username", ""))

        ctk.CTkLabel(outer, text="Password", anchor="w").pack(fill="x")
        self.v_pass = tk.StringVar(value=load_password(self._cfg.get("username", "")))
        ctk.CTkEntry(outer, textvariable=self.v_pass, width=340, show="•").pack(
            fill="x", pady=(2, 12))

        self.lbl_status = ctk.CTkLabel(outer, text="", text_color="gray",
                                        wraplength=340, anchor="w")
        self.lbl_status.pack(fill="x", pady=(4, 12))

        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="Test Connection", width=140,
                      fg_color="transparent", border_width=1,
                      command=self._test).pack(side="left")
        ctk.CTkButton(btn_row, text="Save", width=100,
                      command=self._save).pack(side="right")

    def _test(self):
        self.lbl_status.configure(text="Testing…", text_color="gray")
        self.update_idletasks()
        server = self.v_server.get().strip()
        user   = self.v_user.get().strip()
        pw     = self.v_pass.get()
        wg     = self.v_workgroup.get().strip() or "AvidWorkgroup"

        def work():
            try:
                client = InterplayClient(server, user, pw)
                client.get_children(f"interplay://{wg}/",
                                    folders=True, files=False, mobs=False)
                self.after(0, lambda: self.lbl_status.configure(
                    text="Connected successfully.", text_color="green"))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self.lbl_status.configure(
                    text=f"Failed: {m}", text_color="red"))

        threading.Thread(target=work, daemon=True).start()

    def _save(self):
        username = self.v_user.get().strip()
        new_cfg = {
            **self._cfg,
            "server":    self.v_server.get().strip(),
            "workgroup": self.v_workgroup.get().strip() or "AvidWorkgroup",
            "username":  username,
        }
        save_config(new_cfg)
        save_password(username, self.v_pass.get())
        self._on_save(new_cfg)
        self.destroy()

# ---------------------------------------------------------------------------
# UI — Onboarding view (first-run)
# ---------------------------------------------------------------------------

class OnboardingView(ctk.CTkFrame):
    def __init__(self, parent, on_complete):
        super().__init__(parent, fg_color="transparent")
        self._on_complete = on_complete
        self._build()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(self, width=420, corner_radius=16)
        card.grid(row=0, column=0, padx=40, pady=40)
        card.grid_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=36, pady=36)

        ctk.CTkLabel(inner, text="MediaCentral Explorer",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(0, 6))
        ctk.CTkLabel(inner, text="Connect to your Avid MediaCentral workgroup",
                     text_color="gray").pack(pady=(0, 28))

        def labeled_entry(label, default="", show=""):
            ctk.CTkLabel(inner, text=label, anchor="w").pack(fill="x")
            var = tk.StringVar(value=default)
            ctk.CTkEntry(inner, textvariable=var, show=show).pack(
                fill="x", pady=(2, 12))
            return var

        self.v_server    = labeled_entry("Server (IP or hostname)")
        self.v_workgroup = labeled_entry("Workgroup name", "AvidWorkgroup")
        self.v_user      = labeled_entry("Username")
        self.v_pass      = labeled_entry("Password", show="•")

        self.lbl_status = ctk.CTkLabel(inner, text="", text_color="gray",
                                        wraplength=340, anchor="w")
        self.lbl_status.pack(fill="x", pady=(4, 12))

        ctk.CTkButton(inner, text="Test Connection",
                      fg_color="transparent", border_width=1,
                      command=self._test).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(inner, text="Get Started",
                      command=self._save).pack(fill="x")

    def _test(self):
        self.lbl_status.configure(text="Testing…", text_color="gray")
        self.update_idletasks()
        server = self.v_server.get().strip()
        user   = self.v_user.get().strip()
        pw     = self.v_pass.get()
        wg     = self.v_workgroup.get().strip() or "AvidWorkgroup"

        def work():
            try:
                client = InterplayClient(server, user, pw)
                client.get_children(f"interplay://{wg}/",
                                    folders=True, files=False, mobs=False)
                self.after(0, lambda: self.lbl_status.configure(
                    text="Connected successfully.", text_color="green"))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self.lbl_status.configure(
                    text=f"Failed: {m}", text_color="red"))

        threading.Thread(target=work, daemon=True).start()

    def _save(self):
        server = self.v_server.get().strip()
        user   = self.v_user.get().strip()
        if not server or not user:
            self.lbl_status.configure(
                text="Server and username are required.", text_color="orange")
            return
        cfg = {
            "server":    server,
            "workgroup": self.v_workgroup.get().strip() or "AvidWorkgroup",
            "username":  user,
        }
        save_config(cfg)
        save_password(user, self.v_pass.get())
        self._on_complete(cfg)

# ---------------------------------------------------------------------------
# UI — Navigation panel (left sidebar folder browser)
# ---------------------------------------------------------------------------

class NavPanel(ctk.CTkFrame):
    def __init__(self, parent, on_load_project):
        super().__init__(parent, width=280, corner_radius=0)
        self.pack_propagate(False)
        self._on_load       = on_load_project
        self._client: InterplayClient | None = None
        self._cfg:    dict = {}
        self._stack:  list[tuple[str, str]] = []   # (display_name, uri)
        self._items:  list[dict] = []
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._render_list())
        self._build()

    def _build(self):
        # Back + breadcrumb row
        nav_row = ctk.CTkFrame(self, fg_color="transparent")
        nav_row.pack(fill="x", padx=8, pady=(12, 0))

        self._btn_back = ctk.CTkButton(
            nav_row, text="← Back", width=72, height=28,
            fg_color="transparent", border_width=1,
            state="disabled", command=self._go_back)
        self._btn_back.pack(side="left")

        self._lbl_crumb = ctk.CTkLabel(
            nav_row, text="", anchor="w", text_color="gray",
            font=ctk.CTkFont(size=11), wraplength=170)
        self._lbl_crumb.pack(side="left", padx=(8, 0))

        # Filter
        ctk.CTkEntry(self, textvariable=self._filter_var,
                     placeholder_text="Filter…",
                     height=32).pack(fill="x", padx=8, pady=8)

        # Scrollable list
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Hint label (shown while empty / loading)
        self._lbl_hint = ctk.CTkLabel(
            self._scroll, text="",
            text_color="gray", font=ctk.CTkFont(size=12),
            wraplength=240)
        self._lbl_hint.pack(pady=20)

        # Status bar at bottom of panel
        self._lbl_status = ctk.CTkLabel(
            self, text="", text_color="gray",
            font=ctk.CTkFont(size=11), anchor="w")
        self._lbl_status.pack(fill="x", padx=10, pady=(0, 8))

    # ── Public ────────────────────────────────────────────────────────────────

    def connect(self, client: InterplayClient, cfg: dict):
        self._client = client
        self._cfg    = cfg
        wg           = cfg.get("workgroup", "AvidWorkgroup")
        root_uri     = f"interplay://{wg}/"
        self._stack  = [("Root", root_uri)]
        self._load_level(root_uri)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _load_level(self, uri: str):
        self._set_status("Loading…")
        self._lbl_hint.configure(text="Loading…")
        self._clear_list()
        client = self._client

        def work():
            try:
                items = client.get_children(uri, folders=True, files=False, mobs=False)
                self.after(0, lambda i=items: self._level_done(i))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self._load_error(m))

        threading.Thread(target=work, daemon=True).start()

    def _level_done(self, items: list[dict]):
        self._items = sorted(items, key=lambda a: natural_key(a["name"]))
        self._render_list()
        n = len(self._items)
        self._set_status(f"{n} item{'s' if n != 1 else ''}")
        # Update breadcrumb (skip the root sentinel)
        crumb = " › ".join(name for name, _ in self._stack[1:])
        self._lbl_crumb.configure(text=crumb)
        self._btn_back.configure(
            state="normal" if len(self._stack) > 1 else "disabled")

    def _load_error(self, msg: str):
        self._lbl_hint.configure(text=f"Error: {msg}")
        self._set_status("Error")

    def _render_list(self):
        self._clear_list()
        q = self._filter_var.get().lower()
        visible = [i for i in self._items
                   if not q or q in i["name"].lower()]

        if not visible:
            hint = "No items match." if q else "Empty."
            self._lbl_hint.configure(text=hint)
            self._lbl_hint.pack(pady=20)
            return

        self._lbl_hint.pack_forget()
        for item in visible:
            btn = ctk.CTkButton(
                self._scroll,
                text=item["name"],
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray85", "gray25"),
                height=34,
                command=lambda i=item: self._navigate(i))
            btn.pack(fill="x", pady=1)
            btn.bind("<Double-1>", lambda e, i=item: self._load_as_project(i))

    def _clear_list(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._lbl_hint = ctk.CTkLabel(
            self._scroll, text="",
            text_color="gray", font=ctk.CTkFont(size=12),
            wraplength=240)

    def _navigate(self, item: dict):
        self._stack.append((item["name"], item["uri"]))
        self._load_level(item["uri"])

    def _load_as_project(self, item: dict):
        self._on_load(item["name"], item["uri"], self._client)

    def _go_back(self):
        if len(self._stack) > 1:
            self._stack.pop()
            _, uri = self._stack[-1]
            self._load_level(uri)

    def _set_status(self, msg: str):
        self._lbl_status.configure(text=msg)

# ---------------------------------------------------------------------------
# UI — Detail panel (right: output + actions)
# ---------------------------------------------------------------------------

class DetailPanel(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._last_output   = ""
        self._last_project  = ""
        self._last_sections: list[dict] = []
        self._active_fields = DEFAULT_FIELDS
        self._loading       = False
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Top bar ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

        self._lbl_project = ctk.CTkLabel(
            top, text="No project loaded",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
        self._lbl_project.pack(side="left", fill="x", expand=True)

        self._btn_fields = ctk.CTkButton(
            top, text="Fields…", width=90,
            fg_color="transparent", border_width=1,
            command=self._open_fields)
        self._btn_export = ctk.CTkButton(
            top, text="Save…", width=80,
            state="disabled", command=self._export)
        self._btn_email  = ctk.CTkButton(
            top, text="Email", width=80,
            state="disabled", command=self._email)
        self._btn_copy   = ctk.CTkButton(
            top, text="Copy", width=80,
            state="disabled", command=self._copy)

        for btn in (self._btn_export, self._btn_email,
                    self._btn_copy, self._btn_fields):
            btn.pack(side="right", padx=(6, 0))

        # ── Text output ───────────────────────────────────────────────────────
        self._txt = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Courier New", size=10),
            wrap="none",
            state="disabled",
            corner_radius=6)
        self._txt.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 4))

        # ── Status bar ────────────────────────────────────────────────────────
        self._lbl_status = ctk.CTkLabel(
            self, text="Select a project from the panel on the left.",
            anchor="w", text_color="gray", font=ctk.CTkFont(size=11))
        self._lbl_status.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_status(self, msg: str):
        self._lbl_status.configure(text=msg)

    def set_active_fields(self, fields: frozenset):
        self._active_fields = fields

    def start_loading(self, project_name: str):
        self._loading = True
        self._lbl_project.configure(text=f"{project_name}  —  loading…")
        self._set_output("")
        self._set_action_btns(False)
        self.set_status(f"Loading '{project_name}'…")

    def load_done(self, output: str, name: str, sections: list[dict]):
        self._loading       = False
        self._last_sections = sections
        self._last_project  = name
        self._lbl_project.configure(text=name)
        self._set_output(output)
        self._set_action_btns(True)
        n = sum(len(s["items"]) for s in sections)
        self.set_status(f"Loaded '{name}' — {n} item(s).")

    def load_error(self, msg: str):
        self._loading = False
        self._lbl_project.configure(text="Load failed")
        self.set_status(f"Error: {msg}")
        messagebox.showerror("Load Error", msg, parent=self.winfo_toplevel())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _set_output(self, text: str):
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        if text:
            self._txt.insert("end", text)
        self._txt.configure(state="disabled")
        self._last_output = text

    def _set_action_btns(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for btn in (self._btn_copy, self._btn_email, self._btn_export):
            btn.configure(state=state)

    def _rerender(self):
        if self._last_sections and self._last_project:
            text = format_project(self._last_project,
                                  self._last_sections,
                                  self._active_fields)
            self._set_output(text)

    def _open_fields(self):
        def on_apply(sel: frozenset):
            self._active_fields = sel
            self._rerender()
            self.set_status(f"Fields updated ({len(sel)} selected).")
        FieldsDialog(self.winfo_toplevel(), self._active_fields, on_apply)

    def _copy(self):
        root = self.winfo_toplevel()
        root.clipboard_clear()
        root.clipboard_append(self._last_output)
        self.set_status("Copied to clipboard.")

    def _export(self):
        if not self._last_output.strip():
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=(f"{self._last_project}.txt"
                         if self._last_project else "export.txt"),
            parent=self.winfo_toplevel())
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._last_output)
            self.set_status(f"Saved → {path}")

    def _email(self):
        subject = urllib.parse.quote(f"Interplay Project: {self._last_project}")
        body    = urllib.parse.quote(self._last_output)
        webbrowser.open(f"mailto:?subject={subject}&body={body}")
        self.set_status("Opening email client…")

# ---------------------------------------------------------------------------
# UI — Main application window
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MediaCentral Explorer")
        self.geometry("1100x700")
        self.minsize(800, 520)

        self._cfg          = load_config()
        self._current_view: ctk.CTkFrame | None = None

        self._platform_setup()

        if self._cfg.get("server"):
            self._show_main()
        else:
            self._show_onboarding()

    # ── Platform integration ──────────────────────────────────────────────────

    def _platform_setup(self):
        if sys.platform == "darwin":
            self._setup_mac_menu()
        elif sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "com.markbattistella.mcexplorer")
            except Exception:
                pass

    def _setup_mac_menu(self):
        menubar = tk.Menu(self)

        # "apple" is the special name for the macOS application menu
        app_menu = tk.Menu(menubar, name="apple")
        menubar.add_cascade(menu=app_menu)
        app_menu.add_command(label="About MediaCentral Explorer",
                             command=self._show_about)
        app_menu.add_separator()
        app_menu.add_command(label="Settings…", command=self._open_settings)

        # Standard Window menu
        window_menu = tk.Menu(menubar, name="window")
        menubar.add_cascade(label="Window", menu=window_menu)

        self.configure(menu=menubar)

        # Hook system-level commands so our handlers run instead of defaults
        self.createcommand("tk::mac::ShowAbout", self._show_about)
        self.createcommand("tk::mac::Quit",      self.quit)

    def _show_about(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("About")
        dlg.resizable(False, False)

        frame = ctk.CTkFrame(dlg, fg_color="transparent")
        frame.pack(padx=40, pady=36)

        ctk.CTkLabel(frame, text="MediaCentral Explorer",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(0, 4))
        ctk.CTkLabel(frame, text=f"Version {__version__}",
                     text_color="gray").pack(pady=(0, 20))

        ctk.CTkLabel(frame, text="Mark Battistella",
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        ctk.CTkLabel(frame, text="markbattistella.com",
                     text_color="gray").pack(pady=(2, 20))

        ctk.CTkLabel(frame,
                     text=f"© 2010–{datetime.now().year} Mark Battistella.\nAll rights reserved.",
                     text_color="gray", font=ctk.CTkFont(size=11),
                     justify="center").pack(pady=(0, 20))

        ctk.CTkButton(frame, text="Close", width=100,
                      command=dlg.destroy).pack()

        dlg.after(50,  dlg.lift)
        dlg.after(100, dlg.grab_set)

    # ── View switching ────────────────────────────────────────────────────────

    def _show_onboarding(self):
        if self._current_view:
            self._current_view.destroy()
        self._current_view = OnboardingView(self, self._onboarding_complete)
        self._current_view.pack(fill="both", expand=True)

    def _onboarding_complete(self, cfg: dict):
        self._cfg = cfg
        self._show_main()

    def _show_main(self):
        if self._current_view:
            self._current_view.destroy()

        root_frame = ctk.CTkFrame(self, fg_color="transparent")
        root_frame.pack(fill="both", expand=True)
        self._current_view = root_frame

        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(root_frame, height=48, corner_radius=0,
                               fg_color=("gray90", "gray15"))
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="MediaCentral Explorer",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(
            side="left", padx=16)
        ctk.CTkButton(
            header, text="⚙", width=40, height=36,
            fg_color="transparent",
            font=ctk.CTkFont(size=17),
            command=self._open_settings).pack(side="right", padx=8, pady=6)

        # ── Divider under header ───────────────────────────────────────────────
        ctk.CTkFrame(root_frame, height=1,
                     fg_color=("gray80", "gray30")).pack(side="top", fill="x")

        # ── Content area ──────────────────────────────────────────────────────
        content = ctk.CTkFrame(root_frame, fg_color="transparent")
        content.pack(side="top", fill="both", expand=True)

        # Nav panel (fixed width left sidebar)
        self._nav = NavPanel(content, self._load_project)
        self._nav.pack(side="left", fill="y")

        # Vertical divider between nav and detail
        ctk.CTkFrame(content, width=1,
                     fg_color=("gray80", "gray30")).pack(side="left", fill="y")

        # Detail panel (fills remaining space)
        self._detail = DetailPanel(content)
        self._detail.pack(side="left", fill="both", expand=True)

        # Restore saved field preferences
        saved = self._cfg.get("default_fields")
        if saved:
            self._detail.set_active_fields(frozenset(tuple(x) for x in saved))

        # Connect nav panel using saved credentials
        self._reconnect()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        if not hasattr(self, "_nav"):
            return
        def on_save(new_cfg: dict):
            self._cfg = new_cfg
            self._reconnect()
        SettingsDialog(self, self._cfg, on_save)

    def _reconnect(self):
        try:
            client = self._make_client()
        except ValueError:
            return
        self._nav.connect(client, self._cfg)

    def _make_client(self) -> InterplayClient:
        server = self._cfg.get("server", "").strip()
        user   = self._cfg.get("username", "").strip()
        pw     = load_password(user)
        if not server:
            raise ValueError("No server configured.")
        if not user:
            raise ValueError("No username configured.")
        return InterplayClient(server, user, pw)

    # ── Project loading ───────────────────────────────────────────────────────

    def _load_project(self, name: str, uri: str, client: InterplayClient):
        self._detail.start_loading(name)

        def work():
            try:
                def sf(msg):
                    self.after(0, lambda m=msg: self._detail.set_status(m))
                sections = load_project_data(client, uri, status_fn=sf)
                output   = format_project(name, sections, self._detail._active_fields)
                self.after(0, lambda o=output, n=name, s=sections:
                           self._detail.load_done(o, n, s))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda m=msg: self._detail.load_error(m))

        threading.Thread(target=work, daemon=True).start()

# ---------------------------------------------------------------------------
# CLI entry point
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
    parser.add_argument("--raw-xml", action="store_true",
                        help="Dump raw SOAP XML for the first bin and exit")
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
            if args.debug:
                print(f"    type : {p.get('type', '(empty)')}")
                print(f"    uri  : {p['uri']}")
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
        print("Available projects:")
        for p in sorted(projects, key=lambda x: natural_key(x["name"])):
            print(f"  {p['name']}")
        sys.exit(1)

    proj = matches[0]
    if len(matches) > 1:
        print(f"Multiple matches — using: {proj['name']}")

    if args.fields:
        active = frozenset(tuple(f.split(".", 1)) for f in args.fields if "." in f)
    else:
        active = DEFAULT_FIELDS

    if getattr(args, "raw_xml", False):
        import xml.dom.minidom
        print(f"Fetching children of project URI: {proj['uri']}")
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
        uri  = target["uri"]
        body = (f"<types:GetChildren>"
                f"<types:InterplayURI>{html_lib.escape(uri)}</types:InterplayURI>"
                f"<types:IncludeFolders>false</types:IncludeFolders>"
                f"<types:IncludeFiles>true</types:IncludeFiles>"
                f"<types:IncludeMOBs>true</types:IncludeMOBs>"
                f"<types:ReturnAttributes>{ra}</types:ReturnAttributes>"
                f"</types:GetChildren>")
        raw = client._post(client._envelope(body))
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
    if len(sys.argv) > 1:
        _cli()
    else:
        app = App()
        app.mainloop()
