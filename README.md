# Guia de Compras · Abertura de Unidade Sou Coluna

Checklist de compras para abrir uma unidade Sou Coluna, em três versões geradas da mesma lista (`data.py`):

| Versão | Para quê | Onde fica o progresso |
|---|---|---|
| **Site com login** (`site/` + `functions/`) | O franqueado entra com e-mail e senha, marca as compras e anota os valores. A franqueadora acompanha todas as unidades num painel. | Banco de dados na Cloudflare (D1), com cópia semanal neste repositório |
| **HTML offline** (`out/guia-compras-sou-coluna.html`) | Arquivo único para mandar por e-mail/WhatsApp, sem login. | No navegador de quem abriu |
| **PDF** (`out/Guia-de-Compras-Sou-Coluna.pdf`) | Versão impressa, com caixas de marcação e linhas para valor e data. | No papel |

O site roda no **plano gratuito da Cloudflare** (Pages + D1), na conta da Sou Coluna. Ele não "dorme" por falta de uso, não apaga dados por inatividade e os limites gratuitos ficam muito acima do que o guia usa.

---

## Como o site está montado

Na conta da Cloudflare da Sou Coluna (plano gratuito), criados pelo Claude via API:

- **Banco D1** `compras-sou-coluna`. As tabelas são criadas sozinhas no primeiro acesso.
- **Projeto Pages** `compras-sou-coluna`, no endereço `https://compras-sou-coluna.pages.dev`, com o banco ligado como `DB` e o segredo `CODIGO_FRANQUEADORA` (a **chave da franqueadora**).
- **Endereço:** https://compras.soucoluna.com
- **Publicar uma versão nova:** rode `python3 build.py` e depois `scripts/publicar.sh` (é assim que o Claude publica). O site inteiro vai num único arquivo de servidor (`_worker.js`, gerado por `scripts/montar_worker.py`).
- **Publicação automática pelo GitHub (opcional):** a automação `.github/workflows/publicar.yml` roda o mesmo script a cada mudança, se o segredo `CLOUDFLARE_API_TOKEN` do GitHub tiver um token válido. Para trocar o segredo, abra [Settings → Secrets → Actions](https://github.com/soucoluna-br/compras-sou-coluna/settings/secrets/actions), clique no lápis ao lado de `CLOUDFLARE_API_TOKEN` e cole o token **com o botão Copy da Cloudflare** (copiar de print ou digitar troca letras). Sem token válido, a automação só avisa e não publica.

**Token da Cloudflare** (Profile → API Tokens → Create Token → Custom token), com as permissões:
- Account · Cloudflare Pages · Edit
- Account · D1 · Edit
- Zone · DNS · Edit (zona soucoluna.com, só para o endereço próprio)
- Zone · Zone · Read

**Conta da franqueadora:** no site, clique em **Criar conta** e, no campo **Código da unidade**, digite a chave da franqueadora. Cada pessoa da franqueadora cria a própria conta assim.

**Trocar a chave da franqueadora:** na Cloudflare, **Workers & Pages → compras-sou-coluna → Settings → Variables and Secrets → CODIGO_FRANQUEADORA**. Depois, publique de novo (`scripts/publicar.sh`).

**Endereço próprio:** no projeto do Pages, **Custom domains → Set up a custom domain → `compras.soucoluna.com`**. Como o domínio já está nessa conta, a Cloudflare cria o apontamento sozinha.

**Backup semanal:** `.github/workflows/backup.yml` usa o mesmo segredo `CLOUDFLARE_API_TOKEN`. Ele só grava quando o repositório é **privado**, porque o backup tem os e-mails dos franqueados e os valores das compras. Enquanto o repositório estiver público, a automação avisa e não grava nada. Para deixar privado: no GitHub, **Settings** → role até **Danger Zone** → **Change visibility → Change to private**.

**Montar do zero em outra conta** (se um dia precisar): crie o banco D1 `compras-sou-coluna`; crie um projeto Pages `compras-sou-coluna` (em **Workers & Pages → Create → Pages**, por upload direto ou ligado ao GitHub com a pasta de saída `site`); em **Settings**, ligue o banco como `DB` e crie o segredo `CODIGO_FRANQUEADORA` (mínimo de 12 caracteres); rode `scripts/publicar.sh` com `CLOUDFLARE_API_TOKEN` apontando para o token da nova conta.

---

## Dia a dia

**Abrir uma unidade nova**
1. No painel, clique em **+ Nova unidade** e preencha nome, cidade e previsão de inauguração.
2. Na janela do convite, clique em **Copiar mensagem** e mande para o franqueado. A mensagem tem o link e o código.
3. O franqueado abre o link, cria a conta e já cai no guia da unidade. Sócios e equipe da mesma unidade usam o mesmo código, cada um com a própria conta.

**Acompanhar**
- Cada unidade aparece num card com: % de itens comprados, quanto já investiu, se está acima ou abaixo da previsão, a última atualização e quantas pessoas têm acesso.
- **Abrir guia** mostra a lista daquela unidade como o franqueado vê. A franqueadora também pode marcar itens.
- **Exportar planilha** baixa um CSV com todas as unidades.

**Senhas e acessos**
- **Franqueado esqueceu a senha:** no painel, **Acessos → Link de senha**. O link é copiado pronto para colar no WhatsApp e vale por 7 dias.
- **Franqueadora esqueceu a senha:** no site, **Esqueci a senha → Sou da franqueadora**, com a chave da franqueadora.
- **Acessos → Remover** tira o acesso de alguém na hora.
- **Convite → Gerar novo código** invalida o código antigo. Quem já tem conta continua entrando.

---

## Backup e restauração

- **Desfazer um erro recente (até 7 dias atrás):** a Cloudflare guarda o histórico do banco ("Time Travel"). Na pasta `ferramentas/`, com o token da Cloudflare em `CLOUDFLARE_API_TOKEN`:

  ```bash
  npx wrangler d1 time-travel restore compras-sou-coluna --timestamp=2026-11-10T12:00:00Z
  ```

- **Recuperar da cópia semanal do GitHub** (ex.: o banco foi apagado):
  1. Crie um banco D1 novo (passo 1 acima) e rode, na pasta `ferramentas/`:

     ```bash
     npx wrangler d1 execute NOME-DO-BANCO-NOVO --remote --file ../backups/banco.sql
     ```

  2. Ligue o banco novo ao projeto (**Settings → Bindings → DB**) e publique de novo (`scripts/publicar.sh`).
  3. As senhas não ficam no backup: a franqueadora cria uma senha nova com a chave, e cada franqueado recebe um link de senha nova pelo painel.

---

## Mudar itens, preços ou fotos

**Pelo painel (o jeito normal):** entre como franqueadora → aba **Catálogo** → **Editar** no item. Dá para mudar nome, especificação, etapa, categoria, quantidade sugerida, valor de referência, fornecimento, fornecedor, observação e foto, criar item novo (**+ Novo item**), remover e **Voltar ao original**. Vale na hora para todas as unidades; o que elas já marcaram continua valendo.

Para a versão offline e o PDF também refletirem essas mudanças: `python3 scripts/baixar_catalogo.py`, depois `python3 build.py` e `python3 scripts/gerar_pdf.py` (ou peça ao Claude).

**Pelo código (mudanças grandes na lista base):**

1. Edite `data.py` (itens e valores) ou coloque fotos em `images/` com o nome do id do item (lista em `out/ids-dos-itens.json`).
2. Rode:

   ```bash
   pip install -r requirements.txt
   python3 build.py              # gera o site, o HTML offline e a lista de ids
   python3 scripts/gerar_pdf.py  # gera o PDF
   ```

3. Faça o commit e publique com `scripts/publicar.sh` (ou peça ao Claude).

> **Atenção ao renomear um item:** o id do item vem do nome. Se uma unidade já marcou esse item no site, renomear faz o progresso dele sumir. Antes de publicar, na pasta `ferramentas/`:
> `npx wrangler d1 execute compras-sou-coluna --remote --command "UPDATE compras SET item_id = 'id-novo' WHERE item_id = 'id-antigo'"`

---

## Rodar e testar no computador

```bash
cd ferramentas && npm ci && cd ..      # instala o wrangler (ferramenta da Cloudflare)
python3 build.py
ferramentas/node_modules/.bin/wrangler pages dev site --d1 DB=banco-local --binding CODIGO_FRANQUEADORA=uma-chave-de-teste
# abre em http://localhost:8788, com um banco local só para testes
```

Testes automáticos (sobem o site sozinhos, com um banco zerado):

```bash
python3 tests/test_api.py    # login, regras de acesso, links de senha, limite de tentativas, backup
python3 tests/test_site.py   # telas de login, guia e painel num Chromium (computador e celular)
```

`gerar_pdf.py` e `test_site.py` aceitam `CHROMIUM_PATH=/caminho/do/chromium` para usar um Chromium já instalado.
