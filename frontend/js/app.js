// App shell: hash router, shared state, and the current-list sidebar.
import { api } from './api.js';
import { h, clear, money, toast, modal, confirmModal, promptModal, qtyBox, dealBadge, productTitle, unitPrice } from './ui.js';
import * as home from './pages/home.js';
import * as stores from './pages/stores.js';
import * as favorites from './pages/favorites.js';
import * as lists from './pages/lists.js';
import * as settings from './pages/settings.js';

const pages = { home, stores, favorites, lists, settings };

export const state = {
  list: null,          // current (draft) list payload
  settings: null,      // user settings
  selected: [],        // selected store locations
  listeners: new Set(),
};
const emit = () => state.listeners.forEach(fn => { try { fn(); } catch (e) { console.error(e); } });
export const onChange = (fn) => { state.listeners.add(fn); return () => state.listeners.delete(fn); };

export async function refreshList(payload) {
  state.list = payload || await api.currentList();
  updatePills();
  emit();
  return state.list;
}
export async function refreshStores() {
  state.selected = await api.selectedStores();
  updatePills();
  emit();
  return state.selected;
}
export async function loadSettings() {
  const r = await api.settings();
  state.settings = r.settings;
  return r;
}
function updatePills() {
  const sp = document.getElementById('store-pill');
  const lp = document.getElementById('list-pill');
  if (sp) sp.textContent = `${state.selected.length} store${state.selected.length === 1 ? '' : 's'}`;
  if (lp && state.list) lp.textContent = `${state.list.breakdown.item_count} item${state.list.breakdown.item_count === 1 ? '' : 's'} · ${money(state.list.breakdown.total)}`;
}

/** Add an offer to the current list (and therefore favorites). */
export async function addToList(offer, qty = 1) {
  try {
    const l = await api.addItem(offer, qty);
    await refreshList(l);
    toast(`Added ${productTitle(offer)} (${offer.chain_name})`);
  } catch (e) { toast(`Could not add: ${e.message}`, 'err'); }
}

