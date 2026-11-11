-- Testes das regras de acesso de supabase/schema.sql.
-- Rodar com tests/testar_banco.sh (cria um banco descartável, aplica stub + schema e roda isto).
\set ON_ERROR_STOP 1
\set QUIET 1

-- Espera que um comando falhe (permissão negada, RLS ou exceção da função).
create or replace function pg_temp.deve_falhar(sql text, rotulo text) returns void language plpgsql as $$
begin
  begin
    execute sql;
  exception when others then
    raise notice 'ok (bloqueado): % → %', rotulo, sqlerrm;
    return;
  end;
  raise exception 'FALHOU: deveria ter sido bloqueado: %', rotulo;
end $$;
grant execute on function pg_temp.deve_falhar(text, text) to anon, authenticated;

create or replace function pg_temp.confere(cond boolean, rotulo text) returns void language plpgsql as $$
begin
  if cond is distinct from true then raise exception 'FALHOU: %', rotulo; end if;
  raise notice 'ok: %', rotulo;
end $$;
grant execute on function pg_temp.confere(boolean, text) to anon, authenticated;

-- ---------- cenário (como superusuário, igual ao SQL Editor do Supabase) ----------
insert into public.unidades (id, nome, cidade) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'Sou Coluna Florianópolis', 'Florianópolis'),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'Sou Coluna Curitiba', 'Curitiba');

select codigo as cod_a from public.unidades where nome like '%Florian%' \gset
select codigo as cod_b from public.unidades where nome like '%Curitiba%' \gset

select pg_temp.confere(:'cod_a' ~ '^[0-9A-F]{5}-[0-9A-F]{5}$', 'código no formato XXXXX-XXXXX');

-- cadastros (o trigger em auth.users cria o perfil e liga à unidade pelo código)
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-0000000000ad', 'adm@x.com', '{"nome":"Franqueadora"}'),
  ('00000000-0000-0000-0000-00000000000a', 'fa@x.com',  json_build_object('nome','Ana','codigo', lower(:'cod_a'))::jsonb),
  ('00000000-0000-0000-0000-00000000000b', 'fb@x.com',  json_build_object('nome','Bruno','codigo', :'cod_b')::jsonb),
  ('00000000-0000-0000-0000-00000000000c', 'fc@x.com',  '{"nome":"Carla","codigo":"00000-00000"}'),
  ('00000000-0000-0000-0000-00000000000d', 'fd@x.com',  '{}');

select pg_temp.confere((select count(*) from public.perfis) = 5, 'todo cadastro gera perfil');
select pg_temp.confere(exists(select 1 from public.membros where user_id = '00000000-0000-0000-0000-00000000000a'
  and unidade_id = 'aaaaaaaa-0000-0000-0000-000000000001'), 'código em minúsculas também liga à unidade');
select pg_temp.confere(not exists(select 1 from public.membros where user_id = '00000000-0000-0000-0000-00000000000c'),
  'código inválido no cadastro não liga a nada');

update public.perfis set franqueadora = true where email = 'adm@x.com';

-- ---------- visitante sem login ----------
set role anon;
select pg_temp.deve_falhar('select * from public.unidades', 'anon lendo unidades');
select pg_temp.deve_falhar('select * from public.compras', 'anon lendo compras');
select pg_temp.deve_falhar($q$select public.entrar_com_codigo('X')$q$, 'anon entrando com código');
select pg_temp.confere(public.codigo_valido(lower(:'cod_a')), 'anon confere código válido');
select pg_temp.confere(not public.codigo_valido('00000-00000'), 'anon: código inválido dá falso');
reset role;

-- ---------- franqueada Ana (unidade A) ----------
set role authenticated;
set request.jwt.claim.sub = '00000000-0000-0000-0000-00000000000a';
select pg_temp.confere((select count(*) from public.unidades) = 1, 'Ana vê só a própria unidade');
select pg_temp.confere((select count(*) from public.perfis) = 1, 'Ana vê só o próprio perfil');
select pg_temp.confere((select count(*) from public.membros) = 1, 'Ana vê só o próprio vínculo');
select pg_temp.confere(not public.e_franqueadora(), 'Ana não é franqueadora');

insert into public.compras (unidade_id, item_id, comprado, valor_pago)
values ('aaaaaaaa-0000-0000-0000-000000000001', 'enxoval-geladeira', true, 2899.90);
insert into public.compras (unidade_id, item_id, comprado, valor_pago)
values ('aaaaaaaa-0000-0000-0000-000000000001', 'enxoval-geladeira', true, 2799.90)
on conflict (unidade_id, item_id) do update set comprado = excluded.comprado, valor_pago = excluded.valor_pago;
select pg_temp.confere((select valor_pago from public.compras where item_id = 'enxoval-geladeira') = 2799.90,
  'Ana grava e regrava (upsert) compra da própria unidade');
