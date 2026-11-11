# Guia de Compras · Abertura de Unidade Sou Coluna

Checklist de compras para abrir uma unidade Sou Coluna, em três versões geradas da mesma lista (`data.py`):

| Versão | Para quê | Onde fica o progresso |
|---|---|---|
| **Site com login** (`site/` + `functions/`) | O franqueado entra com e-mail e senha, marca as compras e anota os valores. A franqueadora acompanha todas as unidades num painel. | Banco de dados na Cloudflare (D1), com cópia semanal neste repositório |
| **HTML offline** (`out/guia-compras-sou-coluna.html`) | Arquivo único para mandar por e-mail/WhatsApp, sem login. | No navegador de quem abriu |
| **PDF** (`out/Guia-de-Compras-Sou-Coluna.pdf`) | Versão impressa, com caixas de marcação e linhas para valor e data. | No papel |

O site roda no **plano gratuito da Cloudflare** (Pages + D1). Ele não "dorme" por falta de uso, não apaga dados por inatividade e os limites gratuitos ficam muito acima do que o guia usa.

---

## Colocar o site no ar (uma vez só)

### 1. Conta e banco de dados na Cloudflare

1. Crie uma conta gratuita em [dash.cloudflare.com](https://dash.cloudflare.com/sign-up). Não pede cartão.
2. No menu, abra **Storage & Databases → D1 SQL Database → Create**.
3. Dê o nome **`compras-sou-coluna`** (exatamente assim, porque o backup usa esse nome) e clique em **Create**.

As tabelas são criadas sozinhas no primeiro acesso ao site. Não precisa rodar nenhum SQL.

### 2. Site (Cloudflare Pages)

1. No menu, abra **Workers & Pages → Create → Pages → Connect to Git** (ou *Import an existing Git repository*).
2. Autorize o GitHub com a conta **soucoluna-br** e escolha o repositório **compras-sou-coluna** → **Begin setup**.
3. Em *Build settings*:
   - **Framework preset:** None
   - **Build command:** deixe vazio
   - **Build output directory:** `site`

   Clique em **Save and Deploy**.
4. No projeto criado, abra **Settings → Bindings → Add → D1 database**:
   - **Variable name:** `DB`
   - **D1 database:** `compras-sou-coluna`
5. Em **Settings → Variables and Secrets → Add**:
   - **Type:** Secret
   - **Variable name:** `CODIGO_FRANQUEADORA`
   - **Value:** uma frase longa só sua (mínimo 12 caracteres; por exemplo, quatro palavras aleatórias). Essa é a **chave da franqueadora**: guarde num lugar seguro e não mande para franqueados.
6. Em **Deployments**, clique em **⋯ → Retry deployment** na publicação mais recente, para o banco e a chave passarem a valer.
7. Abra o endereço `https://compras-sou-coluna.pages.dev` (o nome exato aparece no topo do projeto).

### 3. Conta da franqueadora

Abra o site → **Criar conta** → no campo **Código da unidade**, digite a **chave da franqueadora** → preencha nome, e-mail e senha. Você entra direto no **Painel das unidades**. Cada pessoa da franqueadora cria a própria conta do mesmo jeito.

### 4. Backup automático semanal (recomendado)

Toda segunda-feira o GitHub copia o banco (contas, unidades, acessos e compras; **sem as senhas**) para `backups/banco.sql` neste repositório.

1. Na Cloudflare, clique no ícone do seu perfil (canto superior direito) → **My Profile → API Tokens → Create Token → Create Custom Token**:
   - **Permissions:** Account · D1 · Edit
   - **Continue to summary → Create Token** → copie o token.
2. Copie também o **Account ID** da sua conta (aparece em **Workers & Pages**, na coluna da direita).
3. No GitHub, abra o repositório → **Settings → Secrets and variables → Actions → New repository secret** e crie os dois:
   - `CLOUDFLARE_API_TOKEN` (o token)
   - `CLOUDFLARE_ACCOUNT_ID` (o Account ID)
4. Para testar, abra **Actions → Backup do banco → Run workflow**. Em um minuto deve aparecer `backups/banco.sql` no repositório.

> O repositório precisa ser **privado**: o backup tem os e-mails dos franqueados e os valores das compras.

### 5. Endereço próprio (opcional)

No projeto do Pages: **Custom domains → Set up a custom domain** → por exemplo `compras.soucoluna.com.br`. Se o domínio está na HostGator, crie no **cPanel → Editor de Zona DNS** um registro **CNAME** `compras` apontando para `compras-sou-coluna.pages.dev`.

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

  2. Ligue o banco novo ao site (passo 2.4) e refaça a publicação (passo 2.6).
  3. As senhas não ficam no backup: a franqueadora cria uma senha nova com a chave, e cada franqueado recebe um link de senha nova pelo painel.

---

## Mudar itens, preços ou fotos

1. Edite `data.py` (itens e valores) ou coloque fotos em `images/` com o nome do id do item (lista em `out/ids-dos-itens.json`).
2. Rode:

   ```bash
   pip install -r requirements.txt
   python3 build.py              # gera o site, o HTML offline e a lista de ids
   python3 scripts/gerar_pdf.py  # gera o PDF
   ```

3. Faça o commit e o push. A Cloudflare publica o site novo sozinha.

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