// ---------------------------------------------------------------------------
// Sidebar: current list broken down by store and aisle
// ---------------------------------------------------------------------------
export function renderListSidebar(container, { showDeals = true } = {}) {
  const box = h('div.card.sidebar-list');
  container.appendChild(box);
  let dealsPanel = null;

  const draw = () => {
    clear(box);
    const l = state.list;
    if (!l) { box.appendChild(h('div.muted', 'Loading list…')); return; }
    const b = l.breakdown;
    box.appendChild(h('div.card-title', h('h2', l.source_list_id ? l.name : 'Current list'),
      l.source_list_id ? h('span.badge', 'loaded') : null));
    box.appendChild(h('div.list-totals',
      h('div.stat', h('div.v', money(b.total)), h('div.l', 'Total')),
      h('div.stat', h('div.v', b.item_count), h('div.l', 'Items')),
      h('div.stat', h('div.v', b.store_count), h('div.l', 'Stores'))));
    if (b.deal_savings > 0) box.appendChild(h('div.small.muted', { style: { marginBottom: '.5rem' } }, `Deal savings on this list: ${money(b.deal_savings)}`));

    if (!l.items.length) box.appendChild(h('div.empty', 'Your list is empty. Search for items and click Add.'));
    for (const s of b.stores) {
      const store = h('div.list-store', { style: { '--chain': chainColor(s.chain_slug) } });
      store.appendChild(h('div.list-store-head',
        h('div', h('div.store-name', s.chain_name), h('div.addr', s.location_name, s.location_address ? ` · ${s.location_address}` : '')),
        h('div.right', h('div.price-main', money(s.subtotal)), h('div.small.muted', `${s.item_count} item${s.item_count === 1 ? '' : 's'}`))));
      for (const a of s.aisles) {
        const aisle = h('div.list-aisle', h('h5', a.aisle, a.section && a.section !== a.aisle ? ` · ${a.section}` : ''));
        for (const it of a.items) aisle.appendChild(itemRow(it));
        store.appendChild(aisle);
      }
      box.appendChild(store);
    }

    box.appendChild(h('div.list-actions',
      h('button.btn.btn-primary.btn-sm', { onclick: saveFlow, disabled: !l.items.length }, '💾 Save'),
      h('button.btn.btn-sm', { onclick: loadFlow }, '📂 Load…'),
      h('button.btn.btn-sm', { onclick: regenFlow, disabled: !l.items.length, title: 'Re-price every item at your currently selected stores' }, '🔄 Re-price'),
      h('button.btn.btn-sm', { onclick: () => window.print(), disabled: !l.items.length }, '🖨 Print'),
      h('button.btn.btn-sm.btn-danger', { onclick: clearFlow, disabled: !l.items.length }, 'Clear')));

    if (showDeals && l.items.length) {
      dealsPanel = h('div.deals-panel');
      box.appendChild(dealsPanel);
      loadDeals(dealsPanel);
    }
  };

  const itemRow = (it) => {
    const row = h('div.list-item', { className: `list-item ${it.checked ? 'checked' : ''}` });
    row.appendChild(h('label.check', h('input', { type: 'checkbox', checked: it.checked, onchange: async (e) => { await refreshList(await api.patchItem(it.item_id, { checked: e.target.checked })); } }),
      h('div', h('div.li-name', productTitle(it)), h('div.li-meta', [it.size_text, unitPrice(it)].filter(Boolean).join(' · '), ' ', dealBadge(it)))));
    row.appendChild(qtyBox(it.qty, async (q) => refreshList(await api.patchItem(it.item_id, { qty: q }))));
    row.appendChild(h('div.right', h('div.price-main', money(it.line_total)),
      h('button.btn.btn-xs.btn-danger.li-remove', { onclick: async () => refreshList(await api.removeItem(it.item_id)), title: 'Remove' }, '✕')));
    return row;
  };

  const loadDeals = async (panel) => {
    try {
      const r = await api.dealsForList();
      if (!r.recommendations.length) return;
      panel.appendChild(h('h4', { style: { marginTop: '.75rem' } }, '💡 Better deals on your list'));
      for (const rec of r.recommendations) {
        const d = rec.deal;
        panel.appendChild(h('div.card.deal-card', { style: { padding: '8px 10px', marginBottom: '6px' } },
          h('div', h('strong', productTitle(d)), ' ', dealBadge(d)),
          h('div.small', `${d.chain_name} · ${money(d.effective_price)} each vs ${money(rec.current.effective_price)} at ${rec.current.chain_name}`),
          h('div.small.muted', d.deal?.text || ''),
          h('div', { style: { marginTop: '4px' } },
            h('button.btn.btn-xs.btn-primary', { onclick: async () => {
              await api.removeItem(rec.item_id); await refreshList(await api.addItem(d, rec.qty)); toast(`Switched to ${d.chain_name} deal, saving ${money(rec.savings_total)}`);
            } }, `Switch & save ${money(rec.savings_total)}`))));
      }
    } catch { /* deals are optional */ }
  };

  const saveFlow = async () => {
    const l = state.list;
    if (l.source_list_id) {
      const overwrite = await new Promise((resolve) => modal({ title: 'Save list', body: h('p', `Update "${l.name}" or save as a new list?`), onClose: () => resolve(null), actions: [
        { label: 'Save as new', onClick: () => resolve(false) }, { label: `Update "${l.name}"`, cls: 'btn-primary', onClick: () => resolve(true) }] }));
      if (overwrite === null) return;
      if (overwrite) { await api.saveList(l.name, l.source_list_id); await refreshList(); toast(`Updated "${l.name}"`); return; }
    }
    const name = await promptModal('Save shopping list', { label: 'List name', value: l.source_list_id ? '' : (l.name === 'Current list' ? '' : l.name), placeholder: 'e.g. Weekly groceries' });
    if (!name) return;
    await api.saveList(name); await refreshList(); toast(`Saved "${name}"`);
  };
  const loadFlow = async () => {
    const saved = await api.savedLists();
    const body = h('div');
    if (!saved.length) body.appendChild(h('p.muted', 'No saved lists yet. Add items and click Save.'));
    const strategy = state.settings?.regen_strategy || 'cheapest';
    for (const s of saved) {
      body.appendChild(h('div.loc-row',
        h('div', h('div.loc-name', s.name), h('div.loc-addr', `${s.qty} items · ${money(s.total)} · ${s.stores.join(', ')}`)),
        h('div.spacer'),
        h('button.btn.btn-sm', { onclick: async () => { await refreshList(await api.loadList(s.id, false)); close(); toast(`Loaded "${s.name}"`); } }, 'Load'),
        h('button.btn.btn-sm.btn-primary', { title: 'Load and re-price at your current stores', onclick: async () => { const r = await api.loadList(s.id, true, strategy); await refreshList(r); close(); toast(`Loaded and re-priced "${s.name}"`); } }, 'Load & re-price')));
    }
    const close = modal({ title: 'Load a saved list', body, actions: [{ label: 'Close' }] });
  };
  const regenFlow = async () => {
    const strategy = state.settings?.regen_strategy || 'cheapest';
    const r = await api.regenerate(strategy);
    await refreshList(r);
    const moved = r.changes.filter(c => c.moved).length, missing = r.changes.filter(c => c.status === 'unavailable').length;
    toast(`Re-priced ${r.changes.length} items${moved ? `, ${moved} moved to a cheaper store` : ''}${missing ? `, ${missing} not available at your stores` : ''}`);
  };
  const clearFlow = async () => { if (await confirmModal('Clear list', 'Remove every item from the current list?', { okLabel: 'Clear', danger: true })) { await refreshList(await api.clearList()); } };

  draw();
  return onChange(draw);
}

const CHAIN_COLORS = {};
export function chainColor(slug) { return CHAIN_COLORS[slug] || 'var(--primary)'; }
export function setChainColors(chains) { for (const c of chains) if (c.color) CHAIN_COLORS[c.slug] = c.color; }

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
let cleanup = null;
async function route() {
  const hash = location.hash.replace(/^#\/?/, '') || 'home';
  const [name, ...rest] = hash.split('/');
  const page = pages[name] || pages.home;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.route === (pages[name] ? name : 'home')));
  if (cleanup) { try { cleanup(); } catch {} cleanup = null; }
  const root = clear(document.getElementById('app'));
  try {
    cleanup = await page.render(root, { params: rest, state, refreshList, refreshStores, addToList, renderListSidebar, onChange, chainColor }) || null;
  } catch (e) {
    console.error(e);
    root.appendChild(h('div.alert.alert-danger', `Something went wrong loading this page: ${e.message}`));
  }
}

async function boot() {
  try {
    const st = await api.stores();
    setChainColors(st.chains);
    await Promise.all([loadSettings(), refreshStores(), refreshList()]);
  } catch (e) { toast(`Could not reach the Shopper API: ${e.message}`, 'err', 6000); }
  window.addEventListener('hashchange', route);
  route();
}
boot();
