'use strict';

// ── Mock API (browser preview — not used inside pywebview) ────────────────
const _MOCK_TEXT = `\
PROJECT: 2026002 BRAVO
Date:    2026-05-26  10:30
────────────────────────────────────────────────────────────────────────

├── CAMERA RUSHES 2026-01-20  [3 items]
│   ├── A001C001 INTERVIEW WIDE       00:04:12:09   Online   MC
│   │   Created: jsmith 2026-01-20 08:14   |   Modified: jsmith 2026-01-20 08:14
│   │   Markers (3):
│   │     01:00:08:14  RED      jsmith: False start — ignore
│   │     01:00:45:02  GREEN    jsmith: Best answer — use this
│   │     01:03:21:18  YELLOW   jeditor: Check audio dropout here
│   │
│   ├── A001C002 INTERVIEW WIDE       00:02:58:22   Online   MC
│   │   Created: jsmith 2026-01-20 08:14   |   Modified: jsmith 2026-01-20 14:37
│   │
│   └── A002C001 INTERVIEW CU         00:06:01:11   Online   MC
│       Created: jsmith 2026-01-20 09:45   |   Modified: jeditor 2026-05-24 16:02
│       Markers (1):
│         01:02:14:00  CYAN     jeditor: Reaction shot — good cutaway
│
├── RAW AUDIO 2026-01-20  [2 items]
│   ├── INT LAV TRACK 1               00:12:58:00   Online   MC
│   │   Created: jsmith 2026-01-20 08:14   |   Modified: jsmith 2026-01-20 08:14
│   └── INT LAV TRACK 2               00:12:58:00   Online   MC
│       Created: jsmith 2026-01-20 08:14   |   Modified: jsmith 2026-01-20 08:14
│
└── SEQUENCES 2026-01-22  [2 items]
    ├── Assembly Edit v1              00:12:45:00   Online   SEQ
    │   Created: jeditor 2026-01-22 11:03   |   Modified: jeditor 2026-01-22 11:03
    │   Markers (2):
    │     00:00:00:00  WHITE    jeditor: Opening approved by director
    │     00:08:34:12  RED      jeditor: Needs colour grade — skin tones off
    └── Assembly Edit v2              00:11:28:14   Online   SEQ
        Created: jeditor 2026-01-22 11:03   |   Modified: jeditor 2026-05-25 09:51
`;

