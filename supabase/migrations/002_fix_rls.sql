-- 002_fix_rls.sql
-- Row-level security: dashboard (anon key) reads only; bot (service role) writes.
--
-- The dashboard at /CryptoBot_Dashboard uses the anon key in browser code, so
-- it must be read-only. The bot in GitHub Actions uses the service-role key
-- (SUPABASE_KEY secret), which bypasses RLS by design.

alter table public.bot_runs       enable row level security;
alter table public.bot_logs       enable row level security;
alter table public.bot_errors     enable row level security;
alter table public.bot_events     enable row level security;
alter table public.crypto_trades  enable row level security;

-- Allow read for anon + authenticated. Service role bypasses RLS so the bot
-- still inserts/updates without policies.
do $$
declare
    t text;
begin
    foreach t in array array['bot_runs', 'bot_logs', 'bot_errors', 'bot_events', 'crypto_trades']
    loop
        execute format(
            'drop policy if exists "%s_read" on public.%I',
            t, t
        );
        execute format(
            'create policy "%s_read" on public.%I for select to anon, authenticated using (true)',
            t, t
        );
    end loop;
end $$;
