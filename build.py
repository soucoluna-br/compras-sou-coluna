"""Gera o HTML final do Guia de Compras a partir de data.py + imagens.

Imagens de produto: coloque em build/images/<id-do-item>.(jpg|png|webp).
Sufixo "__cover" no nome (ex.: enxoval-geladeira__cover.jpg) faz a foto preencher o card inteiro.
Uso: python3 build.py  -> out/guia-compras-sou-coluna.html
"""
import base64, json, re, unicodedata, sys
from pathlib import Path
from io import BytesIO
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from data import SECTIONS

ROOT = Path(__file__).parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)


def slugify(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def data_uri(path, max_side=None, fmt=None):
    im = Image.open(path)
    if max_side and max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = BytesIO()
    if fmt == "JPEG" or (fmt is None and im.mode == "RGB"):
        im.convert("RGB").save(buf, "JPEG", quality=84, optimize=True); mime = "image/jpeg"
    else:
        im.save(buf, "PNG", optimize=True); mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()


sections = []
seen = set()
for s in SECTIONS:
    cats = []
    for cname, ckey, items in s["cats"]:
        out_items = []
        for t in items:
            name, spec, qty, unit, supply, supplier, note = t[:7]
            uom = t[7] if len(t) > 7 else None
            iid = f"{s['id']}-{slugify(name)}"
            assert iid not in seen, iid
            seen.add(iid)
            out_items.append(dict(id=iid, name=name, spec=spec, qty=qty, unit=unit, uom=uom,
                                  supply=supply, supplier=supplier, note=note))
        cats.append(dict(name=cname, key=ckey, items=out_items))
    sections.append(dict(id=s["id"], title=s["title"], short=s["short"], desc=s["desc"], cats=cats))

images = {}
img_dir = ROOT / "images"
for p in sorted(img_dir.glob("*")):
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        continue
    stem = p.stem
    fit = "contain"
    if stem.endswith("__cover"):
        stem, fit = stem[:-7], "cover"
    if stem not in seen:
        print("AVISO: imagem sem item correspondente:", p.name); continue
    images[stem] = dict(src=data_uri(p, 1100, "JPEG"), fit=fit)

html = (ROOT / "template.html").read_text(encoding="utf-8")
logo_white = data_uri(ROOT / "assets/logo-white.png", 900)
symbol_white = data_uri(ROOT / "assets/symbol-white.png", 700)
html = (html.replace("/*__DATA__*/null", json.dumps(sections, ensure_ascii=False))
            .replace("/*__IMAGES__*/{}", json.dumps(images))
            .replace("__LOGO_WHITE__", logo_white)
            .replace("__SYMBOL_WHITE__", symbol_white))
dest = OUT / "guia-compras-sou-coluna.html"
dest.write_text(html, encoding="utf-8")
print(f"ok: {dest} ({dest.stat().st_size/1024:.0f} KB) · itens={len(seen)} · imagens={len(images)}")
json.dump(sorted(seen), open(OUT / "ids-dos-itens.json", "w"), ensure_ascii=False, indent=1)
