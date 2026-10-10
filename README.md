# TSE BU Collector

Coleta os **Boletins de Urna (arquivo `bweb`) do TSE** para qualquer município
brasileiro e transforma em três produtos:

- **CSV consolidado por seção** com ranking de abstenção e indicador de
  potencial de virada.
- **Dashboard interativo** (Streamlit) com mapa geográfico, heatmaps e
  tabelas filtráveis.
- **Relatório HTML/PDF autocontido** pronto para imprimir ou enviar por e-mail.

Fonte oficial: portal de dados abertos do TSE
(https://dadosabertos.tse.jus.br), dataset `Resultados - <ano> - Boletim de Urna`.
O arquivo é baixado por inteiro da UF (ex.: ~490 MB para MG) com download
paralelo por ranges e retentativas; na segunda execução ele é reutilizado
do cache local (default: pasta temporária do sistema — arquivos de centenas
de MB podem falhar em mounts de rede).

---

## Requisitos

- Python 3.11 ou 3.12 (evite 3.13+; algumas dependências ainda não têm
  wheels estáveis)
- ~600 MB de disco livre para o ZIP do bweb + cache de coordenadas

---

## Instalação

```bash
pip install -r requirements.txt
playwright install chromium        # baixa o Chromium (~150 MB) para gerar o PDF
```

O passo `playwright install chromium` é necessário **apenas** para gerar o
PDF do relatório (flag `--pdf`). Se você só for usar o CSV, os PDFs por urna
ou o dashboard, pode pular.

---

## Uso rápido

Pipeline completo (CSV + PDFs por urna + relatório HTML + PDF + abre no navegador):

```bash
python main.py --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
    --cand1 22 --cand2 13 --relatorio --pdf --abrir
```

Só o CSV (bem mais rápido):

```bash
python main.py --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
    --cand1 22 --cand2 13 --somente-csv
```

Governador — basta trocar `--cargo`:

```bash
python main.py --uf BA --cidade "SALVADOR" --ano 2026 --turno 1 \
    --cargo governador --cand1 13 --cand2 44
```

Dashboard interativo (lê o CSV de `saida/`):

```bash
streamlit run dashboard.py
```

Relatório avulso (sem rerodar o pipeline):

```bash
python report.py --csv saida/ouro_preto_urnas_1turno_2026.csv \
                 --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
                 --pdf --abrir
```

---

## Flags do `main.py`

- `--uf` — UF de 2 letras (ex.: `MG`) — **obrigatório**
- `--cidade` — Nome do município (ex.: `"OURO PRETO"`) — **obrigatório**
- `--ano` — Ano da eleição (default: `2026`)
- `--turno` — `1` ou `2` (default: `1`)
- `--cargo` — `presidente`, `governador`, `senador`, `deputado-federal`,
  `deputado-estadual`, `deputado-distrital`, `prefeito`, `vereador`, `outro`
  (default: `presidente`)
- `--cargo-codigo` — Código numérico do cargo, quando `--cargo outro`
- `--cand1` — Número do candidato 1 (ex.: `22`) — **obrigatório**
- `--cand2` — Número do candidato 2 (ex.: `13`) — **obrigatório**
- `--saida` — Pasta de saída (default: `saida`)
- `--workers` — Conexões paralelas no download (default: `16`)
- `--cache` — Pasta do ZIP bweb (default: pasta temporária do sistema)
- `--somente-csv` — Pula a geração dos PDFs por urna e do relatório
- `--relatorio` — Gera o relatório HTML ao final
- `--pdf` — Gera também o PDF do relatório (implica `--relatorio`)
- `--abrir` — Abre o relatório no navegador ao final

---

## Saída (pasta `saida/`)

- `<cidade>_urnas_<turno>turno_<ano>.csv` — Todas as seções, ordenadas por
  prioridade de mobilização
- `boletins_<cidade>_<turno>turno_<ano>.zip` — Um PDF por urna (votos por
  candidato, aptos, abstenções, brancos, nulos)
- `relatorio_<cidade>_<turno>turno_<ano>.html` — Relatório HTML autocontido
  (abre em qualquer navegador)
- `relatorio_<cidade>_<turno>turno_<ano>.pdf` — Mesmo relatório em PDF
  (requer Playwright + Chromium)
- `boletins_<cidade>/` — Os PDFs individuais antes de compactar

Caches (não versionar):

- `/tmp/tse_bu_cache/bweb_*.zip` — ZIP da UF (centenas de MB)
- `/tmp/tse_bu_cache/locais_votacao_<ano>_<uf>.csv` — Coordenadas dos locais
  de votação

---

## Colunas do CSV

- `zona`, `secao` — Identificadores da seção eleitoral
- `local_votacao` — Código do local de votação (TSE)
- `aptos` — Eleitores aptos na seção
- `comparecimentos` — Quantos compareceram
- `abstencoes` — Quantos faltaram (número absoluto)
- `abstencao_pct` — `abstencoes / aptos × 100`
- `turnout_pct` — `comparecimentos / aptos × 100`
- `invalid_pct` — `(brancos + nulos) / comparecimentos × 100`
- `validos_por_apto` — `votos_validos / aptos × 100` — métrica "dura" de
  participação efetiva
- `votos_validos` — Votos válidos (exclui brancos e nulos)
- `brancos`, `nulos` — Votos em branco e nulo
- `cand_<nr>` — Votos do candidato, uma coluna por candidato
- `outros_candidatos` — Votos de candidatos que não são o 1 nem o 2
- `dif_votos` — `votos(cand1) − votos(cand2)`
- `dif_pct_validos` — `|dif_votos| / votos_validos × 100`
- `potencial_virada` — `abstencao_rate × (1 − dif_pp)` — matemático, vai de 0 a 1
- `prioridade_mobilizacao` — `abstencoes_absolutas × (1 − dif_pp)` — versão intuitiva
- `consistencia` — Booleano: `votos(cand1) + votos(cand2) ≤ votos_validos`

Interpretação:

- **`prioridade_mobilizacao` alto** → a seção tem muitos faltantes **e** a
  disputa é apertada. Prioridade máxima para o 2º turno.
- **`validos_por_apto` baixo** → muita gente faltou ou votou inválido. Sinal
  de desengajamento.
- **`invalid_pct` alto** → possível dificuldade de operação da urna, não
  necessariamente protesto.

---

## Dashboard interativo

```bash
streamlit run dashboard.py
```

O dashboard lê qualquer CSV de `saida/`. Você também pode apontar um arquivo
específico:

```bash
TSE_BU_CSV=saida/ouro_preto_urnas_1turno_2026.csv streamlit run dashboard.py
```

Configurações na barra lateral:

- **Ano da eleição** e **UF** — usados para buscar as coordenadas dos locais
  de votação. Use os mesmos valores que você passou em `main.py`.
- **Zonas** — filtra as zonas exibidas.
- **Mínimo de eleitores aptos** — esconde seções muito pequenas.
- **Candidato 1 / 2 (coluna)** — detectados automaticamente; ajustáveis.

Abas:

- **🎯 Onde mobilizar** — Dispersão abstenção × diferença entre candidatos.
  Bolhas maiores = mais abstenções absolutas. Responde "se eu só puder
  visitar 15 seções, quais?".
- **🗺️ Mapa geográfico** — Um ponto por seção (ou por local, alternável).
  Cor e tamanho controlados por dropdowns. Hover mostra todos os campos
  da linha.
- **🔥 Heatmap por seção** — Matriz zona × seção colorida pela abstenção.
  Útil quando não há coordenadas disponíveis.
- **📊 Comparação** — Distribuição de votos de cada candidato e dispersão
  entre eles.
- **📋 Tabela** — Todos os campos do CSV, ordenável, com botão de download.

O mapa usa tiles gratuitos (Carto, OpenStreetMap). Sem chave de API, sem
limites de uso. Estilos disponíveis: `carto-positron`, `carto-darkmatter`,
`open-street-map`, `carto-voyager`.

---

## Relatório HTML/PDF

```bash
python report.py --csv saida/ouro_preto_urnas_1turno_2026.csv \
                 --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
                 --pdf --abrir
```

Flags:

- `--csv` — CSV de entrada (**obrigatório**)
- `--uf`, `--cidade`, `--ano`, `--turno`, `--cargo` — Metadados de cabeçalho
- `--saida` — Nome do arquivo HTML (default: `saida/relatorio.html`)
- `--pdf` — Gera também o PDF via Chromium headless
- `--abrir` — Abre o HTML no navegador ao final
- `--sem-mapa` — Pula o mapa geográfico (útil quando não há coordenadas)
- `--top` — Quantas linhas exibir nas tabelas de topo (default: `20`)

O HTML é **autocontido** (Plotly embutido, CSS embutido, sem CDN): dá para
enviar por e-mail ou rodar de um pendrive. O PDF é gerado via Playwright.

---

## Estrutura do projeto

```
main.py            # CLI (argparse) — orquestra o pipeline
dashboard.py       # Dashboard Streamlit (5 abas)
report.py          # Gerador de relatório HTML/PDF
test_e2e.py        # Teste ponta-a-ponta
probe_locais.py    # Diagnóstico: descobre os datasets do TSE
tse_bu/
  __init__.py
  config.py        # Descobre a URL do bweb no portal CKAN do TSE
  downloader.py    # Download paralelo por ranges com retry
  bu_data.py       # Filtro em streaming do CSV bweb (cidade + cargo)
  analysis.py      # DataFrame, ranking, potencial de virada, resumo
  geodata.py       # Junta lat/long dos locais de votação
  pdfgen.py        # Geração e compactação dos PDFs por urna
requirements.txt
```

---

## Como funciona o geodata

O arquivo `bweb` **não traz latitude/longitude**. O TSE publica um dataset
separado — `Eleitorado por local de votação - <ano>` — com endereço e
coordenadas de cada local.

O módulo `tse_bu/geodata.py`:

1. Descobre o dataset via CKAN (`eleitorado-<ano>`).
2. Baixa o ZIP correspondente (que contém **um CSV por UF**).
3. Seleciona o CSV da UF correta (ex.: `eleitorado_local_votacao_2026_MG.csv`).
4. Filtra por UF e faz o join com o CSV de urnas por
   `(NR_ZONA, NR_LOCAL_VOTACAO)`.
5. Cacheia o resultado em `/tmp/tse_bu_cache/locais_votacao_<ano>_<uf>.csv`.

Se o dataset não existir ou o join falhar, o dashboard mostra uma mensagem
amigável e você pode usar a aba **🔥 Heatmap por seção**.

---

## Solução de problemas

**`Temporary failure in name resolution`** — Erro de DNS. Teste fora do
ambiente conda:

```bash
python -c "import socket; print(socket.gethostbyname('dadosabertos.tse.jus.br'))"
```

Se funcionar fora e falhar dentro do env, recrie o ambiente com Python 3.12.

**`Dataset 'resultados-<ano>-boletim-de-urna' não encontrado`** — O TSE ainda
não publicou os dados desse ano. Verifique
https://dadosabertos.tse.jus.br.

**`KeyError: 'cand_22'` em `resumo_cidade`** — O `main.py` está passando o
nome de exibição em vez do nome de coluna. Use
`analysis.resumo_cidade(df, col_c1, col_c2)` com `col_c1 = f"cand_{nr}"`.

**Dashboard mostra "Sem coordenadas disponíveis"** — Verifique na barra
lateral se **Ano** e **UF** batem com o CSV. Se persistir, o TSE pode não
ter publicado as coordenadas desse ano/UF — use a aba **🔥 Heatmap por seção**.

**Playwright reclama de Chromium ausente** — Rode `playwright install chromium`
uma vez.

**`AttributeError: module 'plotly.express' has no attribute 'scatter_mapbox'`**
— Plotly 6 removeu `scatter_mapbox`. Use `px.scatter_map` (o `dashboard.py`
atual já usa).

---

## Observações

- **Não é raspagem de HTML**: usa o arquivo oficial `bweb`, que contém os
  mesmos dados de cada Boletim de Urna (mais confiável e sem limite de
  requisições).
- O TSE só disponibiliza **imagem escaneada** do BU para urnas de contingência;
  para urnas normais não existe PDF oficial por urna — os PDFs gerados
  reproduzem a totalização oficial.
- `--cargo outro --cargo-codigo <n>` cobre qualquer cargo fora da tabela
  padrão (ex.: consultas populares).
- Funciona para qualquer ano/turno publicado no portal (2012, 2016, 2020,
  2022, 2024, 2026...), municipais ou gerais.
- O ZIP da UF é reutilizado entre execuções. Para forçar novo download,
  apague o arquivo em `/tmp/tse_bu_cache/`.

---

## Feito por

Davi e Kevin