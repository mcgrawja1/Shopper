// Thin fetch wrapper around the Shopper API.
async function req(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const j = await r.json(); msg = j.detail ? (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)) : msg; } catch {}
    throw new Error(msg);
  }
  return r.status === 204 ? null : r.json();
}
const qs = (o) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o || {})) if (v !== undefined && v !== null && v !== '') p.set(k, v); const s = p.toString(); return s ? `?${s}` : ''; };

export const api = {
  health: () => req('GET', '/api/health'),
  search: (params) => req('GET', `/api/search${qs(params)}`),
  lookup: (product_key, sort) => req('GET', `/api/lookup${qs({ product_key, sort })}`),
  autocomplete: (field, q) => req('GET', `/api/autocomplete${qs({ field, q })}`),

  stores: () => req('GET', '/api/stores'),
  selectedStores: () => req('GET', '/api/stores/selected'),
  selectLocation: (id, selected) => req('PATCH', `/api/stores/locations/${id}`, { selected }),
  bulkSelect: (location_ids, selected) => req('POST', '/api/stores/locations/select', { location_ids, selected }),
  addLocation: (chain, body) => req('POST', `/api/stores/${chain}/locations`, body),
  deleteLocation: (id) => req('DELETE', `/api/stores/locations/${id}`),
  findNearby: (chain, zip, radius) => req('POST', `/api/stores/${chain}/find${qs({ zip, radius })}`),

  favorites: () => req('GET', '/api/favorites'),
  pinFavorite: (id, pinned) => req('PATCH', `/api/favorites/${id}`, { pinned }),
  deleteFavorite: (id) => req('DELETE', `/api/favorites/${id}`),

  currentList: () => req('GET', '/api/lists/current'),
  addItem: (offer, qty = 1) => req('POST', '/api/lists/current/items', { offer, qty }),
  patchItem: (id, patch) => req('PATCH', `/api/lists/current/items/${id}`, patch),
  removeItem: (id) => req('DELETE', `/api/lists/current/items/${id}`),
  clearList: () => req('DELETE', '/api/lists/current'),
  saveList: (name, overwrite_id) => req('POST', '/api/lists/current/save', { name, overwrite_id }),
  regenerate: (strategy) => req('POST', '/api/lists/current/regenerate', { strategy }),
  savedLists: () => req('GET', '/api/lists'),
  savedList: (id) => req('GET', `/api/lists/${id}`),
  loadList: (id, regenerate, strategy) => req('POST', `/api/lists/${id}/load${qs({ regenerate, strategy })}`),
  renameList: (id, name) => req('PATCH', `/api/lists/${id}`, { name }),
  deleteList: (id) => req('DELETE', `/api/lists/${id}`),

  settings: () => req('GET', '/api/settings'),
  saveSettings: (body) => req('PUT', '/api/settings', body),
  addAccount: (body) => req('POST', '/api/settings/accounts', body),
  deleteAccount: (id) => req('DELETE', `/api/settings/accounts/${id}`),

  deals: () => req('GET', '/api/deals'),
  dealsForList: () => req('GET', '/api/deals/for-list'),
};
