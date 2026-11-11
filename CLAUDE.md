# Guia de Compras · Abertura de Unidade Sou Coluna

Checklist de compras para franqueados abrirem uma nova unidade da Sou Coluna. Ele substitui a planilha `src/planilha-original.xlsx` por um material bonito para enviar ao franqueado, em três versões geradas da mesma base:

- **Site com login** (`site/`, Vercel + Supabase): o franqueado entra com e-mail e senha e vê só a(s) unidade(s) dele; o progresso fica no banco. A franqueadora tem um painel (`site/painel.html`) com todas as unidades. Passo a passo para colocar no ar: `README.md`.
- **Offline** (`out/guia-compras-sou-coluna.html`): página única e autossuficiente. O franqueado marca o item como comprado, informa o valor pago e acompanha o andamento (% de itens, valor investido, economia ou estouro em relação à previsão). O estado fica salvo no `localStorage` do navegador. Também tem copiar resumo, exportar CSV, backup/restauração em JSON e impressão.
- **Impressa** (`out/Guia-de-Compras-Sou-Coluna.pdf`): capa, página "Como usar" com tabela de totais e os cards com caixa de marcação e linhas para valor pago e data.

## Estrutura

- `data.py`: fonte única dos itens. Em `SECTIONS`, cada etapa tem categorias, e cada item é uma tupla `(nome, especificação, qtd, valor_unit, fornecimento, fornecedor, observação[, unidade_de_medida])`.
  - `fornecimento`: `"homologado"` | `"marca"` | `"livre"` | `None`
  - `valor_unit=None` indica item recorrente ou a definir (mensalidades e locação). Esses itens não entram no total de investimento.
- `template.html`: layout, CSS (tela + `@media print`) e JS do guia. Os placeholders `/*__DATA__*/`, `/*__IMAGES__*/`, `<!--__HEAD_EXTRA__-->`, `__LOGO_WHITE__` e `__SYMBOL_WHITE__` são preenchidos pelo build. O mesmo template serve às duas versões: se `window.SC` existe (site), salva no banco item a item; senão, usa `localStorage`. Elementos `.online-only` / `.offline-only` aparecem só em uma delas.
- `build.py`: lê `data.py` e `images/` e gera `out/guia-compras-sou-coluna.html` (tudo embutido, imagens em base64) e, para o site, `site/guia.html`, `site/catalogo.js` (catálogo para o painel), `site/img/` (fotos como arquivos) e `site/assets/`. **Os arquivos gerados são versionados**: a Vercel só publica a pasta `site/`, sem build.
- `site/`: `index.html` (entrar, criar conta com código da unidade, esqueci a senha, escolher unidade), `painel.html` (franqueadora: unidades, convite, acessos, CSV), `app.js` (toda a conversa com o Supabase), `estilo.css`, `config.js` (URL + chave pública do Supabase) e `vendor/supabase-2.118.0.js` (supabase-js embutido, sem CDN).
- `supabase/schema.sql`: tabelas `perfis`, `unidades`, `membros`, `compras`, regras de acesso (RLS), trigger que cria o perfil no cadastro e liga à unidade pelo código, e RPCs (`codigo_valido`, `entrar_com_codigo`, `definir_responsavel`, `renovar_codigo`). Pode ser reaplicado sem perder dados.
- `vercel.json`: publica `site/` como site estático.
- `tests/`: `testar_banco.sh` (regras de acesso num Postgres local, imitando o Supabase) e `test_site.py` (ponta a ponta no Chromium com `tests/site/fake-supabase.js`).
- `scripts/gerar_pdf.py`: renderiza o HTML em modo impressão e gera o PDF.
- `images/`: fotos dos produtos. O nome do arquivo é o **id do item** (lista em `out/ids-dos-itens.json`), por exemplo `enxoval-geladeira.jpg`. Com o sufixo `__cover` (`enxoval-geladeira__cover.jpg`), a foto preenche o card inteiro em vez de ficar centralizada em fundo branco. Item sem foto mostra um ícone da categoria.

## Como rodar

