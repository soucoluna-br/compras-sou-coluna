-- Imita o mínimo do Supabase num Postgres comum, só para testar supabase/schema.sql:
-- papéis anon/authenticated, schema auth com auth.users e auth.uid(), e os grants padrão.
-- papéis valem para o servidor inteiro: só cria se ainda não existirem
do $$ begin create role anon nologin; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$;
create schema auth;
create table auth.users (
  id uuid primary key default gen_random_uuid(),
  email text,
  raw_user_meta_data jsonb default '{}'::jsonb
);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
grant usage on schema public, auth to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;
alter default privileges in schema public grant all on tables to anon, authenticated;
-- cenário mais restrito: funções novas NÃO ficam liberadas para todos (o schema precisa dar os grants)
alter default privileges revoke execute on functions from public;
