#!/usr/bin/env python3
"""Gera um relatório HTML autocontido a partir do CSV de urnas.

Uso:
    python report.py --csv saida/ouro_preto_urnas_1turno_2026.csv \
                     --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
                     --saida saida/relatorio_ouro_preto.html

Opções:
    --csv        caminho do CSV gerado por main.py (obrigatório)
    --uf         UF (default: MG)
    --cidade     nome do município (default: inferido do CSV)
    --ano        ano da eleição (default: 2026)
    --turno      turno (default: 1)
    --cargo      cargo (default: presidente)
    --saida      arquivo HTML de saída (default: saida/relatorio.html)
    --sem-mapa   pula o mapa geográfico (útil se não houver coordenadas)
    --top        quantas linhas nas tabelas de topo (default: 20)
"""

import argparse
import base64
import datetime as dt
import os
import re

import pandas as pd
import plotly.express as px
import plotly.io as pio


def _cidade_do_nome_csv(path: str) -> str:
    """Extrai o nome do município do nome do CSV.

    'saida/ouro_preto_urnas_1turno_2026.csv' -> 'Ouro Preto'
    (preserva nomes compostos; aceita o sufixo '_urnas' ou '_secoes').
    """
    base = os.path.basename(path)
    m = re.match(r"^(.*?)_(?:urnas|secoes)(?:_|\.|$)", base, re.IGNORECASE)
    slug = m.group(1) if m else base.split("_")[0]
    return slug.replace("_", " ").replace("-", " ").title()


# ---------------------------------------------------------------- helpers
def _kpi_row(label, value, hint=""):
    return f"""
    <div class="kpi">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-hint">{hint}</div>
    </div>
    """


def _fig_html(fig, first=False):
    """Serializa uma figura Plotly para HTML inline.

    A primeira figura carrega o plotly.js completo; as demais reutilizam.
    """
    return pio.to_html(
        fig,
        include_plotlyjs="inline" if first else False,
        full_html=False,
        config={"displayModeBar": False, "responsive": True},
    )

def build_censo(df: pd.DataFrame) -> str:
    """Seção do Censo 2022, se as colunas existirem."""
    cols = [c for c in df.columns if c.startswith("censo_")]
    tem_dados = ("censo_total_pessoas" in df.columns
                 and df["censo_total_pessoas"].notna().any())
    if not cols or not tem_dados:
        return (
            "<section><h3>Censo 2022</h3>"
            "<p>Sem dados do Censo para esta seleção. O `geocensobr` "
            "não conseguiu consultar os setores censitários — verifique "
            "o terminal do `main.py`.</p></section>"
        )

    total_p = int(df["censo_total_pessoas"].sum(skipna=True))
    total_d = int(df["censo_total_domicilios"].sum(skipna=True))
    media = df["censo_media_moradores"].mean(skipna=True)

    html = ["<section>", "<h3>Censo 2022 — contexto socioeconômico</h3>",
            "<p class='desc'>Dados do IBGE por setor censitário, cruzados "
            "com os locais de votação.</p>",
            "<div class='kpis'>"]
    html.append(_kpi_row("Pessoas nos setores", f"{total_p:,}"))
    html.append(_kpi_row("Domicílios", f"{total_d:,}"))
    if pd.notna(media):
        html.append(_kpi_row("Média moradores/domicílio", f"{media:.2f}"))
    html.append("</div>")

    if "censo_tipo_setor_desc" in df.columns:
        tipos = (df.groupby("censo_tipo_setor_desc", as_index=False)
                   .agg(secoes=("secao", "count")))
        fig = px.bar(tipos, x="secoes", y="censo_tipo_setor_desc",
                     orientation="h",
                     labels={"secoes": "Nº de seções",
                             "censo_tipo_setor_desc": ""},
                     height=300,
                     title="Distribuição por tipo de setor censitário")
        html.append(_fig_html(fig))

    if "censo_total_pessoas" in df.columns and "abstencao_pct" in df.columns:
        sub = df.dropna(subset=["censo_total_pessoas"])
        if not sub.empty:
            fig = px.scatter(
                sub, x="censo_total_pessoas", y="abstencao_pct",
                size="aptos", color="prioridade_mobilizacao",
                hover_data=["zona", "secao", "local_votacao",
                            "censo_bairro", "censo_municipio"],
                color_continuous_scale="Reds",
                labels={"censo_total_pessoas": "População do setor",
                        "abstencao_pct": "Abstenção (%)",
                        "prioridade_mobilizacao": "Prioridade"},
                height=400,
                title="Abstenção × população do setor censitário",
            )
            html.append(_fig_html(fig))

    html.append("</section>")
    return "\n".join(html)

