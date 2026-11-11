# Guia de Compras · Abertura de Unidade Sou Coluna

Checklist de compras para franqueados abrirem uma nova unidade da Sou Coluna. Ele substitui a planilha `src/planilha-original.xlsx` (fica só no computador, fora do GitHub: `src/` está no `.gitignore` e foi tirada do histórico, porque a aba RESUMO é interna) por um material bonito para enviar ao franqueado, em três versões geradas da mesma base:

- **Site com login** (`site/` + `functions/`, Cloudflare Pages + banco D1, plano gratuito): o franqueado entra com e-mail e senha e vê só a(s) unidade(s) dele; o progresso fica no banco. A franqueadora tem um painel (`site/painel.html`) com todas as unidades. Passo a passo para colocar no ar: `README.md`.
- **Offline** (`out/guia-compras-sou-coluna.html`): página única e autossuficiente. O franqueado marca o item como comprado, informa o valor pago e acompanha o andamento (% de itens, valor investido, economia ou estouro em relação à previsão). O estado fica salvo no `localStorage` do navegador. Também tem copiar resumo, exportar CSV, backup/restauração em JSON e impressão.
- **Impressa** (`out/Guia-de-Compras-Sou-Coluna.pdf`): capa, página "Como usar" com tabela de totais e os cards com caixa de marcação e linhas para valor pago e data.

## Estrutura

- `data.py`: fonte única dos itens. Em `SECTIONS`, cada etapa tem categorias, e cada item é uma tupla `(nome, especificação, qtd, valor_unit, fornecimento, fornecedor, observação[, unidade_de_medida])`.
  - `fornecimento`: `"homologado"` | `"marca"` | `"livre"` | `None`
  - `valor_unit=None` indica item recorrente ou a definir (mensalidades e locação). Esses itens não entram no total de investimento.
- `template.html`: layout, CSS (tela + `@media print`) e JS do guia. Os placeholders `/*__DATA__*/`, `/*__IMAGES__*/`, `<!--__HEAD_EXTRA__-->`, `__LOGO_WHITE__` e `__SYMBOL_WHITE__` são preenchidos pelo build. O mesmo template serve às duas versões: se `window.SC` existe (site), salva no banco item a item; senão, usa `localStorage`. Elementos `.online-only` / `.offline-only` aparecem só em uma delas. Visual de tela em estilo "loja" (barra superior com abas Todos/Pendentes/Comprados e busca, faixa escura, selo "Comprando para a unidade", filtros laterais, ordenação, blocos/lista) todo dentro de `@media screen`; as regras de `@media print` (PDF) são as originais e não devem mudar. Ao mexer no template, conferir que o PDF continua idêntico (comparar as páginas em imagem com o PDF anterior).
- `build.py`: lê `data.py` e `images/` e gera `out/guia-compras-sou-coluna.html` (tudo embutido, imagens em base64) e, para o site, `site/guia.html`, `site/catalogo.js` (catálogo para o painel), `site/img/` (fotos como arquivos) e `site/assets/`. **Os arquivos gerados são versionados**: a Cloudflare só publica a pasta `site/` (sem comando de build) mais as funções de `functions/`.
- `site/`: `index.html` (entrar, criar conta com código da unidade, esqueci a senha, link de senha nova, escolher unidade), `painel.html` (franqueadora: unidades em cards, convite, acessos, link de senha, CSV), `app.js` (toda a conversa com a API), `estilo.css` e `_headers` (cabeçalhos de segurança).
- `functions/api/[[rota]].js`: a API (Cloudflare Pages Functions) em `/api/...`. Login próprio (PBKDF2-SHA256 com 25 mil rodadas, para caber nos 10 ms de CPU do plano gratuito; o número fica no hash e é refeito no login se aumentar), sessão em cookie HttpOnly, limite de tentativas, bloqueio de chamadas de outros sites, regras de acesso (franqueado só a(s) própria(s) unidade(s); franqueadora tudo). Cria as tabelas sozinha no primeiro acesso (`usuarios`, `unidades`, `membros`, `compras`; e `senhas`, `sessoes`, `links_senha`, `tentativas` separadas para o backup poder deixá-las de fora).
- Configuração na Cloudflare: binding D1 `DB` e o segredo `CODIGO_FRANQUEADORA` (a "chave da franqueadora": usada no lugar do código da unidade para criar conta de franqueadora e para ela trocar a própria senha).
- `.github/workflows/backup.yml`: toda segunda exporta o D1 (`compras-sou-coluna`) para `backups/banco.sql`, sem senhas/sessões, com `[CI Skip]` para não republicar o site. Precisa dos segredos `CLOUDFLARE_API_TOKEN` (D1 Edit) e `CLOUDFLARE_ACCOUNT_ID` no GitHub.
- `ferramentas/`: `package.json` com o wrangler fixado (4.152.0), usado nos testes e no backup. Fica fora da raiz para a Cloudflare não instalar nada na publicação.
- `tests/`: `servidor_local.py` (sobe `wrangler pages dev` com D1 local zerado), `test_api.py` (regras de acesso, login, links, limites, comando de backup) e `test_site.py` (ponta a ponta no Chromium, computador e celular, mais a versão offline). `tests/banco-local/wrangler.toml` só serve para os testes consultarem/exportarem o banco local.
- `scripts/gerar_pdf.py`: renderiza o HTML em modo impressão e gera o PDF.
- `images/`: fotos dos produtos. O nome do arquivo é o **id do item** (lista em `out/ids-dos-itens.json`), por exemplo `enxoval-geladeira.jpg`. Com o sufixo `__cover` (`enxoval-geladeira__cover.jpg`), a foto preenche o card inteiro em vez de ficar centralizada em fundo branco. Item sem foto mostra um ícone da categoria.

