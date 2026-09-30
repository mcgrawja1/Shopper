// Settings: preferences, live provider status, and rewards / subscription accounts (Phase 2).
import { api } from '../api.js';
import { h, clear, toast, confirmModal, spinner } from '../ui.js';

export async function render(root, ctx) {
  root.appendChild(h('div.page-head', h('div', h('h1', 'Settings'))));
  root.appendChild(spinner());
  const data = await api.settings();
  const chains = (await api.stores()).chains;
  root.querySelector('.spinner')?.parentElement.remove();
  ctx.state.settings = data.settings;

  // --- Preferences --------------------------------------------------------
  const s = data.settings;
  const f = {
    home_zip: h('input', { type: 'text', value: s.home_zip || '', placeholder: '32504', maxLength: 10 }),
    search_radius: h('input', { type: 'number', value: s.search_radius, min: 1, max: 100 }),
    default_sort: h('select', h('option', { value: 'unit_price' }, 'Lowest unit price'), h('option', { value: 'price' }, 'Lowest total price'), h('option', { value: 'relevance' }, 'Best match'), h('option', { value: 'store' }, 'Store')),
    regen_strategy: h('select', h('option', { value: 'cheapest' }, 'Move each item to the cheapest store'), h('option', { value: 'same_store' }, 'Keep the same store, refresh the price')),
    in_stock_only: h('input', { type: 'checkbox', checked: !!s.in_stock_only }),
    show_deals: h('input', { type: 'checkbox', checked: s.show_deals !== false }),
  };
  f.default_sort.value = s.default_sort || 'unit_price';
  f.regen_strategy.value = s.regen_strategy || 'cheapest';
  root.appendChild(h('form.card', { onsubmit: async (e) => { e.preventDefault(); const body = { home_zip: f.home_zip.value.trim(), search_radius: Number(f.search_radius.value) || 10, default_sort: f.default_sort.value, regen_strategy: f.regen_strategy.value, in_stock_only: f.in_stock_only.checked, show_deals: f.show_deals.checked }; ctx.state.settings = await api.saveSettings(body); toast('Settings saved'); } },
    h('h2', 'Preferences'),
    h('div.form-grid',
      h('div.field', h('label', 'Home ZIP code'), f.home_zip, h('span.small.muted', 'Used to find nearby stores for live providers')),
      h('div.field', h('label', 'Search radius (miles)'), f.search_radius),
      h('div.field', h('label', 'Default result sorting'), f.default_sort),
      h('div.field', h('label', 'When re-pricing a saved list'), f.regen_strategy)),
    h('div.form-actions', h('label.check', f.in_stock_only, ' Hide out-of-stock items by default'), h('label.check', f.show_deals, ' Recommend better deals for items on my list')),
    h('div.form-actions', h('button.btn.btn-primary', { type: 'submit' }, 'Save preferences'))));

  // --- Providers ----------------------------------------------------------
  const prov = h('div.card', h('h2', 'Live price providers'),
    h('p.small.muted', 'Shopper ships with a sample catalog so every page works out of the box. Connect a live provider to search real inventory, prices and aisle locations. Keys are read from the server environment (.env) and are never stored in the browser.'));
  for (const p of data.providers) prov.appendChild(h('div.loc-row',
    h('div', h('div.loc-name', p.name, ' ', p.live ? h('span.badge.badge-live', 'live') : h('span.badge', 'built-in')), h('div.loc-addr', p.description)),
    h('div.spacer'),
    h('span.badge', { className: `badge ${p.configured ? 'badge-best' : 'badge-oos'}` }, p.configured ? 'Connected' : 'Not configured')));
  prov.appendChild(h('details', { style: { marginTop: '.5rem' } }, h('summary', { style: { cursor: 'pointer' } }, 'How to connect Kroger'),
    h('ol.small', h('li', 'Create a free developer account at developer.kroger.com and register an application with the Products and Locations APIs.'),
      h('li', 'Put the client ID and secret in the .env file next to docker-compose.yml as KROGER_CLIENT_ID and KROGER_CLIENT_SECRET.'),
      h('li', 'Run "docker compose up -d" again. Then use "Find nearby" on the Stores page to add your real Kroger-family stores.'))));
  root.appendChild(prov);

  // --- Accounts (Phase 2) -------------------------------------------------
  const acct = h('div.card');
  const list = h('div');
  const af = { chain: h('select', h('option', { value: '' }, 'Any / not store-specific'), chains.map(c => h('option', { value: c.slug }, c.name))), program: h('input', { type: 'text', placeholder: 'e.g. Walmart+, Kroger Plus, Sam\'s Club Plus' }), kind: h('select', h('option', { value: 'rewards' }, 'Rewards / loyalty'), h('option', { value: 'membership' }, 'Membership'), h('option', { value: 'subscription' }, 'Subscription'), h('option', { value: 'coupon' }, 'Digital coupons')), member_id: h('input', { type: 'text', placeholder: 'Member / card number (optional)' }), username: h('input', { type: 'text', placeholder: 'Login email (optional)' }), notes: h('input', { type: 'text', placeholder: 'Notes, e.g. 2% back on fuel' }) };
  const drawAccounts = () => {
    clear(list);
    if (!data.accounts.length) list.appendChild(h('div.empty', 'No accounts added yet.'));
    for (const a of data.accounts) list.appendChild(h('div.loc-row',
      h('div', h('div.loc-name', a.program, ' ', h('span.badge', a.kind), a.chain_slug ? h('span.badge', { style: { marginLeft: '4px' } }, chains.find(c => c.slug === a.chain_slug)?.name || a.chain_slug) : null),
        h('div.loc-addr', [a.member_id && `# ${a.member_id}`, a.username, a.notes].filter(Boolean).join(' · '))),
      h('div.spacer'),
      h('button.btn.btn-xs.btn-danger', { onclick: async () => { if (await confirmModal('Remove account', `Remove ${a.program}?`, { okLabel: 'Remove', danger: true })) { await api.deleteAccount(a.id); data.accounts = data.accounts.filter(x => x.id !== a.id); drawAccounts(); } } }, '✕')));
  };
  acct.append(h('h2', 'Rewards, memberships & subscriptions'),
    h('p.small.muted', 'Track the programs you belong to so deal recommendations can call out member-only pricing (e.g. Winn-Dixie rewards BOGOs, Target Circle offers). Passwords are never stored here.'),
    list,
    h('form', { onsubmit: async (e) => { e.preventDefault(); if (!af.program.value.trim()) return; const a = await api.addAccount({ chain_slug: af.chain.value || null, program: af.program.value.trim(), kind: af.kind.value, member_id: af.member_id.value.trim(), username: af.username.value.trim(), notes: af.notes.value.trim() }); data.accounts.push(a); af.program.value = af.member_id.value = af.username.value = af.notes.value = ''; drawAccounts(); toast('Account added'); } },
      h('h4', { style: { marginTop: '1rem' } }, 'Add an account'),
      h('div.form-grid', h('div.field', h('label', 'Store'), af.chain), h('div.field', h('label', 'Program'), af.program), h('div.field', h('label', 'Type'), af.kind), h('div.field', h('label', 'Member ID'), af.member_id), h('div.field', h('label', 'Username'), af.username), h('div.field', h('label', 'Notes'), af.notes)),
      h('div.form-actions', h('button.btn.btn-primary', { type: 'submit' }, 'Add account'))));
  drawAccounts();
  root.appendChild(acct);

  root.appendChild(h('div.card', h('h2', 'About'), h('p.small.muted', 'Shopper runs entirely on your own server. Data lives in a SQLite database on the Docker volume "shopper-data". Sample prices are illustrative until a live provider is connected.')));
}
