/* LUMIO — bridge to the bot via Telegram.WebApp.sendData. */
(function (global) {
  'use strict';

  function getTG() {
    return (global.Telegram && global.Telegram.WebApp) || null;
  }

  /**
   * Send a structured tool request to the bot.
   * Telegram closes the WebApp after sendData; the bot will reply in chat.
   */
  function sendToBot(tool, payload) {
    const tg = getTG();
    if (!tg) {
      LumioUI.showToast('Открой через Telegram, чтобы отправить запрос.', 'error');
      return false;
    }

    const data = JSON.stringify({ tool: tool, payload: payload || {} });

    try {
      tg.HapticFeedback && tg.HapticFeedback.impactOccurred('medium');
    } catch (_) { /* noop */ }

    try {
      tg.sendData(data);
      return true;
    } catch (err) {
      LumioUI.showToast('Не удалось отправить данные: ' + (err.message || err), 'error');
      return false;
    }
  }

  function expandAndConfigure() {
    const tg = getTG();
    if (!tg) return;
    tg.ready();
    tg.expand();
    if (tg.setHeaderColor) {
      try { tg.setHeaderColor('secondary_bg_color'); } catch (_) {}
    }
    if (tg.enableClosingConfirmation) {
      try { tg.disableClosingConfirmation(); } catch (_) {}
    }
  }

  global.LumioAPI = {
    sendToBot: sendToBot,
    expandAndConfigure: expandAndConfigure,
    getTG: getTG,
  };
})(window);
