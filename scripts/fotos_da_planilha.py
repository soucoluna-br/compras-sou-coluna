"""Extrai as fotos de produto da planilha de enxoval (xlsx do Google Drive) para images/.

Prints de página de loja (Mercado Livre, Amazon...) são recortados para mostrar só o produto, sem preço,
botões ou textos da loja. Fotos limpas entram inteiras; fotos de ambiente entram como "__cover".

Uso:  python3 scripts/fotos_da_planilha.py src/drive/planilha-com-fotos.xlsx
      python3 build.py            # gera o site e o HTML offline com as fotos
Depois, confira as fotos novas (o recorte automático erra às vezes) e ajuste em RECORTE_MANUAL.
Precisa de: pip install numpy scipy pillow
"""
import io, re, sys, unicodedata, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data import SECTIONS  # noqa: E402

# linha da aba "Enxoval Inicial" -> nome do item no guia (data.py)
MAPA = {
 3:"Adesivos de café e chá", 4:"Adjuster", 5:"Impressora", 8:"Ar-condicionado", 9:"Balança corporal", 10:"Balde",
 11:"Bandeja de café", 14:"Borrifadores", 15:"Box cama para exposição", 16:"Cadeiras com rodinhas", 17:"Cadeiras Ouvidor",
 18:"Cadeiras da recepção", 21:"Caixa de som portátil", 22:"Caixa organizadora", 23:"Caixa térmica", 24:"Calculadora",
 25:"Câmera de segurança externa", 26:"Câmeras de segurança internas", 27:"Capacho de entrada", 29:"Cartões de memória para as câmeras",
 31:"Celulares (recepção e supervisora)", 32:"Cesto de roupa suja", 33:"Chaleira elétrica", 34:"Colchão casal para exposição",
 35:"Coluna vertebral (modelo anatômico)", 36:"Conjunto de plantas e vasos", 37:"Desktops", 38:"Escada de alumínio",
 39:"Escada de massagem", 41:"Fachada", 43:"Garrafa térmica branca", 44:"Geladeira", 45:"Grampeador",
 46:"Compressas úmidas Hot Carci", 50:"Kit pratos da copa (6 unidades)", 51:"Kit suporte expositor de produtos ortopédicos (2 peças)",
 53:"Kit banheiro: porta-papel toalha, saboneteira e porta-papel higiênico", 54:"Kit porta-sachê de açúcar e porta-copos (chá e café)",
 55:"Kit copos da copa (6 unidades)", 56:"Kit talheres da copa", 57:"Kit pano de chão", 59:"Lixeira dupla com porta-copos (água e café)",
 60:"Lixeira de banheiro (inox)", 61:"Lixeira de cozinha (inox)", 62:"Lixeira aramada de escritório", 64:"Luva térmica",
 65:"Maca de massagem", 66:"Maca de flexo-distração automática", 67:"Máquina de lavar", 69:"Mesa e cadeiras da copa (colaboradores)",
 70:"Mesa de apoio da cama", 72:"Mesa da recepção", 75:"Micro-ondas", 76:"Modelo de hérnia de disco", 77:"Monitores",
 78:"Neon da recepção", 79:"Notebook", 80:"Pá de lixo com cabo", 82:"Porta-lenço de papel", 83:"Porta-sabonete líquido / álcool gel",
 84:"Prancheta de acrílico", 89:"Puff para a sala de consulta", 90:"Purificador de água", 91:"Quadros 55 × 55 cm",
 92:"Quadros 69,4 × 94,1 cm", 93:"Régua", 94:"Régua de tomadas", 95:"Rodo", 96:"Máquina de secar", 98:"Sistema de Wi-Fi em rede mesh",
 100:"Suporte pedestal para TV (expositor de produtos)", 101:"Suporte universal para TV", 102:"Tablet", 103:"Telefone sem fio",
 104:"Televisão da recepção", 105:"Tesoura", 106:"Thermoscan", 108:"Tração cervical elétrica", 109:"Turbilhão de água quente",
 110:"Televisão dos produtos", 115:"Varal para toalhas", 116:"Vassoura",
}
LIMPAS = {3, 4, 5, 8, 11, 16, 18, 24, 29, 50, 51, 66, 91, 92, 93, 98, 106, 108, 109}   # usar a foto inteira
COVER = {15, 34, 36, 41, 78}                                                          # foto de ambiente: preenche o card
# recortes conferidos à mão (fração da imagem: x0, y0, x1, y1), onde o automático não acerta
RECORTE_MANUAL = {14: (0.02, 0.05, 0.31, 0.61), 44: (0.22, 0.18, 0.35, 0.90), 56: (0.0, 0.0, 0.45, 0.66),
                  77: (0.06, 0.21, 0.47, 0.69), 84: (0.05, 0.02, 0.36, 0.62), 94: (0.12, 0.16, 0.47, 0.91),
                  103: (0.12, 0.05, 0.36, 0.915), 115: (0.06, 0.22, 0.40, 0.75)}
