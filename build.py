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

def webp_bytes(path, max_side, quality):
    im = Image.open(path)
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = BytesIO()
    im.convert("RGB").save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()


# Fotos em WebP (bem mais leve que JPEG): o site inteiro vai num único _worker.js, que no plano gratuito
# da Cloudflare tem limite de 3 MB, e o HTML offline também fica leve para mandar por WhatsApp/e-mail.
FOTO_SITE = (640, 78)      # lado máximo (px), qualidade — cards e ampliação no site
FOTO_OFFLINE = (520, 74)   # embutida no HTML offline (e no PDF)
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
    images[stem] = dict(src="data:image/webp;base64," + base64.b64encode(webp_bytes(p, *FOTO_OFFLINE)).decode(), fit=fit)
    (site_img / f"{stem}.webp").write_bytes(webp_bytes(p, *FOTO_SITE))
    site_images[stem] = dict(src=f"img/{stem}.webp", fit=fit)
for old in site_img.glob("*"):
    if old.stem not in site_images or old.suffix != ".webp":
        old.unlink()

template = (ROOT / "template.html").read_text(encoding="utf-8")
logo_white = data_uri(ROOT / "assets/logo-white.png", 900)
logo_coral = data_uri(ROOT / "assets/logo-coral.png", 600)
symbol_white = data_uri(ROOT / "assets/symbol-white.png", 700)
data_json = json.dumps(sections, ensure_ascii=False)


def page(imgs, head_extra="", secoes_json=None):
    return (template.replace("/*__DATA__*/null", secoes_json or data_json)
                    .replace("/*__IMAGES__*/{}", json.dumps(imgs))
                    .replace("<!--__HEAD_EXTRA__-->", head_extra)
                    .replace("__LOGO_WHITE__", logo_white)
                    .replace("__LOGO_CORAL__", logo_coral)
                    .replace("__SYMBOL_WHITE__", symbol_white))


def aplicar_ajustes(secs, imgs):
    """Alterações feitas pela franqueadora no painel (baixadas por scripts/baixar_catalogo.py para ajustes/).
    Mesma regra de SC.aplicarAjustes (site/app.js). Só entra na versão offline e no PDF: o site junta sozinho."""
    arq = ROOT / "ajustes" / "catalogo.json"
    if not arq.exists():
        return secs, imgs
    aj = json.loads(arq.read_text(encoding="utf-8"))
    secs, imgs = json.loads(json.dumps(secs)), dict(imgs)
    lugar = {i["id"]: c for s in secs for c in s["cats"] for i in c["items"]}
    mexidas = set()
    for r in aj["itens"]:
        c = lugar.get(r["id"])
        if c:
            c["items"] = [x for x in c["items"] if x["id"] != r["id"]]
    for r in aj["itens"]:
        if r.get("removido"):
            imgs.pop(r["id"], None); continue
        sec = next((x for x in secs if x["id"] == r.get("etapa")), None)
        if not sec or not r.get("nome"):
            continue
        cat = next((c for c in sec["cats"] if c["name"].lower() == str(r.get("categoria") or "").lower()), None)
        if not cat:
            cat = {"name": r["categoria"], "key": r.get("icone") or "utensilio", "items": []}; sec["cats"].append(cat)
        cat["items"].append(dict(id=r["id"], name=r["nome"], spec=r.get("especificacao") or None, qty=r["qtd"], unit=r.get("valor_unit"),
                                 uom=r.get("unidade_medida") or None, supply=r.get("fornecimento") or None,
                                 supplier=r.get("fornecedor") or None, note=r.get("observacao") or None))
        mexidas.add(id(cat))
    for f in aj["fotos"]:
        fid, fit = f["item_id"], ("cover" if f.get("ajuste") == "cover" else "contain")
        if f.get("removida"):
            imgs.pop(fid, None)
        elif f.get("tem_foto"):
            arqs = sorted((ROOT / "ajustes" / "fotos").glob(fid + ".*"))
            if arqs:
                imgs[fid] = dict(src="data:image/webp;base64," + base64.b64encode(webp_bytes(arqs[0], *FOTO_OFFLINE)).decode(), fit=fit)
        elif fid in imgs:
            imgs[fid] = {**imgs[fid], "fit": fit}
    sem_acento = lambda t: unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()
    for sec in secs:
        sec["cats"] = [c for c in sec["cats"] if c["items"]]
        for c in sec["cats"]:
            if id(c) in mexidas:
                c["items"].sort(key=lambda x: sem_acento(x["name"]))
    n = len(aj["itens"]) + len(aj["fotos"])
    print(f"   (versão offline e PDF com {n} alterações do painel, de ajustes/catalogo.json)")
    return secs, imgs


# 1) versão offline (um arquivo só, progresso no navegador) — também é a base do PDF
secoes_off, images_off = aplicar_ajustes(sections, images)
dest = OUT / "guia-compras-sou-coluna.html"
dest.write_text(page(images_off, secoes_json=json.dumps(secoes_off, ensure_ascii=False)), encoding="utf-8")
print(f"ok: {dest} ({dest.stat().st_size/1024:.0f} KB) · itens={len(seen)} · imagens={len(images)}")
json.dump(sorted(seen), open(OUT / "ids-dos-itens.json", "w"), ensure_ascii=False, indent=1)

# 2) site com login (Cloudflare Pages + D1): mesma página, mas salvando no banco
head_site = ("<script>document.documentElement.classList.add('online')</script>\n"
             '<link rel="icon" href="assets/favicon.png">\n'
             '<script src="app.js"></script>')
(SITE / "guia.html").write_text(page(site_images, head_site), encoding="utf-8")
(SITE / "catalogo.js").write_text(
    "// Gerado por build.py a partir de data.py — não editar à mão.\nwindow.SECTIONS = " + data_json + ";\n"
    "window.FOTOS_BASE = " + json.dumps(site_images) + ";\n",
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
