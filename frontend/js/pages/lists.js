// Shopping Lists: saved lists to reload, re-price, rename or delete.
import { api } from '../api.js';
import { h, clear, money, toast, confirmModal, promptModal, fmtDate, productTitle, spinner } from '../ui.js';

export async function render(root, ctx) {
  const { refreshList, state } = ctx;
  root.appendChild(h('div.page-head', h('div', h('h1', 'Shopping Lists'), h('p.muted', 'Saved lists. Load one to make it your current list, or load & re-price to refresh every item against today\'s prices at your selected stores.')),
    h('a.btn', { href: '#/home' }, '← Back to current list')));
  const box = h('div');
  root.appendChild(spinner());
  let lists = [];
  const reload = async () => { lists = await api.savedLists(); draw(); };
  const strategy = () => state.settings?.regen_strategy || 'cheapest';

  const draw = () => {
    root.querySelector('.spinner')?.parentElement.remove();
    clear(box);
    if (!lists.length) { box.appendChild(h('div.empty', 'No saved lists yet. Build a list on the Home page and click Save.')); }
    else {
      const tbl = h('table.data', h('thead', h('tr', h('th', 'Name'), h('th', 'Items'), h('th', 'Stores'), h('th', 'Total'), h('th', 'Updated'), h('th', ''))));
      const tb = h('tbody');
      for (const l of lists) {
        const row = h('tr');
        const detail = h('tr.hidden', h('td', { colSpan: 6 }));
        row.append(
          h('td', h('a', { href: '#', onclick: (e) => { e.preventDefault(); toggleDetail(l, detail); } }, h('strong', l.name)), state.list?.source_list_id === l.id ? h('span.badge.badge-best', { style: { marginLeft: '6px' } }, 'current') : null),
          h('td', `${l.qty}`), h('td.small', l.stores.join(', ')), h('td', money(l.total)), h('td.small.muted', fmtDate(l.updated_at)),
          h('td.right', { style: { whiteSpace: 'nowrap' } },
            h('button.btn.btn-sm', { onclick: async () => { await refreshList(await api.loadList(l.id, false)); toast(`Loaded "${l.name}"`); location.hash = '#/home'; } }, 'Load'), ' ',
            h('button.btn.btn-sm.btn-primary', { onclick: async () => { const r = await api.loadList(l.id, true, strategy()); await refreshList(r); const moved = r.changes.filter(c => c.moved).length; toast(`Loaded & re-priced "${l.name}"${moved ? ` (${moved} items moved to a cheaper store)` : ''}`); location.hash = '#/home'; } }, 'Load & re-price'), ' ',
            h('button.btn.btn-sm', { onclick: async () => { const n = await promptModal('Rename list', { value: l.name, okLabel: 'Rename' }); if (n) { await api.renameList(l.id, n); await reload(); } } }, 'Rename'), ' ',
            h('button.btn.btn-sm.btn-danger', { onclick: async () => { if (await confirmModal('Delete list', `Delete "${l.name}"? This cannot be undone.`, { okLabel: 'Delete', danger: true })) { await api.deleteList(l.id); await reload(); } } }, 'Delete')));
        tb.append(row, detail);
      }
      tbl.appendChild(tb);
      box.appendChild(h('div.card', tbl));
    }
    if (!box.parentElement) root.appendChild(box);
  };

  const toggleDetail = async (l, tr) => {
    if (!tr.classList.contains('hidden')) { tr.classList.add('hidden'); return; }
    const td = tr.firstChild; clear(td); td.appendChild(spinner());
    tr.classList.remove('hidden');
    const full = await api.savedList(l.id);
    clear(td);
    for (const s of full.breakdown.stores) {
      const st = h('div.list-store', { style: { '--chain': ctx.chainColor(s.chain_slug) } });
      st.appendChild(h('div.list-store-head', h('div', h('div.store-name', s.chain_name), h('div.addr', s.location_name)), h('div.price-main', money(s.subtotal))));
      for (const a of s.aisles) {
        const al = h('div.list-aisle', h('h5', a.aisle));
        for (const it of a.items) al.appendChild(h('div.list-item', h('div', h('div.li-name', productTitle(it)), h('div.li-meta', it.size_text)), h('div', `× ${it.qty}`), h('div.right.price-main', money(it.line_total))));
        st.appendChild(al);
      }
      td.appendChild(st);
    }
  };

  await reload();
}