def _read_csv(path):
    df = pd.read_csv(path)
    for c in ["zona", "secao", "aptos", "comparecimentos", "abstencoes",
              "abstencao_pct", "turnout_pct", "invalid_pct",
              "validos_por_apto", "votos_validos", "brancos", "nulos",
              "dif_votos", "dif_pct_validos", "potencial_virada",
              "prioridade_mobilizacao"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _detect_candidates(df):
    cands = [c for c in df.columns if c.startswith("cand_")]
    if len(cands) >= 2:
        return cands[:2]
    nums = [c for c in df.columns if c.isdigit()]
    if len(nums) >= 2:
        return nums[:2]
    if "outros_candidatos" in df.columns:
        i = list(df.columns).index("outros_candidatos")
        return [df.columns[i - 2], df.columns[i - 1]]
    return None


# ---------------------------------------------------------------- sections
def build_cover(cidade, uf, ano, turno, cargo):
    now = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""
    <header class="cover">
      <h1>Relatório de Boletins de Urna</h1>
      <h2>{cidade} — {uf.upper()}</h2>
      <p class="meta">
        Eleição {ano} · {turno}º turno · cargo: {cargo}
      </p>
      <p class="meta small">Gerado em {now} · fonte: dados abertos do TSE (bweb)</p>
    </header>
    """


def build_kpis(df, c1, c2, nome_c1, nome_c2):
    aptos = int(df["aptos"].sum())
    comp = int(df["comparecimentos"].sum())
    abst = int(df["abstencoes"].sum())
    validos = int(df["votos_validos"].sum())
    brancos = int(df["brancos"].sum())
    nulos = int(df["nulos"].sum())
    v1 = int(df[c1].sum())
    v2 = int(df[c2].sum())
    turnout = comp / aptos * 100 if aptos else 0
    invalid = (brancos + nulos) / comp * 100 if comp else 0
    vpa = validos / aptos * 100 if aptos else 0
    diff = abs(v1 - v2)

    html = '<section class="kpis">'
    html += _kpi_row("Seções analisadas", f"{len(df):,}")
    html += _kpi_row("Eleitores aptos", f"{aptos:,}")
    html += _kpi_row("Comparecimento", f"{comp:,}", f"{turnout:.1f}% dos aptos")
    html += _kpi_row("Abstenções", f"{abst:,}", f"{100 - turnout:.1f}% dos aptos")
    html += _kpi_row("Votos inválidos", f"{brancos + nulos:,}", f"{invalid:.1f}% dos comparecimentos")
    html += _kpi_row("Votos válidos / apto", f"{vpa:.1f}%", "participação efetiva")
    html += _kpi_row(nome_c1, f"{v1:,}", f"{v1 / validos * 100:.1f}% dos válidos" if validos else "")
    html += _kpi_row(nome_c2, f"{v2:,}", f"{v2 / validos * 100:.1f}% dos válidos" if validos else "")
    html += _kpi_row("Diferença", f"{diff:,}", f"{(nome_c1 if v1 > v2 else nome_c2)} na frente")
    html += "</section>"
    return html


def build_table(df, cols, titulo, descricao, n):
    sub = df.head(n).copy()
    for c in ["abstencao_pct", "turnout_pct", "invalid_pct", "dif_pct_validos"]:
        if c in sub.columns:
            sub[c] = sub[c].map(lambda v: f"{v:.2f}" if pd.notna(v) else "")
    if "prioridade_mobilizacao" in sub.columns:
        sub["prioridade_mobilizacao"] = sub["prioridade_mobilizacao"].map(
            lambda v: f"{v:.2f}" if pd.notna(v) else "")
    if "potencial_virada" in sub.columns:
        sub["potencial_virada"] = sub["potencial_virada"].map(
            lambda v: f"{v:.4f}" if pd.notna(v) else "")

    headers = "".join(f"<th>{c}</th>" for c in sub.columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>"
        for row in sub.itertuples(index=False)
    )
    return f"""
    <section>
      <h3>{titulo}</h3>
      <p class="desc">{descricao}</p>
      <table>
        <thead><tr>{headers}</tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


def build_map(df, uf, ano, cidade):
    """Mapa das seções. Se o CSV já tem LATITUDE/LONGITUDE (o main.py
    --censo grava), não faz join de novo — só usa o que está lá."""
    # Se o CSV já tem coordenadas preenchidas, usa direto
    if ("LATITUDE" in df.columns and "LONGITUDE" in df.columns
            and df["LATITUDE"].notna().any()):
        df_geo = df.copy()
    else:
        try:
            from tse_bu import geodata
        except ImportError:
            return ("<section><h3>Mapa</h3><p>Módulo geodata não disponível."
                    "</p></section>")
        try:
            df_geo = geodata.juntar_coordenadas(df.copy(), ano, uf,
                                                municipio=cidade)
        except Exception as exc:
            return (f"<section><h3>Mapa</h3><p>Não foi possível obter "
                    f"coordenadas: {exc}</p></section>")

    if "LATITUDE" not in df_geo.columns or df_geo["LATITUDE"].isna().all():
        return ("<section><h3>Mapa</h3><p>Sem coordenadas disponíveis para "
                "este ano/UF. Veja o heatmap por seção abaixo.</p></section>")

    base = df_geo.dropna(subset=["LATITUDE", "LONGITUDE"]).copy()
    if base.empty:
        return "<section><h3>Mapa</h3><p>Nenhuma seção com coordenadas.</p></section>"

    fig = px.scatter_map(
        base,
        lat="LATITUDE", lon="LONGITUDE",
        size="abstencoes", color="abstencao_pct",
        hover_name="local_votacao",
        hover_data={"zona": True, "secao": True, "aptos": True,
                    "abstencoes": True, "abstencao_pct": ":.2f",
                    "LATITUDE": False, "LONGITUDE": False},
        color_continuous_scale="OrRd",
        size_max=30, zoom=11, height=600,
        labels={"abstencao_pct": "Abstenção (%)"},
        title=f"Abstenção por seção — {cidade} ({len(base)} pontos)",
    )
    fig.update_layout(
        map=dict(
            style="carto-positron",
            # Centro dinâmico: o município processado, nunca hardcoded.
            center=dict(lat=float(base["LATITUDE"].mean()),
                        lon=float(base["LONGITUDE"].mean())),
            zoom=11,
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        height=600,
        width=None,   # deixa o Plotly calcular a partir do container
        coloraxis_colorbar=dict(title="Abstenção (%)"),
    )
    return f"<section>{_fig_html(fig)}</section>"


def build_heatmap(df):
    pivot = df.pivot_table(index="zona", columns="secao",
                           values="abstencao_pct", aggfunc="mean")
    if pivot.empty:
        return "<section><h3>Heatmap por seção</h3><p>Sem dados.</p></section>"
    fig = px.imshow(
        pivot, aspect="auto", color_continuous_scale="OrRd",
        labels=dict(x="Seção", y="Zona", color="Abstenção (%)"),
        title="Abstenção média por zona × seção",
        height=min(900, 80 + 18 * len(pivot)),
    )
    return f"<section>{_fig_html(fig)}</section>"

def gerar_pdf(html_path: str, pdf_path: str) -> None:
    """Converte o HTML em PDF usando Chromium headless (Playwright)."""
    from playwright.sync_api import sync_playwright

    abs_html = os.path.abspath(html_path)
    url = "file://" + abs_html

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url, wait_until="networkidle", timeout=60_000)
        # Espera o Plotly terminar de renderizar (mapa, hover, etc.)
        page.wait_for_timeout(2500)
        page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={"top": "12mm", "bottom": "12mm",
                    "left": "10mm", "right": "10mm"},
        )
        browser.close()

