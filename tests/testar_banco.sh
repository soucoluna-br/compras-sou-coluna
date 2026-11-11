#!/usr/bin/env bash
# Testa supabase/schema.sql num Postgres local (não precisa de conta no Supabase).
# Uso: PGHOST=... PGPORT=... PGUSER=postgres tests/testar_banco.sh
set -euo pipefail
cd "$(dirname "$0")/.."
DB=guia_teste_$$
export PGOPTIONS="-c client_min_messages=warning"
createdb "$DB"
trap 'dropdb --if-exists "$DB"' EXIT
psql -q -v ON_ERROR_STOP=1 -d "$DB" -f tests/banco/stub_supabase.sql
psql -q -v ON_ERROR_STOP=1 -d "$DB" -f supabase/schema.sql
psql -q -v ON_ERROR_STOP=1 -d "$DB" -f supabase/schema.sql   # aplicar de novo não pode quebrar
PGOPTIONS= psql -q -v ON_ERROR_STOP=1 -d "$DB" -o /dev/null -f tests/banco/testes.sql 2>&1 | sed -E "s/^psql:[^ ]+ NOTICE:  //"
