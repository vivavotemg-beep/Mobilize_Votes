#!/usr/bin/env python3
"""Dashboard interativo para os dados de Boletim de Urna (bweb).

Uso:
    streamlit run dashboard.py

Ele lê um CSV gerado por main.py (pasta saida/). Selecione o arquivo na
barra lateral ou passe via variável de ambiente TSE_BU_CSV.

Abas:
  1. Onde mobilizar      -> dispersão abstenção × diferença entre candidatos
  2. Mapa geográfico     -> pontos georreferenciados (precisa do dataset TSE
                            "locais de votação")
  3. Heatmap por seção   -> matriz zona × seção (sem geografia)
  4. Comparação          -> distribuição e dispersão dos candidatos
  5. Tabela              -> todos os campos, ordenável, download
"""

import os
import glob
import sys
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="TSE BU — Painel", layout="wide")


# ---------------------------------------------------------------- helpers
@st.cache_data(show_spinner=False)
def carregar_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in ["zona", "secao", "aptos", "comparecimentos", "abstencoes",
              "abstencao_pct", "turnout_pct", "invalid_pct", "validos_por_apto",
              "votos_validos", "brancos", "nulos", "dif_votos",
              "dif_pct_validos", "potencial_virada", "prioridade_mobilizacao"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def carregar_geodata(csv_path: str, ano: int, uf: str,
                     municipio: str = "") -> pd.DataFrame:
    """Adiciona coordenadas ao CSV, se ainda não estiverem presentes.

    O `main.py --censo` já grava LATITUDE e LONGITUDE no CSV (porque
    o geodata roda antes do censo). Nesse caso não precisa juntar de
    novo — só devolve o CSV como está.
    """
    df = carregar_csv(csv_path)

    # Se o CSV já tem coordenadas preenchidas, nada a fazer
    if ("LATITUDE" in df.columns and "LONGITUDE" in df.columns
            and df["LATITUDE"].notna().any()):
        print("[geodata] CSV já tem LATITUDE/LONGITUDE; join ignorado",
              file=sys.stderr)
        return df

    # Caso contrário, faz o join como antes
    try:
        from tse_bu import geodata
        return geodata.juntar_coordenadas(df, ano, uf, municipio=municipio)
    except Exception as exc:
        df = df.copy()
        df["LATITUDE"] = None
        df["LONGITUDE"] = None
        st.warning(f"Não foi possível obter coordenadas: {exc}")
        return df


def encontrar_csvs() -> list:
    if os.environ.get("TSE_BU_CSV"):
        return [os.environ["TSE_BU_CSV"]]
    return sorted(glob.glob("saida/*.csv"))


def municipio_do_csv(csv_path: str) -> str:
    """Extrai o nome do município do nome do arquivo.

    O main.py salva como '<slug>_urnas_<turno>turno_<ano>.csv',
    então o slug é tudo antes de '_urnas'.
    """
    base = os.path.basename(csv_path)
    return base.split("_urnas")[0].replace("_", " ").upper()


def detectar_candidatos(df: pd.DataFrame) -> list:
    """Descobre as duas colunas de candidatos no CSV."""
    cand_prefix = [c for c in df.columns if c.startswith("cand_")]
    if len(cand_prefix) >= 2:
        return cand_prefix[:2]

    numericas = [c for c in df.columns if c.isdigit()]
    if len(numericas) >= 2:
        return numericas[:2]

    if "outros_candidatos" in df.columns:
        i = list(df.columns).index("outros_candidatos")
        if i >= 2:
            return [df.columns[i - 2], df.columns[i - 1]]

    conhecidas = {
        "zona", "secao", "local_votacao", "aptos", "comparecimentos",
        "abstencoes", "abstencao_pct", "turnout_pct", "invalid_pct",
        "validos_por_apto", "votos_validos", "brancos", "nulos",
        "outros_candidatos", "dif_votos", "dif_pct_validos",
        "potencial_virada", "prioridade_mobilizacao", "consistencia",
    }
    sobra = [c for c in df.columns if c not in conhecidas]
    return sobra[:2] if len(sobra) >= 2 else []


def label_candidato(col: str) -> str:
    """Transforma 'cand_22' em 'Candidato 22'."""
    if col.startswith("cand_"):
        return f"Candidato {col[5:]}"
    return col


def calcular_zoom(lat_min, lat_max, lon_min, lon_max) -> float:
    """Zoom aproximado para enquadrar os pontos visíveis."""
    span = max(abs(lat_max - lat_min), abs(lon_max - lon_min))
    if span < 0.005:
        return 14
    if span < 0.02:
        return 13
    if span < 0.05:
        return 12
    if span < 0.1:
        return 11
    if span < 0.5:
        return 10
    if span < 2:
        return 8
    return 6


# ---------------- Sidebar ----------------
st.sidebar.title("TSE BU — Painel")
csvs = encontrar_csvs()
if not csvs:
    st.error("Nenhum CSV encontrado. Rode `python main.py ...` primeiro ou "
             "aponte TSE_BU_CSV para um arquivo.")
    st.stop()

if "csv_path" not in st.session_state or st.session_state["csv_path"] not in csvs:
    st.session_state["csv_path"] = csvs[0]

csv_path = st.sidebar.selectbox(
    "Arquivo CSV", csvs,
    index=csvs.index(st.session_state["csv_path"]),
)
st.session_state["csv_path"] = csv_path

df = carregar_csv(csv_path)

detectadas = detectar_candidatos(df)
if len(detectadas) < 2:
    st.error(
        "Não consegui identificar as duas colunas de candidatos no CSV. "
        "Esperado encontrar colunas imediatamente antes de "
        "`outros_candidatos`, ou duas colunas com nomes numéricos."
    )
    st.write("Colunas encontradas:", list(df.columns))
    st.stop()
else:
    c1, c2 = detectadas
    nome_c1, nome_c2 = label_candidato(c1), label_candidato(c2)

# ---------- Sidebar: Filtros ----------
st.sidebar.markdown("### Filtros")
zonas = sorted(df["zona"].dropna().unique().tolist())
zonas_sel = st.sidebar.multiselect("Zonas", zonas, default=zonas)

if zonas_sel:
    df = df[df["zona"].isin(zonas_sel)]

max_aptos = int(df["aptos"].max()) if not df.empty else 1000
min_aptos = st.sidebar.slider("Mínimo de eleitores aptos", 0,
                              max_aptos, 0, step=10)
df = df[df["aptos"] >= min_aptos]

if df.empty:
    st.warning("Nenhuma seção passa pelos filtros atuais. "
               "Ajuste as Zonas ou o mínimo de eleitores na barra lateral.")
    st.stop()

# ---------- Sidebar: Candidatos ----------
st.sidebar.markdown("### Candidatos")
_conhecidas = {
    "zona", "secao", "local_votacao", "aptos", "comparecimentos",
    "abstencoes", "abstencao_pct", "turnout_pct", "invalid_pct",
    "validos_por_apto", "votos_validos", "brancos", "nulos",
    "outros_candidatos", "dif_votos", "dif_pct_validos",
    "potencial_virada", "prioridade_mobilizacao", "consistencia",
}
opcoes = [c for c in df.columns if c not in _conhecidas]

if len(opcoes) >= 2:
    c1 = st.sidebar.selectbox(
        "Candidato 1 (coluna)", opcoes,
        index=opcoes.index(c1) if c1 in opcoes else 0)
    c2 = st.sidebar.selectbox(
        "Candidato 2 (coluna)", opcoes,
        index=opcoes.index(c2) if c2 in opcoes else min(1, len(opcoes) - 1))
    nome_c1, nome_c2 = label_candidato(c1), label_candidato(c2)
else:
    st.sidebar.warning("CSV não tem colunas de candidatos reconhecíveis.")
    c1 = c2 = None
    nome_c1 = nome_c2 = ""

# ---------- Sidebar: Geodados ----------
st.sidebar.markdown("### Geodados")
ano = st.sidebar.number_input(
    "Ano da eleição", min_value=2000, max_value=2100,
    value=int(os.environ.get("TSE_BU_ANO", 2026)))
uf = st.sidebar.text_input(
    "UF (2 letras)", value=os.environ.get("TSE_BU_UF", "MG")).upper()
st.session_state["ano"] = int(ano)
st.session_state["uf"] = uf

# ---------------- Header ----------------
st.title("Painel de Boletins de Urna")
st.caption(f"Arquivo: `{csv_path}` — {len(df)} seções após filtros")

# ---------------- KPI cards ----------------
aptos = int(df["aptos"].sum())
comp = int(df["comparecimentos"].sum())
abst = int(df["abstencoes"].sum())
validos = int(df["votos_validos"].sum())
brancos = int(df["brancos"].sum())
nulos = int(df["nulos"].sum())
turnout = comp / aptos * 100 if aptos else 0
abstencao = 100 - turnout if aptos else 0
invalid = (brancos + nulos) / comp * 100 if comp else 0
vpa = validos / aptos * 100 if aptos else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Eleitores aptos", f"{aptos:,}")
k2.metric("Comparecimento", f"{comp:,}", f"{turnout:.1f}%")
k3.metric("Abstenções", f"{abst:,}", f"{abstencao:.1f}%", delta_color="inverse")
k4.metric("Votos inválidos", f"{brancos + nulos:,}", f"{invalid:.1f}%",
          delta_color="inverse")
k5.metric("Válidos por apto", f"{vpa:.1f}%")

st.divider()

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(
    ["🎯 Onde mobilizar", "🗺️ Mapa geográfico", "🔥 Heatmap por seção",
     "📊 Comparação", "📈 Perfil do eleitorado", "🏘️ Censo 2022",
     "🎯 Matriz de priorização", "🟥 Treemap por zona",
     "📋 Tabela"]
)

# ---------------- Tab 1: priority ----------------
with tab1:
    st.subheader("Prioridade de mobilização")
    st.markdown(
        "O eixo X mostra a **abstenção (%)**. O eixo Y mostra a **diferença "
        "entre os dois candidatos** (quanto mais perto de 0, mais disputada "
        "a seção). O tamanho da bolha é o **número absoluto de abstenções**. "
        "A cor é a **prioridade de mobilização** — quanto mais escura, mais "
        "vale a pena investir naquela seção."
    )
    fig = px.scatter(
        df, x="abstencao_pct", y="dif_pct_validos",
        size="abstencoes", color="prioridade_mobilizacao",
        hover_data=["zona", "secao", "local_votacao", "aptos",
                    "abstencoes", c1, c2],
        color_continuous_scale="Reds",
        labels={"abstencao_pct": "Abstenção (%)",
                "dif_pct_validos": f"Diferença {nome_c1} vs {nome_c2} (%)",
                "prioridade_mobilizacao": "Prioridade"},
        height=550,
    )
    fig.update_layout(coloraxis_colorbar_title="Prioridade")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Top 15 seções por prioridade de mobilização**")
    top = df.sort_values("prioridade_mobilizacao", ascending=False).head(15)
    st.dataframe(
        top[["zona", "secao", "local_votacao", "aptos", "abstencoes",
             "abstencao_pct", c1, c2, "dif_pct_validos",
             "prioridade_mobilizacao"]],
        width="stretch", hide_index=True,
    )

# ---------------- Tab 2: interactive geographic map ----------------
with tab2:
    st.subheader("Mapa interativo das seções")
    st.markdown(
        "Cada ponto é uma **seção eleitoral**. Passe o mouse para ver os "
        "dados completos. Use os controles abaixo para mudar a cor e o "
        "tamanho dos pontos, e o mapa-base."
    )

    ano_ = st.session_state.get("ano", 2026)
    uf_ = st.session_state.get("uf", "MG")
    municipio = municipio_do_csv(csv_path)

    df_geo = carregar_geodata(csv_path, int(ano_), uf_, municipio)

    # Alinha o tipo de 'zona' antes de filtrar (geodata casta para str)
    if "zona" in df_geo.columns and df["zona"].dtype != df_geo["zona"].dtype:
        df_geo["zona"] = df_geo["zona"].astype(df["zona"].dtype)

    # Reaplica os filtros da sidebar
    df_geo = df_geo[df_geo["zona"].isin(zonas_sel)]
    df_geo = df_geo[df_geo["aptos"] >= min_aptos]

    # Diagnóstico explícito
    if "LATITUDE" not in df_geo.columns:
        st.warning(
            "O join de coordenadas não produziu a coluna `LATITUDE`. "
            "Verifique o terminal — linhas `[geodata]` mostram o motivo. "
            f"Ano/UF: {ano_}/{uf_} · município: {municipio}"
        )
    elif df_geo.empty:
        st.warning(
            "Os filtros da barra lateral excluíram todas as seções. "
            "Verifique **Zonas** e **Mínimo de eleitores aptos**."
        )
    elif df_geo["LATITUDE"].isna().all():
        st.warning(
            f"O join retornou {len(df_geo)} linhas, mas nenhuma com "
            "coordenadas. Possível incompatibilidade entre "
            "`NR_LOCAL_VOTACAO` do bweb e do dataset de locais. "
            "Verifique o terminal para a linha `[geodata] join: K/N`."
        )
    else:
        m1, m2, m3, m4 = st.columns([1.2, 1.2, 1.2, 1])
        metricas_cor = {
            "Abstenção (%)": "abstencao_pct",
            "Inválidos (%)": "invalid_pct",
            "Diferença cand1-cand2 (%)": "dif_pct_validos",
            "Prioridade de mobilização": "prioridade_mobilizacao",
            "Comparecimento (%)": "turnout_pct",
        }
        metricas_tam = {
            "Abstenções": "abstencoes",
            "Aptos": "aptos",
            "Comparecimentos": "comparecimentos",
            "Votos válidos": "votos_validos",
            "Prioridade": "prioridade_mobilizacao",
        }
        with m1:
            cor_label = st.selectbox("Cor =", list(metricas_cor.keys()), index=0)
        with m2:
            tam_label = st.selectbox("Tamanho =", list(metricas_tam.keys()), index=0)
        with m3:
            basemap = st.selectbox(
                "Mapa-base",
                ["carto-positron", "carto-darkmatter",
                 "open-street-map", "carto-voyager"],
                index=0,
            )
        with m4:
            modo = st.radio("Modo", ["Por seção", "Por local"], index=0)

        color_col = metricas_cor[cor_label]
        size_col = metricas_tam[tam_label]

        base = df_geo.dropna(subset=["LATITUDE", "LONGITUDE"]).copy()
        base["secao"] = base["secao"].astype(str)

        if base.empty:
            st.info("Nenhuma seção com coordenadas após os filtros.")
        else:
            if modo == "Por local":
                agg = (
                    base.groupby(["local_votacao", "LATITUDE", "LONGITUDE"],
                                 as_index=False)
                        .agg(
                            aptos=("aptos", "sum"),
                            comparecimentos=("comparecimentos", "sum"),
                            abstencoes=("abstencoes", "sum"),
                            votos_validos=("votos_validos", "sum"),
                            brancos=("brancos", "sum"),
                            nulos=("nulos", "sum"),
                            secoes=("secao", "count"),
                        )
                )
                agg["abstencao_pct"] = (agg["abstencoes"] / agg["aptos"] * 100).round(2)
                agg["turnout_pct"] = (agg["comparecimentos"] / agg["aptos"] * 100).round(2)
                agg["invalid_pct"] = ((agg["brancos"] + agg["nulos"])
                                      / agg["comparecimentos"] * 100).round(2)

                for c in (c1, c2):
                    if c in base.columns:
                        agg = agg.merge(
                            base.groupby(["local_votacao"], as_index=False)
                                .agg(**{c: (c, "sum")}),
                            on="local_votacao", how="left",
                        )
                if c1 in agg.columns and c2 in agg.columns:
                    agg["dif_votos"] = agg[c1] - agg[c2]
                    agg["dif_pct_validos"] = (
                        agg["dif_votos"].abs()
                        / agg["votos_validos"].replace(0, 1) * 100
                    ).round(2)
                    agg["potencial_virada"] = (
                        (agg["abstencoes"] / agg["aptos"])
                        * (1 - agg["dif_pct_validos"] / 100)
                    ).round(4)
                    agg["prioridade_mobilizacao"] = (
                        agg["abstencoes"] * (1 - agg["dif_pct_validos"] / 100)
                    ).round(2)

                plot_df = agg
                hover_extra = {
                    "secoes": True, "aptos": True, "comparecimentos": True,
                    "abstencoes": True,
                    "abstencao_pct": ":.2f", "turnout_pct": ":.2f",
                    "invalid_pct": ":.2f",
                    c1: True, c2: True,
                    "dif_votos": True, "dif_pct_validos": ":.2f",
                    "prioridade_mobilizacao": ":.2f",
                    "LATITUDE": False, "LONGITUDE": False,
                }
            else:
                plot_df = base
                hover_extra = {
                    "zona": True, "secao": True,
                    "aptos": True, "comparecimentos": True, "abstencoes": True,
                    "abstencao_pct": ":.2f", "turnout_pct": ":.2f",
                    "invalid_pct": ":.2f", "validos_por_apto": ":.2f",
                    "votos_validos": True,
                    c1: True, c2: True,
                    "dif_votos": True, "dif_pct_validos": ":.2f",
                    "potencial_virada": ":.4f",
                    "prioridade_mobilizacao": ":.2f",
                    "LATITUDE": False, "LONGITUDE": False,
                }

            lat_c = float(plot_df["LATITUDE"].mean())
            lon_c = float(plot_df["LONGITUDE"].mean())
            zoom = calcular_zoom(
                plot_df["LATITUDE"].min(), plot_df["LATITUDE"].max(),
                plot_df["LONGITUDE"].min(), plot_df["LONGITUDE"].max(),
            )

            fig_map = px.scatter_map(
                plot_df,
                lat="LATITUDE", lon="LONGITUDE",
                size=size_col,
                color=color_col,
                hover_name="local_votacao",
                hover_data=hover_extra,
                color_continuous_scale="OrRd",
                size_max=30,
                height=650,
                labels={
                    "abstencao_pct": "Abstenção (%)",
                    "turnout_pct": "Comparecimento (%)",
                    "invalid_pct": "Inválidos (%)",
                    "dif_pct_validos": f"Diferença {nome_c1} vs {nome_c2} (%)",
                    "prioridade_mobilizacao": "Prioridade",
                    "abstencoes": "Abstenções",
                    "aptos": "Aptos",
                },
            )
            fig_map.update_layout(
                map=dict(
                    style=basemap,
                    center=dict(lat=lat_c, lon=lon_c),
                    zoom=zoom,
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                coloraxis_colorbar=dict(title=cor_label),
            )
            st.plotly_chart(fig_map, use_container_width=True)

            st.markdown("**Top 15 pontos no mapa (ordenados pela métrica de cor)**")
            top_map = plot_df.sort_values(color_col, ascending=False).head(15)
            cols_show = ["local_votacao"]
            for extra in ("zona", "secao", "aptos", "abstencoes", "abstencao_pct",
                          "turnout_pct", "invalid_pct", c1, c2,
                          "dif_pct_validos", "prioridade_mobilizacao"):
                if extra in top_map.columns:
                    cols_show.append(extra)
            st.dataframe(top_map[cols_show], width="stretch", hide_index=True)

            st.download_button(
                "Baixar dados do mapa (CSV)",
                data=plot_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"mapa_{modo.lower().replace(' ', '_')}.csv",
                mime="text/csv",
            )

# ---------------- Tab 3: section heatmap ----------------
with tab3:
    st.subheader("Heatmap por seção (sem geografia)")
    st.markdown(
        "Cada célula é uma seção. Linhas = zona, colunas = seção. "
        "Cor = abstenção (%). Útil quando não há coordenadas."
    )

    MAX_COLS = 60
    pivot = df.pivot_table(index="zona", columns="secao",
                           values="abstencao_pct", aggfunc="mean")
    if pivot.empty:
        st.info("Sem dados para exibir.")
    else:
        if pivot.shape[1] > MAX_COLS:
            st.caption(
                f"Exibindo as primeiras {MAX_COLS} seções de "
                f"{pivot.shape[1]} (para legibilidade). Use os filtros "
                f"da barra lateral para reduzir o conjunto."
            )
            pivot = pivot.iloc[:, :MAX_COLS]

        fig_hm = px.imshow(
            pivot, aspect="auto", color_continuous_scale="OrRd",
            labels=dict(x="Seção", y="Zona", color="Abstenção (%)"),
            height=max(400, 60 + 20 * len(pivot)),
        )
        st.plotly_chart(fig_hm, use_container_width=True)

        st.markdown("**Abstenções absolutas por zona × seção**")
        pivot_abs = df.pivot_table(index="zona", columns="secao",
                                   values="abstencoes", aggfunc="sum")
        if pivot_abs.shape[1] > MAX_COLS:
            pivot_abs = pivot_abs.iloc[:, :MAX_COLS]
        fig_hm2 = px.imshow(
            pivot_abs, aspect="auto", color_continuous_scale="Reds",
            labels=dict(x="Seção", y="Zona", color="Abstenções"),
            height=max(400, 60 + 20 * len(pivot_abs)),
        )
        st.plotly_chart(fig_hm2, use_container_width=True)

# ---------------- Tab 4: comparison ----------------
with tab4:
    st.subheader(f"{nome_c1} vs {nome_c2} — votos por seção")

    df_melt = df.melt(
        id_vars=["zona", "secao", "local_votacao"],
        value_vars=[c1, c2], var_name="candidato", value_name="votos",
    )
    df_melt["candidato"] = df_melt["candidato"].map(
        {c1: nome_c1, c2: nome_c2})

    fig4 = px.histogram(
        df_melt, x="votos", color="candidato", barmode="overlay",
        nbins=40, opacity=0.7, height=450,
        labels={"votos": "Votos na seção", "candidato": "Candidato"},
    )
    st.plotly_chart(fig4, use_container_width=True)

    st.markdown("**Dispersão: votos cand1 vs cand2**")
    aptos_safe = df["aptos"].clip(lower=1)
    size_scaled = np.log10(aptos_safe)
    fig5 = px.scatter(
        df.assign(_size=size_scaled),
        x=c1, y=c2, color="abstencao_pct", size="_size",
        hover_data=["zona", "secao", "local_votacao", "aptos"],
        color_continuous_scale="Viridis",
        labels={c1: nome_c1, c2: nome_c2, "abstencao_pct": "Abstenção (%)"},
        height=500,
    )
    st.plotly_chart(fig5, use_container_width=True)

# ---------------- Tab 5: perfil do eleitorado ----------------
with tab5:
    st.subheader("Perfil do eleitorado")
    st.markdown(
        "Composição demográfica das seções filtradas, segundo o **Perfil do "
        "eleitorado por seção eleitoral** do TSE. Colunas geradas quando o "
        "`main.py` roda com `--perfil`."
    )

    colunas_perfil = [c for c in df.columns if c.startswith("perfil_")]
    tem_dados_perfil = ("perfil_total" in df.columns
                        and df["perfil_total"].notna().any())

    if not colunas_perfil or not tem_dados_perfil:
        st.warning(
            "Este CSV não tem colunas de perfil. Rode o `main.py` com "
            "`--perfil` para gerar, ou use um CSV já enriquecido."
        )
    else:
        # --- KPIs agregados ---
        total = int(df["perfil_total"].sum())
        pct_fem = (df["perfil_genero_feminino"].sum() / total * 100
                   if "perfil_genero_feminino" in df.columns and total else 0)
        pct_jov = (df["perfil_jovens_16_24"].sum() / total * 100
                   if "perfil_jovens_16_24" in df.columns and total else 0)
        pct_ido = (df["perfil_idosos_60_mais"].sum() / total * 100
                   if "perfil_idosos_60_mais" in df.columns and total else 0)
        pct_pcd = (df["perfil_pcd"].sum() / total * 100
                   if "perfil_pcd" in df.columns and total else 0)

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total de eleitores", f"{total:,}")
        k2.metric("Mulheres", f"{pct_fem:.1f}%")
        k3.metric("Jovens 16–24", f"{pct_jov:.1f}%")
        k4.metric("Idosos 60+", f"{pct_ido:.1f}%")
        k5.metric("PCD", f"{pct_pcd:.1f}%")

        # --- Faixa etária ---
        st.markdown("**Distribuição por faixa etária**")
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
                fig_idade = px.bar(
                    resumo, x="faixa", y="pct",
                    labels={"faixa": "Faixa etária",
                            "pct": "% do eleitorado"},
                    height=380,
                )
                st.plotly_chart(fig_idade, use_container_width=True)

        # --- Gênero ---
        st.markdown("**Distribuição por gênero**")
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
                fig_gen = px.pie(resumo, names="genero", values="pct",
                                 height=380, hole=0.4)
                st.plotly_chart(fig_gen, use_container_width=True)

        # --- Instrução ---
        st.markdown("**Grau de instrução**")
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
                resumo = resumo.sort_values("pct", ascending=True)
                fig_ins = px.bar(resumo, x="pct", y="grau", orientation="h",
                                 labels={"pct": "% do eleitorado", "grau": ""},
                                 height=380)
                st.plotly_chart(fig_ins, use_container_width=True)

        # --- Top 15 seções por % de jovens ---
        if "perfil_jovens_16_24_pct" in df.columns:
            st.markdown("**Top 15 seções por % de jovens (16–24)**")
            top_jov = df.sort_values("perfil_jovens_16_24_pct",
                                     ascending=False).head(15)
            cols_mostrar = ["zona", "secao", "local_votacao",
                            "perfil_total", "perfil_jovens_16_24_pct",
                            "abstencao_pct", "prioridade_mobilizacao"]
            cols_mostrar = [c for c in cols_mostrar if c in top_jov.columns]
            st.dataframe(top_jov[cols_mostrar], width="stretch",
                         hide_index=True)

        # --- Correlação abstenção × % de jovens ---
        if ("perfil_jovens_16_24_pct" in df.columns
                and "abstencao_pct" in df.columns):
            st.markdown("**Abstenção × % de jovens**")
            fig_corr = px.scatter(
                df, x="perfil_jovens_16_24_pct", y="abstencao_pct",
                size="perfil_total", color="prioridade_mobilizacao",
                hover_data=["zona", "secao", "local_votacao",
                            "perfil_total", "aptos"],
                color_continuous_scale="Reds",
                labels={"perfil_jovens_16_24_pct": "% de jovens (16–24)",
                        "abstencao_pct": "Abstenção (%)",
                        "prioridade_mobilizacao": "Prioridade"},
                height=500,
            )
            st.plotly_chart(fig_corr, use_container_width=True)
                # --- Radar demográfico: compara até 3 seções ---
        st.markdown("---")
        st.markdown("**Radar demográfico — comparação entre seções**")
        st.markdown(
            "Selecione até 3 seções para comparar os perfis lado a lado. "
            "Cada eixo é um percentual do eleitorado da seção (0–100%)."
        )

        # Monta os rótulos das seções disponíveis
        secoes_disponiveis = df.apply(
            lambda r: f"{r['zona']}-{r['secao']}", axis=1
        ).tolist()
        secoes_radar = st.multiselect(
            "Selecione até 3 seções",
            options=secoes_disponiveis,
            max_selections=3,
            default=secoes_disponiveis[:2] if len(secoes_disponiveis) >= 2 else [],
            key="radar_secoes",
        )

        if secoes_radar:
            categorias = [
                ("perfil_genero_feminino_pct", "% Mulheres"),
                ("perfil_jovens_16_24_pct", "% Jovens 16–24"),
                ("perfil_idosos_60_mais_pct", "% Idosos 60+"),
                ("perfil_instrucao_superior_completo_pct", "% Superior"),
                ("perfil_instrucao_analfabeto_pct", "% Analfabeto"),
                ("perfil_raca_parda_pct", "% Parda"),
                ("perfil_raca_preta_pct", "% Preta"),
                ("perfil_pcd_pct", "% PCD"),
            ]
            # Filtra só as colunas que existem no CSV
            categorias = [(c, l) for c, l in categorias if c in df.columns]

            if len(categorias) < 3:
                st.warning(
                    "Poucas colunas de perfil disponíveis para desenhar "
                    "o radar. Rode o `main.py` com `--perfil`."
                )
            else:
                import plotly.graph_objects as go
                cores = ["#c0392b", "#2980b9", "#27ae60"]
                fig_radar = go.Figure()
                for i, slug in enumerate(secoes_radar):
                    z, s = slug.split("-")
                    row = df[(df["zona"].astype(str) == z) &
                             (df["secao"].astype(str) == s)]
                    if row.empty:
                        continue
                    vals = []
                    for c, _ in categorias:
                        v = row.iloc[0].get(c, 0)
                        vals.append(float(v) if pd.notna(v) else 0.0)
                    vals_plot = vals + [vals[0]]
                    cats_plot = [l for _, l in categorias] + [categorias[0][1]]
                    fig_radar.add_trace(go.Scatterpolar(
                        r=vals_plot,
                        theta=cats_plot,
                        fill="toself",
                        name=f"Zona {z} · Seção {s}",
                        line=dict(color=cores[i % len(cores)]),
                        opacity=0.6,
                    ))
                fig_radar.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 100],
                                        ticksuffix="%"),
                    ),
                    height=550,
                    showlegend=True,
                    legend=dict(orientation="h", y=-0.1),
                )
                st.plotly_chart(fig_radar, use_container_width=True)

                # Tabela comparativa com os valores
                st.markdown("**Valores por eixo**")
                linhas_tab = []
                for c, label in categorias:
                    linha = {"Dimensão": label}
                    for slug in secoes_radar:
                        z, s = slug.split("-")
                        row = df[(df["zona"].astype(str) == z) &
                                 (df["secao"].astype(str) == s)]
                        v = row.iloc[0].get(c, 0) if not row.empty else 0
                        linha[f"Zona {z} · Seção {s}"] = (
                            f"{float(v):.1f}%" if pd.notna(v) else "—"
                        )
                    linhas_tab.append(linha)
                st.dataframe(pd.DataFrame(linhas_tab),
                             width="stretch", hide_index=True)