## Como rodar

```bash
pip install -r requirements.txt
playwright install chromium
python3 build.py              # gera o HTML offline e o site
python3 scripts/gerar_pdf.py  # gera o PDF
cd ferramentas && npm ci && cd ..   # wrangler (Cloudflare), para rodar o site local e os testes
python3 tests/test_api.py     # testa a API e o banco (sobe o site local sozinho)
python3 tests/test_site.py    # testa login, guia e painel (opcional: --telas pasta/ salva capturas)
```

Se já existir um Chromium instalado e o `playwright install` não for possível (ou a versão não bater), aponte para ele: `CHROMIUM_PATH=/caminho/do/chromium python3 scripts/gerar_pdf.py` (vale também para `tests/test_site.py`). Se a pasta temporária tiver um caminho muito longo, o Chromium falha ("Socket path too long"): use `GUIA_TMP=pasta` para os dados do teste em vez de mudar `TMPDIR`.

## Decisões já tomadas (manter)

- A antiga aba **Comodato** foi para o **Enxoval** como categoria "Equipamentos clínicos". A Sou Coluna não tem mais comodato, então a palavra não aparece.
- Links, CNPJs e telefones foram removidos (os links ficavam desatualizados). O modelo que estava no link foi para a especificação do item. O nome do fornecedor homologado continua.
- Ficaram fora do material: o Blazer (qtd 0), as notas internas de cálculo de obra (BH/Fortaleza) e a aba RESUMO (tem o ganho da franqueadora e prints de benchmark, que são internos).
- Nunca usar "avaliação" em material de clínica, sempre "consulta" (ex.: "Puff para a sala de consulta").
- Itens em ordem alfabética dentro de cada categoria. Etapas na ordem da jornada: 1 Obra/projeto/marcenaria → 2 Enxoval → 3 Produtos da franqueadora → 4 Estoque inicial.
- Marca: coral `#EF7B60`, fontes Poppins (títulos) e Inter (texto).
- Totais conferidos com a planilha: Obra R$ 164.169,40 · Enxoval R$ 122.831 · Franqueadora R$ 13.670 · Estoque R$ 1.968 · **Total R$ 302.638,40** (130 itens).

### Site com login

- Hospedagem: **Cloudflare Pages + D1, plano gratuito**. Supabase foi descartado (projeto gratuito pausa após 7 dias sem uso) e Render também (Postgres gratuito expira em 30 dias). O site precisa ficar parado meses e voltar a funcionar quando abrir uma unidade nova.
- Sem envio de e-mail: "esqueci a senha" é resolvido por **link de senha nova gerado pela franqueadora** no painel (vale 7 dias, uma vez só) e enviado pelo WhatsApp; a franqueadora troca a própria senha com a chave.
- Acesso por **código de convite da unidade** (`unidades.codigo`, formato `XXXXX-XXXXX`). Sem o código não dá para criar conta. Várias pessoas da mesma unidade usam o mesmo código, cada uma com a própria conta; uma pessoa pode ter várias unidades.
- O progresso é gravado por item em `compras` (chave `unidade_id + item_id`, valor em centavos). O `item_id` é o slug do nome em `data.py`: **renomear um item faz o progresso dele sumir** nas unidades. Antes de publicar, migrar com `UPDATE compras SET item_id = 'novo' WHERE item_id = 'velho'` (comando no README).
- O painel calcula os números no navegador a partir de `catalogo.js` + compras, com a mesma conta do guia (itens recorrentes fora do total; diferença só nos itens com valor).
- Links do site sem `.html` (`/guia?u=...`, `/painel`, `/?codigo=...`), porque a Cloudflare Pages tira a extensão.
- O repositório `soucoluna-br/compras-sou-coluna` está **público** por enquanto (decisão do usuário). Por isso a planilha original não vai para o GitHub e o backup semanal **só grava se o repositório for privado** (a automação confere antes). Nunca commitar dados de franqueados, a planilha ou segredos.

## Pendências (aguardando o Rossanão)

1. Origem das fotos dos produtos: fotos reais de uma unidade modelo (recomendado) ou geração por IA. Para IA: GPT Image 2.5 em 4K e **só gerar com autorização explícita**.
2. Produtos da franqueadora: a planilha original diz "adicionar imposto". Falta confirmar se os valores devem aparecer com imposto.
3. Incluir ou não o restante do investimento (taxa de franquia, abertura de empresa + marketing inaugural + contratação, reserva de giro).

## Status do site

Código pronto e testado localmente com o servidor da própria Cloudflare (`tests/test_api.py` e `tests/test_site.py`). Para ir ao ar falta o que só o usuário pode fazer: criar a conta na Cloudflare, o banco D1 `compras-sou-coluna`, o projeto Pages ligado ao GitHub (saída `site`), o binding `DB`, o segredo `CODIGO_FRANQUEADORA` e, para o backup, os segredos no GitHub (passo a passo no `README.md`).
