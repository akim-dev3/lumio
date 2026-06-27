/* LUMIO — shared UI components (loader, toast, plan badge). */
(function (global) {
  'use strict';

  const $ = (sel) => document.querySelector(sel);

  function showLoader(text) {
    const el = $('#loader');
    const txt = $('#loaderText');
    if (txt) txt.textContent = text || 'Загрузка…';
    el.classList.remove('hidden');
    el.setAttribute('aria-hidden', 'false');
  }

  function hideLoader() {
    const el = $('#loader');
    el.classList.add('hidden');
    el.setAttribute('aria-hidden', 'true');
  }

  let toastTimer = null;

  function showToast(message, type) {
    const el = $('#toast');
    if (!el) return;
    el.classList.remove('toast--success', 'toast--error', 'toast--info');
    if (type) el.classList.add('toast--' + type);
    el.textContent = message;
    el.classList.remove('hidden');
    // Force reflow so the transition reliably plays even on repeat calls.
    void el.offsetWidth;
    el.classList.add('is-visible');

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.classList.remove('is-visible');
      setTimeout(() => el.classList.add('hidden'), 200);
    }, 2400);

    const tg = global.Telegram && global.Telegram.WebApp;
    if (tg && tg.HapticFeedback) {
      try {
        tg.HapticFeedback.notificationOccurred(type === 'error' ? 'error' : 'success');
      } catch (_) { /* unsupported on old clients */ }
    }
  }

  function setPlanBadge(plan, remaining, freeLimit) {
    const el = $('#planBadge');
    if (!el) return;
    el.classList.remove('badge--free', 'badge--pro', 'badge--exhausted');
    if (plan === 'pro') {
      el.classList.add('badge--pro');
      el.textContent = '💎 PRO';
    } else if (remaining <= 0) {
      el.classList.add('badge--exhausted');
      el.textContent = 'free · 0/' + freeLimit;
    } else {
      el.classList.add('badge--free');
      el.textContent = 'free · ' + remaining + '/' + freeLimit;
    }
  }

  function setTitle(title) {
    const el = $('#screenTitle');
    if (el) el.textContent = title;
  }

  function setBack(visible) {
    const el = $('#backBtn');
    if (!el) return;
    el.classList.toggle('hidden', !visible);
  }

  function showPaywall() {
    showToast('Лимит исчерпан. Купи Pro в чате с ботом.', 'error');
    const tg = global.Telegram && global.Telegram.WebApp;
    if (tg) {
      // Pop the WebApp so the user sees the paywall message in chat.
      setTimeout(() => tg.close(), 800);
    }
  }

  function bindSegmentedControl(seg) {
    seg.addEventListener('click', (e) => {
      const opt = e.target.closest('.seg__opt');
      if (!opt) return;
      seg.querySelectorAll('.seg__opt').forEach((b) => b.classList.remove('is-active'));
      opt.classList.add('is-active');
    });
  }

  function getSegmentedValue(seg) {
    const active = seg.querySelector('.seg__opt.is-active');
    return active ? active.dataset.value : null;
  }

  global.LumioUI = {
    showLoader,
    hideLoader,
    showToast,
    setPlanBadge,
    setTitle,
    setBack,
    showPaywall,
    bindSegmentedControl,
    getSegmentedValue,
  };
})(window);