# ---------------- Tab 6: Censo 2022 ----------------
with tab6:
    st.subheader("Censo 2022 — contexto socioeconômico")
    st.markdown(
        "Dados do **Censo 2022 (IBGE)** por setor censitário, cruzados com "
        "os locais de votação via `geocensobr`. Cada seção herda os atributos "
        "do setor censitário onde seu local de votação está inserido."
    )

    colunas_censo = [c for c in df.columns if c.startswith("censo_")]
    tem_dados = ("censo_total_pessoas" in df.columns
                 and df["censo_total_pessoas"].notna().any())
    if not colunas_censo or not tem_dados:
        st.warning(
            "Nenhuma seção tem dados do Censo. Isso pode acontecer se o "
            "`geocensobr` não conseguiu consultar os setores censitários. "
            "Verifique o terminal onde o `main.py` rodou — a linha "
            "`[censo] N/203 pontos com dados do Censo` mostra quantos "
            "pontos retornaram."
        )
        st.stop()
    else:
        # --- KPIs ---
        total_pessoas = int(df["censo_total_pessoas"].sum(skipna=True))
        total_dom = int(df["censo_total_domicilios"].sum(skipna=True))
        media_mor = df["censo_media_moradores"].mean(skipna=True)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total de pessoas (setores)", f"{total_pessoas:,}")
        k2.metric("Total de domicílios", f"{total_dom:,}")
        k3.metric("Média de moradores/domicílio",
                  f"{media_mor:.2f}" if pd.notna(media_mor) else "—")
        k4.metric("Seções com dados do Censo",
                  f"{df['censo_total_pessoas'].notna().sum()}/{len(df)}")

        # --- Distribuição por tipo de setor ---
        if "censo_tipo_setor_desc" in df.columns:
            st.markdown("**Distribuição por tipo de setor censitário**")
            tipos = (df.groupby("censo_tipo_setor_desc", as_index=False)
                       .agg(secoes=("secao", "count"),
                            aptos=("aptos", "sum")))
            fig_tipos = px.bar(
                tipos, x="secoes", y="censo_tipo_setor_desc",
                orientation="h",
                labels={"secoes": "Nº de seções",
                        "censo_tipo_setor_desc": ""},
                height=350,
            )
            st.plotly_chart(fig_tipos, use_container_width=True)

        # --- Abstenção × total de pessoas no setor ---
        if "censo_total_pessoas" in df.columns and "abstencao_pct" in df.columns:
            st.markdown("**Abstenção × total de pessoas no setor**")
            fig_censo = px.scatter(
                df.dropna(subset=["censo_total_pessoas"]),
                x="censo_total_pessoas", y="abstencao_pct",
                size="aptos", color="prioridade_mobilizacao",
                hover_data=["zona", "secao", "local_votacao",
                            "censo_bairro", "censo_municipio"],
                color_continuous_scale="Reds",
                labels={"censo_total_pessoas": "População do setor",
                        "abstencao_pct": "Abstenção (%)",
                        "prioridade_mobilizacao": "Prioridade"},
                height=500,
            )
            st.plotly_chart(fig_censo, use_container_width=True)

        # --- Tabela detalhada ---
        st.markdown("**Seções com dados do Censo**")
        cols_censo_mostrar = ["zona", "secao", "local_votacao",
                              "censo_total_pessoas", "censo_total_domicilios",
                              "censo_media_moradores", "censo_tipo_setor_desc",
                              "censo_bairro", "abstencao_pct"]
        cols_existentes = [c for c in cols_censo_mostrar if c in df.columns]
        st.dataframe(df[cols_existentes].dropna(
            subset=["censo_total_pessoas"] if "censo_total_pessoas" in df else []),
            width="stretch", hide_index=True)