def build_scatter(df, nome_c1, nome_c2):
    fig = px.scatter(
        df, x="abstencao_pct", y="dif_pct_validos",
        size="abstencoes", color="prioridade_mobilizacao",
        hover_data=["zona", "secao", "local_votacao", "aptos", "abstencoes"],
        color_continuous_scale="Reds",
        labels={"abstencao_pct": "Abstenção (%)",
                "dif_pct_validos": f"Diferença {nome_c1} vs {nome_c2} (%)",
                "prioridade_mobilizacao": "Prioridade"},
        title="Prioridade de mobilização — abstenção × disputa",
        height=550,
    )
    return f"<section>{_fig_html(fig)}</section>"

def build_perfil(df: pd.DataFrame) -> str:
    """Seção de perfil do eleitorado, se as colunas existirem."""
    cols = [c for c in df.columns if c.startswith("perfil_")]
    if not cols:
        return (
            "<section><h3>Perfil do eleitorado</h3>"
            "<p>CSV sem colunas de perfil. Rode <code>main.py --perfil</code> "
            "para gerar.</p></section>"
        )

    total = int(df["perfil_total"].sum())

    def _pct(col: str) -> float:
        if col not in df.columns or total == 0:
            return 0.0
        return df[col].sum() / total * 100

    # Cabeçalho com KPIs
    html = ["<section>", "<h3>Perfil do eleitorado (TSE)</h3>",
            "<p class='desc'>Composição demográfica das seções analisadas, "
            "segundo o Perfil do Eleitorado por Seção Eleitoral do TSE.</p>",
            "<div class='kpis'>"]
    html.append(_kpi_row("Total de eleitores", f"{total:,}"))
    html.append(_kpi_row("Mulheres", f"{_pct('perfil_genero_feminino'):.1f}%"))
    html.append(_kpi_row("Jovens 16–24", f"{_pct('perfil_jovens_16_24'):.1f}%"))
    html.append(_kpi_row("Idosos 60+", f"{_pct('perfil_idosos_60_mais'):.1f}%"))
    html.append(_kpi_row("PCD", f"{_pct('perfil_pcd'):.1f}%"))
    html.append("</div>")

    # Distribuição por faixa etária
    cols_idade = [c for c in df.columns
                  if c.startswith("perfil_idade_") and c.endswith("_pct")]
    if cols_idade:
        agregado = df[cols_idade].multiply(df["perfil_total"], axis=0).sum()
        if agregado.sum() > 0:
            resumo = (agregado / agregado.sum() * 100).reset_index()
            resumo.columns = ["faixa", "pct"]
            resumo["faixa"] = (resumo["faixa"]
                               .str.replace("perfil_idade_", "", regex=False)
                               .str.replace("_pct", "", regex=False))
            fig = px.bar(resumo, x="faixa", y="pct",
                         labels={"faixa": "Faixa etária",
                                 "pct": "% do eleitorado"},
                         height=350,
                         title="Distribuição por faixa etária")
            html.append(_fig_html(fig))

    # Grau de instrução
    cols_ins = [c for c in df.columns
                if c.startswith("perfil_instrucao_") and c.endswith("_pct")]
    if cols_ins:
        agregado = df[cols_ins].multiply(df["perfil_total"], axis=0).sum()
        if agregado.sum() > 0:
            resumo = (agregado / agregado.sum() * 100).reset_index()
            resumo.columns = ["grau", "pct"]
            resumo["grau"] = (resumo["grau"]
                              .str.replace("perfil_instrucao_", "", regex=False)
                              .str.replace("_pct", "", regex=False))
            resumo = resumo.sort_values("pct")
            fig = px.bar(resumo, x="pct", y="grau", orientation="h",
                         labels={"pct": "% do eleitorado", "grau": ""},
                         height=350,
                         title="Grau de instrução")
            html.append(_fig_html(fig))

    # Gênero
    cols_gen = [c for c in df.columns
                if c.startswith("perfil_genero_") and c.endswith("_pct")]
    if cols_gen:
        agregado = df[cols_gen].multiply(df["perfil_total"], axis=0).sum()
        if agregado.sum() > 0:
            resumo = (agregado / agregado.sum() * 100).reset_index()
            resumo.columns = ["genero", "pct"]
            resumo["genero"] = (resumo["genero"]
                                .str.replace("perfil_genero_", "", regex=False)
                                .str.replace("_pct", "", regex=False))
            fig = px.pie(resumo, names="genero", values="pct",
                         height=350, hole=0.4,
                         title="Distribuição por gênero")
            html.append(_fig_html(fig))

    html.append("</section>")
    return "\n".join(html)


