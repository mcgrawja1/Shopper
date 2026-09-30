// Stores: pick chains and the specific locations to include in searches.
import { api } from '../api.js';
import { h, clear, toast, confirmModal, spinner } from '../ui.js';

export async function render(root, ctx) {
  const { refreshStores } = ctx;
  root.appendChild(h('div.page-head', h('div', h('h1', 'Stores'), h('p.muted', 'Choose the chains and the exact locations you shop at. Only selected locations are searched, so prices and aisles reflect what is actually near you.')),
    h('div.chips', { id: 'store-summary' })));
  const grid = h('div.chain-grid');
  root.appendChild(spinner());
  let data;
  const reload = async () => { data = await api.stores(); draw(); await refreshStores(); };

  const summary = () => {
    const s = root.querySelector('#store-summary'); clear(s);
    const n = data.chains.reduce((a, c) => a + c.selected_count, 0);
    s.appendChild(h('span.pill.pill-accent', `${n} location${n === 1 ? '' : 's'} selected`));
    if (data.home_zip) s.appendChild(h('span.pill', `Home ZIP ${data.home_zip}`));
  };

  const draw = () => {
    root.querySelector('.spinner')?.parentElement.remove();
    clear(grid);
    summary();
    for (const c of data.chains) grid.appendChild(chainCard(c));
    if (!grid.parentElement) root.appendChild(grid);
  };

  const chainCard = (c) => {
    const card = h('div.card.chain-card', { style: { '--chain': c.color || 'var(--primary)' } });
    const allIds = c.locations.map(l => l.id);
    card.appendChild(h('div.card-title',
      h('h3', c.name, c.live ? h('span.badge.badge-live', { title: c.provider_configured ? 'Live prices enabled' : 'Live prices available with API keys (see Settings)' }, c.provider_configured ? 'live' : 'live-capable') : null,
        c.membership_required ? h('span.badge', 'membership') : null),
      h('div', h('button.btn.btn-xs', { onclick: async () => { await api.bulkSelect(allIds, true); await reload(); } }, 'All'), ' ',
        h('button.btn.btn-xs', { onclick: async () => { await api.bulkSelect(allIds, false); await reload(); } }, 'None'))));
    if (c.notes) card.appendChild(h('p.small.muted', c.notes));
    for (const l of c.locations) {
      card.appendChild(h('div.loc-row',
        h('input', { type: 'checkbox', checked: !!l.selected, onchange: async (e) => { await api.selectLocation(l.id, e.target.checked); c.selected_count += e.target.checked ? 1 : -1; l.selected = e.target.checked ? 1 : 0; summary(); await refreshStores(); } }),
        h('div', h('div.loc-name', l.name, l.user_added ? h('span.badge', { style: { marginLeft: '4px' } }, 'mine') : null), h('div.loc-addr', [l.address, l.city, l.state, l.zip].filter(Boolean).join(', '))),
        h('div.spacer'),
        l.user_added ? h('button.btn.btn-xs.btn-danger', { title: 'Remove this location', onclick: async () => { if (await confirmModal('Remove location', `Remove "${l.name}"?`, { okLabel: 'Remove', danger: true })) { await api.deleteLocation(l.id); await reload(); } } }, '✕') : null));
    }
    // add / find
    const adder = h('details.adder', h('summary', '+ Add a location'));
    const nf = { name: h('input', { type: 'text', placeholder: `e.g. ${c.name} - Main St` }), address: h('input', { type: 'text', placeholder: 'Street address' }), city: h('input', { type: 'text', placeholder: 'City' }), state: h('input', { type: 'text', placeholder: 'ST', maxLength: 2 }), zip: h('input', { type: 'text', placeholder: 'ZIP' }) };
    adder.appendChild(h('form', { onsubmit: async (e) => { e.preventDefault(); if (!nf.name.value.trim()) return; await api.addLocation(c.slug, { name: nf.name.value.trim(), address: nf.address.value.trim(), city: nf.city.value.trim(), state: nf.state.value.trim().toUpperCase(), zip: nf.zip.value.trim() }); toast('Location added and selected'); await reload(); } },
      h('div.form-grid', { style: { marginTop: '6px' } }, h('div.field', { style: { gridColumn: '1 / -1' } }, h('label', 'Store name'), nf.name), h('div.field', { style: { gridColumn: '1 / -1' } }, h('label', 'Address'), nf.address), h('div.field', h('label', 'City'), nf.city), h('div.field', h('label', 'State'), nf.state), h('div.field', h('label', 'ZIP'), nf.zip)),
      h('div.form-actions', h('button.btn.btn-sm.btn-primary', { type: 'submit' }, 'Add location'))));
    card.appendChild(adder);
    if (c.live) {
      const zip = h('input', { type: 'text', placeholder: data.home_zip || 'ZIP code', value: data.home_zip || '', style: { maxWidth: '120px' } });
      const radius = h('select', [5, 10, 15, 25, 50].map(r => h('option', { value: r }, `${r} mi`)));
      radius.value = '10';
      const btn = h('button.btn.btn-sm', { type: 'button', disabled: !c.provider_configured, title: c.provider_configured ? '' : 'Add Kroger API keys to enable', onclick: async () => {
        btn.disabled = true; btn.textContent = 'Searching…';
        try { const found = await api.findNearby(c.slug, zip.value.trim(), Number(radius.value)); toast(`Found ${found.length} ${c.name} stores. Tick the ones you shop at.`); await reload(); }
        catch (e) { toast(e.message, 'err', 5000); btn.disabled = false; btn.textContent = '📍 Find nearby'; }
      } }, '📍 Find nearby');
      card.appendChild(h('div.form-actions', zip, radius, btn, !c.provider_configured ? h('span.small.muted', 'Needs API keys (Settings → Live providers)') : null));
    }
    return card;
  };

  await reload();
}