# ---------------- Tab 7: quadrant matrix ----------------
with tab7:
    st.subheader("Matriz de priorização")
    st.markdown(
        "Cada ponto é uma seção. As **linhas tracejadas** marcam a mediana "
        "de cada eixo. O **quadrante superior direito** (alta abstenção + "
        "disputa acirrada) é a prioridade máxima de mobilização."
    )

    if df.empty:
        st.info("Sem dados após os filtros.")
    else:
        med_abst = df["abstencao_pct"].median()
        med_dif = df["dif_pct_validos"].median()

        # Classifica cada seção em um quadrante
        def _quadrante(row):
            alta_abst = row["abstencao_pct"] >= med_abst
            acirrado = row["dif_pct_validos"] <= med_dif
            if alta_abst and acirrado:
                return "Prioridade máxima"
            if alta_abst and not acirrado:
                return "Alta abstenção, disputa definida"
            if not alta_abst and acirrado:
                return "Baixa abstenção, disputa acirrada"
            return "Baixa prioridade"

        df_q = df.copy()
        df_q["quadrante"] = df_q.apply(_quadrante, axis=1)

        fig = px.scatter(
            df_q,
            x="abstencao_pct",
            y="dif_pct_validos",
            color="quadrante",
            size="aptos",
            hover_data=["zona", "secao", "local_votacao",
                        "abstencoes", c1, c2, "prioridade_mobilizacao"],
            color_discrete_map={
                "Prioridade máxima": "#c0392b",
                "Alta abstenção, disputa definida": "#e67e22",
                "Baixa abstenção, disputa acirrada": "#2980b9",
                "Baixa prioridade": "#95a5a6",
            },
            height=600,
            labels={"abstencao_pct": "Abstenção (%)",
                    "dif_pct_validos": f"Diferença {nome_c1} vs {nome_c2} (%)",
                    "quadrante": "Quadrante"},
        )
        fig.add_vline(x=med_abst, line_dash="dash", line_color="grey")
        fig.add_hline(y=med_dif, line_dash="dash", line_color="grey")
        fig.update_layout(legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, use_container_width=True)

        # Sumário por quadrante
        st.markdown("**Resumo por quadrante**")
        resumo_q = (df_q.groupby("quadrante", as_index=False)
                    .agg(secoes=("secao", "count"),
                         aptos=("aptos", "sum"),
                         abstencoes=("abstencoes", "sum"),
                         votos_validos=("votos_validos", "sum"),
                         abstencao_media=("abstencao_pct", "mean")))
        resumo_q["abstencao_media"] = resumo_q["abstencao_media"].round(2)
        st.dataframe(resumo_q, width="stretch", hide_index=True)

        # Top 15 do quadrante "Prioridade máxima"
        st.markdown("**Top 15 seções do quadrante 'Prioridade máxima'**")
        prio = (df_q[df_q["quadrante"] == "Prioridade máxima"]
                .sort_values("prioridade_mobilizacao", ascending=False)
                .head(15))
        cols_prio = ["zona", "secao", "local_votacao", "aptos",
                     "abstencoes", "abstencao_pct", "dif_pct_validos",
                     c1, c2, "prioridade_mobilizacao"]
        cols_prio = [c for c in cols_prio if c in prio.columns]
        st.dataframe(prio[cols_prio], width="stretch", hide_index=True)


