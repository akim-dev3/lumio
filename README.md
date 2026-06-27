# LUMIO

AI-powered productivity Telegram Mini App: Anki flashcards, TG copywriter, PDF analyst, resume builder — all in one bot.

Stack: **aiogram 3.15+** · **OpenRouter** (free LLM models, no geo restrictions) · **PyMuPDF** · **genanki** · **SQLite/aiosqlite** · **Vanilla JS SPA** · **Telegram Stars** for payments. Zero paid APIs, single Render free-tier deployment.

---

## Project layout

```
lumio/
├── bot/
│   ├── main.py              # webhook entry point
│   ├── config.py            # env loader
│   ├── handlers/            # /start, payment, webapp dispatcher
│   ├── services/            # gemini, anki_gen, pdf_parser, limits
│   └── db/                  # aiosqlite schema + queries
├── docs/
│   ├── index.html           # SPA shell + templates
│   ├── css/style.css        # dark-first, TG theme vars
│   └── js/{app,api,ui}.js   # router + bridge + components
├── .env.example
├── requirements.txt
└── README.md
```

---

## Local setup

```bash
# 1) clone + virtualenv
python -m venv .venv
.venv\Scripts\activate                # Windows
# source .venv/bin/activate            # macOS / Linux
pip install -r requirements.txt

# 2) env
copy .env.example .env                 # Windows
# cp .env.example .env                 # macOS / Linux
# fill BOT_TOKEN, GEMINI_API_KEY, WEBAPP_URL, WEBHOOK_URL

# 3) run in polling mode for dev
python -m bot.main --polling
```

For local Mini App testing, serve `docs/` with any static server and expose it over HTTPS (e.g. with [`ngrok`](https://ngrok.com) or [`cloudflared`](https://github.com/cloudflare/cloudflared)) — Telegram requires HTTPS for `WebAppInfo.url`.

```bash
cd webapp
python -m http.server 5173
# in another terminal:
ngrok http 5173
# put the https URL into .env as WEBAPP_URL
```

---

## Deploying to Render (free tier)

### A. Static site — webapp

1. New Static Site → connect repo → root `docs/`.
2. Build command: *(empty)* — Publish dir: `.`.
3. Render gives you `https://lumio-webapp.onrender.com` → put it in `WEBAPP_URL`.

### B. Web service — bot

1. New Web Service → connect repo → root project.
2. Runtime: Python 3.11+.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `python -m bot.main`.
5. Add env vars from `.env.example`. `WEBHOOK_URL` = the public URL Render gives you (e.g. `https://lumio-bot.onrender.com`).
6. Render assigns `PORT` automatically — the bot reads it.

The bot registers its webhook on startup (`/webhook`) using `WEBHOOK_SECRET`.

---

## Bot setup in @BotFather

1. Create a bot, copy the token → `BOT_TOKEN`.
2. `/setmenubutton` → choose your bot → set name **"Open LUMIO"** → set URL = `WEBAPP_URL`.
3. `/setdomain` → set to your `WEBAPP_URL` domain.
4. (Optional) `/setcommands`:
   ```
   start - Главное меню
   status - Мой план и остаток
   plans - Купить безлимит
   help - Помощь
   ```

---

## Freemium logic

| Tier | Daily limit | Paid via |
|------|-------------|----------|
| Free | 3 requests / UTC day | — |
| Top-up | +20 requests one-time | ⭐ 99 Stars |
| Pro 30 | unlimited 30 days | ⭐ 299 Stars |
| Pro 180 | unlimited 180 days | ⭐ 999 Stars |

Limits are enforced server-side in `bot/services/limits.py` before any AI call. The frontend badge is informational only.

---

## Tools

| Tool | UI input | Bot output |
|------|----------|-----------|
| 🎴 Cards | textarea + count (10/20/30) | preview + `.apkg` Anki deck |
| ✍️ Posts | topic + count + tone | N posts, one per message |
| 📄 PDF | upload PDF in chat | summary + key points + questions |
| 💼 Resume | vacancy + experience | resume + cover letter + tips |

All Gemini calls retry once on JSON parse / validation failure, then surface a graceful "try again" message.

---

## Database

Single SQLite file (`lumio.db`). Schema is created on startup; no migrations framework needed at this scale.

| Table | Purpose |
|-------|---------|
| `users` | tg_id, plan, plan_expires, daily_count, last_reset |
| `transactions` | log of every successful Stars payment |

To reset a user during testing:

```sql
UPDATE users SET daily_count = 0 WHERE tg_id = <your tg id>;
```

---

## Troubleshooting

- **WebApp button does nothing** — `/setdomain` not set in BotFather, or `WEBAPP_URL` is HTTP (must be HTTPS).
- **`sendData` from Mini App is ignored** — you opened the app via an inline-keyboard button. Use the reply-keyboard "🚀 Open LUMIO" button or the menu button.
- **LLM returns null** — check `OPENROUTER_API_KEY` at <https://openrouter.ai/keys>. Free models have a per-day quota (currently 50 requests/day per key); pick another `OPENROUTER_MODEL` if exhausted. Browse free models: <https://openrouter.ai/models?max_price=0>.
- **Render free tier sleeps** — the first request after idle takes ~30 s. That's fine for a personal/MVP bot; Render keeps the webhook URL valid through restarts.
