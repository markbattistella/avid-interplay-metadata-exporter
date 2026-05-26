'use strict';

// ── Mock API (browser preview — not used inside pywebview) ────────────────
const _MOCK_TEXT = `\
PROJECT: 2026002 BRAVO
Date:    2026-05-26  10:30
────────────────────────────────────────────────────────────────────────

├── RAW AUDIO RECORDINGS 2026-01-22  [2 items]
│   ├── Interview A                   00:07:39:18   Online   MC
│   │   Created: jsmith 2026-01-22   |   Modified: jsmith 2026-05-25
│   └── Interview B                   00:03:12:04   Online   MC
│       Created: jsmith 2026-01-22   |   Modified: jsmith 2026-05-25
│
│
└── SEQUENCES 2026-01-22  [1 items]
    └── Assembly Edit                 00:12:45:00   Online   SEQ
        Created: jsmith 2026-01-22   |   Modified: jeditor 2026-05-24
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
  'interplay://AvidWorkgroup/Projects/2025': [
    { name: '2025001 ALPHA',   uri: 'interplay://AvidWorkgroup/Projects/2025/2025001 ALPHA' },
    { name: '2025002 BRAVO',   uri: 'interplay://AvidWorkgroup/Projects/2025/2025002 BRAVO' },
    { name: '2025003 CHARLIE', uri: 'interplay://AvidWorkgroup/Projects/2025/2025003 CHARLIE' },
  ],
};

const _MOCK_API = {
  async get_version()                       { return 'dev'; },
  async get_config()                        { return { server: '192.168.1.10', workgroup: 'AvidWorkgroup', username: 'jsmith', start_path: '', max_depth: 3 }; },
  async get_password()                      { return '••••••••'; },
  async get_children(uri)                   { return _MOCK_TREE[uri] || []; },
  async load_project(name)                  { return { text: _MOCK_TEXT.replace('2026002 BRAVO', name), summary: '3 items loaded.' }; },
  async save_to_file()                      { alert('Save not available in preview mode.'); return { ok: false }; },
  async open_email()                        { return { ok: true }; },
  async test_connection()                   { return { ok: true, message: 'Connected successfully. (mock)' }; },
  async save_settings()                     { return { ok: true }; },
  async check_updates()                     { return { available: false, current: 'dev' }; },
  async install_update_now()                { return { ok: false, error: 'Mock mode' }; },
  async queue_update()                      { return { ok: false, error: 'Mock mode' }; },
};

// When running in a plain browser pywebview is undefined — wire up mock.
if (typeof pywebview === 'undefined') {
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
  updateUrl:    null,
  treeCache:    {},         // uri -> [{name, uri}]
  treeExpanded: new Set(), // URIs currently expanded
  maxDepth:     0,          // 0 = unlimited
  startUri:     null,
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
const contentTools     = el('content-tools');
const btnGenerate      = el('btn-generate');
const emptyState       = el('empty-state');
const output           = el('output');
const fontSlider       = el('font-slider');
const btnCopy          = el('btn-copy');
const btnEmail         = el('btn-email');
const btnSave          = el('btn-save');

const backdrop         = el('backdrop');
const settingsModal    = el('settings-modal');
const btnSettings      = el('btn-settings');
const btnModalClose    = el('btn-modal-close');
const sServer          = el('s-server');
const sWorkgroup       = el('s-workgroup');
const sUsername        = el('s-username');
const sPassword        = el('s-password');
const sStartPath       = el('s-start-path');
const sMaxDepth        = el('s-max-depth');
const connStatus       = el('conn-status');
const btnTest          = el('btn-test');
const btnSaveSettings  = el('btn-save-settings');

const updateBanner     = el('update-banner');
const updateMsg        = el('update-msg');
const btnUpdateNow     = el('btn-update-now');
const btnUpdateQuit    = el('btn-update-quit');
const btnUpdateDismiss = el('btn-update-dismiss');

// ── Icons + copyright ──────────────────────────────────────────────────────
lucide.createIcons();
sidebarCopyright.textContent = `© ${new Date().getFullYear()} Mark Battistella`;

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('pywebviewready', init);

async function init() {
  const ver = await pywebview.api.get_version();
  sidebarVersion.textContent = ver !== 'dev' ? `v${ver}` : '';

  const cfg = await pywebview.api.get_config();
  if (!cfg.server) {
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
  if (state.treeExpanded.has(item.uri)) {
    li.classList.add('expanded');
    const cached = state.treeCache[item.uri];
    if (cached && cached.length > 0) renderTreeItems(childUl, cached, depth + 1);
  }

  // Single click: select + schedule auto-expand (timer lets dblclick cancel it)
  row.addEventListener('click', () => {
    selectTreeNode(item, row);
    if (!li.classList.contains('expanded')) {
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

async function expandNode(item, li, childUl, depth) {
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

async function generateMetadata() {
  if (!state.folderName || !state.folderUri || state.generating) return;

  state.generating = true;
  btnGenerate.textContent = 'Generating…';
  btnGenerate.disabled    = true;
  emptyState.style.display = 'none';
  output.style.display     = 'none';
  contentTools.classList.add('invisible');
  contentSubtitle.textContent = '';

  const result = await pywebview.api.load_project(state.folderName, state.folderUri);

  state.generating = false;
  btnGenerate.textContent = 'Generate Metadata';
  btnGenerate.disabled    = false;

  if (result.error) {
    emptyState.style.display = 'flex';
    contentSubtitle.textContent = `Error: ${result.error}`;
    return;
  }

  state.metadataText = result.text;
  output.textContent = result.text;
  output.style.display = 'block';
  contentTools.classList.remove('invisible');
  contentSubtitle.textContent = result.summary || '';
}

function clearOutput() {
  state.metadataText = null;
  output.textContent  = '';
  output.style.display = 'none';
  emptyState.style.display = 'flex';
  contentTools.classList.add('invisible');
  contentSubtitle.textContent = '';
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
  await navigator.clipboard.writeText(state.metadataText);
  flash('Copied to clipboard.');
});

btnEmail.addEventListener('click', async () => {
  if (!state.metadataText) return;
  await pywebview.api.open_email(state.folderName, state.metadataText);
});

btnSave.addEventListener('click', async () => {
  if (!state.metadataText) return;
  const r = await pywebview.api.save_to_file(`${state.folderName}.txt`, state.metadataText);
  if (r.ok) flash(`Saved → ${r.path}`);
});

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
backdrop.addEventListener('click',     closeModal);

async function populateSheet() {
  const cfg = await pywebview.api.get_config();
  sServer.value    = cfg.server    || '';
  sWorkgroup.value = cfg.workgroup || 'AvidWorkgroup';
  sUsername.value  = cfg.username  || '';
  sPassword.value  = cfg.username
    ? await pywebview.api.get_password(cfg.username)
    : '';
  sStartPath.value = cfg.start_path || '';
  sMaxDepth.value  = cfg.max_depth != null ? String(cfg.max_depth) : '0';
  connStatus.textContent = '';
  connStatus.className   = '';
}

function openModal() {
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

// ── Updates ────────────────────────────────────────────────────────────────
async function checkForUpdates() {
  const r = await pywebview.api.check_updates();
  if (!r.available) return;
  updateMsg.textContent = `v${r.tag} available (you have v${r.current}).`;
  state.updateUrl = r.url;
  updateBanner.classList.remove('hidden');
}

btnUpdateNow.addEventListener('click', async () => {
  btnUpdateNow.disabled = btnUpdateQuit.disabled = true;
  updateMsg.textContent = 'Downloading…';
  const r = await pywebview.api.install_update_now(state.updateUrl);
  if (!r.ok) {
    updateMsg.textContent = `Download failed: ${r.error}`;
    btnUpdateNow.disabled = btnUpdateQuit.disabled = false;
  }
});

btnUpdateQuit.addEventListener('click', async () => {
  btnUpdateNow.disabled = btnUpdateQuit.disabled = true;
  updateMsg.textContent = 'Downloading…';
  const r = await pywebview.api.queue_update(state.updateUrl);
  updateMsg.textContent = r.ok ? 'Will install on quit.' : `Failed: ${r.error}`;
});

btnUpdateDismiss.addEventListener('click', () => {
  updateBanner.classList.add('hidden');
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

  // Escape → close modal, clear filter, or blur filter
  if (e.key === 'Escape') {
    if (!settingsModal.classList.contains('hidden')) {
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
