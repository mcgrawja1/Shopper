// Home: search form (top), results (below), current list (right sidebar).
import { api } from '../api.js';
import { h, clear, money, toast, autocomplete, unitPrice, unitPriceAlt, dealBadge, productTitle, spinner, qtyBox } from '../ui.js';

const CATEGORIES = ['Beverages', 'Dairy', 'Produce', 'Meat', 'Bakery', 'Pantry', 'Breakfast', 'Snacks', 'Frozen', 'Canned Goods', 'Condiments', 'Household', 'Personal Care', 'Baby', 'Pet', 'Deli'];
let lastQuery = null; // remembered across navigation

export async function render(root, ctx) {
  const { state, addToList, renderListSidebar, chainColor } = ctx;
  const layout = h('div.home-layout');
  const main = h('div');
  const side = h('aside.sidebar');
  layout.append(main, side);
  root.appendChild(layout);

  // ----- Search form -------------------------------------------------------
  const f = {
    brand: h('input', { type: 'text', placeholder: 'e.g. Kraft (optional)' }),
    item: h('input', { type: 'text', placeholder: 'e.g. macaroni and cheese, bananas', required: true }),
    size: h('input', { type: 'text', placeholder: 'e.g. 12 pack, 16 oz (optional)' }),
    category: h('select', h('option', { value: '' }, 'Any category'), CATEGORIES.map(c => h('option', { value: c }, c))),
    sort: h('select',
      h('option', { value: 'unit_price' }, 'Lowest unit price'), h('option', { value: 'price' }, 'Lowest total price'),
      h('option', { value: 'relevance' }, 'Best match'), h('option', { value: 'store' }, 'Store')),
    inStock: h('input', { type: 'checkbox' }),
  };
  f.sort.value = state.settings?.default_sort || 'unit_price';
  f.inStock.checked = !!state.settings?.in_stock_only;

  const storeChips = h('div.chips');
  const storeSel = new Set(state.selected.map(s => s.id));
  const drawStoreChips = () => {
    clear(storeChips);
    if (!state.selected.length) { storeChips.appendChild(h('span.small.muted', 'No stores selected. ', h('a', { href: '#/stores' }, 'Choose your stores →'))); return; }
    storeChips.appendChild(h('span.chip', { className: `chip ${storeSel.size === state.selected.length ? 'on' : ''}`, onclick: () => { state.selected.forEach(s => storeSel.add(s.id)); drawStoreChips(); } }, 'All'));
    for (const s of state.selected) {
      storeChips.appendChild(h('span.chip', { className: `chip ${storeSel.has(s.id) ? 'on' : ''}`, title: s.address, style: storeSel.has(s.id) ? { background: chainColor(s.chain_slug), borderColor: chainColor(s.chain_slug) } : {},
        onclick: () => { if (storeSel.has(s.id)) { if (storeSel.size > 1) storeSel.delete(s.id); } else storeSel.add(s.id); drawStoreChips(); } }, `${s.chain_name} · ${s.name.replace(s.chain_name, '').replace(/^[\s\-–]+/, '') || s.name}`));
    }
  };
  drawStoreChips();

  const form = h('form.card.search-card', { onsubmit: (e) => { e.preventDefault(); runSearch(); } },
    h('div.card-title', h('h2', 'Find the best price'), h('span.small.muted', 'Start typing for suggestions')),
    h('div.form-grid',
      h('div.field', h('label', 'Brand'), f.brand),
      h('div.field', { style: { gridColumn: 'span 2' } }, h('label', 'Product / item'), f.item),
      h('div.field', h('label', 'Size / pack'), f.size),
      h('div.field', h('label', 'Category'), f.category),
      h('div.field', h('label', 'Sort by'), f.sort)),
    h('div.field', { style: { marginTop: '10px' } }, h('label', 'Search these stores'), storeChips),
    h('div.form-actions',
      h('button.btn.btn-primary', { type: 'submit' }, '🔍 Search'),
      h('button.btn', { type: 'button', onclick: () => { f.brand.value = f.item.value = f.size.value = ''; f.category.value = ''; clear(results); lastQuery = null; f.item.focus(); } }, 'Clear'),
      h('label.check', f.inStock, ' In-stock only'),
      h('span.small.muted', { style: { marginLeft: 'auto' } }, 'Tip: use the size field to jump straight to a pack size, e.g. "24 pack"')));
  main.appendChild(form);
  autocomplete(f.brand, 'brand');
  autocomplete(f.item, 'item', { onPick: () => runSearch() });
  autocomplete(f.size, 'size');

  const results = h('div.results');
  main.appendChild(results);

  // ----- Results -----------------------------------------------------------
  let variantFilter = null;
  async function runSearch(prefill) {
    if (prefill) { f.brand.value = prefill.brand || ''; f.item.value = prefill.item || ''; f.size.value = prefill.size || ''; f.category.value = prefill.category || ''; }
    const q = { brand: f.brand.value.trim(), item: f.item.value.trim(), size: f.size.value.trim(), category: f.category.value, sort: f.sort.value,
      in_stock_only: f.inStock.checked, locations: storeSel.size && storeSel.size !== state.selected.length ? [...storeSel].join(',') : '' };
    if (!q.brand && !q.item && !q.size) { toast('Enter a brand, item or size to search', 'err'); return; }
    lastQuery = q; variantFilter = null;
    clear(results); results.appendChild(spinner('Searching your stores…'));
    try {
      const r = await api.search(q);
      drawResults(r);
    } catch (e) { clear(results); results.appendChild(h('div.alert.alert-danger', `Search failed: ${e.message}`)); }
  }

  function drawResults(r) {
    clear(results);
    for (const w of r.warnings) results.appendChild(h('div.alert.alert-warn', w));
    if (!r.groups.length) { results.appendChild(h('div.empty', `No matches for "${[r.query.brand, r.query.item, r.query.size].filter(Boolean).join(' ')}" at your selected stores. Try a broader term or add more stores.`)); return; }

    const head = h('div.card', { style: { padding: '10px 14px' } });
    head.appendChild(h('div.card-title', h('h3', `${r.groups.length} matching product${r.groups.length === 1 ? '' : 's'} · ${r.offers.length} price${r.offers.length === 1 ? '' : 's'} across ${r.stores_searched.length} store${r.stores_searched.length === 1 ? '' : 's'}`),
      h('span.small.muted', `Sorted by ${f.sort.options[f.sort.selectedIndex].text.toLowerCase()}`)));
    if (r.variants.length > 1) {
      const chips = h('div.chips');
      const draw = () => {
        clear(chips);
        chips.appendChild(h('span.chip', { className: `chip ${variantFilter ? '' : 'on'}`, onclick: () => { variantFilter = null; draw(); drawGroups(); } }, 'All sizes'));
        for (const v of r.variants) chips.appendChild(h('span.chip', { className: `chip ${variantFilter === v.size_text ? 'on' : ''}`, onclick: () => { variantFilter = variantFilter === v.size_text ? null : v.size_text; draw(); drawGroups(); } }, `${v.size_text}`, v.count > 1 ? ` (${v.count})` : ''));
      };
      draw();
      head.appendChild(h('div.field', h('label', 'Choose a size / pack'), chips));
    }
    results.appendChild(head);
    const groupsBox = h('div');
    results.appendChild(groupsBox);
    const drawGroups = () => {
      clear(groupsBox);
      const gs = r.groups.filter(g => !variantFilter || g.size_text === variantFilter);
      gs.forEach((g, i) => groupsBox.appendChild(groupCard(g, i === 0)));
    };
    drawGroups();
  }

  function groupCard(g, isTop) {
    const best = g.best;
    const card = h('div.result-group');
    let open = isTop || g.offers.length <= 3;
    const body = h('div.rg-body');
    const headEl = h('div.rg-head', { onclick: (e) => { if (e.target.closest('button')) return; open = !open; drawBody(); } },
      h('div.rg-thumb', g.image_url ? h('img', { src: g.image_url, alt: '' }) : categoryIcon(g.category)),
      h('div', h('div.rg-name', productTitle(g), ' ', isTop ? h('span.badge.badge-best', 'Best unit price') : null, g.has_deal ? h('span.badge.badge-deal', { style: { marginLeft: '4px' } }, 'Deal') : null),
        h('div.rg-meta', [g.size_text, g.category, g.upc ? `UPC ${g.upc}` : ''].filter(Boolean).join(' · '), ` · ${g.offers.length} store${g.offers.length === 1 ? '' : 's'}`,
          g.price_range[0] !== g.price_range[1] ? ` · ${money(g.price_range[0])} – ${money(g.price_range[1])}` : '')),
      h('div.rg-price', h('div.big', money(best.effective_price)), h('div.small.muted', `${unitPrice(best)} · ${best.chain_name}`)),
      h('button.btn.btn-sm.btn-primary', { onclick: () => addToList(best, 1), title: `Add the cheapest option (${best.chain_name})` }, '+ Add best'));
    card.append(headEl, body);
    const drawBody = () => {
      clear(body);
      if (!open) { body.appendChild(h('div.small.muted', { style: { padding: '6px 8px', cursor: 'pointer' }, onclick: () => { open = true; drawBody(); } }, `Show all ${g.offers.length} stores ▾`)); return; }
      const tbl = h('table.offers', h('thead', h('tr', h('th', 'Store'), h('th', 'Price'), h('th', 'Per unit'), h('th', 'Aisle'), h('th', 'Deal'), h('th.right', 'Qty / Add'))));
      const tb = h('tbody');
      g.offers.forEach((o, i) => {
        let qty = 1;
        tb.appendChild(h('tr', { className: `${i === 0 ? 'best' : ''} ${o.in_stock ? '' : 'oos'}`, style: { '--chain': chainColor(o.chain_slug) } },
          h('td', h('div.store-name', o.chain_name, o.provider !== 'catalog' ? h('span.badge.badge-live', { style: { marginLeft: '4px' } }, 'live') : null), h('div.store-loc', o.location_name, o.location_address ? h('span.addr', ` · ${o.location_address}`) : null)),
          h('td', h('span.price-main', money(o.effective_price)), o.effective_price < o.price ? h('span.price-strike', money(o.price)) : null),
          h('td', h('div', unitPrice(o)), h('div.small.muted', unitPriceAlt(o))),
          h('td', h('div', o.aisle || '—'), h('div.small.muted', o.section && o.section !== o.aisle ? o.section : '')),
          h('td', dealBadge(o), o.deal?.text ? h('div.small.muted', o.deal.text) : null, o.in_stock ? null : h('span.badge.badge-oos', 'Out of stock')),
          h('td.right', h('div', { style: { display: 'inline-flex', gap: '6px', alignItems: 'center' } }, qtyBox(1, (v) => { qty = v; }), h('button.btn.btn-sm', { onclick: () => addToList(o, qty) }, 'Add')))));
      });
      tbl.appendChild(tb);
      body.appendChild(tbl);
      if (g.offers.length > 3) body.appendChild(h('div.small.muted', { style: { padding: '6px 8px', cursor: 'pointer' }, onclick: () => { open = false; drawBody(); } }, 'Collapse ▴'));
    };
    drawBody();
    return card;
  }

  // ----- Sidebar -------------------------------------------------------------
  const unsub = renderListSidebar(side);

  // restore last query or handle a prefill from favorites (#/home/search?...)
  const pre = ctx.params[0] === 'search' ? Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || '')) : null;
  if (pre) { history.replaceState(null, '', '#/home'); runSearch(pre); }
  else if (lastQuery) { runSearch(lastQuery); }
  else setTimeout(() => f.item.focus(), 0);
  return unsub;
}

function categoryIcon(c) {
  return { Beverages: '🥤', Dairy: '🥛', Produce: '🍌', Meat: '🥩', Bakery: '🍞', Pantry: '🥫', Breakfast: '🥣', Snacks: '🍿', Frozen: '🧊', 'Canned Goods': '🥫', Condiments: '🧂', Household: '🧻', 'Personal Care': '🧴', Baby: '🍼', Pet: '🐾', Deli: '🧀' }[c] || '🛒';
}
