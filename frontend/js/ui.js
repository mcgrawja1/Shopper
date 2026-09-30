// Small DOM helpers, toasts, modals and the autocomplete widget.
import { api } from './api.js';

/** h('div.card#id', {onclick, title}, children...) */
export function h(tag, attrs, ...children) {
  if (attrs && (typeof attrs !== 'object' || attrs instanceof Node || Array.isArray(attrs))) { children.unshift(attrs); attrs = {}; }
  const [name, ...rest] = tag.split(/(?=[.#])/);
  const el = document.createElement(name || 'div');
  for (const r of rest) { if (r[0] === '.') el.classList.add(r.slice(1)); else el.id = r.slice(1); }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'html') el.innerHTML = v;
    else if (k in el && k !== 'list') { try { el[k] = v; } catch { el.setAttribute(k, v); } }
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, children);
  return el;
}
function append(el, children) {
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else if (c instanceof Node) el.appendChild(c);
    else el.appendChild(document.createTextNode(String(c)));
  }
}
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

export const money = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : `$${Number(n).toFixed(2)}`;
export function unitPrice(o) {
  if (o.unit_price === null || o.unit_price === undefined) return '—';
  const up = o.unit_price < 0.1 ? `${(o.unit_price * 100).toFixed(1)}¢` : `$${o.unit_price.toFixed(2)}`;
  return `${up}/${o.unit_label}`;
}
export function unitPriceAlt(o) {
  return (o.unit_price_alt !== null && o.unit_price_alt !== undefined) ? `${money(o.unit_price_alt)}/${o.unit_label_alt}` : '';
}
export const fmtDate = (iso) => iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '';
export const productTitle = (o) => [o.brand, o.name].filter(Boolean).join(' ');

export function toast(msg, kind = 'ok', ms = 2600) {
  const root = document.getElementById('toasts');
  const t = h('div.toast', { className: `toast ${kind === 'err' ? 'err' : ''}` }, msg);
  root.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

export function modal({ title, body, actions = [], onClose }) {
  const root = document.getElementById('modal-root');
  const close = () => { bg.remove(); onClose && onClose(); };
  const bg = h('div.modal-bg', { onclick: (e) => { if (e.target === bg) close(); } });
  const box = h('div.modal', h('h2', title), body,
    h('div.modal-actions', actions.map(a => h('button.btn', { className: `btn ${a.cls || ''}`, onclick: async () => { const r = await a.onClick?.(close); if (r !== false && a.close !== false) close(); } }, a.label))));
  bg.appendChild(box);
  root.appendChild(bg);
  const esc = (e) => { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } };
  document.addEventListener('keydown', esc);
  return close;
}

export function confirmModal(title, text, { okLabel = 'OK', danger = false } = {}) {
  return new Promise((resolve) => {
    modal({ title, body: h('p', text), onClose: () => resolve(false), actions: [
      { label: 'Cancel', onClick: () => resolve(false) },
      { label: okLabel, cls: danger ? 'btn-danger' : 'btn-primary', onClick: () => resolve(true) },
    ] });
  });
}

export function promptModal(title, { label = 'Name', value = '', okLabel = 'Save', placeholder = '' } = {}) {
  return new Promise((resolve) => {
    const input = h('input', { type: 'text', value, placeholder });
    const submit = () => { const v = input.value.trim(); if (!v) return false; resolve(v); return true; };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && submit()) close(); });
    const close = modal({ title, body: h('div.field', h('label', label), input), onClose: () => resolve(null), actions: [
      { label: 'Cancel', onClick: () => resolve(null) },
      { label: okLabel, cls: 'btn-primary', onClick: () => submit() },
    ] });
    setTimeout(() => input.focus(), 0);
  });
}

/** Attach autocomplete to a text input. field: brand|item|size|category */
export function autocomplete(input, field, { onPick } = {}) {
  const wrap = input.parentElement;
  const list = h('div.ac-list');
  wrap.appendChild(list);
  let items = [], idx = -1, timer = null, seq = 0;
  const close = () => { clear(list); list.classList.remove('open'); idx = -1; };
  const pick = (v) => { input.value = v; close(); onPick && onPick(v); };
  const render = () => {
    clear(list);
    if (!items.length) return close();
    items.forEach((it, i) => list.appendChild(h('div.ac-item', { className: `ac-item ${i === idx ? 'active' : ''}`, onmousedown: (e) => { e.preventDefault(); pick(it.value); } },
      h('span', it.value), h('span.src', it.source === 'history' ? 'recent' : ''))));
    list.classList.add('open');
  };
  const load = async () => {
    const my = ++seq;
    try {
      const res = await api.autocomplete(field, input.value.trim());
      if (my !== seq) return;
      items = res.filter(r => r.value.toLowerCase() !== input.value.trim().toLowerCase() || res.length > 1);
      idx = -1; render();
    } catch { close(); }
  };
  input.setAttribute('autocomplete', 'off');
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 120); });
  input.addEventListener('focus', () => { if (!list.classList.contains('open')) load(); });
  input.addEventListener('blur', () => setTimeout(close, 120));
  input.addEventListener('keydown', (e) => {
    if (!list.classList.contains('open')) { if (e.key === 'ArrowDown') load(); return; }
    if (e.key === 'ArrowDown') { idx = Math.min(idx + 1, items.length - 1); render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { idx = Math.max(idx - 1, -1); render(); e.preventDefault(); }
    else if (e.key === 'Enter' && idx >= 0) { pick(items[idx].value); e.preventDefault(); }
    else if (e.key === 'Escape') close();
    else if (e.key === 'Tab' && idx >= 0) pick(items[idx].value);
  });
}

export function qtyBox(value, onChange) {
  const span = h('span', value);
  return h('div.qty-box',
    h('button', { type: 'button', onclick: () => { if (value > 1) { value--; span.textContent = value; onChange(value); } } }, '−'),
    span,
    h('button', { type: 'button', onclick: () => { if (value < 99) { value++; span.textContent = value; onChange(value); } } }, '+'));
}

export function dealBadge(o) {
  if (!o.deal) return null;
  const t = o.deal.type;
  const label = t === 'bogo' ? 'BOGO' : t === 'multibuy' ? (o.deal.text || `${o.deal.qty} for ${money(o.deal.price)}`) : t === 'coupon' ? 'Coupon' : 'Sale';
  return h('span.badge.badge-deal', { title: o.deal.text || '' }, label);
}

export function spinner(text = 'Loading…') { return h('div.muted', { style: { padding: '1rem' } }, h('span.spinner'), ' ', text); }
