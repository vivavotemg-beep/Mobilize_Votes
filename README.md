# TSE BU Collector

Coleta os **Boletins de Urna (arquivo `bweb`) do TSE** para qualquer município
brasileiro, gera um PDF de boletim por urna, um CSV consolidado por seção com
ranking de abstenção e um indicador de **potencial de virada** para o 2º turno.

Fonte oficial: portal de dados abertos do TSE
(https://dadosabertos.tse.jus.br), dataset `Resultados - <ano> - Boletim de Urna`.
O arquivo é baixado por inteiro da UF (ex.: ~490 MB para MG) com download
paralelo por ranges e retentativas; na segunda execução ele é reutilizado
do cache local (`--cache`, default: pasta temporária do sistema — arquivos
de centenas de MB podem falhar em mounts de rede).

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
# Ouro Preto - Presidente 2026, 1º turno, virada Bolsonaro(22) x Lula(13)
python main.py --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
    --cand1 22 --cand2 13

# Governador: basta trocar --cargo
python main.py --uf BA --cidade "SALVADOR" --ano 2026 --turno 1 \
    --cargo governador --cand1 13 --cand2 44

# Só o CSV, sem gerar os  PDFs (bem mais rápido)
python main.py --uf MG --cidade "OURO PRETO" --cand1 22 --cand2 13 --somente-csv
```

## Saída (pasta `saida/`)

| Arquivo | Conteúdo |
|---|---|
| `boletins_<cidade>_<turno>turno_<ano>.zip` | Um PDF por urna (votos por candidato, aptos, abstenções, brancos, nulos) |
| `<cidade>_urnas_<turno>turno_<ano>.csv` | Todas as seções, ordenadas por abstenção |
| `_cache/` | ZIP bweb da UF (reutilizado entre execuções) |

## Dashboard interativo

```bash
pip install -r requirements.txt   # inclui streamlit e plotly
streamlit run dashboard.py

### Colunas do CSV

- `abstencao_pct` — percentual de abstentes na seção
- `potencial_virada` — `taxa_abstencao × (1 − |dif% válitos entre cand1 e cand2|)`
- `dif_pct_validos` — diferença percentual entre os dois candidatos nos votos válidos

Quanto maior o `potencial_virada`, mais a seção combina **muitos abstentes**
com **disputa empatada** — prioridade máxima de mobilização até o 2º turno.

## Estrutura

```
main.py            # CLI (argparse) — orquestra o pipeline
tse_bu/
  config.py        # Descobre a URL do bweb no portal CKAN do TSE
  downloader.py    # Download paralelo por ranges com retry
  bu_data.py       # Filtro em streaming do CSV (cidade + cargo)
  analysis.py      # DataFrame, ranking, potencial de virada, resumo
  pdfgen.py        # Geração e compactação dos PDFs por urna
```

## Observações

- **Não é raspagem de HTML**: usa o arquivo oficial `bweb`, que contém os
  mesmos dados de cada Boletim de Urna (mais confiável e sem limite de
  requisições).
- O TSE só disponibiliza **imagem escaneada** do BU para urnas de contingência;
  para urnas normais não existe PDF oficial por urna — os PDFs gerados
  reproduzem a totalização oficial.
- `--cargo outro --cargo-codigo <n>` cobre qualquer cargo fora da tabela
  padrão (ex.: consultas populares).
- Funciona para qualquer ano/turno publicado no portal (2024, 2026...),
  municipais ou gerais.

## Done BY
```
Davi and Kevin
```