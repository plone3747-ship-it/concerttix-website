/* ConcertTix admin: dashboard charts, inventory map, door check-in */
(function () {
  'use strict';
  const { api, toast, $, $$ } = window.CTXUI;

  /* ================= Dashboard charts ================= */
  if (window.DASH && window.Chart) {
    const charts = [];
    const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
    function palette() {
      const dark = document.documentElement.getAttribute('data-theme') === 'dark';
      return {
        dark,
        text: css('--muted'),
        grid: dark ? 'rgba(255,255,255,.07)' : 'rgba(67,47,46,.08)',
        main: dark ? '#FEEFB6' : '#432F2E',
        second: dark ? '#C3DAE8' : '#7FA7C4',
        fill: dark ? 'rgba(254,239,182,.14)' : 'rgba(195,218,232,.55)',
        tiers: ['#EFCB5C', '#8FB7D3', '#C7A49E', '#A9C49B'],
        surface: css('--surface'),
      };
    }
    function draw() {
      charts.forEach((c) => c.destroy());
      charts.length = 0;
      const p = palette();
      Chart.defaults.font.family = 'Manrope, system-ui, sans-serif';
      Chart.defaults.color = p.text;
      const axes = (money) => ({
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 14 } },
        y: { beginAtZero: true, grid: { color: p.grid }, border: { display: false },
             ticks: { callback: (v) => (money ? 'S$' + (v >= 1000 ? (v / 1000) + 'k' : v) : v) } },
      });
      const tooltip = { backgroundColor: p.dark ? '#FEEFB6' : '#432F2E', titleColor: p.dark ? '#432F2E' : '#FEEFB6',
                        bodyColor: p.dark ? '#432F2E' : '#FEEFB6', padding: 10, cornerRadius: 8, displayColors: false };
      const D = window.DASH;

      charts.push(new Chart($('#salesChart'), {
        type: 'line',
        data: { labels: D.sales.labels, datasets: [{ label: 'Tickets', data: D.sales.tickets, borderColor: p.main, backgroundColor: p.fill,
                fill: true, tension: .35, pointRadius: 0, pointHoverRadius: 5, borderWidth: 2.5 }] },
        options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
                   plugins: { legend: { display: false }, tooltip: { ...tooltip, callbacks: {
                     label: (c) => `${c.parsed.y} tickets · S$${D.sales.revenue[c.dataIndex].toLocaleString('en-US', { maximumFractionDigits: 0 })}` } } },
                   scales: axes(false) },
      }));
      charts.push(new Chart($('#revenueChart'), {
        type: 'bar',
        data: { labels: D.revenue.labels, datasets: [{ label: 'Revenue', data: D.revenue.values, backgroundColor: p.second, hoverBackgroundColor: p.main, borderRadius: 8, maxBarThickness: 46 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { ...tooltip, callbacks: {
                     label: (c) => 'S$' + c.parsed.y.toLocaleString('en-US', { minimumFractionDigits: 2 }) } } }, scales: axes(true) },
      }));
      charts.push(new Chart($('#popularChart'), {
        type: 'bar',
        data: { labels: D.popular.labels, datasets: [{ label: 'Tickets sold', data: D.popular.values, backgroundColor: p.main, borderRadius: 6, maxBarThickness: 22 }] },
        options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { ...tooltip, callbacks: {
                     title: (items) => D.popular.titles[items[0].dataIndex], label: (c) => `${c.parsed.x} tickets` } } },
                   scales: { x: { beginAtZero: true, grid: { color: p.grid }, border: { display: false } }, y: { grid: { display: false } } } },
      }));
      charts.push(new Chart($('#typeChart'), {
        type: 'doughnut',
        data: { labels: D.types.labels, datasets: [{ data: D.types.values, backgroundColor: p.tiers, borderColor: p.surface, borderWidth: 3, hoverOffset: 6 }] },
        options: { maintainAspectRatio: false, cutout: '62%', plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8, padding: 14 } },
                   tooltip: { ...tooltip, displayColors: true } } },
      }));
    }
    draw();
    document.addEventListener('ctx:theme', draw);
  }

  /* ================= Inventory seat map ================= */
  if (window.INVENTORY) {
    /* --- zone map: click a zone to show its seats --- */
    const GA = 'General Admission';
    const label = (t) => (t === GA ? 'GA' : t);
    const sgd = (v) => window.CTXUI.formatMoney(v, 'SGD');
    Object.entries(INVENTORY.stats).forEach(([type, st]) => {
      $$(`.zone[data-zone="${type}"]`).forEach((g) => {
        g.classList.toggle('soldout', st.left <= 0);
        $$('[data-zone-price]', g).forEach((t) => { t.textContent = `${sgd(st.price)} · ${st.sold} sold`; });
        $$('[data-zone-left]', g).forEach((t) => { t.textContent = `${st.left}/${st.total} left`; });
      });
    });
    function showZone(type) {
      $$('.inv-map .zone-grid').forEach((el) => el.classList.toggle('hidden', el.dataset.zone !== type));
      $('[data-inv-ga]').classList.toggle('hidden', type !== GA);
      $$('.zone').forEach((g) => {
        g.classList.toggle('active', g.dataset.zone === type);
        g.classList.toggle('dim', g.dataset.zone !== type);
      });
      $$('[data-zone-tab]').forEach((t) => t.classList.toggle('active', t.dataset.zoneTab === type));
      $('[data-inv-heading]').textContent = `${label(type)} · ${INVENTORY.notes[type] || ''}`;
    }
    $$('.zone').forEach((g) => {
      g.addEventListener('click', () => showZone(g.dataset.zone));
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showZone(g.dataset.zone); } });
    });
    $$('[data-zone-tab]').forEach((t) => t.addEventListener('click', () => showZone(t.dataset.zoneTab)));
    showZone(INVENTORY.zones[0]);

    const picked = new Set();
    const buttons = $$('.inv-map .seat:not(:disabled)');
    const btnBlock = $('[data-inv-action="block"]'), btnRelease = $('[data-inv-action="release"]');
    const refresh = () => {
      const statuses = [...picked].map((id) => $(`.inv-map .seat[data-id="${id}"]`).dataset.status);
      $('[data-picked-count]').textContent = `${picked.size} selected`;
      btnBlock.disabled = !statuses.includes('available');
      btnRelease.disabled = !statuses.includes('blocked');
    };
    buttons.forEach((b) => b.addEventListener('click', () => {
      const id = b.dataset.id;
      if (picked.has(id)) picked.delete(id); else picked.add(id);
      b.classList.toggle('picked', picked.has(id));
      refresh();
    }));
    $$('[data-inv-action]').forEach((btn) => btn.addEventListener('click', async () => {
      const action = btn.dataset.invAction;
      const want = action === 'block' ? 'available' : 'blocked';
      const ids = [...picked].filter((id) => $(`.inv-map .seat[data-id="${id}"]`).dataset.status === want);
      const res = await api(INVENTORY.toggleUrl, { ids, action });
      if (!res.ok) return toast(res.error || 'Could not update seats.', 'error');
      ids.forEach((id) => {
        const b = $(`.inv-map .seat[data-id="${id}"]`);
        b.classList.remove('available', 'blocked', 'picked');
        b.classList.add(res.new_status);
        b.dataset.status = res.new_status;
        b.title = b.title.split("·")[0] + "· " + res.new_status;
        picked.delete(id);
      });
      refresh();
      toast(`${res.changed} seat${res.changed === 1 ? '' : 's'} ${action === 'block' ? 'blocked' : 'released'}. Reload to update the totals table.`, 'success');
    }));
  }

  /* ================= Door check-in ================= */
  if (window.CHECKIN) {
    const form = $('[data-checkin-form]'), input = $('#code'), box = $('[data-result]');
    let busy = false;
    async function check(code) {
      if (busy || !code) return;
      busy = true;
      const res = await api(CHECKIN.url, { code, concert_id: CHECKIN.concertId });
      busy = false;
      box.classList.remove('hidden', 'ok', 'bad', 'warn');
      box.classList.add(res.result === 'ok' ? 'ok' : res.result === 'used' || res.result === 'wrong' ? 'warn' : 'bad');
      $('[data-result-title]').textContent = { ok: '✓ Admit', used: 'Already used', wrong: 'Wrong event', invalid: '✕ Invalid' }[res.result] || 'Error';
      $('[data-result-text]').textContent = res.message || '';
      $('[data-result-ticket]').textContent = res.ticket ? `${res.ticket.name} · ${res.ticket.type} · Seat ${res.ticket.seat} · ${res.ticket.order}` : '';
      if (res.result === 'ok') {
        const el = $('[data-checked]');
        if (el) el.textContent = Number(el.textContent) + 1;
      }
      input.value = '';
      input.focus();
    }
    form.addEventListener('submit', (e) => { e.preventDefault(); check(input.value.trim().toUpperCase()); });

    let scanner = null;
    $('[data-camera]').addEventListener('click', async () => {
      if (!window.Html5Qrcode) return toast('Camera scanner could not load. Type the code instead.', 'error');
      if (scanner) { await scanner.stop(); scanner = null; $('#qr-reader').innerHTML = ''; return; }
      scanner = new Html5Qrcode('qr-reader');
      let last = '';
      try {
        await scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: 220 }, (text) => {
          if (text === last) return;
          last = text;
          check(text.trim().toUpperCase());
          setTimeout(() => { last = ''; }, 3000);
        });
      } catch (err) {
        scanner = null;
        toast('Camera not available. Allow camera access or type the code.', 'error');
      }
    });
  }
})();