select pg_temp.confere((select atualizado_por from public.compras where item_id = 'enxoval-geladeira')
  = '00000000-0000-0000-0000-00000000000a', 'compra carimbada com quem alterou');

select pg_temp.deve_falhar($q$insert into public.compras (unidade_id, item_id, comprado)
  values ('bbbbbbbb-0000-0000-0000-000000000002', 'enxoval-geladeira', true)$q$, 'Ana gravando compra de outra unidade');
select pg_temp.deve_falhar($q$insert into public.compras (unidade_id, item_id, valor_pago)
  values ('aaaaaaaa-0000-0000-0000-000000000001', 'enxoval-balde', -5)$q$, 'valor pago negativo');
select pg_temp.deve_falhar($q$update public.perfis set franqueadora = true$q$, 'Ana se promovendo a franqueadora');
update public.perfis set nome = 'Ana Paula';
select pg_temp.confere((select nome from public.perfis) = 'Ana Paula', 'Ana muda o próprio nome');
select pg_temp.deve_falhar($q$insert into public.unidades (nome) values ('Pirata')$q$, 'Ana criando unidade');
select pg_temp.deve_falhar($q$insert into public.membros (user_id, unidade_id)
  values ('00000000-0000-0000-0000-00000000000a', 'bbbbbbbb-0000-0000-0000-000000000002')$q$, 'Ana se colocando na unidade B');
select public.definir_responsavel('aaaaaaaa-0000-0000-0000-000000000001', '  Ana Paula  ');
select pg_temp.confere((select responsavel from public.unidades) = 'Ana Paula', 'Ana define o responsável da própria unidade');
select pg_temp.deve_falhar($q$select public.definir_responsavel('bbbbbbbb-0000-0000-0000-000000000002', 'x')$q$,
  'Ana definindo responsável de outra unidade');
select pg_temp.deve_falhar($q$select public.renovar_codigo('aaaaaaaa-0000-0000-0000-000000000001')$q$, 'Ana renovando código');
select pg_temp.deve_falhar($q$select public.entrar_com_codigo('00000-00000')$q$, 'Ana com código inválido');
reset role;

-- ---------- Bruno (unidade B) não enxerga a compra da Ana ----------
set role authenticated;
set request.jwt.claim.sub = '00000000-0000-0000-0000-00000000000b';
select pg_temp.confere((select count(*) from public.compras) = 0, 'Bruno não vê compras da unidade A');
update public.compras set valor_pago = 1 where item_id = 'enxoval-geladeira';
reset role;
select pg_temp.confere((select valor_pago from public.compras where item_id = 'enxoval-geladeira') = 2799.90,
  'Bruno não consegue alterar compra da unidade A');

-- ---------- Daniel (sem unidade) entra depois com o código de B ----------
set role authenticated;
set request.jwt.claim.sub = '00000000-0000-0000-0000-00000000000d';
select pg_temp.confere((select count(*) from public.unidades) = 0, 'Daniel sem código não vê nada');
select pg_temp.confere(public.entrar_com_codigo(' ' || lower(:'cod_b') || ' ') = 'bbbbbbbb-0000-0000-0000-000000000002',
  'Daniel entra na unidade B com o código');
select pg_temp.confere((select count(*) from public.unidades) = 1, 'Daniel passa a ver a unidade B');
reset role;

-- ---------- franqueadora ----------
set role authenticated;
set request.jwt.claim.sub = '00000000-0000-0000-0000-0000000000ad';
select pg_temp.confere(public.e_franqueadora(), 'franqueadora reconhecida');
select pg_temp.confere((select count(*) from public.unidades) = 2, 'franqueadora vê todas as unidades');
select pg_temp.confere((select count(*) from public.perfis) = 5, 'franqueadora vê todos os perfis');
select pg_temp.confere((select count(*) from public.compras) = 1, 'franqueadora vê todas as compras');
select pg_temp.confere((select count(*) from public.membros m join public.perfis p using (user_id)) = 3,
  'franqueadora vê membros com e-mail');
insert into public.unidades (nome, cidade, inauguracao) values ('Sou Coluna Joinville', 'Joinville', '2027-03-01');
select pg_temp.confere((select codigo from public.unidades where cidade = 'Joinville') is not null, 'nova unidade ganha código');
select public.renovar_codigo('aaaaaaaa-0000-0000-0000-000000000001') as novo_a \gset
select pg_temp.confere(:'novo_a' <> :'cod_a', 'renovar gera código diferente');
select pg_temp.confere(not public.codigo_valido(:'cod_a'), 'código antigo deixa de valer');
delete from public.membros where user_id = '00000000-0000-0000-0000-00000000000d';
select pg_temp.confere((select count(*) from public.membros) = 2, 'franqueadora remove acesso de um membro');
reset role;

\echo
\echo 'TODOS OS TESTES DO BANCO PASSARAM'
