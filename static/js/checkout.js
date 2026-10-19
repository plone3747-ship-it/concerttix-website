/* ConcertTix checkout: steps, validation, demo payment */
(function () {
  'use strict';
  const C = window.CHECKOUT;
  const { api, toast, formatMoney, getCurrency, renderPrices, $, $$ } = window.CTXUI;
  let step = 2;
  let paying = false;
  let done = false;

  /* ---------- steps ---------- */
  function go(n) {
    if (done && n !== 4) return;
    step = n;
    $$('[data-pane]').forEach((p) => p.classList.toggle('active', Number(p.dataset.pane) === n));
    $$('[data-step-ind]').forEach((s) => {
      const i = Number(s.dataset.stepInd);
      s.classList.toggle('active', i === n);
      s.classList.toggle('done', i < n || (n === 4 && i === 4));
      if (i === n) s.setAttribute('aria-current', 'step'); else s.removeAttribute('aria-current');
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  $$('[data-go]').forEach((b) => b.addEventListener('click', () => go(Number(b.dataset.go))));

  /* ---------- hold timer ---------- */
  let remaining = C.holdSeconds;
  const timerText = $('[data-timer-text]');
  const tick = () => {
    if (done) return;
    remaining = Math.max(0, remaining - 1);
    const m = Math.floor(remaining / 60), s = remaining % 60;
    timerText.textContent = `${m}:${String(s).padStart(2, '0')}`;
    $('[data-timer]').classList.toggle('low', remaining < 120);
    if (remaining === 0) {
      clearInterval(timer);
      showOverlay('Seat hold expired', 'Your seats have been released. Please pick them again.', false);
      setTimeout(() => { location.href = C.seatsUrl; }, 2500);
    }
  };
  const timer = setInterval(tick, 1000);
  tick();

  /* ---------- field errors ---------- */
  function setErrors(errors, scope = document) {
    $$('[data-err]', scope).forEach((el) => { el.textContent = ''; el.closest('.field').classList.remove('invalid'); });
    Object.entries(errors || {}).forEach(([k, msg]) => {
      const el = $(`[data-err="${k}"]`, scope);
      if (el) { el.textContent = msg; el.closest('.field').classList.add('invalid'); }
    });
  }

  /* ---------- step 2: customer ---------- */
  const custForm = $('[data-customer-form]');
  const customer = () => ({ name: custForm.name.value.trim(), email: custForm.email.value.trim(), phone: custForm.phone.value.trim() });
  function validateCustomer() {
    const c = customer(), e = {};
    if (c.name.length < 2) e.name = 'Please enter your full name.';
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.email)) e.email = 'Please enter a valid email.';
    if (!/^\+?[\d\s\-()]{7,20}$/.test(c.phone)) e.phone = 'Please enter a valid phone number.';
    setErrors(e, custForm);
    return !Object.keys(e).length;
  }
  custForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (validateCustomer()) {
      go(3);
      const holder = $('#cc-name');
      if (!holder.value) { holder.value = customer().name; holder.dispatchEvent(new Event('input')); }
    }
  });

  /* ---------- step 3: payment method ---------- */
  const method = () => $('input[name="method"]:checked').value;
  $$('input[name="method"]').forEach((r) => r.addEventListener('change', () => {
    $$('[data-method-pane]').forEach((p) => p.classList.toggle('hidden', p.dataset.methodPane !== method()));
    $('[data-pay]').classList.toggle('hidden', method() !== 'card');
  }));

  /* card formatting + live preview */
  const num = $('#cc-number'), exp = $('#cc-exp'), cvv = $('#cc-cvv'), holder = $('#cc-name');
  const brandOf = (n) => (/^4/.test(n) ? 'VISA' : /^(5[1-5]|2[2-7])/.test(n) ? 'MASTERCARD' : /^3[47]/.test(n) ? 'AMEX' : 'CARD');
  num.addEventListener('input', () => {
    const d = num.value.replace(/\D/g, '').slice(0, 19);
    num.value = d.replace(/(.{4})/g, '$1 ').trim();
    const brand = brandOf(d);
    $('[data-card-brand]').textContent = brand;
    $('[data-brand-suffix]').textContent = d ? brand : '';
    $('[data-card-num]').textContent = (d + '•'.repeat(Math.max(0, 16 - d.length))).replace(/(.{4})/g, '$1 ').trim();
    cvv.maxLength = brand === 'AMEX' ? 4 : 3;
  });
  exp.addEventListener('input', (e) => {
    let d = exp.value.replace(/\D/g, '').slice(0, 4);
    if (d.length === 1 && Number(d) > 1) d = '0' + d;
    exp.value = d.length > 2 || (d.length === 2 && e.inputType !== 'deleteContentBackward') ? `${d.slice(0, 2)}/${d.slice(2)}` : d;
    $('[data-card-exp]').textContent = exp.value || 'MM/YY';
  });
  cvv.addEventListener('input', () => { cvv.value = cvv.value.replace(/\D/g, ''); });
  holder.addEventListener('input', () => { $('[data-card-holder]').textContent = holder.value.toUpperCase() || 'YOUR NAME'; });

  function luhn(n) {
    let sum = 0;
    n.split('').reverse().forEach((c, i) => { let d = Number(c); if (i % 2) { d *= 2; if (d > 9) d -= 9; } sum += d; });
    return sum % 10 === 0;
  }
  function validateCard() {
    const e = {};
    const d = num.value.replace(/\D/g, '');
    if (d.length < 13 || !luhn(d)) e.number = 'Card number is not valid.';
    const m = exp.value.match(/^(\d{2})\/(\d{2})$/);
    if (!m || Number(m[1]) < 1 || Number(m[1]) > 12) e.expiry = 'Use MM/YY.';
    else {
      const now = new Date();
      const y = 2000 + Number(m[2]), mo = Number(m[1]);
      if (y < now.getFullYear() || (y === now.getFullYear() && mo < now.getMonth() + 1)) e.expiry = 'This card has expired.';
    }
    const need = brandOf(d) === 'AMEX' ? 4 : 3;
    if (!new RegExp(`^\\d{${need}}$`).test(cvv.value)) e.cvv = `CVV must be ${need} digits.`;
    if (holder.value.trim().length < 2) e.holder = 'Enter the name on the card.';
    setErrors(e, $('[data-card-form]'));
    return !Object.keys(e).length;
  }

  /* ---------- overlay (simulated wallet sheets) ---------- */
  const overlay = $('[data-overlay]');
  function showOverlay(title, text, spinning = true, actions = false) {
    overlay.classList.remove('hidden');
    $('[data-overlay-title]').textContent = title;
    $('[data-overlay-text]').textContent = text;
    $('[data-overlay-spin]').classList.toggle('hidden', !spinning);
    $('[data-overlay-actions]').classList.toggle('hidden', !actions);
  }
  const hideOverlay = () => overlay.classList.add('hidden');

  function walletConfirm(m) {
    const names = { apple_pay: 'Apple Pay', google_pay: 'Google Pay', paypal: 'PayPal' };
    const text = { apple_pay: 'Double-click to pay with Face ID (simulated).', google_pay: 'Choose your saved card (simulated).', paypal: 'Log in to PayPal and approve the payment (simulated).' };
    return new Promise((resolve) => {
      showOverlay(`${names[m]} · ${formatMoney(C.total)}`, text[m], false, true);
      const ok = $('[data-overlay-confirm]'), cancel = $('[data-overlay-cancel]');
      const cleanup = (v) => { ok.onclick = cancel.onclick = null; resolve(v); };
      ok.onclick = () => cleanup(true);
      cancel.onclick = () => { hideOverlay(); cleanup(false); };
      ok.focus();
    });
  }

  /* ---------- pay ---------- */
  async function pay(m) {
    if (paying || done) return;
    if (!validateCustomer()) { go(2); return; }
    if (!$('[data-terms]').checked) { toast('Please accept the terms & refund policy.', 'error'); $('[data-terms]').focus(); return; }
    if (m === 'card' && !validateCard()) return;
    if (m !== 'card' && !(await walletConfirm(m))) return;

    paying = true;
    showOverlay('Processing payment…', 'Contacting the (demo) payment gateway. Please don’t close this window.');
    const payload = { customer: customer(), method: m, currency: getCurrency() };
    if (m === 'card') payload.card = { number: num.value, expiry: exp.value, cvv: cvv.value, holder: holder.value };
    await new Promise((r) => setTimeout(r, 1300));
    const res = await api(C.payUrl, payload);
    paying = false;
    if (res.ok) {
      done = true;
      hideOverlay();
      clearInterval(timer);
      $('[data-timer]').classList.add('hidden');
      $('[data-conf-ref]').textContent = res.order_ref;
      $('[data-conf-email]').textContent = customer().email;
      $('[data-conf-seats]').textContent = res.seats.join(', ');
      $('[data-conf-total]').textContent = formatMoney(res.total, res.currency);
      $('[data-conf-link]').href = res.confirmation_url + '?new=1';
      go(4);
      return;
    }
    hideOverlay();
    if (res.expired) { toast(res.error, 'error'); setTimeout(() => { location.href = res.redirect; }, 1800); return; }
    if (res.step === 2) { go(2); setErrors(res.errors, custForm); }
    if (res.step === 3) setErrors(res.errors, $('[data-card-form]'));
    const first = res.errors && Object.values(res.errors)[0];
    toast(first || res.error || 'Payment failed.', 'error');
  }
  $('[data-pay]').addEventListener('click', () => pay('card'));
  $$('[data-wallet]').forEach((b) => b.addEventListener('click', () => pay(b.dataset.wallet)));
  document.addEventListener('ctx:currency', () => renderPrices());
  window.addEventListener('beforeunload', (e) => { if (paying) { e.preventDefault(); e.returnValue = ''; } });
  go(2);
})();
