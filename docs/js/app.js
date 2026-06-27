/* LUMIO — SPA router + per-screen logic. */
(function (global) {
  'use strict';

  const FREE_LIMIT = 3;

  const ROUTES = {
    home:   { title: 'LUMIO',           tpl: 'tpl-home',   showBack: false, mount: mountHome   },
    cards:  { title: '🎴 Anki Cards',   tpl: 'tpl-cards',  showBack: true,  mount: mountCards  },
    posts:  { title: '✍️ TG Posts',     tpl: 'tpl-posts',  showBack: true,  mount: mountPosts  },
    pdf:    { title: '📄 PDF Analyst',  tpl: 'tpl-pdf',    showBack: true,  mount: mountPdf    },
    resume: { title: '💼 Resume',       tpl: 'tpl-resume', showBack: true,  mount: mountResume },
  };

  const state = {
    route: 'home',
    plan: 'free',
    remaining: FREE_LIMIT,
  };

  function navigate(route) {
    if (!ROUTES[route]) route = 'home';
    state.route = route;
    render();
    syncTGBackButton();
  }

  function render() {
    const def = ROUTES[state.route];
    const tpl = document.getElementById(def.tpl);
    if (!tpl) return;
    const screen = document.getElementById('screen');
    screen.innerHTML = '';
    screen.appendChild(tpl.content.cloneNode(true));

    LumioUI.setTitle(def.title);
    LumioUI.setBack(def.showBack);
    LumioUI.setPlanBadge(state.plan, state.remaining, FREE_LIMIT);

    // Bind segmented controls on the freshly mounted screen.
    screen.querySelectorAll('.seg').forEach(LumioUI.bindSegmentedControl);

    def.mount(screen);
  }

  function syncTGBackButton() {
    const tg = LumioAPI.getTG();
    if (!tg || !tg.BackButton) return;
    if (state.route === 'home') {
      tg.BackButton.hide();
    } else {
      tg.BackButton.show();
    }
  }

  // ---------------------------------------------------------------------
  // Screen mounters
  // ---------------------------------------------------------------------

  function mountHome(screen) {
    screen.querySelectorAll('.tool').forEach((btn) => {
      btn.addEventListener('click', () => navigate(btn.dataset.route));
    });
    const upgrade = screen.querySelector('#upgradeBtn');
    if (upgrade) {
      upgrade.addEventListener('click', () => {
        LumioAPI.sendToBot('plans', {});
        // Bot will send invoice; the app closes itself for visibility.
        setTimeout(() => {
          const tg = LumioAPI.getTG();
          if (tg) tg.close();
        }, 400);
      });
    }
  }

  function mountCards(screen) {
    const submit = screen.querySelector('#cardsSubmit');
    const textEl = screen.querySelector('#cardsText');
    const countSeg = screen.querySelector('.seg[data-name="count"]');
    submit.addEventListener('click', () => {
      const text = (textEl.value || '').trim();
      if (text.length < 30) {
        LumioUI.showToast('Дай хотя бы 30 символов текста.', 'error');
        return;
      }
      const count = parseInt(LumioUI.getSegmentedValue(countSeg) || '20', 10);
      if (!preflight()) return;
      submit.disabled = true;
      const ok = LumioAPI.sendToBot('cards', { text: text, count: count });
      if (!ok) submit.disabled = false;
    });
  }

  function mountPosts(screen) {
    const submit = screen.querySelector('#postsSubmit');
    const topicEl = screen.querySelector('#postsTopic');
    const countSeg = screen.querySelector('.seg[data-name="count"]');
    const toneSeg = screen.querySelector('.seg[data-name="tone"]');
    submit.addEventListener('click', () => {
      const topic = (topicEl.value || '').trim();
      if (topic.length < 5) {
        LumioUI.showToast('Уточни тему — хотя бы 5 символов.', 'error');
        return;
      }
      const count = parseInt(LumioUI.getSegmentedValue(countSeg) || '3', 10);
      const tone = LumioUI.getSegmentedValue(toneSeg) || 'casual';
      if (!preflight()) return;
      submit.disabled = true;
      const ok = LumioAPI.sendToBot('posts', { topic: topic, count: count, tone: tone });
      if (!ok) submit.disabled = false;
    });
  }

  function mountPdf(screen) {
    const btn = screen.querySelector('#pdfOpenChat');
    btn.addEventListener('click', () => {
      const tg = LumioAPI.getTG();
      LumioUI.showToast('Открываю чат…', 'info');
      if (tg) setTimeout(() => tg.close(), 400);
    });
  }

  function mountResume(screen) {
    const submit = screen.querySelector('#resumeSubmit');
    const vacancyEl = screen.querySelector('#resumeVacancy');
    const expEl = screen.querySelector('#resumeExperience');
    submit.addEventListener('click', () => {
      const vacancy = (vacancyEl.value || '').trim();
      const exp = (expEl.value || '').trim();
      if (vacancy.length < 30 || exp.length < 30) {
        LumioUI.showToast('Опиши вакансию и опыт подробнее (от 30 символов каждый).', 'error');
        return;
      }
      if (!preflight()) return;
      submit.disabled = true;
      const ok = LumioAPI.sendToBot('resume', { vacancy: vacancy, experience: exp });
      if (!ok) submit.disabled = false;
    });
  }

  // ---------------------------------------------------------------------
  // Quota preflight (UI-only — authoritative check happens on the bot)
  // ---------------------------------------------------------------------

  function preflight() {
    if (state.plan === 'pro') return true;
    if (state.remaining <= 0) {
      LumioUI.showPaywall();
      return false;
    }
    return true;
  }

  // ---------------------------------------------------------------------
  // Initial quota hint from initDataUnsafe (best-effort)
  // ---------------------------------------------------------------------

  function readInitialPlan() {
    const tg = LumioAPI.getTG();
    if (!tg || !tg.initDataUnsafe) return;
    // The bot may pass a start_param like "plan=pro" or "left=2" but we don't
    // strictly need it — the badge updates after the first server response.
    const start = tg.initDataUnsafe.start_param || '';
    if (!start) return;
    const params = start.split(';').reduce((acc, kv) => {
      const [k, v] = kv.split('=');
      if (k) acc[k.trim()] = (v || '').trim();
      return acc;
    }, {});
    if (params.plan) state.plan = params.plan;
    if (params.left) state.remaining = parseInt(params.left, 10) || 0;
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------

  function bindGlobalUI() {
    const back = document.getElementById('backBtn');
    back.addEventListener('click', () => navigate('home'));

    const tg = LumioAPI.getTG();
    if (tg && tg.BackButton) {
      tg.BackButton.onClick(() => navigate('home'));
    }
    if (tg && tg.MainButton) {
      tg.MainButton.hide();
    }
  }

  function boot() {
    LumioAPI.expandAndConfigure();
    readInitialPlan();
    bindGlobalUI();
    navigate('home');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  global.LumioApp = { navigate: navigate, state: state };
})(window);
