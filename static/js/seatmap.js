/* ConcertTix interactive zone + seat map
   Step 1: click a zone on the venue map (VVIP, VIP, CAT 1, GA).
   Step 2: pick seats in that zone (or a quantity for GA standing). */
(function () {
  'use strict';
  const S = window.SEATMAP;
  const { api, toast, renderPrices, formatMoney, $, $$ } = window.CTXUI;
  const storeKey = `ctx-sel-${S.concertId}`;
  const GA = 'General Admission';

  const seatsById = new Map();
  const selected = new Set();
  const zoneGrids = {};
  let ga = S.data.ga;
  let gaQty = 0;
  let activeZone = null;

  const zoneInfo = Object.fromEntries(S.layout.map((z) => [z.type, z]));
  const rowRange = (z) => (z.rows ? `Rows ${z.rows[0]}–${z.rows[z.rows.length - 1]}` : 'Standing');

  /* ---------- build one seat grid per seated zone ---------- */
  function build() {
    const wrap = $('#seat-sections');
    const byRow = {};
    S.data.seats.forEach((s) => { (byRow[s.row] = byRow[s.row] || []).push(s); });

    S.layout.filter((z) => z.rows).forEach((z) => {
      const block = document.createElement('div');
      block.className = 'zone-grid hidden';
      block.dataset.zone = z.type;
      z.rows.forEach((r) => {
        const row = document.createElement('div');
        row.className = 'seat-row';
        row.setAttribute('role', 'group');
        row.setAttribute('aria-label', `Row ${r}`);
        row.appendChild(label(r));
        const seats = (byRow[r] || []).sort((a, b) => a.n - b.n);
        const half = Math.ceil(seats.length / 2);
        seats.forEach((s, i) => {
          if (i === half) { const a = document.createElement('span'); a.className = 'aisle'; row.appendChild(a); }
          const b = document.createElement('button');
          b.type = 'button';
          b.className = 'seat';
          b.dataset.id = s.id;
          b.dataset.type = s.type;
          b.textContent = s.n;
          seatsById.set(s.id, { ...s, el: b });
          row.appendChild(b);
        });
        row.appendChild(label(r));
        block.appendChild(row);
      });
      zoneGrids[z.type] = block;
      wrap.appendChild(block);
    });
    function label(r) { const l = document.createElement('span'); l.className = 'row-label'; l.textContent = r; return l; }
  }

  function applyState(seat) {
    const taken = seat.state === 'taken';
    const isSel = selected.has(seat.id);
    seat.el.disabled = taken || !S.canBook;
    seat.el.classList.toggle('selected', isSel);
    seat.el.setAttribute('aria-pressed', isSel);
    seat.el.setAttribute('aria-label',
      `Row ${seat.row} seat ${seat.n}, ${seat.type}, ${formatMoney(seat.price)}${taken ? ', unavailable' : isSel ? ', selected' : ''}`);
  }

  /* ---------- zone statistics ---------- */
  function zoneStats(type) {
    if (type === GA) return { left: ga.available + ga.mine - gaQty, min: ga.price, chosen: gaQty };
    let left = 0, min = Infinity, chosen = 0;
    seatsById.forEach((s) => {
      if (s.type !== type) return;
      min = Math.min(min, s.price);
      if (selected.has(s.id)) chosen++;
      else if (s.state !== 'taken') left++;
    });
    return { left, min: min === Infinity ? 0 : min, chosen };
  }

  function renderZones() {
    S.layout.forEach((z) => {
      const st = zoneStats(z.type);
      const soldOut = st.left <= 0 && st.chosen === 0;
      $$(`.zone[data-zone="${z.type}"]`).forEach((g) => {
        g.classList.toggle('active', z.type === activeZone);
        g.classList.toggle('dim', activeZone && z.type !== activeZone);
        g.classList.toggle('soldout', soldOut);
        g.setAttribute('aria-pressed', z.type === activeZone);
        g.setAttribute('aria-label', `${z.label} zone, from ${formatMoney(st.min)}, ${soldOut ? 'sold out' : st.left + ' left'}`);
        $$('[data-zone-price]', g).forEach((t) => { t.textContent = `from ${formatMoney(st.min)}`; });
        $$('[data-zone-left]', g).forEach((t) => { t.textContent = soldOut ? 'SOLD OUT' : `${st.left} left`; });
      });
      const tab = $(`[data-zone-tab="${z.type}"]`);
      tab.classList.toggle('active', z.type === activeZone);
      tab.classList.toggle('soldout', soldOut);
      tab.setAttribute('aria-selected', z.type === activeZone);
      $('[data-tab-info]', tab).textContent = soldOut ? 'Sold out' : `from ${formatMoney(st.min)} · ${st.left} left`;
      const count = $('[data-tab-count]', tab);
      count.textContent = st.chosen;
      count.classList.toggle('hidden', !st.chosen);
    });
  }

  function setZone(type, scroll) {
    activeZone = type;
    const z = zoneInfo[type];
    Object.entries(zoneGrids).forEach(([t, el]) => el.classList.toggle('hidden', t !== type));
    $('#ga-zone').classList.toggle('hidden', type !== GA);
    $('#seat-sections').classList.toggle('hidden', type === GA);
    $('[data-zone-heading]').textContent = type === GA ? 'GA standing: choose quantity' : `${z.label}: pick your seats`;
    $('[data-zone-note]').textContent = `${rowRange(z)} · ${z.note}`;
    renderZones();
    if (scroll && window.innerWidth < 1021) $('#seat-title').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ---------- selection ---------- */
  const total = () => selected.size + gaQty;

  function toggle(id) {
    const seat = seatsById.get(id);
    if (!seat || seat.state === 'taken' || !S.canBook) return;
    if (selected.has(id)) selected.delete(id);
    else {
      if (total() >= S.maxTickets) {
        seat.el.classList.add('flash');
        setTimeout(() => seat.el.classList.remove('flash'), 400);
        return toast(`You can select up to ${S.maxTickets} tickets per order.`, 'info');
      }
      selected.add(id);
    }
    applyState(seat);
    update();
  }

  const gaMax = () => ga.available + ga.mine;
  const order = Object.fromEntries(S.layout.map((z, i) => [z.type, i]));

  function update() {
    const list = [...selected].map((id) => seatsById.get(id))
      .sort((a, b) => order[a.type] - order[b.type] || a.row.localeCompare(b.row) || a.n - b.n);
    const tags = $('[data-sum-seats]');
    tags.innerHTML = '';
    list.forEach((s) => { const t = document.createElement('span'); t.className = 'seat-tag'; t.textContent = s.seat; tags.appendChild(t); });
    if (gaQty) { const t = document.createElement('span'); t.className = 'seat-tag'; t.textContent = `GA × ${gaQty}`; tags.appendChild(t); }
    if (!list.length && !gaQty) tags.innerHTML = '<span class="muted">None yet</span>';

    const groups = {};
    list.forEach((s) => { groups[s.type] = groups[s.type] || { n: 0, sum: 0 }; groups[s.type].n++; groups[s.type].sum += s.price; });
    if (gaQty) groups[GA] = { n: gaQty, sum: gaQty * ga.price };
    const lines = $('[data-sum-lines]');
    lines.innerHTML = '';
    Object.entries(groups).forEach(([type, g]) => {
      const row = document.createElement('div');
      row.className = 'summary-row small';
      row.innerHTML = `<span class="k"></span><span data-sgd="${g.sum.toFixed(2)}"></span>`;
      row.firstChild.textContent = `${zoneInfo[type].label} × ${g.n}`;
      lines.appendChild(row);
    });

    const subtotal = list.reduce((a, s) => a + s.price, 0) + gaQty * ga.price;
    const fee = Math.round(subtotal * S.feeRate * 100) / 100;
    const tot = subtotal + fee;
    $('[data-sum-count]').textContent = total();
    $('[data-sum-count-m]').textContent = total();
    $('[data-sum-subtotal]').dataset.sgd = subtotal.toFixed(2);
    $('[data-sum-fee]').dataset.sgd = fee.toFixed(2);
    $('[data-sum-total]').dataset.sgd = tot.toFixed(2);
    $('[data-sum-total-m]').dataset.sgd = tot.toFixed(2);
    $$('[data-continue]').forEach((b) => { b.disabled = !S.canBook || total() === 0; });

    $('[data-ga-qty]').textContent = gaQty;
    $('[data-ga-left]').textContent = Math.max(0, gaMax() - gaQty);
    $('[data-ga-price]').dataset.sgd = ga.price;
    $('[data-ga-minus]').disabled = gaQty === 0 || !S.canBook;
    $('[data-ga-plus]').disabled = !S.canBook || gaQty >= gaMax() || total() >= S.maxTickets;
    renderPrices();
    renderZones();
  }

  /* ---------- tooltip ---------- */
  const tip = document.createElement('div');
  tip.className = 'seat-tip hidden';
  document.body.appendChild(tip);
  function showTip(el) {
    const s = seatsById.get(Number(el.dataset.id));
    if (!s) return;
    const r = el.getBoundingClientRect();
    tip.textContent = `${zoneInfo[s.type].label} · Row ${s.row} · Seat ${s.n} · ${s.state === 'taken' ? 'Unavailable' : formatMoney(s.price)}`;
    tip.style.left = `${r.left + r.width / 2}px`;
    tip.style.top = `${r.top}px`;
    tip.classList.remove('hidden');
  }
  const hideTip = () => tip.classList.add('hidden');

  /* ---------- live refresh every 20 s ---------- */
  async function refresh() {
    try {
      const res = await fetch(S.seatsUrl, { credentials: 'same-origin' });
      if (!res.ok) return;
      const data = await res.json();
      const lost = [];
      data.seats.forEach((n) => {
        const s = seatsById.get(n.id);
        if (!s) return;
        s.state = n.state;
        s.price = n.price;
        if (n.state === 'taken' && selected.has(n.id)) { selected.delete(n.id); lost.push(s.seat); }
        applyState(s);
      });
      ga = data.ga;
      if (gaQty > gaMax()) gaQty = gaMax();
      if (lost.length) toast(`Sorry, ${lost.join(', ')} ${lost.length > 1 ? 'were' : 'was'} just booked by someone else.`, 'error');
      update();
    } catch (e) { /* offline - try again next time */ }
  }

  /* ---------- continue to checkout ---------- */
  async function proceed() {
    if (!total()) return;
    const payload = { seats: [...selected], ga: gaQty };
    if (!CTX.loggedIn) {
      try { sessionStorage.setItem(storeKey, JSON.stringify(payload)); } catch (e) { /* ignore */ }
      toast('Please log in or sign up to book. Your seats will be kept on this page.', 'info');
      setTimeout(() => { location.href = `${CTX.loginUrl}?next=${encodeURIComponent(S.selfUrl)}`; }, 900);
      return;
    }
    $$('[data-continue]').forEach((b) => { b.disabled = true; b.textContent = 'Holding your seats…'; });
    const res = await api(S.holdUrl, payload);
    if (res.ok) {
      try { sessionStorage.removeItem(storeKey); } catch (e) { /* ignore */ }
      location.href = res.redirect;
      return;
    }
    toast(res.error || 'Could not hold those seats.', 'error');
    $$('[data-continue]').forEach((b) => { b.textContent = b.closest('.mobile-bar') ? 'Continue' : 'Continue to checkout'; });
    await refresh();
  }

  /* ---------- start ---------- */
  build();
  S.data.seats.forEach((s) => { if (s.state === 'mine') selected.add(s.id); });
  gaQty = ga.mine || 0;
  try {
    const saved = JSON.parse(sessionStorage.getItem(storeKey) || 'null');
    if (saved && CTX.loggedIn) {
      saved.seats.forEach((id) => { const s = seatsById.get(id); if (s && s.state !== 'taken') selected.add(id); });
      gaQty = Math.min(saved.ga || 0, gaMax());
      sessionStorage.removeItem(storeKey);
      if (selected.size || gaQty) toast('Welcome back! We kept the seats you picked.', 'success');
    }
  } catch (e) { /* ignore */ }
  seatsById.forEach(applyState);

  // open the zone the fan already has seats in, otherwise the first zone with seats left
  const firstSel = [...selected].map((id) => seatsById.get(id))[0];
  const startZone = firstSel ? firstSel.type
    : gaQty ? GA
      : (S.layout.find((z) => zoneStats(z.type).left > 0) || S.layout[0]).type;
  setZone(startZone);
  update();

  $$('.zone').forEach((g) => {
    g.addEventListener('click', () => setZone(g.dataset.zone, true));
    g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setZone(g.dataset.zone, true); } });
  });
  $$('[data-zone-tab]').forEach((t) => t.addEventListener('click', () => setZone(t.dataset.zoneTab, true)));
  $('#seat-sections').addEventListener('click', (e) => { const b = e.target.closest('.seat'); if (b) toggle(Number(b.dataset.id)); });
  $('#seat-sections').addEventListener('mouseover', (e) => { const b = e.target.closest('.seat'); if (b) showTip(b); });
  $('#seat-sections').addEventListener('mouseout', hideTip);
  $('#seat-sections').addEventListener('focusin', (e) => { const b = e.target.closest('.seat'); if (b) showTip(b); });
  $('#seat-sections').addEventListener('focusout', hideTip);
  window.addEventListener('scroll', hideTip, { passive: true });
  $('[data-ga-plus]').addEventListener('click', () => {
    if (total() >= S.maxTickets) return toast(`You can select up to ${S.maxTickets} tickets per order.`, 'info');
    if (gaQty < gaMax()) { gaQty++; update(); }
  });
  $('[data-ga-minus]').addEventListener('click', () => { if (gaQty > 0) { gaQty--; update(); } });
  $('[data-clear]').addEventListener('click', () => { selected.clear(); gaQty = 0; seatsById.forEach(applyState); update(); });
  $$('[data-continue]').forEach((b) => b.addEventListener('click', proceed));
  document.addEventListener('ctx:currency', () => { seatsById.forEach(applyState); renderZones(); });
  if (S.canBook) setInterval(refresh, 20000);
})();
