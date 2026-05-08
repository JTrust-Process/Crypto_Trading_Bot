-- 001_create_bot_tables.sql
-- Initial schema for the crypto trading bot.
--
-- Run order:
--   001_create_bot_tables.sql   (this file)
--   002_fix_rls.sql             (RLS policies — write requires service role)
--   003_bot_state.sql           (Supabase fallback for state.json — audit H1)
--
-- All run_id columns are TEXT so they line up with what monitor.py inserts
-- (it stringifies the inserted id from bot_runs).

-- ── Run lifecycle ────────────────────────────────────────────────────────────
create table if not exists public.bot_runs (
    id          bigserial primary key,
    started_at  timestamptz not null default now(),
    ended_at    timestamptz,
    status      text not null default 'running'
                check (status in ('running', 'completed', 'error'))
);

create index if not exists bot_runs_started_at_idx
    on public.bot_runs (started_at desc);

-- ── Stdout mirror ────────────────────────────────────────────────────────────
create table if not exists public.bot_logs (
    id          bigserial primary key,
    run_id      text,
    level       text not null,
    message     text not null,
    created_at  timestamptz not null default now()
);

create index if not exists bot_logs_created_at_idx
    on public.bot_logs (created_at desc);
create index if not exists bot_logs_run_id_idx
    on public.bot_logs (run_id);

-- ── Errors ───────────────────────────────────────────────────────────────────
create table if not exists public.bot_errors (
    id          bigserial primary key,
    run_id      text,
    context     text,
    error       text not null,
    created_at  timestamptz not null default now()
);

create index if not exists bot_errors_created_at_idx
    on public.bot_errors (created_at desc);
create index if not exists bot_errors_run_id_idx
    on public.bot_errors (run_id);

-- ── Discrete events (signals, buys, sells, filtered, circuit_breaker, …) ────
create table if not exists public.bot_events (
    id          bigserial primary key,
    run_id      text,
    event_type  text not null,
    message     text not null,
    created_at  timestamptz not null default now()
);

create index if not exists bot_events_created_at_idx
    on public.bot_events (created_at desc);
create index if not exists bot_events_run_id_idx
    on public.bot_events (run_id);

-- ── Trades ───────────────────────────────────────────────────────────────────
create table if not exists public.crypto_trades (
    id          bigserial primary key,
    run_id      text,
    timestamp   timestamptz not null default now(),
    symbol      text not null,
    side        text not null check (side in ('BUY', 'SELL')),
    price       double precision not null,
    size        double precision not null,
    pnl         double precision not null default 0,
    reason      text,
    order_id    text
);

-- Defense-in-depth: if Public's order_id is present, insertions for the same
-- order_id should not duplicate. The bot doesn't currently retry trade
-- inserts, but if it ever does, this prevents double-counting.
create unique index if not exists crypto_trades_order_id_uq
    on public.crypto_trades (order_id)
    where order_id is not null;

create index if not exists crypto_trades_timestamp_idx
    on public.crypto_trades (timestamp desc);
create index if not exists crypto_trades_symbol_idx
    on public.crypto_trades (symbol);
