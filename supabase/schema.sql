-- =====================================================================
-- Guia de Compras Sou Coluna · banco de dados (Supabase / Postgres)
--
-- Como aplicar: Supabase → SQL Editor → cole este arquivo inteiro → Run.
-- Pode rodar de novo sem perder dados (tudo é "if not exists" / "or replace").
--
-- Modelo:
--   perfis    1 linha por pessoa com login (criada sozinha no cadastro)
--   unidades  as unidades em abertura; cada uma tem um código de convite
--   membros   quem tem acesso a qual unidade (franqueado ↔ unidade)
--   compras   o progresso: 1 linha por item marcado em cada unidade
--
-- Quem vê o quê (Row Level Security):
--   franqueado   só as unidades de que é membro e as compras delas
--   franqueadora tudo (perfis.franqueadora = true, definido só pelo SQL)
-- =====================================================================

-- ---------- tabelas ----------
create table if not exists public.perfis (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  email        text not null,
  nome         text,
  franqueadora boolean not null default false,
  criado_em    timestamptz not null default now()
);

create or replace function public.gerar_codigo() returns text
language sql volatile set search_path = '' as $$
  -- 10 caracteres hexadecimais (~1 trilhão de combinações), ex.: 7F3A9-C0D41
  select upper(substr(md5(gen_random_uuid()::text), 1, 5) || '-' ||
               substr(md5(gen_random_uuid()::text), 1, 5));
$$;

create table if not exists public.unidades (
  id          uuid primary key default gen_random_uuid(),
  nome        text not null check (length(trim(nome)) > 0),
  cidade      text,
  responsavel text,
  inauguracao date,
  codigo      text not null unique default public.gerar_codigo(),
  criado_em   timestamptz not null default now()
);

create table if not exists public.membros (
  user_id    uuid not null references public.perfis(user_id) on delete cascade,
  unidade_id uuid not null references public.unidades(id) on delete cascade,
  criado_em  timestamptz not null default now(),
  primary key (user_id, unidade_id)
);
create index if not exists membros_unidade_idx on public.membros(unidade_id);

create table if not exists public.compras (
  unidade_id     uuid not null references public.unidades(id) on delete cascade,
  item_id        text not null,                 -- id do item em data.py (ex.: enxoval-geladeira)
  comprado       boolean not null default false,
  valor_pago     numeric(12,2) check (valor_pago is null or valor_pago >= 0),
  atualizado_em  timestamptz not null default now(),
  atualizado_por uuid references auth.users(id) on delete set null default auth.uid(),
  primary key (unidade_id, item_id)
);

-- ---------- funções auxiliares (security definer evita recursão nas políticas) ----------
create or replace function public.e_franqueadora() returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((select p.franqueadora from public.perfis p where p.user_id = auth.uid()), false);
$$;

create or replace function public.e_membro(u uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.membros m where m.user_id = auth.uid() and m.unidade_id = u);
$$;

-- ---------- carimbo de quem/quando alterou a compra ----------
create or replace function public.carimbar_compra() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.atualizado_em := now();
  new.atualizado_por := auth.uid();
  return new;
end $$;

drop trigger if exists compras_carimbo on public.compras;
create trigger compras_carimbo before insert or update on public.compras
  for each row execute function public.carimbar_compra();

-- ---------- cadastro: cria o perfil e, se veio código válido, liga à unidade ----------
create or replace function public.novo_usuario() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  u uuid;
begin
  insert into public.perfis (user_id, email, nome)
  values (new.id, coalesce(new.email, ''), nullif(trim(new.raw_user_meta_data ->> 'nome'), ''))
  on conflict (user_id) do nothing;

  select id into u from public.unidades
   where codigo = upper(trim(coalesce(new.raw_user_meta_data ->> 'codigo', '')));
  if u is not null then
    insert into public.membros (user_id, unidade_id) values (new.id, u) on conflict do nothing;
  end if;
  return new;
end $$;

drop trigger if exists ao_criar_usuario on auth.users;
create trigger ao_criar_usuario after insert on auth.users
  for each row execute function public.novo_usuario();

-- ---------- RPCs chamadas pelo site ----------
-- Confere um código antes de criar a conta (só diz sim/não, não revela a unidade).
create or replace function public.codigo_valido(codigo text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.unidades u where u.codigo = upper(trim(codigo_valido.codigo)));
$$;

