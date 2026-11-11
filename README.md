# Guia de Compras · Abertura de Unidade Sou Coluna

Checklist de compras para abrir uma unidade Sou Coluna, em três versões geradas da mesma lista (`data.py`):

| Versão | Para quê | Onde fica o progresso |
|---|---|---|
| **Site com login** (`site/`) | O franqueado entra com e-mail e senha, marca as compras e anota os valores. A franqueadora acompanha todas as unidades num painel. | No banco de dados (Supabase) |
| **HTML offline** (`out/guia-compras-sou-coluna.html`) | Arquivo único para mandar por e-mail/WhatsApp, sem login. | No navegador de quem abriu |
| **PDF** (`out/Guia-de-Compras-Sou-Coluna.pdf`) | Versão impressa, com caixas de marcação e linhas para valor e data. | No papel |

---

## Colocar o site no ar (uma vez só)

Você precisa de duas contas gratuitas: **Supabase** (banco de dados e login) e **Vercel** (hospedagem do site).

### 1. Supabase

1. Entre em [supabase.com](https://supabase.com), crie uma conta e um **projeto novo**. Na região, escolha **South America (São Paulo)**.
2. No menu do projeto, abra **SQL Editor → New query**, cole o conteúdo inteiro de [`supabase/schema.sql`](supabase/schema.sql) e clique em **Run**. Isso cria as tabelas e as regras de quem pode ver o quê.
3. Em **Project Settings → API Keys**, copie:
   - o **Project URL** (algo como `https://abcdxyz.supabase.co`);
   - a **chave pública**: a *Publishable key* (`sb_publishable_...`) ou, em projetos mais antigos, a *anon public*.

   Cole os dois em [`site/config.js`](site/config.js) (ou mande para o Claude colar). Essas duas informações são públicas por natureza. **Nunca** use a *secret key* / *service_role* no site.
4. Em **Authentication → Sign In / Providers → Email**, recomendamos **desligar "Confirm email"** no começo. O código da unidade já controla quem entra, e o envio de e-mails padrão do Supabase é limitado a poucos por hora. Se quiser manter a confirmação, configure um envio de e-mails próprio em **Authentication → Emails → SMTP Settings** (Resend, Brevo ou o e-mail da empresa).

### 2. Vercel

1. Entre em [vercel.com](https://vercel.com) com a conta do GitHub **soucoluna-br**.
2. **Add New → Project →** importe o repositório **compras-sou-coluna** → **Deploy**. Não precisa mudar nada: o `vercel.json` já manda publicar a pasta `site/`.
3. Anote o endereço gerado (ex.: `https://compras-sou-coluna.vercel.app`). Dá para trocar por um domínio próprio depois (ex.: `compras.soucoluna.com.br`) em **Settings → Domains**.

### 3. Ligar o Supabase ao endereço do site

No Supabase, em **Authentication → URL Configuration**:

- **Site URL**: o endereço da Vercel (ex.: `https://compras-sou-coluna.vercel.app`);
- **Redirect URLs**: adicione `https://compras-sou-coluna.vercel.app/**`.

Sem isso, os links de e-mail (confirmação e "esqueci a senha") não voltam para o site.

### 4. Conta da franqueadora

1. No Supabase, **Authentication → Users → Add user → Create new user**: informe seu e-mail e uma senha e marque **Auto Confirm User**.
2. No **SQL Editor**, rode (com o seu e-mail):

   ```sql
   update public.perfis set franqueadora = true where email = 'seu-email@soucoluna.com.br';
   ```

3. Abra o site e entre. Você cai direto no **Painel das unidades**. Repita os dois passos para cada pessoa da franqueadora que precisa ver o painel.

---

## Dia a dia

**Abrir uma unidade nova**
1. No painel, clique em **+ Nova unidade** e preencha nome, cidade e previsão de inauguração.
2. Na janela do convite, clique em **Copiar mensagem** e mande para o franqueado (WhatsApp ou e-mail). A mensagem tem o link e o código.
3. O franqueado abre o link, cria a conta com o código e já cai no guia da unidade. Sócios e equipe da mesma unidade usam o mesmo código, cada um com a própria conta.

**Acompanhar**
- O painel mostra, por unidade: % de itens comprados, quanto já investiu, se está acima ou abaixo da previsão, quando foi a última atualização e quem tem acesso.
- **Abrir guia** mostra a lista daquela unidade exatamente como o franqueado vê (a franqueadora também pode marcar itens).
- **Exportar planilha** baixa um CSV com todas as unidades.

**Acessos**
- **Acessos** lista quem entra em cada unidade e permite remover alguém.
- **Convite → Gerar novo código** invalida o código antigo (quem já tem conta continua entrando).

---

## Mudar itens, preços ou fotos

1. Edite `data.py` (itens e valores) ou coloque fotos em `images/` com o nome do id do item (lista em `out/ids-dos-itens.json`).
2. Rode:

   ```bash
   pip install -r requirements.txt
   python3 build.py              # gera o site, o HTML offline e a lista de ids
   python3 scripts/gerar_pdf.py  # gera o PDF
   ```

3. Faça o commit e o push. A Vercel publica o site novo sozinha.

> **Atenção ao renomear um item:** o id do item vem do nome. Se uma unidade já marcou esse item no site, renomear faz o progresso dele sumir. Antes de publicar, rode no SQL Editor:
> `update public.compras set item_id = 'id-novo' where item_id = 'id-antigo';`

---

## Testes

```bash
tests/testar_banco.sh        # regras de acesso do banco, num Postgres local (precisa de psql/createdb)
python3 tests/test_site.py   # login, guia e painel num Chromium, com um Supabase simulado
```

`gerar_pdf.py` e `test_site.py` aceitam `CHROMIUM_PATH=/caminho/do/chromium` para usar um Chromium já instalado.