const _MOCK_TREE = {
  'interplay://AvidWorkgroup/': [
    { name: '2026001 ALPHA',   uri: 'interplay://AvidWorkgroup/Projects/2026/2026001 ALPHA' },
    { name: '2026002 BRAVO',   uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO' },
    { name: '2026003 CHARLIE', uri: 'interplay://AvidWorkgroup/Projects/2026/2026003 CHARLIE' },
    { name: '2026004 DELTA',   uri: 'interplay://AvidWorkgroup/Projects/2026/2026004 DELTA' },
    { name: '2026005 ECHO',    uri: 'interplay://AvidWorkgroup/Projects/2026/2026005 ECHO' },
    { name: '2025 Archive',    uri: 'interplay://AvidWorkgroup/Projects/2025' },
  ],
  // 2026001 ALPHA intentionally absent → leaf node (tests leaf detection)
  'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO': [
    { name: 'CAMERA RUSHES',   uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/CAMERA RUSHES' },
    { name: 'RAW AUDIO',       uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/RAW AUDIO' },
    { name: 'SEQUENCES',       uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/SEQUENCES' },
  ],
  'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/CAMERA RUSHES': [
    { name: 'DAY 01',          uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/CAMERA RUSHES/DAY 01' },
    { name: 'DAY 02',          uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/CAMERA RUSHES/DAY 02' },
    { name: 'DAY 03',          uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/CAMERA RUSHES/DAY 03' },
  ],
  // DAY 01 and DAY 03 are leaves; DAY 02 has sub-bins
  'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/CAMERA RUSHES/DAY 02': [
    { name: 'CAM A',           uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/CAMERA RUSHES/DAY 02/CAM A' },
    { name: 'CAM B',           uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/CAMERA RUSHES/DAY 02/CAM B' },
  ],
  'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/RAW AUDIO': [
    { name: 'DAY 01',          uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/RAW AUDIO/DAY 01' },
    { name: 'DAY 02',          uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/RAW AUDIO/DAY 02' },
  ],
  'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/SEQUENCES': [
    { name: 'ASSEMBLY',        uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/SEQUENCES/ASSEMBLY' },
    { name: 'FINE CUT',        uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/SEQUENCES/FINE CUT' },
    { name: 'DELIVERY',        uri: 'interplay://AvidWorkgroup/Projects/2026/2026002 BRAVO/SEQUENCES/DELIVERY' },
  ],
  'interplay://AvidWorkgroup/Projects/2026/2026003 CHARLIE': [
    { name: 'CAMERA RUSHES',   uri: 'interplay://AvidWorkgroup/Projects/2026/2026003 CHARLIE/CAMERA RUSHES' },
    { name: 'SEQUENCES',       uri: 'interplay://AvidWorkgroup/Projects/2026/2026003 CHARLIE/SEQUENCES' },
  ],
  // CHARLIE bins are leaves (no further children)
  'interplay://AvidWorkgroup/Projects/2025': [
    { name: '2025001 ALPHA',   uri: 'interplay://AvidWorkgroup/Projects/2025/2025001 ALPHA' },
    { name: '2025002 BRAVO',   uri: 'interplay://AvidWorkgroup/Projects/2025/2025002 BRAVO' },
    { name: '2025003 CHARLIE', uri: 'interplay://AvidWorkgroup/Projects/2025/2025003 CHARLIE' },
  ],
  'interplay://AvidWorkgroup/Projects/2025/2025002 BRAVO': [
    { name: 'CAMERA RUSHES',   uri: 'interplay://AvidWorkgroup/Projects/2025/2025002 BRAVO/CAMERA RUSHES' },
    { name: 'SEQUENCES',       uri: 'interplay://AvidWorkgroup/Projects/2025/2025002 BRAVO/SEQUENCES' },
  ],
};

const _DEFAULT_FIELDS = [
  ['System','Duration'], ['System','Media Status'],
  ['System','Created By'], ['System','Creation Date'],
  ['System','Modified By'], ['System','Modified Date'],
];

const _MOCK_API = {
  async get_version()                       { return 'dev'; },
  async get_config()                        { return { server: 'http://192.168.1.10:80', workgroup: 'AvidWorkgroup', username: 'jsmith', has_password: true, start_path: '', max_depth: 3, default_fields: _DEFAULT_FIELDS }; },
  async get_children(uri)                   { return _MOCK_TREE[uri] || []; },
  async load_project(name)                  { return { text: _MOCK_TEXT.replace('2026002 BRAVO', name), summary: '7 items loaded.' }; },
  async save_to_file()                      { alert('Save not available in preview mode.'); return { ok: false }; },
  async open_email()                        { return { ok: true }; },
  async test_connection()                   { return { ok: true, message: 'Connected successfully. (mock)' }; },
  async save_settings()                     { return { ok: true }; },
  async save_fields()                       { return { ok: true }; },
  async check_updates() {
    if (new URLSearchParams(window.location.search).has('update')) {
      return {
        available: true, tag: '2099.01.01', current: 'dev',
        notes: '## What\'s New\n\n- Added Markers support — fetch timecode markers per clip\n- Metadata Fields moved to a standalone toolbar panel\n- Fixed generate button layout jump during metadata generation\n- Copy, email, and save buttons now always visible\n\n## Fixes\n\n- Version stamping now picks up GitHub release tags correctly\n- Build workflow permissions fixed for release asset uploads',
      };
    }
    return { available: false, current: 'dev' };
  },
  async install_update_now()                { return { ok: false, error: 'Mock mode' }; },
  async queue_update()                      { return { ok: false, error: 'Mock mode' }; },
};

// ── Field group definitions (mirrors FIELD_DEFS in Python) ────────────────
const FIELD_GROUPS = [
  { label: 'Core', fields: [
    { key: 'System.Duration',     label: 'Duration' },
    { key: 'System.Media Status', label: 'Media Status' },
  ]},
  { label: 'Dates', fields: [
    { key: 'System.Created By',    label: 'Created By' },
    { key: 'System.Creation Date', label: 'Creation Date' },
    { key: 'System.Modified By',   label: 'Modified By' },
    { key: 'System.Modified Date', label: 'Modified Date' },
  ]},
  { label: 'Timecode', fields: [
    { key: 'System.Start', label: 'Start TC' },
    { key: 'System.End',   label: 'End TC' },
  ]},
  { label: 'Technical', fields: [
    { key: 'System.Tracks',           label: 'Tracks' },
    { key: 'System.Format',           label: 'Format' },
    { key: 'System.Tape',             label: 'Tape / Reel' },
    { key: 'System.Original Project', label: 'Original Project' },
  ]},
  { label: 'Production', fields: [
    { key: 'User.Comments',     label: 'Comments' },
    { key: 'User.Scene',        label: 'Scene' },
    { key: 'User.Take',         label: 'Take' },
    { key: 'User.Camera',       label: 'Camera' },
    { key: 'User.Camroll',      label: 'Camera Roll' },
    { key: 'System.Shoot Date', label: 'Shoot Date' },
  ]},
  { label: 'Markers', hint: 'Adds one request per clip — may slow large projects', fields: [
    { key: 'Markers.Locators', label: 'Include markers' },
  ]},
];

const isBrowserPreview =
  typeof pywebview === 'undefined' &&
  (window.location.protocol === 'file:' || new URLSearchParams(window.location.search).has('mock'));

// Plain browser preview only. The desktop app injects pywebview after pywebviewready.
if (isBrowserPreview) {
  window.pywebview = { api: _MOCK_API };
  setTimeout(init, 0);
}

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  folderName:   null,
  folderUri:    null,
  metadataText: null,
  generating:   false,
  filterTimer:  null,
  treeCache:    {},         // uri -> [{name, uri}]
  treeExpanded: new Set(), // URIs currently expanded
  maxDepth:     0,          // 0 = unlimited
  startUri:     null,
  initialized:  false,
};

// ── DOM ────────────────────────────────────────────────────────────────────
const el = id => document.getElementById(id);

const sidebar          = el('sidebar');
const resizeHandle     = el('resize-handle');
const folderList       = el('folder-list');
const filterInput      = el('filter-input');
const sidebarStatus    = el('sidebar-status');
const sidebarVersion   = el('sidebar-version');
const sidebarCopyright = el('sidebar-copyright');

const contentTitle     = el('content-title');
const contentSubtitle  = el('content-subtitle');
const btnGenerate      = el('btn-generate');
const emptyState       = el('empty-state');
const output           = el('output');
const fontSlider       = el('font-slider');
const btnCopy          = el('btn-copy');
const btnEmail         = el('btn-email');
const btnSave          = el('btn-save');
const btnFields        = el('btn-fields');
const fieldsPanel      = el('fields-panel');

const backdrop         = el('backdrop');
const settingsModal    = el('settings-modal');
const btnSettings      = el('btn-settings');
const btnModalClose    = el('btn-modal-close');
const sServer          = el('s-server');
const sWorkgroup       = el('s-workgroup');
const sUsername        = el('s-username');
const sPassword        = el('s-password');
const passwordHint     = el('password-hint');
const sStartPath       = el('s-start-path');
const sMaxDepth        = el('s-max-depth');
const connStatus       = el('conn-status');
const btnTest          = el('btn-test');
const btnSaveSettings  = el('btn-save-settings');

const updateModal      = el('update-modal');
const uvCurrent        = el('uv-current');
const uvNew            = el('uv-new');
const updateNotes      = el('update-notes');
const btnUpdateNow     = el('btn-update-now');
const btnUpdateQuit    = el('btn-update-quit');
const btnUpdateLater   = el('btn-update-later');

// ── Icons + copyright ──────────────────────────────────────────────────────
lucide.createIcons();
sidebarCopyright.textContent = `© ${new Date().getFullYear()} Mark Battistella`;

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('pywebviewready', init);

async function init() {
  if (state.initialized) return;
  state.initialized = true;

  const ver = await pywebview.api.get_version();
  sidebarVersion.textContent = ver !== 'dev' ? `v${ver}` : '';

  const cfg = await pywebview.api.get_config();
  if (!cfg.server) {
    resetShell();
    await populateSheet();
    openModal();
    return;
  }

  const wg       = cfg.workgroup || 'AvidWorkgroup';
  const startUri = cfg.start_path || `interplay://${wg}/`;
  const maxDepth = Number(cfg.max_depth) || 0;

  await initTree(startUri, maxDepth);
  setTimeout(checkForUpdates, 4000);
}

function resetShell() {
  state.folderName = null;
  state.folderUri = null;
  state.treeCache = {};
  state.treeExpanded.clear();
  state.startUri = null;
  folderList.innerHTML = '';
  sidebarStatus.textContent = '';
  clearOutput();
  setTitle(null);
  btnGenerate.disabled = true;
}

// Status callback — Python pushes progress during long loads
window._onStatus = msg => { contentSubtitle.textContent = msg; };

// ── Tree navigation ────────────────────────────────────────────────────────
async function initTree(startUri, maxDepth) {
  state.startUri  = startUri;
  state.maxDepth  = maxDepth;
  state.treeCache = {};
  state.treeExpanded.clear();

  folderList.innerHTML = '<li class="list-hint">Loading…</li>';
  sidebarStatus.textContent = 'Loading…';

  const items = await pywebview.api.get_children(startUri);
  if (items.error) {
    folderList.innerHTML = `<li class="list-hint">Error: ${esc(items.error)}</li>`;
    sidebarStatus.textContent = 'Error';
    return;
  }

  state.treeCache[startUri] = items;
  folderList.innerHTML = '';
  renderTreeItems(folderList, items, 0);
  lucide.createIcons();
  updateSidebarStatus();
}

function renderTreeItems(container, items, depth) {
  items.forEach(item => container.appendChild(createTreeNode(item, depth)));
}

function createTreeNode(item, depth) {
  const li = document.createElement('li');
  li.className = 'tree-node';

  const row = document.createElement('div');
  row.className = 'tree-row';
  row.style.setProperty('--depth', depth);
  if (state.folderUri === item.uri) row.classList.add('selected');

  // Two folder icons — CSS swaps between them via .tree-node.expanded
  const iconClosed = document.createElement('i');
  iconClosed.setAttribute('data-lucide', 'folder');
  iconClosed.className = 'folder-closed';

  const iconOpen = document.createElement('i');
  iconOpen.setAttribute('data-lucide', 'folder-open');
  iconOpen.className = 'folder-open';

  const label = document.createElement('span');
  label.className = 'tree-label';
  label.textContent = item.name;

  row.appendChild(iconClosed);
  row.appendChild(iconOpen);
  row.appendChild(label);

  const childUl = document.createElement('ul');
  childUl.className = 'tree-children';

  li.appendChild(row);
  li.appendChild(childUl);

  // Restore expanded state after filter clear / settings change
  if (state.treeExpanded.has(item.uri) && canExpandDepth(depth)) {
    li.classList.add('expanded');
    const cached = state.treeCache[item.uri];
    if (cached && cached.length > 0) renderTreeItems(childUl, cached, depth + 1);
  }

  // Single click: select + schedule auto-expand (timer lets dblclick cancel it)
  row.addEventListener('click', () => {
    selectTreeNode(item, row);
    if (!li.classList.contains('expanded') && canExpandDepth(depth)) {
      clearTimeout(row._expandTimer);
      row._expandTimer = setTimeout(() => expandNode(item, li, childUl, depth), 250);
    }
  });

  // Double click on open folder: cancel pending expand and collapse
  row.addEventListener('dblclick', e => {
    e.preventDefault();
    clearTimeout(row._expandTimer);
    if (li.classList.contains('expanded')) collapseNode(li, childUl, item);
  });

  return li;
}

function collapseNode(li, childUl, item) {
  li.classList.remove('expanded');
  state.treeExpanded.delete(item.uri);
  childUl.innerHTML = '';
}

function canExpandDepth(depth) {
  return state.maxDepth === 0 || depth + 1 < state.maxDepth;
}

async function expandNode(item, li, childUl, depth) {
  if (!canExpandDepth(depth)) {
    sidebarStatus.textContent = `Depth limit: ${state.maxDepth}`;
    return;
  }
  if (!state.treeCache[item.uri]) {
    sidebarStatus.textContent = 'Loading…';
    const items = await pywebview.api.get_children(item.uri);
    state.treeCache[item.uri] = items.error ? [] : items;
  }
  const childItems = state.treeCache[item.uri] || [];
  if (childItems.length === 0) { updateSidebarStatus(); return; }
  li.classList.add('expanded');
  state.treeExpanded.add(item.uri);
  childUl.innerHTML = '';
  renderTreeItems(childUl, childItems, depth + 1);
  lucide.createIcons();
  updateSidebarStatus();
}

function selectTreeNode(item, row) {
  document.querySelectorAll('.tree-row.selected').forEach(r => r.classList.remove('selected'));
  row.classList.add('selected');
  state.folderName = item.name;
  state.folderUri  = item.uri;
  clearOutput();
  setTitle(item.name);
  btnGenerate.disabled = false;
}

function updateSidebarStatus() {
  const top = state.treeCache[state.startUri] || [];
  sidebarStatus.textContent = `${top.length} item${top.length !== 1 ? 's' : ''}`;
}

// ── Filter ─────────────────────────────────────────────────────────────────
filterInput.addEventListener('input', () => {
  clearTimeout(state.filterTimer);
  state.filterTimer = setTimeout(() => {
    const q = filterInput.value.toLowerCase().trim();
    if (q) {
      showFilterResults(q);
    } else {
      // Rebuild tree from cache, restoring expansion state
      folderList.innerHTML = '';
      renderTreeItems(folderList, state.treeCache[state.startUri] || [], 0);
      lucide.createIcons();
      updateSidebarStatus();
    }
  }, 150);
});

function showFilterResults(q) {
  const matches = flatSearchCache(state.startUri, q);
  folderList.innerHTML = '';

  if (!matches.length) {
    folderList.innerHTML = '<li class="list-hint">No matches.</li>';
    sidebarStatus.textContent = 'No matches';
    return;
  }

  matches.forEach(item => {
    const li = document.createElement('li');
    li.className = 'tree-node';
    const row = document.createElement('div');
    row.className = 'tree-row';
    row.style.setProperty('--depth', 0);
    if (state.folderUri === item.uri) row.classList.add('selected');

    const icon = document.createElement('i');
    icon.setAttribute('data-lucide', 'folder');
    icon.className = 'folder-closed';

    const label = document.createElement('span');
    label.className = 'tree-label';
    label.textContent = item.name;

    row.appendChild(icon);
    row.appendChild(label);
    row.addEventListener('click', () => selectTreeNode(item, row));
    li.appendChild(row);
    folderList.appendChild(li);
  });

  lucide.createIcons();
  sidebarStatus.textContent = `${matches.length} match${matches.length !== 1 ? 'es' : ''}`;
}

function flatSearchCache(uri, q) {
  const results = [];
  (state.treeCache[uri] || []).forEach(item => {
    if (item.name.toLowerCase().includes(q)) results.push(item);
    results.push(...flatSearchCache(item.uri, q));
  });
  return results;
}

// ── Generate ───────────────────────────────────────────────────────────────
btnGenerate.addEventListener('click', generateMetadata);

function setOutputToolsEnabled(enabled) {
  [btnCopy, btnEmail, btnSave].forEach(btn => { btn.disabled = !enabled; });
}

async function generateMetadata() {
  if (!state.folderName || !state.folderUri || state.generating) return;

  state.generating = true;
  btnGenerate.textContent = 'Generating…';
  btnGenerate.disabled    = true;
  setOutputToolsEnabled(false);
  contentSubtitle.textContent = '';

  let result;
  try {
    result = await pywebview.api.load_project(state.folderName, state.folderUri);
  } catch (err) {
    result = { error: err?.message || String(err) };
  } finally {
    state.generating = false;
    btnGenerate.textContent = 'Generate Metadata';
    btnGenerate.disabled    = !state.folderUri;
  }

  if (result.error) {
    if (!state.metadataText) emptyState.style.display = 'flex';
    contentSubtitle.textContent = `Error: ${result.error}`;
    return;
  }

  state.metadataText = result.text;
  output.textContent = result.text;
  output.style.display = 'block';
  emptyState.style.display = 'none';
  setOutputToolsEnabled(true);
  contentSubtitle.textContent = result.summary || '';
  contentSubtitle._summary = result.summary || '';
}

function clearOutput() {
  state.metadataText = null;
  output.textContent  = '';
  output.style.display = 'none';
  emptyState.style.display = 'flex';
  setOutputToolsEnabled(false);
  contentSubtitle.textContent = '';
  contentSubtitle._summary = '';
  btnGenerate.textContent = 'Generate Metadata';
}

function setTitle(name) {
  contentTitle.textContent = name || 'No folder selected';
  document.title = name
    ? `${name} — Avid MediaCentral Metadata Exporter`
    : 'Avid MediaCentral Metadata Exporter';
}

// ── Font slider ────────────────────────────────────────────────────────────
fontSlider.addEventListener('input', () => {
  output.style.fontSize = `${fontSlider.value}px`;
});

// ── Action buttons ─────────────────────────────────────────────────────────
btnCopy.addEventListener('click', async () => {
  if (!state.metadataText) return;
  try {
    await navigator.clipboard.writeText(state.metadataText);
    flash('Copied to clipboard.');
  } catch (err) {
    flash(`Copy failed: ${err?.message || err}`);
  }
});

btnEmail.addEventListener('click', async () => {
  if (!state.metadataText) return;
  const r = await pywebview.api.open_email(state.folderName, state.metadataText);
  if (!r.ok) flash(r.error || 'Email failed.');
});

btnSave.addEventListener('click', async () => {
  if (!state.metadataText) return;
  const r = await pywebview.api.save_to_file(defaultFilename(state.folderName), state.metadataText);
  if (r.ok) {
    flash(`Saved: ${r.path}`);
  } else if (r.error) {
    flash(`Save failed: ${r.error}`);
  }
});

function defaultFilename(name) {
  const safe = String(name || 'metadata').replace(/[\\/:*?"<>|]/g, '_').trim();
  return `${safe || 'metadata'}.txt`;
}

function flash(msg, ms = 3500) {
  contentSubtitle.textContent = msg;
  clearTimeout(contentSubtitle._t);
  contentSubtitle._t = setTimeout(() => {
    if (!state.generating) contentSubtitle.textContent = state.metadataText
      ? (contentSubtitle._summary || '')
      : '';
  }, ms);
}

// ── Settings modal ─────────────────────────────────────────────────────────
btnSettings.addEventListener('click', async () => {
  await populateSheet();
  openModal();
});
btnModalClose.addEventListener('click', closeModal);
backdrop.addEventListener('click', () => {
  if (!settingsModal.classList.contains('hidden')) closeModal();
  if (!updateModal.classList.contains('hidden'))   closeUpdateModal();
});

async function populateSheet() {
  const cfg = await pywebview.api.get_config();
  sServer.value    = cfg.server    || '';
  sWorkgroup.value = cfg.workgroup || 'AvidWorkgroup';
  sUsername.value  = cfg.username  || '';
  sPassword.value = '';
  sPassword.placeholder = cfg.has_password ? 'Saved password' : '';
  passwordHint.textContent = cfg.has_password
    ? 'Leave blank to keep the saved password.'
    : 'Enter a password to save it in the system credential store.';
  sStartPath.value = cfg.start_path || '';
  sMaxDepth.value  = cfg.max_depth != null ? String(cfg.max_depth) : '0';
  connStatus.textContent = '';
  connStatus.className   = '';
}

function buildFieldGroups(activeFields) {
  const activeKeys = new Set((activeFields || []).map(f => Array.isArray(f) ? f.join('.') : f));
  const container  = el('field-groups');
  container.innerHTML = '';

  FIELD_GROUPS.forEach(group => {
    const wrap = document.createElement('div');
    wrap.className = 'field-group';

    const head = document.createElement('div');
    head.className = 'field-group-label';
    head.textContent = group.label;
    wrap.appendChild(head);

    if (group.hint) {
      const hint = document.createElement('div');
      hint.className = 'field-group-hint';
      hint.textContent = group.hint;
      wrap.appendChild(hint);
    }

    const grid = document.createElement('div');
    grid.className = 'field-checks';

    group.fields.forEach(f => {
      const lbl = document.createElement('label');
      lbl.className = 'field-check-row';

      const cb = document.createElement('input');
      cb.type    = 'checkbox';
      cb.name    = 'field';
      cb.value   = f.key;
      cb.checked = activeKeys.has(f.key);

      const span = document.createElement('span');
      span.textContent = f.label;

      lbl.appendChild(cb);
      lbl.appendChild(span);
      grid.appendChild(lbl);
    });

    wrap.appendChild(grid);
    container.appendChild(wrap);
  });
}

function openModal() {
  document.body.classList.add('modal-open');
  backdrop.classList.remove('hidden');
  settingsModal.classList.remove('hidden');
  requestAnimationFrame(() => requestAnimationFrame(() => {
    backdrop.classList.add('visible');
    settingsModal.classList.add('visible');
  }));
}

function closeModal() {
  backdrop.classList.remove('visible');
  settingsModal.classList.remove('visible');
  setTimeout(() => {
    document.body.classList.remove('modal-open');
    backdrop.classList.add('hidden');
    settingsModal.classList.add('hidden');
  }, 220);
}

btnTest.addEventListener('click', async () => {
  connStatus.textContent = 'Testing…';
  connStatus.className   = '';
  const r = await pywebview.api.test_connection(
    sServer.value, sWorkgroup.value, sUsername.value, sPassword.value
  );
  connStatus.textContent = r.message;
  connStatus.className   = r.ok ? 'ok' : 'err';
});

btnSaveSettings.addEventListener('click', async () => {
  const r = await pywebview.api.save_settings(
    sServer.value, sWorkgroup.value, sUsername.value, sPassword.value,
    sStartPath.value.trim(), Number(sMaxDepth.value) || 0
  );
  if (!r.ok) {
    connStatus.textContent = r.error || 'Save failed.';
    connStatus.className   = 'err';
    return;
  }
  closeModal();
  // Re-init tree with updated settings
  const cfg      = await pywebview.api.get_config();
  const wg       = cfg.workgroup || 'AvidWorkgroup';
  const startUri = cfg.start_path || `interplay://${wg}/`;
  const maxDepth = Number(cfg.max_depth) || 0;
  state.folderName = null;
  state.folderUri  = null;
  clearOutput();
  setTitle(null);
  await initTree(startUri, maxDepth);
});

// ── Fields panel ──────────────────────────────────────────────────────────
btnFields.addEventListener('click', async e => {
  e.stopPropagation();
  if (fieldsPanel.classList.contains('hidden')) {
    await openFieldsPanel();
  } else {
    closeFieldsPanel();
  }
});

async function openFieldsPanel() {
  const cfg = await pywebview.api.get_config();
  buildFieldGroups(cfg.default_fields || _DEFAULT_FIELDS);
  fieldsPanel.querySelectorAll('input[name="field"]').forEach(cb => {
    cb.addEventListener('change', saveFieldsFromPanel);
  });
  fieldsPanel.classList.remove('hidden');
  btnFields.classList.add('active');
}

function closeFieldsPanel() {
  fieldsPanel.classList.add('hidden');
  btnFields.classList.remove('active');
}

async function saveFieldsFromPanel() {
  const checked = [...fieldsPanel.querySelectorAll('input[name="field"]:checked')];
  const fields  = checked.map(cb => {
    const dot = cb.value.indexOf('.');
    return [cb.value.slice(0, dot), cb.value.slice(dot + 1)];
  });
  await pywebview.api.save_fields(fields);
}

document.addEventListener('click', e => {
  if (fieldsPanel.classList.contains('hidden')) return;
  if (!fieldsPanel.contains(e.target) && !btnFields.contains(e.target)) {
    closeFieldsPanel();
  }
});

// ── Updates ────────────────────────────────────────────────────────────────
async function checkForUpdates() {
  const r = await pywebview.api.check_updates();
  if (!r.available) return;
  openUpdateModal(r);
}

const _SKIP_KEY = 'mc_update_skip';

function _skipCount(tag) {
  try {
    const d = JSON.parse(localStorage.getItem(_SKIP_KEY) || '{}');
    return d.tag === tag ? (d.count || 0) : 0;
  } catch { return 0; }
}

function _bumpSkip(tag) {
  localStorage.setItem(_SKIP_KEY, JSON.stringify({ tag, count: _skipCount(tag) + 1 }));
}

function openUpdateModal(r) {
  uvCurrent.textContent = r.current || '';
  uvNew.textContent     = r.tag     || '';
  renderUpdateNotes(r.notes || '');
  updateModal.dataset.tag = r.tag || '';
  const forced = _skipCount(r.tag) >= 10;
  updateModal.classList.toggle('skip-limit', forced);
  document.body.classList.add('modal-open');
  backdrop.classList.remove('hidden');
  updateModal.classList.remove('hidden');
  requestAnimationFrame(() => requestAnimationFrame(() => {
    backdrop.classList.add('visible');
    updateModal.classList.add('visible');
  }));
}

function closeUpdateModal() {
  backdrop.classList.remove('visible');
  updateModal.classList.remove('visible');
  setTimeout(() => {
    updateModal.classList.add('hidden');
    if (settingsModal.classList.contains('hidden')) {
      document.body.classList.remove('modal-open');
      backdrop.classList.add('hidden');
    }
  }, 220);
}

function renderUpdateNotes(md) {
  updateNotes.innerHTML = '';
  if (!md) return;
  let curList = null;
  md.split('\n').forEach(line => {
    const t   = line.trimEnd();
    const mH2 = t.match(/^##\s+(.*)/);
    const mH3 = t.match(/^###\s+(.*)/);
    const mLi = t.match(/^[-*]\s+(.*)/);
    if (!t.trim()) { curList = null; return; }
    if (mH2) {
      curList = null;
      const h = document.createElement('h4');
      h.textContent = mH2[1];
      updateNotes.appendChild(h);
    } else if (mH3) {
      curList = null;
      const h = document.createElement('h5');
      h.textContent = mH3[1];
      updateNotes.appendChild(h);
    } else if (mLi) {
      if (!curList) { curList = document.createElement('ul'); updateNotes.appendChild(curList); }
      const li = document.createElement('li');
      li.innerHTML = inlineMd(mLi[1]);
      curList.appendChild(li);
    } else {
      curList = null;
      const p = document.createElement('p');
      p.innerHTML = inlineMd(t);
      updateNotes.appendChild(p);
    }
  });
}

function inlineMd(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g,       '<code>$1</code>');
}

btnUpdateLater.addEventListener('click', () => {
  _bumpSkip(updateModal.dataset.tag || '');
  closeUpdateModal();
});

btnUpdateNow.addEventListener('click', async () => {
  btnUpdateNow.disabled = btnUpdateQuit.disabled = true;
  btnUpdateNow.textContent = 'Downloading…';
  const r = await pywebview.api.install_update_now();
  if (!r.ok) {
    btnUpdateNow.textContent = 'Install Now';
    btnUpdateNow.disabled = btnUpdateQuit.disabled = false;
    flash(`Update failed: ${r.error}`);
    closeUpdateModal();
  }
});

btnUpdateQuit.addEventListener('click', async () => {
  btnUpdateNow.disabled = btnUpdateQuit.disabled = true;
  const r = await pywebview.api.queue_update();
  if (r.ok) {
    closeUpdateModal();
  } else {
    btnUpdateNow.disabled = btnUpdateQuit.disabled = false;
    flash(`Update failed: ${r.error}`);
    closeUpdateModal();
  }
});

// ── Sidebar resize ────────────────────────────────────────────────────────
const SIDEBAR_MIN     = 180;
const SIDEBAR_MAX     = 420;
const SIDEBAR_DEFAULT = 260;
const SIDEBAR_SNAP    = 12;

resizeHandle.addEventListener('mousedown', e => {
  e.preventDefault();
  const startX = e.clientX;
  const startW = sidebar.getBoundingClientRect().width;
  resizeHandle.classList.add('dragging');
  document.body.style.cursor      = 'col-resize';
  document.body.style.userSelect  = 'none';

  function onMove(e) {
    let w = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startW + e.clientX - startX));
    if (Math.abs(w - SIDEBAR_DEFAULT) <= SIDEBAR_SNAP) w = SIDEBAR_DEFAULT;
    document.documentElement.style.setProperty('--sidebar-w', `${w}px`);
  }
  function onUp() {
    resizeHandle.classList.remove('dragging');
    document.body.style.cursor     = '';
    document.body.style.userSelect = '';
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup',   onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup',   onUp);
});

// ── Keyboard shortcuts + browser lockdown ─────────────────────────────────
document.addEventListener('contextmenu', e => e.preventDefault());

document.addEventListener('keydown', e => {
  const inInput = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName);
  const mod     = e.ctrlKey || e.metaKey;

  // Block zoom (Ctrl/Cmd +/-/0) and reload (Ctrl/Cmd+R, F5)
  if (mod && ['-', '=', '+', '0'].includes(e.key)) { e.preventDefault(); return; }
  if (mod && (e.key === 'r' || e.key === 'R'))      { e.preventDefault(); return; }
  if (e.key === 'F5')                                { e.preventDefault(); return; }

  // Ctrl/Cmd+G → generate
  if (mod && (e.key === 'g' || e.key === 'G')) {
    e.preventDefault();
    if (!btnGenerate.disabled) generateMetadata();
    return;
  }

  // / → focus filter (when not already in an input)
  if (e.key === '/' && !inInput) {
    e.preventDefault();
    filterInput.focus();
    filterInput.select();
    return;
  }

  // Escape → close modals/panels in order of priority
  if (e.key === 'Escape') {
    if (!updateModal.classList.contains('hidden')) {
      closeUpdateModal();
    } else if (!fieldsPanel.classList.contains('hidden')) {
      closeFieldsPanel();
    } else if (!settingsModal.classList.contains('hidden')) {
      closeModal();
    } else if (filterInput.value) {
      filterInput.value = '';
      filterInput.dispatchEvent(new Event('input'));
    } else if (document.activeElement === filterInput) {
      filterInput.blur();
    }
    return;
  }
});

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
