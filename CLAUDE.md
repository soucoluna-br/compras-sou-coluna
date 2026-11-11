# Guia de Compras · Abertura de Unidade Sou Coluna

Checklist de compras para franqueados abrirem uma nova unidade da Sou Coluna. Ele substitui a planilha `src/planilha-original.xlsx` por um material bonito para enviar ao franqueado, em duas versões geradas da mesma base:

- **Online** (`out/guia-compras-sou-coluna.html`): página única e autossuficiente. O franqueado marca o item como comprado, informa o valor pago e acompanha o andamento (% de itens, valor investido, economia ou estouro em relação à previsão). O estado fica salvo no `localStorage` do navegador. Também tem copiar resumo, exportar CSV, backup/restauração em JSON e impressão.
- **Impressa** (`out/Guia-de-Compras-Sou-Coluna.pdf`): capa, página "Como usar" com tabela de totais e os cards com caixa de marcação e linhas para valor pago e data.

## Estrutura

- `data.py`: fonte única dos itens. Em `SECTIONS`, cada etapa tem categorias, e cada item é uma tupla `(nome, especificação, qtd, valor_unit, fornecimento, fornecedor, observação[, unidade_de_medida])`.
  - `fornecimento`: `"homologado"` | `"marca"` | `"livre"` | `None`
  - `valor_unit=None` indica item recorrente ou a definir (mensalidades e locação). Esses itens não entram no total de investimento.
- `template.html`: layout, CSS (tela + `@media print`) e JS. Os placeholders `/*__DATA__*/`, `/*__IMAGES__*/`, `__LOGO_WHITE__` e `__SYMBOL_WHITE__` são preenchidos pelo build.
- `build.py`: lê `data.py` e `images/` e gera `out/guia-compras-sou-coluna.html` com tudo embutido (imagens em base64).
- `scripts/gerar_pdf.py`: renderiza o HTML em modo impressão e gera o PDF.
- `images/`: fotos dos produtos. O nome do arquivo é o **id do item** (lista em `out/ids-dos-itens.json`), por exemplo `enxoval-geladeira.jpg`. Com o sufixo `__cover` (`enxoval-geladeira__cover.jpg`), a foto preenche o card inteiro em vez de ficar centralizada em fundo branco. Item sem foto mostra um ícone da categoria.

## Como rodar

```bash
pip install -r requirements.txt
playwright install chromium
python3 build.py              # gera o HTML
python3 scripts/gerar_pdf.py  # gera o PDF
```

Se já existir um Chromium instalado e o `playwright install` não for possível (ou a versão não bater), aponte para ele: `CHROMIUM_PATH=/caminho/do/chromium python3 scripts/gerar_pdf.py`.

## Decisões já tomadas (manter)

- A antiga aba **Comodato** foi para o **Enxoval** como categoria "Equipamentos clínicos". A Sou Coluna não tem mais comodato, então a palavra não aparece.
- Links, CNPJs e telefones foram removidos (os links ficavam desatualizados). O modelo que estava no link foi para a especificação do item. O nome do fornecedor homologado continua.
- Ficaram fora do material: o Blazer (qtd 0), as notas internas de cálculo de obra (BH/Fortaleza) e a aba RESUMO (tem o ganho da franqueadora e prints de benchmark, que são internos).
- Nunca usar "avaliação" em material de clínica, sempre "consulta" (ex.: "Puff para a sala de consulta").
- Itens em ordem alfabética dentro de cada categoria. Etapas na ordem da jornada: 1 Obra/projeto/marcenaria → 2 Enxoval → 3 Produtos da franqueadora → 4 Estoque inicial.
- Marca: coral `#EF7B60`, fontes Poppins (títulos) e Inter (texto).
- Totais conferidos com a planilha: Obra R$ 164.169,40 · Enxoval R$ 122.831 · Franqueadora R$ 13.670 · Estoque R$ 1.968 · **Total R$ 302.638,40** (130 itens).

## Pendências (aguardando o Rossanão)

1. Origem das fotos dos produtos: fotos reais de uma unidade modelo (recomendado) ou geração por IA. Para IA: GPT Image 2.5 em 4K e **só gerar com autorização explícita**.
2. Produtos da franqueadora: a planilha original diz "adicionar imposto". Falta confirmar se os valores devem aparecer com imposto.
3. Incluir ou não o restante do investimento (taxa de franquia, abertura de empresa + marketing inaugural + contratação, reserva de giro).

## Próximo passo possível

Hoje o progresso fica só no navegador do franqueado. A evolução natural é uma versão no Vercel + Supabase com:

- login por unidade;
- progresso salvo no banco;
- painel da franqueadora mostrando o andamento e o orçamento de todas as unidades.
