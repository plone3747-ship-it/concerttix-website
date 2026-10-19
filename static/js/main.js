/* ConcertTix - shared front-end behaviour */
(function () {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } },
  };
  const csrf = () => $('meta[name="csrf-token"]').content;

  /* ---------------- API helper ---------------- */
  async function api(url, data, method = 'POST') {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: method === 'GET' ? undefined : JSON.stringify(data || {}),
      credentials: 'same-origin',
    });
    let body = {};
    try { body = await res.json(); } catch (e) { body = { ok: false, error: 'Unexpected server response.' }; }
    body.status = res.status;
    return body;
  }

  /* ---------------- Toasts ---------------- */
  function toast(message, type = 'info') {
    const box = $('[data-flashes]');
    const el = document.createElement('div');
    el.className = `flash flash-${type}`;
    el.setAttribute('role', 'status');
    el.innerHTML = '<span></span><button type="button" aria-label="Dismiss">×</button>';
    el.firstChild.textContent = message;
    box.appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }
  $$('[data-flashes] .flash').forEach((el) => setTimeout(() => el.remove(), 7000));
  document.addEventListener('click', (e) => {
    if (e.target.matches('.flash button')) e.target.closest('.flash').remove();
  });

  /* ---------------- Theme ---------------- */
  $$('[data-theme-toggle]').forEach((btn) => btn.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    store.set('ctx-theme', next);
    document.dispatchEvent(new CustomEvent('ctx:theme', { detail: next }));
  }));

  /* ---------------- Currency ---------------- */
  const currencies = (window.CTX && CTX.currencies) || { SGD: { rate: 1, symbol: 'S$', decimals: 2 } };
  let currency = store.get('ctx-currency') || (window.CTX && CTX.serverCurrency) || 'SGD';
  if (!currencies[currency]) currency = 'SGD';

  function formatMoney(sgd, code = currency) {
    const c = currencies[code] || currencies.SGD;
    const v = Number(sgd) * c.rate;
    return c.symbol + v.toLocaleString('en-US', { minimumFractionDigits: c.decimals, maximumFractionDigits: c.decimals });
  }
  function renderPrices(root = document) {
    $$('[data-sgd]', root).forEach((el) => { el.textContent = formatMoney(el.dataset.sgd); });
    $$('[data-currency-label]', root).forEach((el) => { el.textContent = currency; });
    $$('[data-currency-note]', root).forEach((el) => el.classList.toggle('hidden', currency === 'SGD'));
  }
  $$('[data-currency-select]').forEach((sel) => {
    sel.value = currency;
    sel.addEventListener('change', () => {
      currency = sel.value;
      store.set('ctx-currency', currency);
      $$('[data-currency-select]').forEach((s) => { s.value = currency; });
      renderPrices();
      document.dispatchEvent(new CustomEvent('ctx:currency', { detail: currency }));
    });
  });
  renderPrices();

  /* ---------------- Menus ---------------- */
  $$('[data-menu]').forEach((menu) => {
    const btn = $('.menu-btn', menu);
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = menu.classList.toggle('open');
      btn.setAttribute('aria-expanded', open);
    });
  });
  document.addEventListener('click', () => $$('[data-menu].open').forEach((m) => m.classList.remove('open')));
  const burger = $('[data-burger]');
  if (burger) burger.addEventListener('click', () => {
    const open = $('[data-mobile-nav]').classList.toggle('open');
    burger.setAttribute('aria-expanded', open);
  });

  /* ---------------- Favourites ---------------- */
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-fav]');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const res = await api(`/api/favorites/${btn.dataset.fav}`);
    if (res.status === 401) {
      toast('Log in to save favourites.', 'info');
      setTimeout(() => { location.href = `${CTX.loginUrl}?next=${encodeURIComponent(location.pathname + location.search)}`; }, 900);
      return;
    }
    if (!res.ok) return toast(res.error || 'Something went wrong.', 'error');
    $$(`[data-fav="${btn.dataset.fav}"]`).forEach((b) => {
      b.classList.toggle('on', res.favorite);
      b.setAttribute('aria-pressed', res.favorite);
      if (b.dataset.favLabel !== undefined) b.querySelector('span').textContent = res.favorite ? 'Saved' : 'Save';
    });
    toast(res.favorite ? 'Saved to your favourites.' : 'Removed from favourites.', 'success');
  });

  /* ---------------- Chat assistant ---------------- */
  const panel = $('#chat-panel');
  if (panel) {
    const body = $('[data-chat-body]', panel);
    const form = $('[data-chat-form]', panel);
    const input = $('input', form);
    const openBtn = $('[data-chat-open]');
    const history = [];
    const toggle = (open) => {
      panel.classList.toggle('open', open);
      openBtn.setAttribute('aria-expanded', open);
      if (open) setTimeout(() => input.focus(), 50);
    };
    openBtn.addEventListener('click', () => toggle(!panel.classList.contains('open')));
    $('[data-chat-close]', panel).addEventListener('click', () => toggle(false));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') toggle(false); });

    const add = (cls, text) => {
      const el = document.createElement('div');
      el.className = `msg ${cls}`;
      el.textContent = text;
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
      return el;
    };
    const addCards = (cards) => {
      if (!cards || !cards.length) return;
      const wrap = document.createElement('div');
      wrap.className = 'chat-cards';
      cards.forEach((c) => {
        const a = document.createElement('a');
        a.className = 'chat-card';
        a.href = c.url;
        a.innerHTML = '<div><b></b><span class="muted small"></span><br><span class="small"></span></div>';
        a.querySelector('b').textContent = `${c.artist} · ${c.title}`;
        a.querySelector('.muted').textContent = `${c.date}, ${c.time} · ${c.venue}`;
        a.querySelector('.small:not(.muted)').textContent = c.min_price != null ? `from ${formatMoney(c.min_price)}` : 'Sold out';
        wrap.appendChild(a);
      });
      body.appendChild(wrap);
      body.scrollTop = body.scrollHeight;
    };
    async function send(text) {
      text = text.trim();
      if (!text) return;
      add('user', text);
      input.value = '';
      $('[data-chat-suggest]', panel).classList.add('hidden');
      const typing = add('bot typing', 'Tixie is typing…');
      try {
        const res = await api('/api/assistant', { message: text, history });
        typing.remove();
        if (!res.ok) { add('bot', res.error || 'Sorry, something went wrong.'); return; }
        add('bot', res.reply);
        addCards(res.concerts);
        history.push({ role: 'user', text }, { role: 'assistant', text: res.reply });
      } catch (err) {
        typing.remove();
        add('bot', 'I could not reach the server. Please try again.');
      }
    }
    form.addEventListener('submit', (e) => { e.preventDefault(); send(input.value); });
    $$('[data-chat-suggest] button', panel).forEach((b) => b.addEventListener('click', () => send(b.textContent)));
  }

  /* expose helpers for page scripts */
  window.CTXUI = { api, toast, formatMoney, renderPrices, getCurrency: () => currency, $, $$ };
})();
