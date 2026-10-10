# TSE BU Collector (Mobilize Votes)

Ferramenta de análise eleitoral que transforma os **Boletins de Urna oficiais
do TSE** (arquivo `bweb`) em decisões de campanha: *onde mobilizar, quantos
votos dá para buscar e quais seções visitar primeiro*.

Funciona para **qualquer município brasileiro**, qualquer cargo e qualquer
eleição publicada no portal de dados abertos do TSE (2012, 2016, 2020, 2022,
2024, 2026...), de vereador a presidente.

---

## O que é o Boletim de Urna (BU)?

O BU é o documento que cada urna eletrônica imprime ao fim da votação com a
totalização daquela seção: votos por candidato, brancos, nulos, aptos e
comparecimentos. O TSE publica esses dados em arquivo único por UF — o
`bweb` — no portal [dadosabertos.tse.jus.br](https://dadosabertos.tse.jus.br),
dataset `Resultados - <ano> - Boletim de Urna`.

Este projeto **não raspa HTML nem usa site de terceiros**: baixa o arquivo
oficial e filtra o seu município. Por isso os números batem com a
totalização do TSE.

## O que o projeto gera

| Produto | O que é | Comando |
|---|---|---|
| **CSV por seção** | Todas as urnas do município com ranking de prioridade para mobilização | `python main.py ...` |
| **Dashboard interativo** | Mapa, heatmaps e gráficos filtráveis no navegador | `streamlit run dashboard.py` |
| **Relatório HTML/PDF** | Síntese executiva autocontida para imprimir ou enviar | `python report.py ...` |
| **Guia tático de campanha** | Manual de instrução: "vá na seção X, ganhe ~N votos" | `python report_tatico.py ...` |
| **PDFs por urna** | Um boletim por seção (votos, aptos, abstenções) | gerado pelo `main.py` |

---

## Comece aqui (10 minutos)

### 1. Instalar

```bash
pip install -r requirements.txt
```

Python **3.11 ou 3.12** recomendado (evite 3.13+; algumas dependências ainda
não têm wheels estáveis). Espaço em disco: ~600 MB livres para o ZIP do
bweb + caches.

Só precisa do passo abaixo se for gerar **PDF** do relatório:

```bash
playwright install chromium   # ~150 MB, baixa o Chromium uma única vez
```

### 2. Rodar o pipeline completo

```bash
python main.py --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
    --cand1 22 --cand2 13 --relatorio --pdf --abrir
```

O que acontece, passo a passo:

1. **Localiza o dataset** — consulta a API CKAN do TSE e descobre a URL do
   `bweb` do ano/UF/turno pedidos.
2. **Baixa o ZIP da UF** — ~490 MB para MG, com download paralelo por ranges
   e retentativas. Na segunda execução, reutiliza o cache.
3. **Filtra o município** — varre o CSV em streaming e extrai só as seções da
   cidade e do cargo escolhidos.
4. **Analisa e exporta** — monta o DataFrame com métricas, salva o CSV,
   imprime o resumo e (se pedido) gera PDFs, relatório e abre no navegador.

### 3. Explorar no dashboard

```bash
streamlit run dashboard.py
```

---

## Exemplos para cada cenário

**Só o CSV** (bem mais rápido, sem PDFs):

```bash
python main.py --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
    --cand1 22 --cand2 13 --somente-csv
```

**Governador** — basta trocar `--cargo`:

```bash
python main.py --uf BA --cidade "SALVADOR" --ano 2026 --turno 1 \
    --cargo governador --cand1 13 --cand2 44
```

**Prefeito ou vereador** (eleições municipais):

```bash
python main.py --uf MG --cidade "OURO PRETO" --ano 2024 --turno 1 \
    --cargo prefeito --cand1 55 --cand2 13
```

**Cargo fora da tabela padrão** (ex.: consulta popular) — use
`--cargo outro --cargo-codigo <n>` com o código numérico do cargo no TSE.

**CSV enriquecido com perfil do eleitorado** (faixa etária, escolaridade por
seção — dataset `Perfil do eleitorado por seção eleitoral` do TSE):

```bash
python main.py --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
    --cand1 22 --cand2 13 --somente-csv --perfil
```

**CSV enriquecido com Censo 2022** (renda, tipo de setor e outras variáveis
do IBGE por local de votação, via [geocensobr](https://pypi.org/project/geocensobr/)):

```bash
python main.py --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
    --cand1 22 --cand2 13 --somente-csv --censo
```

> `--censo` implica baixar a malha de setores censitários do IBGE na primeira
> execução (arquivo grande, alguns minutos). Depois fica em cache.

**Relatório avulso** (sem rerodar o pipeline, a partir de um CSV existente):

```bash
python report.py --csv saida/ouro_preto_urnas_1turno_2026.csv \
    --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 --pdf --abrir
```

**Guia tático de campanha** (manual didático por seção — ver seção abaixo):

```bash
python report_tatico.py \
    --input saida/ouro_preto_urnas_1turno_2026.csv \
    --output guia_candidato_13.html --cand 13
```

---

## Flags do `main.py`

| Flag | Descrição | Default |
|---|---|---|
| `--uf` | UF de 2 letras (ex.: `MG`) — **obrigatório** | — |
| `--cidade` | Nome do município (ex.: `"OURO PRETO"`) — **obrigatório** | — |
| `--cand1` / `--cand2` | Números dos dois candidatos — **obrigatórios** | — |
| `--ano` | Ano da eleição | `2026` |
| `--turno` | `1` ou `2` | `1` |
| `--cargo` | `presidente`, `governador`, `senador`, `deputado-federal`, `deputado-estadual`, `deputado-distrital`, `prefeito`, `vereador`, `outro` | `presidente` |
| `--cargo-codigo` | Código numérico do cargo, quando `--cargo outro` | — |
| `--saida` | Pasta de saída | `saida` |
| `--workers` | Conexões paralelas no download | `16` |
| `--cache` | Pasta do ZIP bweb | pasta temporária do sistema |
| `--somente-csv` | Pula os PDFs por urna e o relatório | off |
| `--perfil` | Enriquece o CSV com o perfil do eleitorado do TSE | off |
| `--censo` | Enriquece o CSV com dados do Censo 2022 (IBGE) | off |
| `--relatorio` | Gera o relatório HTML ao final | off |
| `--pdf` | Gera também o PDF do relatório (implica `--relatorio`) | off |
| `--abrir` | Abre o relatório no navegador ao final | off |

---

## Saída (pasta `saida/`)

- `<cidade>_urnas_<turno>turno_<ano>.csv` — todas as seções, ordenadas por
  abstenção decrescente
- `boletins_<cidade>_<turno>turno_<ano>.zip` — um PDF por urna (votos por
  candidato, aptos, abstenções, brancos, nulos)
- `relatorio_<cidade>_<turno>turno_<ano>.html` / `.pdf` — relatório executivo
- `boletins_<cidade>/` — os PDFs individuais antes de compactar

Caches (não versionados; apague para forçar novo download):

- `/tmp/tse_bu_cache/bweb_*.zip` — ZIP da UF (centenas de MB)
- `/tmp/tse_bu_cache/locais_votacao_<ano>_<uf>.csv` — coordenadas dos locais
- `/tmp/tse_bu_cache/perfil_eleitorado_<ano>_<uf>_agg.csv` — perfil agregado

---

## Como ler os resultados (as métricas, uma a uma)

O coração do projeto é o **CSV por seção**. Cada linha é uma urna e cada
coluna responde uma pergunta:

**"Quantas pessoas votaram?"**

- `aptos` — eleitores registrados na seção
- `comparecimentos` — quantos compareceram
- `abstencoes` / `abstencao_pct` — quantos faltaram, absoluto e em %
- `turnout_pct` — comparecimento em %

**"Os votos são válidos?"**

- `brancos`, `nulos`, `invalid_pct` — votos inválidos e sua fatia. `invalid_pct`
  alto pode indicar dificuldade de operação da urna, não necessariamente protesto
- `votos_validos`, `validos_por_apto` — votos válidos e sua fatia sobre os
  aptos. `validos_por_apto` baixo = desengajamento real

**"Quem está ganhando lá?"**

- `cand_<nr>` — votos de cada candidato (uma coluna por candidato)
- `outros_candidatos` — votos dos demais candidatos
- `dif_votos` — `votos(cand1) − votos(cand2)` (negativo = cand2 lidera)
- `dif_pct_validos` — diferença em pontos percentuais dos válidos

**"Vale a pena mobilizar aqui?"**

- `potencial_virada` — `abstencao_rate × (1 − dif_pp)`, de 0 a 1. Quanto maior,
  mais abstenção **e** mais disputa apertada na seção
- `prioridade_mobilizacao` — `abstencoes_absolutas × (1 − dif_pp)`. Versão
  intuitiva: "muitos faltantes num lugar onde a briga está empatada"
- `consistencia` — checagem: `votos(cand1) + votos(cand2) ≤ votos_validos`

**Interpretação prática:**

- `prioridade_mobilizacao` alto → se você só puder visitar 15 seções, vá nestas.
- `validos_por_apto` baixo → muita gente faltou ou votou inválido; sinal de
  desengajamento que uma campanha de rua pode reverter.
- Diferença pequena + abstenção alta = cenário clássico de virada no 2º turno.

---

## Dashboard interativo

```bash
streamlit run dashboard.py          # lê o CSV mais recente de saida/
TSE_BU_CSV=saida/ouro_preto_urnas_1turno_2026.csv streamlit run dashboard.py
```

Configurações na barra lateral: **ano**, **UF** (usados para buscar as
coordenadas — devem bater com o que você passou ao `main.py`), **zonas**,
**mínimo de aptos** e as **colunas dos candidatos**.

Abas:

- **🎯 Onde mobilizar** — dispersão abstenção × diferença entre candidatos.
  Bolhas maiores = mais abstenções absolutas.
- **🗺️ Mapa geográfico** — um ponto por seção (ou por local). Cor e tamanho
  configuráveis; hover mostra todos os campos.
- **🔥 Heatmap por seção** — matriz zona × seção colorida pela abstenção.
  Útil quando não há coordenadas.
- **📊 Comparação** — distribuição de votos de cada candidato.
- **📋 Tabela** — todos os campos, ordenável, com botão de download.

O mapa usa tiles gratuitos (Carto, OpenStreetMap): sem chave de API e sem
limite de uso.

## Relatório HTML/PDF

```bash
python report.py --csv saida/ouro_preto_urnas_1turno_2026.csv \
    --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 --pdf --abrir
```

Flags: `--csv` (obrigatório), `--uf`, `--cidade`, `--ano`, `--turno`,
`--cargo`, `--saida`, `--top` (linhas nas tabelas de topo, default 20),
`--sem-mapa` (quando não há coordenadas), `--pdf`, `--abrir`.

O HTML é **autocontido** (Plotly e CSS embutidos, sem CDN): dá para enviar
por e-mail ou rodar de um pendrive. O PDF é gerado via Playwright/Chromium.

## Guia tático de campanha (`report_tatico.py`)

Não é um dashboard de dados — é um **manual de instrução tática**. Cada card
responde "onde ir, o que fazer lá e quantos votos se ganha", com estratégia
por perfil do eleitorado:

```bash
python report_tatico.py --input saida/ouro_preto_urnas_1turno_2026.csv \
    --output guia_candidato_13.html --cand 13 --top 15
```

Flags: `--input` (CSV; se omitido, usa o primeiro `saida/*_urnas_*.csv`; se
nenhum existir, gera uma **fixture de demonstração** de Ouro Preto marcada
como DADOS DEMO), `--output`, `--cand`, `--taxa`
(conversão estimada de faltantes em votos, default 30%), `--top` (nº de
seções no guia, default 15), `--sem-mapa`, `--cidade`, `--ano`, `--turno`.

O HTML é mobile-first e autocontido — pode ser enviado por WhatsApp ou impresso.

---

## Como funciona o geodata

O arquivo `bweb` **não traz latitude/longitude**. O TSE publica um dataset
separado — `Eleitorado por local de votação - <ano>` — com endereço e
coordenadas de cada local. O módulo `tse_bu/geodata.py`:

1. Descobre o dataset via CKAN (`eleitorado-<ano>`).
2. Baixa o ZIP (um CSV por UF) e seleciona o da UF correta.
3. Faz o join com o CSV de urnas por `(NR_ZONA, NR_LOCAL_VOTACAO)`.
4. Cacheia o resultado em `/tmp/tse_bu_cache/`.

Se o dataset não existir ou o join falhar, o dashboard avisa e você usa a aba
**🔥 Heatmap por seção**.

---

## Estrutura do projeto

```
main.py               # CLI (argparse) — orquestra o pipeline [1/4]..[4/4]
dashboard.py          # Dashboard Streamlit (5 abas)
report.py             # Relatório executivo HTML/PDF
report_tatico.py      # Guia tático de campanha (HTML mobile-first)
test_e2e.py           # Teste ponta-a-ponta (8 passos, do barato ao caro)
probe.py              # Diagnóstico: descobre datasets no portal CKAN do TSE
debug.py              # Diagnóstico: inspeciona as colunas dos dois lados do join
tse_bu/
  __init__.py
  config.py           # Descobre a URL do bweb no portal CKAN do TSE
  downloader.py       # Download paralelo por ranges com retry
  bu_data.py          # Filtro em streaming do CSV bweb (cidade + cargo)
  analysis.py         # DataFrame, ranking, potencial de virada, resumo
  geodata.py          # Junta lat/long dos locais de votação
  perfil_eleitorado.py# Agrega o perfil do eleitorado por seção (TSE)
  censo.py            # Enriquece com variáveis do Censo 2022 (geocensobr)
  pdfgen.py           # Geração e compactação dos PDFs por urna
requirements.txt
```

---

## Testar

```bash
python test_e2e.py                    # defaults: MG / OURO PRETO / 2026 / 1T / 22 x 13
python test_e2e.py --skip-download    # usa o ZIP já em cache
python test_e2e.py --only 1,2,3       # só os passos de rede leve
python test_e2e.py --skip-geo --skip-pdf
```

O teste roda as camadas em ordem, do mais barato ao mais caro: imports →
descoberta do dataset → download (HEAD only) → extração do município →
análise → geodata → PDFs → import do dashboard.

---

## Solução de problemas

**`Temporary failure in name resolution`** — erro de DNS. Teste:

```bash
python -c "import socket; print(socket.gethostbyname('dadosabertos.tse.jus.br'))"
```

Se funcionar fora do seu ambiente conda/venv e falhar dentro, recrie o
ambiente com Python 3.12.

**`Dataset 'resultados-<ano>-boletim-de-urna' não encontrado`** — o TSE ainda
não publicou os dados desse ano. Verifique
https://dadosabertos.tse.jus.br.

**Download lento ou interrompido** — o ZIP da UF é grande (~490 MB em MG).
Aumente `--workers` se sua rede aguentar; o download tem retentativas e
retoma de onde parou na pasta de cache.

**Dashboard mostra "Sem coordenadas disponíveis"** — confira na barra lateral
se **Ano** e **UF** batem com o CSV. Se persistir, o TSE pode não ter
publicado as coordenadas desse ano/UF — use a aba **🔥 Heatmap por seção**.

**Playwright reclama de Chromium ausente** — rode `playwright install chromium`
uma vez.

**`AttributeError: module 'plotly.express' has no attribute 'scatter_mapbox'`**
— Plotly 6 removeu `scatter_mapbox`; o código usa `px.scatter_map`, que é o
correto. Atualize o plotly.

**`[censo] geocensobr não instalado`** — rode `pip install geocensobr` (já
consta no `requirements.txt`).

---

## Observações

- O TSE só disponibiliza **imagem escaneada** do BU para urnas de contingência;
  para urnas normais não existe PDF oficial por urna — os PDFs gerados
  reproduzem a totalização oficial do bweb.
- Funciona para qualquer ano/turno publicado no portal, municipais ou gerais.
- O ZIP da UF é reutilizado entre execuções; para forçar novo download, apague
  o arquivo em `/tmp/tse_bu_cache/`.
- Arquivos de centenas de MB podem falhar em mounts de rede — por isso o
  cache default é a pasta temporária local do sistema.

---

## Feito por

Davi e Kevin
