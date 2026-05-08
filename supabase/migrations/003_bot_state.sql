-- 003_bot_state.sql
-- Audit H1 — Supabase fallback for state.json.
--
-- One row per branch (key = github.ref_name in CI, "default" locally).
-- The bot upserts on save and reads only when the local cache is missing.
-- See crypto_bot/state/remote.py.

create table if not exists public.bot_state (
    key         text primary key,
    state       jsonb not null,
    updated_at  timestamptz not null default now()
);

alter table public.bot_state enable row level security;

drop policy if exists "bot_state_read" on public.bot_state;
create policy "bot_state_read"
    on public.bot_state for select
    to anon, authenticated
    using (true);
