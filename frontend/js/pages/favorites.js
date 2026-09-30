// Favorites: everything ever added to a list, ready to re-add without searching.
import { api } from '../api.js';
import { h, clear, money, toast, modal, confirmModal, unitPrice, dealBadge, productTitle, spinner, qtyBox } from '../ui.js';

export async function render(root, ctx) {
  const { addToList, state } = ctx;
  const filter = h('input', { type: 'search', placeholder: 'Filter favorites…', style: { maxWidth: '280px' } });
  root.appendChild(h('div.page-head', h('div', h('h1', 'Favorites'), h('p.muted', 'Items you have added to a shopping list before. Add them again at the best current price without searching.')), filter));
  const grid = h('div.fav-grid');
  root.appendChild(spinner());
  let favs = [];
  const reload = async () => { favs = await api.favorites(); draw(); };
  const draw = () => {
    root.querySelector('.spinner')?.parentElement.remove();
    clear(grid);
    const q = filter.value.trim().toLowerCase();
    const shown = favs.filter(f => !q || `${f.brand} ${f.name} ${f.size_text} ${f.category}`.toLowerCase().includes(q));
    if (!favs.length) grid.appendChild(h('div.empty', 'No favorites yet. Anything you add to a shopping list shows up here automatically.'));
    else if (!shown.length) grid.appendChild(h('div.empty', 'Nothing matches that filter.'));
    for (const f of shown) grid.appendChild(favCard(f));
    if (!grid.parentElement) root.appendChild(grid);
  };
  filter.addEventListener('input', draw);

  const favCard = (f) => h('div.card.fav-card',
    h('div.card-title', h('div', h('strong', productTitle(f)), h('div.small.muted', [f.size_text, f.category].filter(Boolean).join(' · '))),
      h('button.btn.btn-icon.btn-xs', { title: f.pinned ? 'Unpin' : 'Pin to top', onclick: async () => { await api.pinFavorite(f.id, !f.pinned); await reload(); } }, f.pinned ? '📌' : '📍')),
    h('div.small', `Last: ${money(f.effective_price)} at ${f.chain_name}`, f.unit_price ? ` · ${unitPrice(f)}` : ''),
    h('div.small.muted', `Added ${f.times_added} time${f.times_added === 1 ? '' : 's'}`),
    h('div.fav-actions',
      h('button.btn.btn-sm.btn-primary', { onclick: () => addBest(f) }, '+ Add cheapest'),
      h('button.btn.btn-sm', { onclick: () => chooseStore(f) }, 'Choose store…'),
      h('button.btn.btn-sm', { title: 'Search for this item', onclick: () => { location.hash = `#/home/search?${new URLSearchParams({ brand: f.brand === 'Fresh' ? '' : f.brand, item: f.name, size: f.size_text || '' })}`; } }, '🔍'),
      h('button.btn.btn-sm.btn-danger', { title: 'Remove favorite', onclick: async () => { if (await confirmModal('Remove favorite', `Remove ${productTitle(f)} from favorites?`, { okLabel: 'Remove', danger: true })) { await api.deleteFavorite(f.id); await reload(); } } }, '✕')));

  const priced = async (f) => {
    const r = await api.lookup(f.product_key, state.settings?.default_sort || 'unit_price');
    const inStock = r.offers.filter(o => o.in_stock);
    return inStock.length ? inStock : r.offers;
  };
  const addBest = async (f) => {
    try {
      const offers = await priced(f);
      if (!offers.length) { toast('Not available at your selected stores right now', 'err'); return; }
      await addToList(offers[0], 1);
    } catch (e) { toast(e.message, 'err'); }
  };
  const chooseStore = async (f) => {
    let offers;
    try { offers = await priced(f); } catch (e) { toast(e.message, 'err'); return; }
    const body = h('div');
    if (!offers.length) body.appendChild(h('p.muted', 'Not available at your selected stores.'));
    let qty = 1;
    body.appendChild(h('div.form-actions', h('span.small.muted', 'Quantity'), qtyBox(1, v => { qty = v; })));
    for (const o of offers) body.appendChild(h('div.loc-row',
      h('div', h('div.loc-name', o.chain_name, ' ', dealBadge(o)), h('div.loc-addr', `${o.location_name} · ${o.aisle || 'aisle unknown'}`)),
      h('div.spacer'),
      h('div.right', h('div.price-main', money(o.effective_price)), h('div.small.muted', unitPrice(o))),
      h('button.btn.btn-sm.btn-primary', { onclick: async () => { await addToList(o, qty); close(); } }, 'Add')));
    const close = modal({ title: productTitle(f), body, actions: [{ label: 'Close' }] });
  };

  await reload();
}