PINTAR_DE_BRANCO = {56: [(0.42, 0.0, 0.46, 0.07)]}   # ícones da loja dentro da área do produto

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def slug(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fotos_por_linha(z, n_aba=1):
    """{linha da planilha (1 = cabeçalho): caminho da imagem no xlsx} da aba n_aba."""
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read(f"xl/drawings/_rels/drawing{n_aba}.xml.rels"))}
    out = {}
    for anc in ET.fromstring(z.read(f"xl/drawings/drawing{n_aba}.xml")):
        fr, blip = anc.find("xdr:from", NS), anc.find(".//a:blip", NS)
        if fr is None or blip is None:
            continue
        out[int(fr.find("xdr:row", NS).text) + 1] = rels[blip.get("{%s}embed" % NS["r"])].replace("../", "xl/")
    return out


def recorte_auto(im, xmax=0.62):
    """Acha a foto do produto num print de loja: a maior área "maciça" (texto some ao afinar a imagem)."""
    W, H = im.size
    esc = 700 / W if W > 700 else 1.0
    pq = im.convert("RGB").resize((max(1, int(W * esc)), max(1, int(H * esc))))
    a = np.asarray(pq).astype(int); w, h = pq.size
    mn, mx = a.min(axis=2), a.max(axis=2)
    obj = ~((mn > 232) & (mx - mn < 14))
    solido = ndimage.binary_erosion(obj, iterations=2)
    lab, _ = ndimage.label(ndimage.binary_dilation(solido, iterations=6))
    melhor, mpont = None, 0
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        ys, xs = sl
        bw, bh, cx = xs.stop - xs.start, ys.stop - ys.start, (xs.start + xs.stop) / 2
        if cx > w * xmax or bw < w * 0.06 or bh < h * 0.12:
            continue
        pont = int((solido[sl] & (lab[sl] == i)).sum())
        if pont > mpont:
            melhor, mpont = sl, pont
    if melhor is None:
        return None
    ys, xs = melhor
    x0, x1, y0, y1 = xs.start / esc, xs.stop / esc, ys.start / esc, ys.stop / esc
    m = 0.03 * max(x1 - x0, y1 - y0)
    return (max(0, int(x0 - m)), max(0, int(y0 - m)), min(W, int(x1 + m)), min(H, int(y1 + m)))


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    z = zipfile.ZipFile(sys.argv[1])
    nome2id = {t[0]: f"{s['id']}-{slug(t[0])}" for s in SECTIONS for _, _, items in s["cats"] for t in items}
    faltando = [n for n in MAPA.values() if n not in nome2id]
    if faltando:
        raise SystemExit(f"Itens do MAPA que não existem em data.py: {faltando}")
    fotos = fotos_por_linha(z)
    dest = ROOT / "images"; dest.mkdir(exist_ok=True)
    feitas = 0
    for linha, nome in sorted(MAPA.items()):
        if linha not in fotos:
            print(f"AVISO: linha {linha} ({nome}) sem foto na planilha"); continue
        im = Image.open(io.BytesIO(z.read(fotos[linha])))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA"); fundo = Image.new("RGB", im.size, "white"); fundo.paste(im, mask=im.split()[-1]); im = fundo
        else:
            im = im.convert("RGB")
        W, H = im.size
        for (a, b, c, e) in PINTAR_DE_BRANCO.get(linha, []):
            ImageDraw.Draw(im).rectangle([a * W, b * H, c * W, e * H], fill="white")
        if linha in RECORTE_MANUAL:
            a, b, c, e = RECORTE_MANUAL[linha]; im = im.crop((int(a * W), int(b * H), int(c * W), int(e * H)))
        elif linha not in LIMPAS and linha not in COVER:
            caixa = recorte_auto(im)
            if caixa:
                im = im.crop(caixa)
            else:
                print(f"AVISO: linha {linha} ({nome}): recorte automático falhou, usando o print inteiro")
        im.thumbnail((1000, 1000), Image.LANCZOS)
        iid = nome2id[nome]
        for velho in dest.glob(f"{iid}.*"):
            velho.unlink()
        for velho in dest.glob(f"{iid}__cover.*"):
            velho.unlink()
        im.save(dest / (f"{iid}__cover.jpg" if linha in COVER else f"{iid}.jpg"), "JPEG", quality=86, optimize=True)
        feitas += 1
    print(f"ok: {feitas} fotos em images/")


if __name__ == "__main__":
    main()