```bash
pip install -r requirements.txt
playwright install chromium
python3 build.py              # gera o HTML offline e o site
python3 scripts/gerar_pdf.py  # gera o PDF
tests/testar_banco.sh         # testa o banco (precisa de Postgres local: PGHOST/PGPORT/PGUSER)
python3 tests/test_site.py    # testa login, guia e painel (opcional: --telas pasta/ salva capturas)
```

Se já existir um Chromium instalado e o `playwright install` não for possível (ou a versão não bater), aponte para ele: `CHROMIUM_PATH=/caminho/do/chromium python3 scripts/gerar_pdf.py` (vale também para `tests/test_site.py`).

## Decisões já tomadas (manter)

- A antiga aba **Comodato** foi para o **Enxoval** como categoria "Equipamentos clínicos". A Sou Coluna não tem mais comodato, então a palavra não aparece.
- Links, CNPJs e telefones foram removidos (os links ficavam desatualizados). O modelo que estava no link foi para a especificação do item. O nome do fornecedor homologado continua.
- Ficaram fora do material: o Blazer (qtd 0), as notas internas de cálculo de obra (BH/Fortaleza) e a aba RESUMO (tem o ganho da franqueadora e prints de benchmark, que são internos).
- Nunca usar "avaliação" em material de clínica, sempre "consulta" (ex.: "Puff para a sala de consulta").
- Itens em ordem alfabética dentro de cada categoria. Etapas na ordem da jornada: 1 Obra/projeto/marcenaria → 2 Enxoval → 3 Produtos da franqueadora → 4 Estoque inicial.
- Marca: coral `#EF7B60`, fontes Poppins (títulos) e Inter (texto).
- Totais conferidos com a planilha: Obra R$ 164.169,40 · Enxoval R$ 122.831 · Franqueadora R$ 13.670 · Estoque R$ 1.968 · **Total R$ 302.638,40** (130 itens).

### Site com login

- Acesso por **código de convite da unidade** (`unidades.codigo`, formato `XXXXX-XXXXX`). Não existe cadastro aberto útil: conta sem código não vê nada. Várias pessoas da mesma unidade usam o mesmo código, cada uma com a própria conta; uma pessoa pode ter várias unidades.
- **Franqueadora** = `perfis.franqueadora = true`, definido só pelo SQL Editor (o site não consegue promover ninguém; a coluna não tem permissão de escrita para usuários).
- O progresso é gravado por item em `compras` (chave `unidade_id + item_id`). O `item_id` é o slug do nome em `data.py`: **renomear um item faz o progresso dele sumir** nas unidades. Antes de publicar, migrar com `update public.compras set item_id = 'novo' where item_id = 'velho';`.
- O painel calcula os números no navegador a partir de `catalogo.js` + `compras`, com a mesma conta do guia (itens recorrentes fora do total; diferença só nos itens com valor).
- `config.js` só pode ter a URL e a chave **pública** (publishable/anon). Nunca a service_role/secret.
- Sem dependência de CDN para JavaScript (supabase-js fica em `site/vendor/`). As fontes continuam vindo do Google Fonts.
- O repositório deve ficar **privado** (tem a planilha original com a aba RESUMO e os preços).

## Pendências (aguardando o Rossanão)

1. Origem das fotos dos produtos: fotos reais de uma unidade modelo (recomendado) ou geração por IA. Para IA: GPT Image 2.5 em 4K e **só gerar com autorização explícita**.
2. Produtos da franqueadora: a planilha original diz "adicionar imposto". Falta confirmar se os valores devem aparecer com imposto.
3. Incluir ou não o restante do investimento (taxa de franquia, abertura de empresa + marketing inaugural + contratação, reserva de giro).

## Status do site

Código pronto e testado (banco: `tests/testar_banco.sh`; site: `tests/test_site.py`). Para ir ao ar falta o que só o usuário pode fazer: criar o projeto no Supabase e rodar `supabase/schema.sql`, preencher `site/config.js`, importar o repositório na Vercel, configurar as URLs de redirecionamento e criar a conta da franqueadora (passo a passo no `README.md`).
