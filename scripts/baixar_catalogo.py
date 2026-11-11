"""Baixa do site as alterações que a franqueadora fez no catálogo (página /catalogo do painel) para a pasta
ajustes/, usada pelo build.py na versão offline e no PDF. O site já mostra as alterações sozinho.

Uso:  python3 scripts/baixar_catalogo.py [endereço do site]     (padrão: https://compras.soucoluna.com)
      python3 build.py && python3 scripts/gerar_pdf.py
"""
import json, shutil, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = (sys.argv[1] if len(sys.argv) > 1 else "https://compras.soucoluna.com").rstrip("/")
DEST = ROOT / "ajustes"
EXT = {"image/webp": ".webp", "image/jpeg": ".jpg", "image/png": ".png"}


def baixar(caminho):
    with urllib.request.urlopen(urllib.request.Request(SITE + caminho, headers={"User-Agent": "guia-compras-build"}), timeout=60) as r:
        return r.read(), r.headers.get("Content-Type", "")


def main():
    dados, _ = baixar("/api/catalogo")
    cat = json.loads(dados)
    fotos = DEST / "fotos"
    shutil.rmtree(fotos, ignore_errors=True)
    fotos.mkdir(parents=True)
    n = 0
    for f in cat["fotos"]:
        if f["tem_foto"] and not f["removida"]:
            img, tipo = baixar(f"/api/foto/{f['item_id']}")
            (fotos / (f["item_id"] + EXT.get(tipo.split(";")[0], ".jpg"))).write_bytes(img)
            n += 1
    (DEST / "catalogo.json").write_text(json.dumps(cat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"ok: {len(cat['itens'])} itens alterados/criados/removidos e {n} fotos novas em {DEST.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