-- Usuário já logado entra em (mais) uma unidade com o código recebido.
create or replace function public.entrar_com_codigo(codigo text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  u uuid;
begin
  if auth.uid() is null then raise exception 'login necessário'; end if;
  select id into u from public.unidades where unidades.codigo = upper(trim(entrar_com_codigo.codigo));
  if u is null then raise exception 'codigo_invalido'; end if;
  insert into public.membros (user_id, unidade_id) values (auth.uid(), u) on conflict do nothing;
  return u;
end $$;

-- Franqueado (ou franqueadora) atualiza o nome do responsável pelas compras.
create or replace function public.definir_responsavel(unidade uuid, nome text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not (public.e_membro(unidade) or public.e_franqueadora()) then
    raise exception 'sem acesso a esta unidade';
  end if;
  update public.unidades set responsavel = nullif(trim(definir_responsavel.nome), '') where id = unidade;
end $$;

-- Franqueadora gera um código novo (o antigo deixa de funcionar).
create or replace function public.renovar_codigo(unidade uuid) returns text
language plpgsql security definer set search_path = '' as $$
declare
  c text;
begin
  if not public.e_franqueadora() then raise exception 'apenas a franqueadora'; end if;
  update public.unidades set codigo = public.gerar_codigo() where id = unidade returning codigo into c;
  return c;
end $$;

-- ---------- permissões ----------
alter table public.perfis   enable row level security;
alter table public.unidades enable row level security;
alter table public.membros  enable row level security;
alter table public.compras  enable row level security;

-- ninguém sem login acessa nada
revoke all on public.perfis, public.unidades, public.membros, public.compras from anon;

-- perfis: cada um só pode mudar o próprio nome (nunca a coluna "franqueadora")
revoke insert, update, delete on public.perfis from authenticated;
grant select on public.perfis to authenticated;
grant update (nome) on public.perfis to authenticated;

drop policy if exists perfis_ler on public.perfis;
create policy perfis_ler on public.perfis for select to authenticated
  using (user_id = (select auth.uid()) or (select public.e_franqueadora()));
drop policy if exists perfis_editar on public.perfis;
create policy perfis_editar on public.perfis for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- unidades: franqueado lê as suas; franqueadora faz tudo
grant select, insert, update, delete on public.unidades to authenticated;
drop policy if exists unidades_ler on public.unidades;
create policy unidades_ler on public.unidades for select to authenticated
  using ((select public.e_franqueadora()) or public.e_membro(id));
drop policy if exists unidades_franqueadora on public.unidades;
create policy unidades_franqueadora on public.unidades for all to authenticated
  using ((select public.e_franqueadora())) with check ((select public.e_franqueadora()));

-- membros: cada um vê os próprios vínculos; franqueadora vê e remove todos
grant select, insert, delete on public.membros to authenticated;
drop policy if exists membros_ler on public.membros;
create policy membros_ler on public.membros for select to authenticated
  using (user_id = (select auth.uid()) or (select public.e_franqueadora()));
drop policy if exists membros_franqueadora on public.membros;
create policy membros_franqueadora on public.membros for all to authenticated
  using ((select public.e_franqueadora())) with check ((select public.e_franqueadora()));

-- compras: membros da unidade e franqueadora leem e gravam
grant select, insert, update, delete on public.compras to authenticated;
drop policy if exists compras_acesso on public.compras;
create policy compras_acesso on public.compras for all to authenticated
  using ((select public.e_franqueadora()) or public.e_membro(unidade_id))
  with check ((select public.e_franqueadora()) or public.e_membro(unidade_id));

-- funções usadas nas políticas e no valor padrão do código
grant execute on function public.e_franqueadora(), public.e_membro(uuid), public.gerar_codigo() to authenticated;

-- RPCs: quem pode chamar
revoke execute on function public.codigo_valido(text), public.entrar_com_codigo(text),
  public.definir_responsavel(uuid, text), public.renovar_codigo(uuid) from public;
revoke execute on function public.entrar_com_codigo(text), public.definir_responsavel(uuid, text),
  public.renovar_codigo(uuid) from anon;
grant execute on function public.codigo_valido(text) to anon, authenticated;
grant execute on function public.entrar_com_codigo(text), public.definir_responsavel(uuid, text),
  public.renovar_codigo(uuid) to authenticated;

-- =====================================================================
-- Depois de criar a SUA conta no site, rode (trocando o e-mail) para
-- virar franqueadora e enxergar o painel com todas as unidades:
--
--   update public.perfis set franqueadora = true where email = 'seu-email@exemplo.com';
-- =====================================================================