# ---------------- Tab 8: treemap ----------------
with tab8:
    st.subheader("Treemap por zona e seção")
    st.markdown(
        "Cada retângulo é uma seção, agrupada por zona. O **tamanho** é "
        "proporcional aos eleitores aptos; a **cor** é a abstenção (%). "
        "Retângulos grandes e escuros = maior contingente de faltantes."
    )

    if df.empty:
        st.info("Sem dados após os filtros.")
    else:
        df_tree = df.copy()
        df_tree["zona"] = df_tree["zona"].astype(str)
        df_tree["secao"] = df_tree["secao"].astype(str)
        df_tree["rotulo"] = "Seção " + df_tree["secao"]

        fig_tree = px.treemap(
            df_tree,
            path=["zona", "rotulo"],
            values="aptos",
            color="abstencao_pct",
            color_continuous_scale="OrRd",
            hover_data={"abstencao_pct": ":.2f",
                        "abstencoes": True,
                        "prioridade_mobilizacao": ":.2f",
                        "aptos": True},
            labels={"abstencao_pct": "Abstenção (%)",
                    "zona": "Zona",
                    "rotulo": "Seção"},
            height=650,
        )
        fig_tree.update_layout(
            margin=dict(l=0, r=0, t=30, b=0),
            coloraxis_colorbar=dict(title="Abstenção (%)"),
        )
        st.plotly_chart(fig_tree, use_container_width=True)

        # Legenda explicativa por tipo de seção
        st.caption(
            "Clique em uma zona para expandir. O tamanho do retângulo é "
            "proporcional ao número de eleitores aptos."
        )
# ---------------- Tab 9: table ----------------
with tab9:
    st.subheader("Tabela completa")
    st.dataframe(df, width="stretch", hide_index=True)
    st.download_button(
        "Baixar CSV filtrado",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="tse_bu_filtrado.csv",
        mime="text/csv",
    )

st.caption(
    "Fonte: dados abertos do TSE (bweb + locais de votação). "
    "Métricas: turnout, invalid_pct, validos_por_apto, prioridade_mobilizacao."
) 