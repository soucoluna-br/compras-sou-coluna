"""Gera o HTML final do Guia de Compras a partir de data.py + imagens.

Imagens de produto: coloque em images/<id-do-item>.(jpg|png|webp).
Sufixo "__cover" no nome (ex.: enxoval-geladeira__cover.jpg) faz a foto preencher o card inteiro.
Uso: python3 build.py  -> out/guia-compras-sou-coluna.html  (versão offline, tudo embutido)
                        -> site/guia.html, site/catalogo.js, site/img/, site/assets/  (site com login)
"""
import base64, json, re, shutil, unicodedata, sys
from pathlib import Path
from io import BytesIO
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from data import SECTIONS

ROOT = Path(__file__).parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)
SITE = ROOT / "site"


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

def jpeg_bytes(path, max_side):
    im = Image.open(path)
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=84, optimize=True)
    return buf.getvalue()


# fotos: embutidas no HTML offline; arquivos separados no site (carrega mais rápido)
images, site_images = {}, {}
img_dir = ROOT / "images"
site_img = SITE / "img"; site_img.mkdir(parents=True, exist_ok=True)
for p in sorted(img_dir.glob("*")):
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        continue
    stem = p.stem
    fit = "contain"
    if stem.endswith("__cover"):
        stem, fit = stem[:-7], "cover"
    if stem not in seen:
        print("AVISO: imagem sem item correspondente:", p.name); continue
    data = jpeg_bytes(p, 1100)
    images[stem] = dict(src="data:image/jpeg;base64," + base64.b64encode(data).decode(), fit=fit)
    (site_img / f"{stem}.jpg").write_bytes(data)
    site_images[stem] = dict(src=f"img/{stem}.jpg", fit=fit)
for old in site_img.glob("*.jpg"):
    if old.stem not in site_images:
        old.unlink()

template = (ROOT / "template.html").read_text(encoding="utf-8")
logo_white = data_uri(ROOT / "assets/logo-white.png", 900)
symbol_white = data_uri(ROOT / "assets/symbol-white.png", 700)
data_json = json.dumps(sections, ensure_ascii=False)


def page(imgs, head_extra=""):
    return (template.replace("/*__DATA__*/null", data_json)
                    .replace("/*__IMAGES__*/{}", json.dumps(imgs))
                    .replace("<!--__HEAD_EXTRA__-->", head_extra)
                    .replace("__LOGO_WHITE__", logo_white)
                    .replace("__SYMBOL_WHITE__", symbol_white))


# 1) versão offline (um arquivo só, progresso no navegador) — também é a base do PDF
dest = OUT / "guia-compras-sou-coluna.html"
dest.write_text(page(images), encoding="utf-8")
print(f"ok: {dest} ({dest.stat().st_size/1024:.0f} KB) · itens={len(seen)} · imagens={len(images)}")
json.dump(sorted(seen), open(OUT / "ids-dos-itens.json", "w"), ensure_ascii=False, indent=1)

# 2) site com login (Vercel + Supabase): mesma página, mas salvando no banco
SUPABASE_JS = "vendor/supabase-2.118.0.js"
head_site = ("<script>document.documentElement.classList.add('online')</script>\n"
             '<link rel="icon" href="assets/favicon.png">\n'
             '<script src="config.js"></script>\n'
             f'<script src="{SUPABASE_JS}"></script>\n'
             '<script src="app.js"></script>')
assert (SITE / SUPABASE_JS).exists(), f"falta {SUPABASE_JS}"
(SITE / "guia.html").write_text(page(site_images, head_site), encoding="utf-8")
(SITE / "catalogo.js").write_text(
    "// Gerado por build.py a partir de data.py — não editar à mão.\nwindow.SECTIONS = " + data_json + ";\n",
    encoding="utf-8")
(SITE / "assets").mkdir(exist_ok=True)
for name in ("logo-white.png", "logo-coral.png", "symbol-white.png"):
    shutil.copyfile(ROOT / "assets" / name, SITE / "assets" / name)
fav = Image.open(ROOT / "assets/symbol-white.png").convert("RGBA")
fav.thumbnail((180, 180), Image.LANCZOS)
bg = Image.new("RGBA", (192, 192), (239, 123, 96, 255))
bg.alpha_composite(fav, ((192 - fav.width) // 2, (192 - fav.height) // 2))
bg.save(SITE / "assets/favicon.png", optimize=True)
print(f"ok: {SITE / 'guia.html'} · site/img: {len(site_images)} fotos")
