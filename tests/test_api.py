"""Testes da API do site (functions/api) com o banco D1 local: login, regras de acesso,
links de senha, limite de tentativas e o comando de backup.

Uso:  python3 build.py && python3 tests/test_api.py
"""
import re, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from servidor_local import CHAVE, Cliente, Servidor

passou = 0
def ok(cond, msg):
    global passou
    if not cond:
        raise AssertionError("FALHOU: " + msg)
    passou += 1
    print("ok:", msg)


def main():
    with Servidor() as srv:
        B = srv.base
        anon = Cliente(B)
        ok(anon.get("eu")[0] == 401, "sem login: /eu responde 401")
        ok(anon.get("painel")[0] == 401, "sem login: painel bloqueado")

        # ---------- franqueadora ----------
        adm = Cliente(B)
        st, r, _ = adm.post("cadastrar", {"codigo": "chave-errada-123", "nome": "X", "email": "x@x.test", "senha": "12345678"})
        ok(st == 400 and r["erro"] == "codigo_invalido", "cadastro com código inexistente é recusado")
        t0 = time.time()
        st, r, h = adm.post("cadastrar", {"codigo": " " + CHAVE.upper() + ". ", "nome": "Franqueadora", "email": "ADM@SouColuna.test", "senha": "senha-adm-123"})
        ok(st == 201, "cadastro com a chave da franqueadora cria a conta (mesmo com ponto final, espaços e maiúsculas)")
        ck = h.get("Set-Cookie", "")
        ok("HttpOnly" in ck and "SameSite=Lax" in ck, "cookie de sessão é HttpOnly e SameSite")
        st, eu, _ = adm.get("eu")
        ok(st == 200 and eu["franqueadora"] and eu["email"] == "adm@souColuna.test".lower(), "conta da franqueadora reconhecida (e-mail em minúsculas)")

        st, ua, _ = adm.post("unidades", {"nome": "Sou Coluna Florianópolis", "cidade": "Florianópolis", "inauguracao": "2027-02-01"})
        ok(st == 201 and re.fullmatch(r"[0-9A-F]{5}-[0-9A-F]{5}", ua["codigo"]), "franqueadora cria unidade com código XXXXX-XXXXX")
        st, ub, _ = adm.post("unidades", {"nome": "Sou Coluna Curitiba", "cidade": "Curitiba"})
        ok(adm.post("unidades", {"nome": ""})[0] == 400, "unidade sem nome é recusada")
        ok(adm.post("unidades", {"nome": "X", "inauguracao": "01/02/2027"})[0] == 400, "data em formato errado é recusada")

        # ---------- franqueada Ana (A) e Bruno (B) ----------
        ana, bruno = Cliente(B), Cliente(B)
        st, _, _ = ana.post("cadastrar", {"codigo": ua["codigo"].lower().replace("-", " "), "nome": "Ana", "email": "ana@unidade.test", "senha": "senha-da-ana"})
        ok(st == 201, "código digitado em minúsculas e sem hífen funciona")
        ok(ana.post("cadastrar", {"codigo": ua["codigo"], "nome": "Ana", "email": "ANA@unidade.test", "senha": "outra-senha"})[0] == 409, "e-mail repetido é recusado")
        ok(bruno.post("cadastrar", {"codigo": ub["codigo"], "nome": "Bruno", "email": "bruno@unidade.test", "senha": "123"})[1]["erro"] == "senha_curta", "senha curta é recusada")
        bruno.post("cadastrar", {"codigo": ub["codigo"], "nome": "Bruno", "email": "bruno@unidade.test", "senha": "senha-do-bruno"})
        st, eu, _ = ana.get("eu")
        ok([u["id"] for u in eu["unidades"]] == [ua["id"]] and not eu["franqueadora"], "Ana vê só a própria unidade")

        A, Bid = ua["id"], ub["id"]
        ok(ana.post(f"unidades/{A}/compras", {"linhas": [{"item_id": "enxoval-geladeira", "comprado": True, "valor_pago": 2899.9}]})[0] == 200, "Ana grava compra")
        ok(ana.post(f"unidades/{A}/compras", {"linhas": [{"item_id": "enxoval-geladeira", "comprado": True, "valor_pago": 2799.9},
                                                        {"item_id": "enxoval-balde", "comprado": False, "valor_pago": None}]})[0] == 200, "Ana regrava (upsert) em lote")
        st, r, _ = ana.get(f"unidades/{A}/compras")
        itens = {i["item_id"]: i for i in r["itens"]}
        ok(itens["enxoval-geladeira"]["valor_pago"] == 2799.9 and itens["enxoval-geladeira"]["comprado"], "valor volta exatamente como gravado (centavos)")
        ok("codigo" not in r["unidade"], "franqueado não recebe o código da unidade pela rota do guia")
        ok(ana.post(f"unidades/{A}/compras", {"linhas": [{"item_id": "enxoval-geladeira", "comprado": True, "valor_pago": 2799.9, "quantidade": 3}]})[0] == 200,
           "Ana ajusta a quantidade de um item")
        itens = {i["item_id"]: i for i in ana.get(f"unidades/{A}/compras")[1]["itens"]}
        ok(itens["enxoval-geladeira"]["quantidade"] == 3 and itens["enxoval-balde"]["quantidade"] is None, "quantidade ajustada volta do banco (e fica vazia onde não mudou)")
        ok(ana.post(f"unidades/{A}/compras", {"linhas": [{"item_id": "enxoval-balde", "quantidade": -1}]})[0] == 400, "quantidade negativa é recusada")
        ok(ana.post(f"unidades/{A}/compras", {"linhas": [{"item_id": "x", "valor_pago": -5}]})[0] == 400, "valor negativo é recusado")
        ok(ana.post(f"unidades/{A}/compras", {"linhas": [{"item_id": "../etc", "comprado": True}]})[0] == 400, "id de item inválido é recusado")
        ok(ana.post(f"unidades/{A}/compras", {"linhas": []})[0] == 400, "lote vazio é recusado")
        ok(ana.get(f"unidades/{Bid}/compras")[0] == 403, "Ana não lê a unidade B")
        ok(ana.post(f"unidades/{Bid}/compras", {"linhas": [{"item_id": "enxoval-balde", "comprado": True}]})[0] == 403, "Ana não grava na unidade B")
        ok(bruno.get(f"unidades/{A}/compras")[0] == 403, "Bruno não lê a unidade A")
        ok(ana.post(f"unidades/{A}/responsavel", {"nome": "  Ana Souza "})[0] == 200, "Ana define o responsável da própria unidade")
        ok(ana.post(f"unidades/{Bid}/responsavel", {"nome": "x"})[0] == 403, "Ana não define responsável de outra unidade")
        for caminho, dados in [("unidades", {"nome": "Pirata"}), (f"unidades/{A}", {"nome": "Renomeada"}), (f"unidades/{A}/renovar-codigo", {}),
                               (f"unidades/{Bid}/excluir", {}), (f"unidades/{A}/membros/x/remover", {}), ("usuarios/x/link-senha", {})]:
            ok(ana.post(caminho, dados)[0] == 403, f"Ana bloqueada em ações da franqueadora: {caminho.split('/')[-1]}")
        ok(ana.get("painel")[0] == 403, "Ana não abre o painel")
        ok(ana.post("entrar-com-codigo", {"codigo": "00000-00000"})[1]["erro"] == "codigo_invalido", "código inválido ao entrar em outra unidade")

        # ---------- proteção contra outros sites ----------
        ok(ana.post(f"unidades/{A}/responsavel", {"nome": "x"}, {"Origin": "https://site-malicioso.test"})[0] == 403, "chamada vinda de outro site é bloqueada")
        st, _, _ = ana.req("POST", f"unidades/{A}/responsavel", None, {"Content-Type": "text/plain"})
        ok(st == 415, "formulário comum (sem JSON) é bloqueado")

        # ---------- painel ----------
        st, p, _ = adm.get("painel")
        ok(st == 200 and len(p["unidades"]) == 2 and all("codigo" in u for u in p["unidades"]), "painel traz as unidades com código")
        ok({m["email"] for m in p["membros"]} == {"ana@unidade.test", "bruno@unidade.test"}, "painel traz quem acessa cada unidade")
        ok(any(c["item_id"] == "enxoval-geladeira" and c["valor_pago"] == 2799.9 for c in p["compras"]), "painel traz as compras")
        ok(next(u for u in p["unidades"] if u["id"] == A)["responsavel"] == "Ana Souza", "responsável aparece no painel")
        ok(adm.post(f"unidades/{A}", {"nome": "Sou Coluna Floripa", "cidade": "Florianópolis", "inauguracao": "2027-03-01"})[0] == 200, "franqueadora edita a unidade")

        # ---------- login ----------
        ana2 = Cliente(B)
        ok(ana2.post("entrar", {"email": "ana@unidade.test", "senha": "errada"})[1]["erro"] == "credenciais", "senha errada")
        ok(ana2.post("entrar", {"email": "ninguem@x.test", "senha": "qualquer-coisa"})[1]["erro"] == "credenciais", "e-mail inexistente dá o mesmo erro")
        t0 = time.time()
        ok(ana2.post("entrar", {"email": " ANA@unidade.test ", "senha": "senha-da-ana"})[0] == 200, "login certo (e-mail com espaços/maiúsculas)")
        print(f"   (login com PBKDF2 levou {1000 * (time.time() - t0):.0f} ms no total, aqui)")
        tent = Cliente(B)
        cods = [tent.post("entrar", {"email": "bruno@unidade.test", "senha": f"chute-{i}"})[0] for i in range(11)]
        ok(cods[-1] == 429, "muitas tentativas de senha seguidas são bloqueadas")
        ok(Cliente(B).post("entrar", {"email": "bruno@unidade.test", "senha": "senha-do-bruno"})[0] == 429, "…inclusive com a senha certa, até o tempo passar")

        # ---------- acessos ----------
        ana_id = next(m["user_id"] for m in p["membros"] if m["email"] == "ana@unidade.test")
        ok(adm.post(f"unidades/{A}/membros/{ana_id}/remover")[0] == 200, "franqueadora remove o acesso da Ana")
        ok(ana.get(f"unidades/{A}/compras")[0] == 403 and ana.get("eu")[1]["unidades"] == [], "Ana perde o acesso na hora")
        ok(ana.post("entrar-com-codigo", {"codigo": ub["codigo"]})[0] == 200 and ana.get("eu")[1]["unidades"][0]["id"] == Bid, "Ana entra em outra unidade com o código")
        st, r, _ = adm.post(f"unidades/{A}/renovar-codigo")
        ok(st == 200 and r["codigo"] != ua["codigo"], "novo código gerado")
        ok(Cliente(B).post("cadastrar", {"codigo": ua["codigo"], "nome": "C", "email": "c@x.test", "senha": "12345678"})[1]["erro"] == "codigo_invalido", "código antigo deixa de valer")

        # ---------- link de senha nova ----------
        st, link, _ = adm.post(f"usuarios/{ana_id}/link-senha")
        ok(st == 200 and len(link["token"]) >= 30, "franqueadora gera link de senha nova")
        ok(Cliente(B).get("redefinir?token=" + link["token"])[1]["email"] == "ana@unidade.test", "link mostra de quem é a conta")
        nova = Cliente(B)
        ok(nova.post("redefinir", {"token": link["token"], "senha": "curta"})[1]["erro"] == "senha_curta", "link: senha curta recusada")
        ok(nova.post("redefinir", {"token": link["token"], "senha": "senha-nova-ana"})[0] == 200, "link: senha nova salva e já entra")
        ok(nova.get("eu")[0] == 200 and ana.get("eu")[0] == 401, "senha nova derruba as sessões antigas")
        ok(Cliente(B).post("redefinir", {"token": link["token"], "senha": "outra-senha-1"})[1]["erro"] == "link_invalido", "link só vale uma vez")
        ok(Cliente(B).post("redefinir", {"token": "inventado", "senha": "outra-senha-1"})[1]["erro"] == "link_invalido", "link inventado não vale")

        # ---------- franqueadora esqueceu a senha ----------
        ok(Cliente(B).post("redefinir-com-chave", {"email": "adm@soucoluna.test", "chave": "errada-errada-1", "senha": "nova-adm-123"})[0] == 401, "chave errada")
        ok(Cliente(B).post("cadastrar", {"codigo": CHAVE[:-1], "nome": "X", "email": "quase@x.test", "senha": "12345678"})[1]["erro"] == "codigo_invalido",
           "chave quase certa (faltando um caractere) não vale")
        ok(Cliente(B).post("redefinir-com-chave", {"email": "bruno@unidade.test", "chave": CHAVE, "senha": "nova-bru-123"})[0] == 401, "chave não troca senha de franqueado")
        ok(Cliente(B).post("redefinir-com-chave", {"email": "adm@soucoluna.test", "chave": CHAVE, "senha": "nova-adm-123"})[0] == 200, "franqueadora troca a própria senha com a chave")

        # ---------- sair / excluir ----------
        ok(nova.post("sair")[0] == 200 and nova.get("eu")[0] == 401, "sair encerra a sessão")
        adm2 = Cliente(B); adm2.post("entrar", {"email": "adm@soucoluna.test", "senha": "nova-adm-123"})
        ok(adm2.post(f"unidades/{Bid}/excluir")[0] == 200, "franqueadora exclui unidade")
        p = adm2.get("painel")[1]
        ok(len(p["unidades"]) == 1 and not [m for m in p["membros"] if m["unidade_id"] == Bid], "unidade excluída leva junto acessos e compras")

        # ---------- catálogo editável pela franqueadora ----------
        import base64, io, urllib.request
        from PIL import Image
        ok(Cliente(B).get("catalogo")[1] == {"itens": [], "fotos": []}, "catálogo sem alterações começa vazio (e é público)")
        franq = Cliente(B); franq.post("entrar", {"email": "bruno@unidade.test", "senha": "senha-do-bruno"})
        item = {"etapa": "enxoval", "categoria": "Eletrodomésticos e eletrônicos", "icone": "eletro", "nome": "Geladeira frost free",
                "qtd": 1, "valor_unit": 2500, "fornecimento": None, "fornecedor": ""}
        ok(franq.post("catalogo/enxoval-geladeira", item)[0] in (401, 403), "franqueado não altera o catálogo")
        ok(adm2.post("catalogo/enxoval-geladeira", item)[0] == 200, "franqueadora altera nome, preço e tira o fornecimento")
        ok(adm2.post("catalogo/enxoval-geladeira", {**item, "etapa": "outra"})[0] == 400, "etapa inválida é recusada")
        ok(adm2.post("catalogo/enxoval-geladeira", {**item, "fornecimento": "qualquer"})[0] == 400, "fornecimento inválido é recusado")
        ok(adm2.post("catalogo/enxoval-geladeira", {**item, "valor_unit": -1})[0] == 400, "valor negativo é recusado")
        ok(adm2.post("catalogo/enxoval-geladeira", {**item, "nome": ""})[0] == 400, "item sem nome é recusado")
        st, r, _ = adm2.post("catalogo/novo", {**item, "nome": "Bebedouro", "categoria": "Categoria nova", "icone": "copa"})
        novo = r["id"]
        ok(st == 201 and novo.startswith("novo-bebedouro-"), "franqueadora cria item novo")
        ok(adm2.post("catalogo/enxoval-balde/remover")[0] == 200, "franqueadora remove item")
        ids = {i["id"]: i for i in Cliente(B).get("catalogo")[1]["itens"]}
        ok(ids["enxoval-geladeira"]["valor_unit"] == 2500 and ids["enxoval-geladeira"]["fornecimento"] is None
           and ids["enxoval-balde"]["removido"] and ids[novo]["categoria"] == "Categoria nova", "catálogo devolve alteração, item novo e item removido")
        buf = io.BytesIO(); Image.new("RGB", (40, 30), (239, 123, 96)).save(buf, "PNG"); png = buf.getvalue()
        ok(adm2.post(f"catalogo/{novo}/foto", {"base64": base64.b64encode(png).decode(), "tipo": "image/png", "ajuste": "cover"})[0] == 200,
           "franqueadora envia foto")
        ok(adm2.post(f"catalogo/{novo}/foto", {"base64": "QUJDRA==", "tipo": "image/png"})[1]["erro"] == "foto_invalida", "arquivo que não é imagem é recusado")
        ok(franq.post(f"catalogo/{novo}/foto", {"remover": True})[0] in (401, 403), "franqueado não mexe nas fotos")
        resp = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f"{B}/api/foto/{novo}")
        ok(resp.headers["Content-Type"] == "image/png" and resp.read() == png, "foto enviada é servida pelo site")
        ok(adm2.post("catalogo/enxoval-geladeira/foto", {"remover": True})[0] == 200, "franqueadora tira a foto de um item")
        fotos = {f["item_id"]: f for f in Cliente(B).get("catalogo")[1]["fotos"]}
        ok(fotos["enxoval-geladeira"]["removida"] and fotos[novo]["tem_foto"] and fotos[novo]["ajuste"] == "cover", "catálogo informa fotos novas e retiradas")
        ok(adm2.post("catalogo/enxoval-geladeira/restaurar")[0] == 200, "voltar ao original")
        cat = Cliente(B).get("catalogo")[1]
        ok("enxoval-geladeira" not in {i["id"] for i in cat["itens"]} and "enxoval-geladeira" not in {f["item_id"] for f in cat["fotos"]},
           "voltar ao original desfaz dados e foto")

        # ---------- banco: senhas protegidas e backup ----------
        hashes = srv.sql("SELECT hash FROM senhas")
        ok(hashes and all(re.match(r"pbkdf2\$\d+\$", h["hash"]) for h in hashes), "senhas guardadas só como hash PBKDF2")
        ok(not any("senha" in h["hash"] for h in hashes), "nenhuma senha em texto puro no banco")
        saida = Path(tempfile.mkdtemp()) / "banco.sql"
        srv.exportar(saida, ["usuarios", "unidades", "membros", "compras"])
        dump = saida.read_text()
        ok("Sou Coluna Floripa" in dump and "enxoval-geladeira" in dump and "ana@unidade.test" in dump, "backup exporta unidades, compras e contas")
        ok("pbkdf2$" not in dump and "sessoes" not in dump and "links_senha" not in dump, "backup não leva senhas, sessões nem links")
    print(f"\nTODOS OS {passou} TESTES DA API PASSARAM")


if __name__ == "__main__":
    main()
