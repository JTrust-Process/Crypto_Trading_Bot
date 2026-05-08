-- 004_bot_state_lockdown.sql
-- Audit H1 (dashboard side) — fix the over-broad public read on bot_state.
--
-- 003_bot_state.sql granted `select using (true)` to anon + authenticated.
-- That meant anyone with the deployed dashboard's anon key (i.e. anyone who
-- could view-source the deployed JS) could read the full state.json blob:
-- capital, open positions with entry/SL/TP, full price history, loss streaks,
-- desync flags. Locking that down here.
--
-- The bot itself uses the SERVICE ROLE key (SUPABASE_KEY secret) which
-- bypasses RLS, so its writes/reads to bot_state continue to work.
--
-- Two options for the dashboard, pick one before applying:
--
--   A) "Read only the production branch row" — the dashboard reads positions
--      and capital from a known key (e.g. 'main'). Capital + positions are
--      still visible to anyone with the anon key, but other branches' state
--      (feature-branch test runs, etc.) is hidden.
--
--   B) "Service-role only" — the dashboard does NOT query bot_state. It
--      keeps reconstructing state from bot_events + bot_logs as before.
--      Use this if you want maximum privacy at the cost of accuracy.
--
-- This file is configured for (A). To switch to (B), comment out the
-- create policy block.

drop policy if exists "bot_state_read" on public.bot_state;

-- Option A — narrow read policy, only for the canonical production row.
-- Adjust the IN list to match your branch / STATE_KEY values. By default
-- this allows reads for the bot's GHA `main` branch and the local "default".
create policy "bot_state_read_main"
    on public.bot_state for select
    to anon, authenticated
    using (key in ('main', 'master', 'default'));
