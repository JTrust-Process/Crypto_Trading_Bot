# Crypto Trading Bot

An automated EMA crossover trading bot for BTC and ETH, built on Public brokerage's API. Runs on GitHub Actions every 15 minutes, 24/7. Logs everything to Supabase. Sends Discord notifications on trades and daily summaries.

---

## How it works

Every 15 minutes GitHub Actions triggers a single bot cycle:

1. Fetches current BTC and ETH prices from Public API
2. Appends price to a rolling 50-candle history stored in GHA cache (`state.json`)
3. Calculates EMA 9 and EMA 21 from the price history
4. If EMA9 crosses above EMA21 → **BUY** signal
5. If EMA9 crosses below EMA21 while in position → **SELL** signal
6. Hard exits always checked first: **stop-loss at -3%**, **take-profit at +5%**
7. All trades, runs, events, and errors logged to Supabase
8. Discord webhook pinged on every trade + daily summary each morning

---

## Stack

| Layer | Technology |
|---|---|
| Exchange | [Public.com](https://public.com) brokerage API |
| Scheduler | GitHub Actions (cron `*/15 * * * *`) |
| State | `state.json` persisted via GHA cache |
| Database | Supabase (PostgreSQL) |
| Notifications | Discord webhook |
| Dashboard | Next.js on Vercel |
| Language | Python 3.11 |

---

## Project structure

```
crypto_bot/
├── core/
│   └── engine.py          # Main cycle logic — one run per GHA trigger
├── config/
│   └── settings.py        # All config — lazy env var loading, no module-level os.getenv()
├── data/
│   └── market_data.py     # Price fetching from Public API
├── exchange/
│   └── public_api.py      # Public API client — auth, quotes, order placement
├── execution/
│   └── trader.py          # Buy/sell execution with DRY_RUN support
├── strategy/
│   └── signal.py          # EMA 9/21 crossover signal generation
├── risk/
│   └── manager.py         # Position sizing with hard USD cap
├── state/
│   └── state.py           # state.json read/write — prices, positions, capital
├── logging/
│   ├── logger.py          # append_log() — stdout + CSV + Supabase
│   ├── monitor.py         # Run lifecycle tracking (bot_runs table)
│   └── supabase_logger.py # Trade logging (crypto_trades table)
├── notifications/
│   └── discord.py         # Discord webhook — trades + daily summary
└── utils/
    └── retry.py           # Retry decorator for API calls

main.py                    # Entry point — try/finally guarantees end_run() always fires
requirements.txt
.github/workflows/crypto_bot.yml
```

---

## Signal logic

```
Warmup: first 22 price readings → signal always HOLD
After warmup:
  EMA9 crosses above EMA21 + not in position → BUY
  EMA9 crosses below EMA21 + in position     → SELL
  Otherwise                                  → HOLD

At 15-min intervals: ~5.5 hours to complete warmup
```

---

## Risk management

| Parameter | Value | Description |
|---|---|---|
| `RISK_PER_TRADE` | 2% | Fraction of capital risked per trade |
| `STOP_LOSS_PCT` | 3% | Hard stop-loss below entry |
| `TAKE_PROFIT_PCT` | 5% | Hard take-profit above entry |
| `MAX_ORDER_AMOUNT_USD` | $10 | Hard cap per order regardless of capital |
| `CIRCUIT_BREAKER_LOSSES` | 3 | Pause symbol after N consecutive losses |

Position size formula: `(capital × risk_pct) / stop_loss_pct`, capped at `MAX_ORDER_AMOUNT_USD`.

---

## Supabase tables

| Table | Description |
|---|---|
| `bot_runs` | One row per GHA trigger — start time, end time, status |
| `bot_events` | Signals fired, buys, sells, exits |
| `bot_errors` | Exceptions caught during a run |
| `bot_logs` | Full stdout mirror |
| `crypto_trades` | Every buy and sell with price, size, P&L, reason |

Run `supabase/migrations/001_create_bot_tables.sql` to create all tables. Run `supabase/migrations/002_fix_rls.sql` to configure row-level security (anon key read-only, service role write).

---

## Environment variables

### GitHub Secrets (never commit these)

| Secret | Description |
|---|---|
| `PUBLIC_SECRET` | Secret key from public.com → Settings → Security → API |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook URL |

### Workflow env vars (non-secrets, visible in repo)

| Variable | Default | Description |
|---|---|---|
| `SYMBOLS` | `BTC,ETH` | Comma-separated symbols to trade |
| `INITIAL_CAPITAL` | `15` | Starting capital in USD |
| `RISK_PER_TRADE` | `0.02` | Risk fraction per trade |
| `STOP_LOSS_PCT` | `0.03` | Stop-loss percentage |
| `TAKE_PROFIT_PCT` | `0.05` | Take-profit percentage |
| `MAX_ORDER_AMOUNT_USD` | `10` | Hard cap per order |
| `CIRCUIT_BREAKER_LOSSES` | `3` | Consecutive losses before pausing |
| `DRY_RUN` | `0` | Set to `1` for paper trading |
| `RUN_ONCE` | `1` | Exit after one cycle (always 1 for GHA) |

---

## Local development

```bash
# Clone and install
git clone https://github.com/your-username/crypto-trading-bot
cd crypto-trading-bot
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Fill in PUBLIC_SECRET, SUPABASE_URL, SUPABASE_KEY, DISCORD_WEBHOOK_URL

# Paper trade locally (DRY_RUN=1 in .env)
python main.py
```

---

## Paper trading vs live trading

Set `DRY_RUN=1` in the workflow YAML to simulate trades without placing real orders. Paper trades are logged to Supabase with `reason` prefixed `DRY_RUN/` so they're clearly separated from live trades in the dashboard.

To go live: set `DRY_RUN=0` and push.

---

## State persistence

`state.json` is persisted between GHA runs using the Actions cache. It stores:

```json
{
  "capital": 15.0,
  "positions": {
    "ETH": { "entry": 2221.20, "usd_amount": 10.0, "stop_loss": 2154.56, "take_profit": 2332.26 }
  },
  "price_history": {
    "BTC": [71986.96, 71468.98, "...up to 50 prices"],
    "ETH": [2244.58, 2238.62, "..."]
  },
  "consecutive_losses": { "BTC": 0, "ETH": 0 },
  "last_daily_summary": "2025-04-13"
}
```

`state.json` is gitignored — it only lives in the GHA cache.

---

## Discord notifications

| Event | Trigger |
|---|---|
| 🟢 Buy order placed | EMA crossover BUY signal |
| 🎯 Take profit | Price hits +5% from entry |
| 🛑 Stop loss | Price hits -3% from entry |
| 💰 Sell — profit | EMA crossover SELL with P&L > 0 |
| 🔴 Sell — loss | EMA crossover SELL with P&L < 0 |
| ⚡ Circuit breaker | 3 consecutive losses on a symbol |
| ❌ Bot error | Any unhandled exception |
| 📊 Daily summary | Once per day — capital, positions, EMA gaps, prices |

---

## Dashboard

Built with Next.js and deployed on Vercel. Reads from Supabase in real time (auto-refresh every 30s).

Features: capital curve, P&L per trade, EMA gap tracker, open position cards with SL/TP progress bar, 7-day sparklines with trade markers, bot health strip, runs/errors explorer.

See `/dashboard` for the source.

---

## Architecture patterns

- **Lazy env var loading** — `os.getenv()` never called at module import time, only inside functions after `load_dotenv()` runs in `__main__`
- **`try/finally` in `main.py`** — `monitor.end_run()` always fires even on crash
- **`_log_to_supabase()` never crashes the bot** — all Supabase calls wrapped in try/except
- **`place_order_buy` uses `amount` (USD notional), `place_order_sell` uses `quantity` (crypto units)** — required by Public API
- **`RUN_ONCE=1`** — each GHA trigger is exactly one cycle, no `while True` loops
- **Deterministic state** — all mutable state lives in `state.json`, never in memory between runs
