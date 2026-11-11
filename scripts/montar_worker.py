"""Monta o site inteiro (páginas, imagens e a API) num único arquivo _worker.js para a Cloudflare Pages
("modo avançado"). Assim a publicação não precisa enviar arquivos soltos: só esse arquivo.

Uso: python3 scripts/montar_worker.py PASTA_DE_SAIDA     (cria PASTA_DE_SAIDA/_worker.js)
Rode python3 build.py antes, para a pasta site/ estar atualizada.
"""
import base64, hashlib, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
API = ROOT / "functions/api/[[rota]].js"

TIPOS = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8",
}
TEXTO = {".html", ".js", ".css", ".json", ".svg", ".txt"}

# cabeçalhos de segurança: os mesmos de site/_headers
SEGURANCA = {}
for linha in (SITE / "_headers").read_text(encoding="utf-8").splitlines():
    m = re.match(r"^\s+([A-Za-z-]+):\s*(.+)$", linha)
    if m:
        SEGURANCA[m.group(1)] = m.group(2).strip()


def arquivos():
    saida = {}
    for p in sorted(SITE.rglob("*")):
        if not p.is_file() or p.name.startswith("_") or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        if ext not in TIPOS:
            continue
        dados = p.read_bytes()
        f = {"t": TIPOS[ext], "h": hashlib.sha1(dados).hexdigest()[:16]}
        if ext in TEXTO:
            f["s"] = dados.decode("utf-8")
        else:
            f["b"] = base64.b64encode(dados).decode()
        saida["/" + p.relative_to(SITE).as_posix()] = f
    return saida


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    destino = Path(sys.argv[1])
    destino.mkdir(parents=True, exist_ok=True)
    api = API.read_text(encoding="utf-8")
    assert "export async function onRequest" in api
    api = api.replace("export async function onRequest", "async function onRequest")
    arq = arquivos()
    worker = f"""// Gerado por scripts/montar_worker.py — não editar à mão.
// Site do Guia de Compras Sou Coluna num arquivo só: a API (functions/api) + as páginas e imagens de site/.

// ===================== API =====================
{api}

// ===================== páginas e imagens =====================
const ARQ = {json.dumps(arq, ensure_ascii=False)};
const SEGURANCA = {json.dumps(SEGURANCA)};
const CORPO = {{}};
function corpo(p) {{
  if (!(p in CORPO)) {{
    const f = ARQ[p];
    CORPO[p] = f.s != null ? f.s : Uint8Array.from(atob(f.b), (c) => c.charCodeAt(0));
  }}
  return CORPO[p];
}}
function comSeguranca(resp) {{
  const r = new Response(resp.body, resp);
  for (const [k, v] of Object.entries(SEGURANCA)) r.headers.set(k, v);
  return r;
}}

export default {{
  async fetch(request, env, ctx) {{
    const url = new URL(request.url);
    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {{
      const rota = url.pathname.split("/").slice(2).filter(Boolean).map(decodeURIComponent);
      return comSeguranca(await onRequest({{ request, env, params: {{ rota }}, waitUntil: (p) => ctx.waitUntil(p) }}));
    }}
    if (request.method !== "GET" && request.method !== "HEAD") return new Response("Método não permitido", {{ status: 405 }});
    let p = decodeURIComponent(url.pathname);
    // endereços sem ".html", como na Cloudflare Pages: /guia.html → /guia, /index.html → /
    if (p.endsWith(".html")) {{
      let alvo = p.slice(0, -5);
      if (alvo.endsWith("/index")) alvo = alvo.slice(0, -5);
      return Response.redirect(url.origin + (alvo || "/") + url.search, 308);
    }}
    const chave = p.endsWith("/") ? p + "index.html" : (ARQ[p] ? p : p + ".html");
    const f = ARQ[chave];
    if (!f) return new Response("Página não encontrada", {{ status: 404, headers: {{ ...SEGURANCA, "Content-Type": "text/plain; charset=utf-8" }} }});
    const etag = '"' + f.h + '"';
    const h = {{ ...SEGURANCA, "Content-Type": f.t, ETag: etag, "Cache-Control": "public, max-age=0, must-revalidate" }};
    if (request.headers.get("If-None-Match") === etag) return new Response(null, {{ status: 304, headers: h }});
    return new Response(request.method === "HEAD" ? null : corpo(chave), {{ headers: h }});
  }},
}};
"""
    (destino / "_worker.js").write_text(worker, encoding="utf-8")
    print(f"ok: {destino / '_worker.js'} ({len(worker.encode()) / 1024:.0f} KB, {len(arq)} arquivos do site)")


if __name__ == "__main__":
    main()
