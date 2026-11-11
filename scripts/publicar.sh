#!/usr/bin/env bash
# Publica o site na Cloudflare Pages (projeto "compras-sou-coluna").
#
# O site inteiro vai num único _worker.js (scripts/montar_worker.py), sem arquivos soltos. Assim a publicação
# só usa o token da Cloudflare e funciona também nas sessões do Claude, onde o proxy troca qualquer chave
# enviada para api.cloudflare.com (o envio de arquivos soltos usa uma chave temporária e seria recusado).
#
# Uso:  python3 build.py && scripts/publicar.sh
#   - no GitHub Actions: CLOUDFLARE_API_TOKEN vem do segredo do repositório
#   - numa sessão do Claude (ambiente "compras-sou-coluna"): não precisa de nada, o proxy põe o token
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
WRANGLER="$RAIZ/ferramentas/node_modules/.bin/wrangler"
[ -x "$WRANGLER" ] || npm ci --prefix "$RAIZ/ferramentas" --no-fund --no-audit
export CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-placeholder}"
if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  CLOUDFLARE_ACCOUNT_ID=$(curl -sS https://api.cloudflare.com/client/v4/accounts -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"][0]["id"])')
  export CLOUDFLARE_ACCOUNT_ID
fi
PASTA=$(mktemp -d)
trap 'rm -rf "$PASTA"' EXIT
python3 "$RAIZ/scripts/montar_worker.py" "$PASTA/publicacao"
cd "$PASTA"   # fora do repositório, para o wrangler não misturar com a pasta functions/
WRANGLER_SEND_METRICS=false "$WRANGLER" pages deploy publicacao --project-name compras-sou-coluna \
  --branch main --skip-caching --commit-dirty=true
