# Crypto Trading Bot

An automated EMA-crossover trading bot for BTC and ETH on the Public.com brokerage API. Runs on GitHub Actions every 15 minutes (cron offset minutes), 24/7. Logs runs, events, errors, logs, and trades to Supabase. Sends Discord notifications on trades, daily summaries, and operator-relevant warnings.

---

## How it works

Every 15 minutes (`7,22,37,52 * * * *`) a GitHub Actions cron triggers a single bot cycle:

1. Loads `state.json` from the GHA cache (or from a Supabase fallback row if the cache missed).
2. Reconciles state against Public's portfolio: if Public holds crypto we don't track, the symbol is marked DESYNC and BUYs are blocked until manually resolved.
3. For each symbol it fetches the spot price from Public, appends to a rolling 80-candle history, and computes EMA9 / EMA21.
4. Hard exits fire first — ATR-based stop-loss / take-profit (with fixed-percent fallback if ATR fetch fails).
5. New entries require: not in cooldown, regime-up (price > EMA50 and EMA50 rising), and a minimum EMA gap. ATR drives both the stop distance AND the position size, so risk-per-trade reflects the real stop, not a fixed assumption.
6. Strategy SELLs require minimum hold candles and minimum profit (so fees don't eat the trade).
7. Run lifecycle, every log line, every event, every error, and every trade goes to Supabase. The Next.js dashboard reads from there.

---

## Stack

| Layer | Technology |
|---|---|
| Exchange | [Public.com](https://public.com) brokerage API |
| Scheduler | GitHub Actions (cron `7,22,37,52 * * * *`) |
| State | `state.json` via GHA cache, with Supabase fallback (`bot_state` table) |
| ATR data | CoinGecko free OHLC (with fixed-pct fallback if rate-limited) |
| Database | Supabase (PostgreSQL) |
| Notifications | Discord webhook |
| Dashboard | Next.js (see `../CryptoBot_Dashboard`) |
| Language | Python 3.11 |

---

## Project structure

```
crypto_bot/
├── core/engine.py          # Per-cycle orchestration: reconcile → signal → filter → exec
├── config/settings.py      # Lazy env vars; all os.getenv() reads happen post-load_dotenv
├── data/market_data.py     # Public spot quote wrapper
├── data/coingecko.py       # OHLC + ATR (free tier, in-process cache)
├── exchange/public_api.py  # Public API client — auth, quotes, orders, portfolio
├── execution/trader.py     # buy / sell, fill polling, partial-fill handling, SL/TP calc
├── strategy/signal.py      # EMA9/21 crossover + EMA50 regime check
├── risk/manager.py         # Position sizing using actual ATR-derived stop
├── state/state.py          # state.json read/write — local primary
├── state/remote.py         # Supabase mirror — recovery for cache miss
├── logging/_supabase.py    # Shared Supabase client
├── logging/logger.py       # log/log_warn/log_error → stdout + bot_logs
├── logging/monitor.py      # bot_runs lifecycle + bot_events + bot_errors
├── logging/supabase_logger # crypto_trades inserts
├── notifications/discord.py
└── utils/retry.py
main.py                     # Entry point — try/except/finally with correct status passing
.github/workflows/crypto_bot.yaml
supabase/migrations/        # 001_create_bot_tables, 002_fix_rls, 003_bot_state
```

---

## Strategy

EMA crossover with regime + ATR + cooldown filters:

```
Warmup: signal needs EMA_SLOW + 2 = 23 prices.
Regime filter needs EMA50 + lookback = 55 prices (~14 hrs at 15-min cadence).

Entry:
  EMA9 crosses above EMA21
  AND not in position
  AND not desynced with Public
  AND past cooldown (4 candles after last exit)
  AND regime-up (price > EMA50, EMA50 rising over last 5 candles)
  AND |EMA9 − EMA21| / price ≥ MIN_SIGNAL_GAP_PCT

Strategy exit:
  EMA9 crosses below EMA21
  AND in position
  AND held ≥ MIN_HOLD_CANDLES
  AND unrealised gain ≥ MIN_SIGNAL_PROFIT_PCT (so fees don't eat profit)

Hard exit (always fires):
  Price hits ATR-based SL or TP, or fixed-% fallback if ATR fetch failed.
```

---

## Risk management

| Parameter | Default | Description |
|---|---|---|
| `RISK_PER_TRADE` | 0.02 | Fraction of capital risked per trade |
| `STOP_LOSS_PCT` | 0.03 | Fallback stop-loss when ATR is unavailable |
| `TAKE_PROFIT_PCT` | 0.05 | Fallback take-profit when ATR is unavailable |
| `MAX_ORDER_AMOUNT_USD` | 25 | Hard cap per order regardless of capital |
| `MIN_BUYING_POWER_BUFFER` | 25 | Don't trade if cash would drop below this |
| `CIRCUIT_BREAKER_LOSSES` | 3 | Pause symbol after N consecutive losses |
| `ATR_PERIOD` | 14 | ATR averaging window |
| `ATR_SL_MULTIPLIER` | 2.0 | SL = entry − 2 × ATR |
| `ATR_TP_MULTIPLIER` | 4.0 | TP = entry + 4 × ATR (2:1 reward:risk) |
| `COOLDOWN_CANDLES` | 4 | Block re-entry for ~1hr after exit |
| `MIN_SIGNAL_GAP_PCT` | 0.0015 | Reject weak crossovers below this gap |
| `MIN_SIGNAL_PROFIT_PCT` | 0.03 | Reject SELLs that wouldn't beat fees |
| `MIN_HOLD_CANDLES` | 4 | Don't strategy-exit before this many candles held |
| `CRYPTO_FEE_PER_ORDER` | 0.06 | Public's per-order fee — round-trip subtracted from PnL |

Position size formula (post-audit C3):

```
risk_amount  = capital × RISK_PER_TRADE
usd_to_spend = risk_amount / actual_stop_pct       # ATR-derived; falls back to STOP_LOSS_PCT
usd_to_spend = min(usd_to_spend, capital, MAX_ORDER_AMOUNT_USD)
```

Buying power is checked against Public's `cashOnlyBuyingPower` before any BUY. If the check fails, the trade is skipped (fail-closed).

---

## Supabase tables

| Table | Description |
|---|---|
| `bot_runs` | One row per GHA trigger — start, end, status (`running` / `completed` / `error`) |
| `bot_logs` | Full stdout mirror with level (INFO/WARN/ERROR) |
| `bot_events` | Discrete events: signals, buys, sells, exits, filtered, circuit_breaker |
| `bot_errors` | Caught exceptions with run_id and context |
| `crypto_trades` | Every BUY and SELL with price, size, pnl, reason, order_id |
| `bot_state` | One row per branch — JSONB mirror of `state.json` for cache-miss recovery |

Apply migrations in order:

```
supabase/migrations/001_create_bot_tables.sql
supabase/migrations/002_fix_rls.sql        # anon read-only, service role writes
supabase/migrations/003_bot_state.sql      # state mirror
```

---

## Environment variables

### GitHub Secrets (do not commit)

| Secret | Description |
|---|---|
| `PUBLIC_SECRET` | Secret key from public.com → Settings → Security → API |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase **service-role** key (RLS bypass) |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook URL |

### Workflow `env:` (set in `.github/workflows/crypto_bot.yaml`)

| Variable | Default | Notes |
|---|---|---|
| `SYMBOLS` | `BTC` | Comma-separated. Currently BTC only in workflow; settings module supports BTC,ETH |
| `INITIAL_CAPITAL` | `50` | Used only on first ever run (when state.json is empty) |
| `RISK_PER_TRADE` | `0.02` | Fraction of capital |
| `STOP_LOSS_PCT` | `0.03` | Fallback only — ATR usually drives the real stop |
| `TAKE_PROFIT_PCT` | `0.05` | Fallback only |
| `MAX_ORDER_AMOUNT_USD` | `25` | Hard cap per order |
| `MIN_BUYING_POWER_BUFFER` | `25` | Skip BUY if cash would drop below this |
| `CIRCUIT_BREAKER_LOSSES` | `3` | Pause symbol after N consecutive losses |
| `MIN_SIGNAL_GAP_PCT` | `0.0015` | Reject weak crossovers |
| `MIN_SIGNAL_PROFIT_PCT` | `0.03` | Reject signal-SELLs below this |
| `MIN_HOLD_CANDLES` | `4` | Min candles held before strategy SELL |
| `ATR_PERIOD` | `14` | |
| `ATR_SL_MULTIPLIER` | `2.0` | |
| `ATR_TP_MULTIPLIER` | `4.0` | |
| `COOLDOWN_CANDLES` | `4` | |
| `DRY_RUN` | `0` | Set to `1` for paper trading (workflow value is the live default) |

---

## Local development

```bash
git clone <this-repo>
cd Crypto_Trading_Bot
pip install -r requirements.txt

cp .env.example .env       # fill in your secrets
# IMPORTANT: keep DRY_RUN=1 in .env — your local runs should never place real
# orders by accident. The GitHub Actions workflow has its own DRY_RUN=0.

python main.py
```

`state.json` and `.env` are gitignored. The committed `state.json` is just a placeholder default; if you have a stale local state.json from an earlier session, move it aside before running locally — see `state.json.local-bak` if you'd previously been holding live positions there.

---

## Paper vs live

| Mode | Where | DRY_RUN |
|---|---|---|
| Local paper | your machine | `1` (default in committed `.env`) |
| Live cron | GitHub Actions | `0` (set in workflow YAML) |
| Manual live test | Actions → run workflow | inherits workflow value |

Paper trades are still logged to Supabase with `reason` prefixed `DRY_RUN/` so they're separated from live trades on the dashboard.

---

## State persistence

The bot is stateless across runs except via `state.json`, which lives in:

1. **Primary:** GitHub Actions cache, keyed by `crypto-bot-state-${branch}-${run_id}` with a prefix-based `restore-keys` so any branch run can pick up the most recent cache.
2. **Fallback:** Supabase `bot_state` row keyed by branch (or `default` locally), upserted on every successful save. Read only when the local state.json is missing or unreadable. See `crypto_bot/state/remote.py` and migration 003.

State shape:

```json
{
  "capital": 50.0,
  "positions": { "BTC": { "entry": ..., "usd_amount": ..., "size_estimate": ..., "stop_loss": ..., "take_profit": ..., "candles_at_entry": ..., "exit_method": "ATR" } },
  "price_history": { "BTC": [..up to 80..] },
  "consecutive_losses": { "BTC": 0 },
  "circuit_notified": { "BTC": "2026-05-07" },
  "last_daily_summary": "2026-05-07",
  "last_exit_candle": { "BTC": 53 },
  "position_desync": {},
  "atr_fallback_notified": {}
}
```

---

## Discord notifications

| Event | Trigger |
|---|---|
| Buy order placed | EMA crossover BUY signal passing all filters |
| Take profit | Price hits ATR-derived TP (or 5% fallback) |
| Stop loss | Price hits ATR-derived SL (or 3% fallback) |
| Sell — profit | Strategy SELL with PnL ≥ 0 |
| Sell — loss | Strategy SELL with PnL < 0 |
| Circuit breaker | 3 consecutive losses on a symbol |
| Bot error | Any unhandled exception (caught at engine or symbol scope), or operator-relevant warnings (DESYNC detected, ATR fallback engaged, partial fill) |
| Daily summary | Once per UTC day — capital, positions, EMA gaps, prices |

---

## Architecture patterns

- **Lazy env-var loading** — `os.getenv()` is never called at module import, only inside functions, so `load_dotenv()` in `main.py` always runs first.
- **`try/except/finally` with explicit run status** — `monitor.end_run()` receives the actual outcome, so the dashboard never shows a failed run as "completed" (audit C1).
- **`safe_insert` wraps every Supabase write** — logging never crashes the bot; failures print to stdout for the GHA log.
- **`place_order_buy` uses `amount` (USD notional)** while **`place_order_sell` uses `quantity` (crypto units)** — required by Public's API.
- **Each cron trigger is one cycle** — no `while True` loops, no in-process scheduling. State lives in `state.json`.
- **Reconcile before trade** — every cycle compares Public's portfolio against local state and blocks BUYs on any symbol where they diverge until manually resolved.
- **Fail-closed on uncertainty** — buying-power check failure, reconcile failure, missing fill price, and missing portfolio quantity all skip the action rather than guess.
- **Position sizing uses real stop distance** (audit C3) — risk-per-trade math reflects the ATR-derived stop, not a hardcoded percent.
- **Partial-fill safe SELLs** (audit C2) — if Public still holds the symbol after a SELL, the position stays open with the residual size and PnL is computed only on what filled.