def build_footer():
    return """
    <section class="metodologia">
      <h3>Metodologia</h3>
      <ul>
        <li><b>Abstenção (%)</b> = abstenções ÷ eleitores aptos.</li>
        <li><b>Comparecimento (%)</b> = comparecimentos ÷ aptos.</li>
        <li><b>Inválidos (%)</b> = (brancos + nulos) ÷ comparecimentos.</li>
        <li><b>Válidos / apto</b> = votos válidos ÷ aptos — medida "dura" de participação efetiva.</li>
        <li><b>Diferença (%)</b> = |votos cand1 − votos cand2| ÷ votos válidos.</li>
        <li><b>Potencial de virada</b> = taxa de abstenção × (1 − diferença). Vai de 0 a 1.</li>
        <li><b>Prioridade de mobilização</b> = abstenções absolutas × (1 − diferença). É a versão "quantos votos estão na mesa".</li>
      </ul>
      <p>
        Fonte: dados abertos do TSE — arquivo <code>bweb</code> (boletim de urna)
        e dataset de locais de votação. Nenhum dado foi inferido ou interpolado.
      </p>
    </section>
    """


# ---------------------------------------------------------------- CSS
CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
       Helvetica, Arial, sans-serif; max-width: 1200px; margin: 24px auto;
       padding: 0 20px; color: #1a1a1a; line-height: 1.45; }
