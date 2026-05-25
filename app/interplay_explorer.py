#!/usr/bin/env python3
"""
Avid Interplay Project Explorer
Browse and export project data via Avid Interplay Web Services (SOAP).
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import requests
import xml.etree.ElementTree as ET
import threading
import html as html_lib

# ---------------------------------------------------------------------------
# SOAP / Interplay constants
# ---------------------------------------------------------------------------

SOAP_NS  = "http://schemas.xmlsoap.org/soap/envelope/"
TYPES_NS = "http://avid.com/interplay/ws/assets/types"

RETURN_ATTRS = [
    ("Asset",  "Name"),
    ("Asset",  "Type"),
    ("System", "Duration"),
    ("System", "StartTimecode"),
    ("System", "CreatedBy"),
    ("System", "CreationDate"),
    ("System", "ModifiedBy"),
    ("System", "ModifyDate"),
    ("System", "Resolution"),
    ("System", "Tracks"),
]

FOLDER_TYPES = {"folder", "bin", ""}  # Asset.Type values that mean "folder"

# ---------------------------------------------------------------------------
# Interplay SOAP client
# ---------------------------------------------------------------------------

class InterplayClient:
    def __init__(self, server: str, username: str, password: str):
        self.username = username
        self.password = password

        server = server.strip()
        if not server.startswith(("http://", "https://")):
            server = f"http://{server}"
        self.assets_url = server.rstrip("/") + "/services/Assets"

    # ---- XML helpers -------------------------------------------------------

    def _creds_header(self) -> str:
        u = html_lib.escape(self.username)
        p = html_lib.escape(self.password)
        return (
            f'<types:UserCredentials xmlns:types="{TYPES_NS}">'
            f"<types:Username>{u}</types:Username>"
            f"<types:Password>{p}</types:Password>"
            f"</types:UserCredentials>"
        )

    def _envelope(self, body: str) -> str:
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" xmlns:types="{TYPES_NS}">'
            f"<soapenv:Header>{self._creds_header()}</soapenv:Header>"
            f"<soapenv:Body>{body}</soapenv:Body>"
            f"</soapenv:Envelope>"
        )

    def _post(self, envelope: str) -> str:
        headers = {
            "Content-Type": "text/xml; charset=UTF-8",
            "SOAPAction": '""',
        }
        resp = requests.post(
            self.assets_url,
            data=envelope.encode("utf-8"),
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text

    # ---- Response parsing --------------------------------------------------

    @staticmethod
    def _check_soap_error(root: ET.Element):
        fault = root.find(f".//{{{SOAP_NS}}}Fault")
        if fault is not None:
            msg_elem = fault.find("faultstring")
            msg = msg_elem.text if msg_elem is not None else "Unknown SOAP fault"
            raise RuntimeError(f"SOAP Fault: {msg}")

        errors = root.findall(f".//{{{TYPES_NS}}}Error")
        if errors:
            msgs = []
            for e in errors:
                m = e.find(f"{{{TYPES_NS}}}Message")
                if m is not None and m.text:
                    msgs.append(m.text)
            if msgs:
                raise RuntimeError(f"Interplay error: {'; '.join(msgs)}")

    @staticmethod
    def _parse_assets(xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        InterplayClient._check_soap_error(root)

        assets = []
        for desc in root.iter(f"{{{TYPES_NS}}}AssetDescription"):
            uri_el = desc.find(f"{{{TYPES_NS}}}InterplayURI")
            uri = (uri_el.text or "").strip() if uri_el is not None else ""

            attrs: dict[str, str] = {}
            for attr in desc.findall(f".//{{{TYPES_NS}}}Attribute"):
                key = f"{attr.get('Group','')}.{attr.get('Name','')}"
                attrs[key] = (attr.text or "").strip()

            name = attrs.get("Asset.Name") or uri.rstrip("/").rsplit("/", 1)[-1]
            asset_type = attrs.get("Asset.Type", "").lower()

            assets.append({
                "uri":           uri,
                "name":          name,
                "type":          asset_type,
                "duration":      attrs.get("System.Duration", ""),
                "start_tc":      attrs.get("System.StartTimecode", ""),
                "created_by":    attrs.get("System.CreatedBy", ""),
                "creation_date": attrs.get("System.CreationDate", ""),
                "resolution":    attrs.get("System.Resolution", ""),
                "attrs":         attrs,
            })

        return assets

    # ---- Public API --------------------------------------------------------

    def get_children(
        self,
        uri: str,
        include_folders: bool = True,
        include_files:   bool = True,
        include_mobs:    bool = True,
    ) -> list[dict]:
        escaped_uri = html_lib.escape(uri)
        return_attrs_xml = "".join(
            f'<types:Attribute Group="{g}" Name="{n}"/>'
            for g, n in RETURN_ATTRS
        )
        body = (
            f"<types:GetChildren>"
            f"<types:InterplayURI>{escaped_uri}</types:InterplayURI>"
            f"<types:IncludeFolders>{'true' if include_folders else 'false'}</types:IncludeFolders>"
            f"<types:IncludeFiles>{'true' if include_files else 'false'}</types:IncludeFiles>"
            f"<types:IncludeMOBs>{'true' if include_mobs else 'false'}</types:IncludeMOBs>"
            f"<types:ReturnAttributes>{return_attrs_xml}</types:ReturnAttributes>"
            f"</types:GetChildren>"
        )
        return self._parse_assets(self._post(self._envelope(body)))


# ---------------------------------------------------------------------------
# Project loading (recursive)
# ---------------------------------------------------------------------------

def load_project(
    client: InterplayClient,
    uri: str,
    lines: list[str],
    depth: int = 0,
    max_depth: int = 10,
    status_fn=None,
):
    """Recursively fetch children and build text lines."""
    if depth > max_depth:
        lines.append("  " * depth + "  [max depth reached]")
        return

    assets = client.get_children(uri)
    indent = "  " * depth

    for asset in assets:
        name     = asset["name"]
        duration = asset["duration"]
        creator  = asset["created_by"]
        a_type   = asset["type"]

        # Build display line
        parts = [f"{indent}{name}"]
        if duration:
            parts.append(f"({duration})")
        if creator:
            parts.append(f"- Created by {creator}")
        lines.append(" ".join(parts))

        # Recurse into folders / bins
        if a_type in FOLDER_TYPES:
            if status_fn:
                status_fn(f"Loading '{name}'…")
            load_project(client, asset["uri"], lines, depth + 1, max_depth, status_fn)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Interplay Project Explorer")
        self.geometry("1200x730")
        self.minsize(900, 580)
        self._projects: list[dict] = []
        self._build_ui()

    # ---- UI construction ---------------------------------------------------

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Connection bar ──────────────────────────────────────────────────
        conn = ttk.LabelFrame(self, text="Interplay Connection", padding=8)
        conn.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        conn.columnconfigure(5, weight=1)

        # Row 0: credentials
        ttk.Label(conn, text="Username:").grid(row=0, column=0, sticky="w")
        self.v_user = tk.StringVar()
        ttk.Entry(conn, textvariable=self.v_user, width=20).grid(
            row=0, column=1, sticky="w", padx=(4, 20))

        ttk.Label(conn, text="Password:").grid(row=0, column=2, sticky="w")
        self.v_pass = tk.StringVar()
        ttk.Entry(conn, textvariable=self.v_pass, width=20, show="•").grid(
            row=0, column=3, sticky="w", padx=(4, 0))

        # Row 1: server + path + search button
        ttk.Label(conn, text="Server:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.v_server = tk.StringVar()
        ttk.Entry(conn, textvariable=self.v_server, width=26).grid(
            row=1, column=1, sticky="w", padx=(4, 20), pady=(6, 0))

        ttk.Label(conn, text="Interplay Path:").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.v_path = tk.StringVar(value="interplay://AvidWorkgroup/Projects/")
        ttk.Entry(conn, textvariable=self.v_path, width=46).grid(
            row=1, column=3, columnspan=2, sticky="ew", padx=(4, 8), pady=(6, 0))

        self.btn_search = ttk.Button(conn, text="Search", command=self._on_search)
        self.btn_search.grid(row=1, column=5, sticky="e", pady=(6, 0))

        # ── Content area ────────────────────────────────────────────────────
        content = ttk.Frame(self)
        content.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        # Left pane – project list
        left = ttk.LabelFrame(content, text="Projects", padding=4)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            left, columns=("name", "uri"), show="headings",
            selectmode="browse", height=24,
        )
        self.tree.heading("name", text="Project", anchor="w")
        self.tree.heading("uri",  text="URI",     anchor="w")
        self.tree.column("name", width=200, stretch=True)
        self.tree.column("uri",  width=180, stretch=True)

        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", lambda _: self._on_load())

        self.btn_load = ttk.Button(
            left, text="Load Project", state=tk.DISABLED, command=self._on_load)
        self.btn_load.grid(row=1, column=0, columnspan=2, sticky="e", pady=(6, 0))

        # Right pane – output
        right = ttk.LabelFrame(content, text="Project Files", padding=4)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        bar = ttk.Frame(right)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        bar.columnconfigure(1, weight=1)

        ttk.Label(bar, text="Project:").grid(row=0, column=0, sticky="w")
        self.lbl_project = ttk.Label(bar, text="", foreground="#666")
        self.lbl_project.grid(row=0, column=1, sticky="w", padx=(4, 0))

        self.btn_copy = ttk.Button(
            bar, text="Copy to Clipboard", state=tk.DISABLED, command=self._copy)
        self.btn_copy.grid(row=0, column=2, padx=(4, 0))
        self.btn_export = ttk.Button(
            bar, text="Export to txt…", state=tk.DISABLED, command=self._export)
        self.btn_export.grid(row=0, column=3, padx=(4, 0))

        self.output = scrolledtext.ScrolledText(
            right, font=("Courier New", 10), state=tk.DISABLED, wrap=tk.NONE)
        self.output.grid(row=1, column=0, sticky="nsew")

        # Horizontal scrollbar for output
        hbar = ttk.Scrollbar(right, orient="horizontal", command=self.output.xview)
        self.output.configure(xscrollcommand=hbar.set)
        hbar.grid(row=2, column=0, sticky="ew")

        # ── Status bar ──────────────────────────────────────────────────────
        self.v_status = tk.StringVar(
            value="Enter connection details above, then click Search.")
        ttk.Label(
            self, textvariable=self.v_status,
            relief="sunken", anchor="w", padding=(6, 2),
        ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 6))

    # ---- Helpers -----------------------------------------------------------

    def _status(self, msg: str):
        self.v_status.set(msg)
        self.update_idletasks()

    def _set_output(self, text: str):
        self.output.configure(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        if text:
            self.output.insert(tk.END, text)
        self.output.configure(state=tk.DISABLED)

    def _get_output(self) -> str:
        self.output.configure(state=tk.NORMAL)
        t = self.output.get("1.0", tk.END)
        self.output.configure(state=tk.DISABLED)
        return t

    def _make_client(self) -> InterplayClient:
        server = self.v_server.get().strip()
        user   = self.v_user.get().strip()
        pw     = self.v_pass.get()
        if not server:
            raise ValueError("Server address is required.")
        if not user:
            raise ValueError("Username is required.")
        return InterplayClient(server, user, pw)

    def _set_buttons(self, search=None, load=None, output_btns=None):
        def _state(val):
            return tk.NORMAL if val else tk.DISABLED
        if search is not None:
            self.btn_search.configure(state=_state(search))
        if load is not None:
            self.btn_load.configure(state=_state(load))
        if output_btns is not None:
            self.btn_export.configure(state=_state(output_btns))
            self.btn_copy.configure(state=_state(output_btns))

    # ---- Search ------------------------------------------------------------

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

        self._set_buttons(search=False)
        self._status("Connecting and searching…")

        def work():
            try:
                assets = client.get_children(
                    path, include_folders=True,
                    include_files=False, include_mobs=False)
                self.after(0, lambda a=assets: self._show_projects(a))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._search_error(e))

        threading.Thread(target=work, daemon=True).start()

    def _show_projects(self, assets: list[dict]):
        self._projects = assets
        self.tree.delete(*self.tree.get_children())
        for a in assets:
            self.tree.insert("", tk.END, values=(a["name"], a["uri"]))
        self._set_buttons(search=True)
        self._status(
            f"Found {len(assets)} project(s). Select one and click Load Project.")

    def _search_error(self, msg: str):
        self._set_buttons(search=True)
        self._status(f"Search failed: {msg}")
        messagebox.showerror("Search Error", msg)

    # ---- Tree selection ----------------------------------------------------

    def _on_tree_select(self, _event=None):
        has_sel = bool(self.tree.selection())
        self._set_buttons(load=has_sel)

    # ---- Load project ------------------------------------------------------

    def _on_load(self):
        sel = self.tree.selection()
        if not sel:
            return

        item_vals = self.tree.item(sel[0])["values"]
        project_name, project_uri = item_vals[0], item_vals[1]

        try:
            client = self._make_client()
        except ValueError as e:
            messagebox.showwarning("Error", str(e))
            return

        self._set_buttons(load=False, output_btns=False)
        self.lbl_project.configure(text=project_name)
        self._set_output("")
        self._status(f"Loading '{project_name}'…")

        def work():
            lines: list[str] = [project_name]
            try:
                def _sf(msg):
                    self.after(0, lambda m=msg: self._status(m))

                load_project(client, project_uri, lines, depth=1, status_fn=_sf)
                output = "\n".join(lines)
                self.after(0, lambda o=output, n=project_name: self._load_done(o, n))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._load_error(e))

        threading.Thread(target=work, daemon=True).start()

    def _load_done(self, output: str, name: str):
        self._set_output(output)
        self._set_buttons(load=True, output_btns=True)
        count = max(0, output.count("\n"))
        self._status(f"Loaded '{name}' — {count} item(s).")

    def _load_error(self, msg: str):
        self._set_buttons(load=True)
        self._status(f"Load failed: {msg}")
        messagebox.showerror("Load Error", msg)

    # ---- Export / clipboard ------------------------------------------------

    def _export(self):
        text = self._get_output()
        if not text.strip():
            messagebox.showinfo("Nothing to export", "Load a project first.")
            return
        project = self.lbl_project.cget("text")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"{project}.txt" if project else "export.txt",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self._status(f"Exported → {path}")

    def _copy(self):
        text = self._get_output()
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status("Copied to clipboard.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