.cover { border-bottom: 3px solid #b8001f; padding-bottom: 16px; margin-bottom: 24px; }
.cover h1 { margin: 0; font-size: 28px; }
.cover h2 { margin: 4px 0 8px; font-size: 20px; font-weight: 500; color: #555; }
.meta { margin: 4px 0; color: #444; }
.meta.small { font-size: 12px; color: #777; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
         gap: 12px; margin: 20px 0 32px; }
.kpi { border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px 14px;
       background: #fafafa; }
.kpi-label { font-size: 12px; color: #666; text-transform: uppercase;
             letter-spacing: 0.5px; }
.kpi-value { font-size: 22px; font-weight: 600; margin: 4px 0; }
.kpi-hint { font-size: 12px; color: #888; }
section { margin-bottom: 40px; }
section h3 { margin-bottom: 6px; font-size: 18px; }
section .desc { color: #555; font-size: 14px; margin: 0 0 12px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { background: #f0f0f0; font-weight: 600; }
tbody tr:nth-child(even) { background: #fafafa; }
.metodologia { font-size: 13px; color: #333; background: #f8f8f8;
               border-left: 4px solid #b8001f; padding: 14px 18px;
               border-radius: 4px; }
.metodologia ul { margin: 6px 0; padding-left: 20px; }
.metodologia li { margin-bottom: 3px; }
code { background: #eee; padding: 1px 5px; border-radius: 3px;
       font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
@media print {
  body { max-width: none; margin: 0; }
  section { page-break-inside: avoid; }
}
"""


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="Gera relatório HTML autocontido.")
    p.add_argument("--csv", required=True)
    p.add_argument("--uf", default="MG")
    p.add_argument("--cidade", default=None)
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--turno", type=int, default=1)
    p.add_argument("--cargo", default="presidente")
    p.add_argument("--saida", default=None)
    p.add_argument("--sem-mapa", action="store_true")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--pdf", action="store_true",help="Gera também um PDF do relatório via Chromium headless.")
    p.add_argument("--abrir", action="store_true",help="Abre o HTML no navegador padrão após gerar.")
    args = p.parse_args()

    df = _read_csv(args.csv)
    if df.empty:
        raise SystemExit("CSV vazio.")

    cands = _detect_candidates(df)
    if not cands:
        raise SystemExit("Não consegui identificar as colunas de candidatos.")
    c1, c2 = cands

    cidade = args.cidade or _cidade_do_nome_csv(args.csv)
    nome_c1, nome_c2 = c1.replace("cand_", "Candidato "), c2.replace("cand_", "Candidato ")

    saida = args.saida or os.path.join(os.path.dirname(args.csv), "relatorio.html")

    print("[1/6] Capa e KPIs...")
    html = ["<!DOCTYPE html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">",
            f"<title>Relatório — {cidade} {args.ano}</title>",
            f"<style>{CSS}</style></head><body>"]
        # Embute o plotly.js uma vez, para que todos os gráficos do relatório
    # possam renderizar (o HTML é autocontido, sem CDN).
    from plotly.offline import get_plotlyjs
    html.append(f"<script>{get_plotlyjs()}</script>")
    html.append(build_cover(cidade, args.uf, args.ano, args.turno, args.cargo))
    html.append(build_kpis(df, c1, c2, nome_c1, nome_c2))

    print("[2/6] Tabela — prioridade de mobilização...")
    top_prio = df.sort_values("prioridade_mobilizacao", ascending=False)
    cols_prio = ["zona", "secao", "local_votacao", "aptos", "abstencoes",
                 "abstencao_pct", c1, c2, "dif_pct_validos",
                 "prioridade_mobilizacao"]
    cols_prio = [c for c in cols_prio if c in top_prio.columns]
    html.append(build_table(
        top_prio[cols_prio], cols_prio,
        f"Top {args.top} seções por prioridade de mobilização",
        "Combina abstenções absolutas com o quão disputada a seção está. "
        "Quanto maior, mais valioso investir aqui.",
        args.top,
    ))

    print("[3/6] Tabela — abstenção absoluta...")
    top_abst = df.sort_values("abstencoes", ascending=False)
    cols_abst = ["zona", "secao", "local_votacao", "aptos", "abstencoes",
                 "abstencao_pct", "turnout_pct", c1, c2]
    cols_abst = [c for c in cols_abst if c in top_abst.columns]
    html.append(build_table(
        top_abst[cols_abst], cols_abst,
        f"Top {args.top} seções por abstenção absoluta",
        "Onde há mais votos ausentes em números absolutos.",
        args.top,
    ))

    print("[4/6] Mapa geográfico...")
    if not args.sem_mapa:
        html.append(build_map(df, args.uf, args.ano, cidade))
    else:
        html.append("<section><h3>Mapa</h3><p>Omitido a pedido (--sem-mapa).</p></section>")

    print("[5/6] Heatmap e dispersão...")
    html.append(build_heatmap(df))
    html.append(build_scatter(df, nome_c1, nome_c2))

        # ---- NOVO: perfil do eleitorado (se o CSV tiver as colunas) ----
    if any(c.startswith("perfil_") for c in df.columns):
        print("[5b/6] Perfil do eleitorado...")
        html.append(build_perfil(df))

    # ---- NOVO: Censo 2022 (se o CSV tiver as colunas) ----
    if any(c.startswith("censo_") for c in df.columns):
        print("[5c/6] Censo 2022...")
        html.append(build_censo(df))

    print("[6/6] Rodapé...")
    html.append(build_footer())

    # Corrige a renderização do mapa: o MapLibre do Plotly inicializa antes
    # do navegador medir o container, então o mapa só aparece após um resize.
    # Este script força um resize em dois momentos (load e depois de um
    # pequeno delay) para garantir que o mapa enquadre corretamente.
    html.append("""
<script>
(function () {
  function refreshPlotly() {
    var divs = document.querySelectorAll('.plotly-graph-div');
    divs.forEach(function (d) {
      if (window.Plotly && window.Plotly.Plots) {
        try { window.Plotly.Plots.resize(d); } catch (e) {}
      }
    });
    window.dispatchEvent(new Event('resize'));
  }
  window.addEventListener('load', function () {
    setTimeout(refreshPlotly, 200);
    setTimeout(refreshPlotly, 800);
  });
  // Também dispara ao redimensionar a janela (útil para Ctrl+P → PDF)
  window.addEventListener('beforeprint', refreshPlotly);
})();
</script>
""")
    html.append("</body></html>")

    os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        f.write("\n".join(html))
    print(f"\n[ok] Relatório salvo em: {saida}")
    print(f"     Abra no navegador e use Ctrl+P para salvar como PDF.")

    if args.pdf:
        pdf_path = os.path.splitext(saida)[0] + ".pdf"
        print("[pdf] gerando PDF via Chromium...")
        try:
            gerar_pdf(saida, pdf_path)
            print(f"[ok] PDF: {pdf_path}")
        except Exception as exc:
            print(f"[aviso] PDF não gerado: {exc}")

    if args.abrir:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(saida))

if __name__ == "__main__":
    main()