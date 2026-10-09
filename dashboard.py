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
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="TSE BU — Painel", layout="wide")


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


def encontrar_csvs() -> list:
    if os.environ.get("TSE_BU_CSV"):
        return [os.environ["TSE_BU_CSV"]]
    return sorted(glob.glob("saida/*.csv"))


def detectar_candidatos(df: pd.DataFrame) -> list:
    """Descobre as duas colunas de candidatos no CSV.

    Ordem de tentativa:
      1. formato novo: nomes começando com 'cand_'
      2. formato antigo: nomes totalmente numéricos
      3. estrutural: colunas imediatamente antes de 'outros_candidatos'
      4. fallback: qualquer coluna que não seja conhecida
    """
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


# ---------------- Sidebar ----------------
st.sidebar.title("TSE BU — Painel")
csvs = encontrar_csvs()
if not csvs:
    st.error("Nenhum CSV encontrado. Rode `python main.py ...` primeiro ou "
             "aponte TSE_BU_CSV para um arquivo.")
    st.stop()

csv_path = st.sidebar.selectbox("Arquivo CSV", csvs, index=0)
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
    nome_c1, nome_c2 = c1, c2

# ---------- Sidebar: Filtros ----------
st.sidebar.markdown("### Filtros")
zonas = sorted(df["zona"].dropna().unique().tolist())
zonas_sel = st.sidebar.multiselect("Zonas", zonas, default=zonas)
df = df[df["zona"].isin(zonas_sel)]

min_aptos = st.sidebar.slider("Mínimo de eleitores aptos", 0,
                              int(df["aptos"].max()), 0, step=10)
df = df[df["aptos"] >= min_aptos]

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
    nome_c1, nome_c2 = c1, c2
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
invalid = (brancos + nulos) / comp * 100 if comp else 0
vpa = validos / aptos * 100 if aptos else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Eleitores aptos", f"{aptos:,}")
k2.metric("Comparecimento", f"{comp:,}", f"{turnout:.1f}%")
k3.metric("Abstenções", f"{abst:,}", f"{100 - turnout:.1f}%", delta_color="inverse")
k4.metric("Votos inválidos", f"{brancos + nulos:,}", f"{invalid:.1f}%", delta_color="inverse")
k5.metric("Válidos por apto", f"{vpa:.1f}%")

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🎯 Onde mobilizar", "🗺️ Mapa geográfico", "🔥 Heatmap por seção",
     "📊 Comparação", "📋 Tabela"]
)

# ---------------- Tab 1: priority ----------------
with tab1:
    st.subheader("Prioridade de mobilização")
    st.markdown(
        "O eixo X mostra a **abstenção (%)**. O eixo Y mostra a **diferença entre "
        "os dois candidatos** (quanto mais perto de 0, mais disputada a seção). "
        "O tamanho da bolha é o **número absoluto de abstenções**."
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
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Top 15 seções por prioridade de mobilização**")
    top = df.sort_values("prioridade_mobilizacao", ascending=False).head(15)
    st.dataframe(
        top[["zona", "secao", "local_votacao", "aptos", "abstencoes",
             "abstencao_pct", "dif_pct_validos", "prioridade_mobilizacao",
             c1, c2]],
        use_container_width=True, hide_index=True,
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

    try:
        from tse_bu import geodata
        df_geo = geodata.juntar_coordenadas(df.copy(), ano_, uf_)
    except Exception as exc:
        df_geo = df.copy()
        df_geo["LATITUDE"] = None
        df_geo["LONGITUDE"] = None
        st.warning(f"Não foi possível obter coordenadas: {exc}")

    if "LATITUDE" not in df_geo.columns or df_geo["LATITUDE"].isna().all():
        st.info(
            "Sem coordenadas disponíveis para este ano/UF. "
            "Veja a aba *Heatmap por seção* para uma visão alternativa."
        )
    else:
        # ---------- controles do mapa ----------
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

        # ---------- agregação opcional ----------
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

        # ---------- scatter_map (Plotly >= 6) ----------
        fig_map = px.scatter_map(
            plot_df,
            lat="LATITUDE", lon="LONGITUDE",
            size=size_col,
            color=color_col,
            hover_name="local_votacao",
            hover_data=hover_extra,
            color_continuous_scale="OrRd",
            size_max=30, zoom=10, height=650,
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
            map=dict(style=basemap),
            margin=dict(l=0, r=0, t=0, b=0),
            coloraxis_colorbar=dict(title=cor_label),
        )
        st.plotly_chart(fig_map, use_container_width=True)

        # ---------- tabela sincronizada abaixo do mapa ----------
        st.markdown("**Top 15 pontos no mapa (ordenados pela métrica de cor)**")
        top_map = plot_df.sort_values(color_col, ascending=False).head(15)
        cols_show = ["local_votacao"]
        for extra in ("zona", "secao", "aptos", "abstencoes", "abstencao_pct",
                      "turnout_pct", "invalid_pct", c1, c2,
                      "dif_pct_validos", "prioridade_mobilizacao"):
            if extra in top_map.columns:
                cols_show.append(extra)
        st.dataframe(top_map[cols_show], use_container_width=True,
                     hide_index=True)

        # ---------- download do que está no mapa ----------
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
    pivot = df.pivot_table(index="zona", columns="secao",
                           values="abstencao_pct", aggfunc="mean")
    if pivot.empty:
        st.info("Sem dados para exibir.")
    else:
        fig_hm = px.imshow(
            pivot, aspect="auto", color_continuous_scale="OrRd",
            labels=dict(x="Seção", y="Zona", color="Abstenção (%)"),
            height=600,
        )
        st.plotly_chart(fig_hm, use_container_width=True)

        st.markdown("**Abstenções absolutas por zona × seção**")
        pivot_abs = df.pivot_table(index="zona", columns="secao",
                                   values="abstencoes", aggfunc="sum")
        fig_hm2 = px.imshow(
            pivot_abs, aspect="auto", color_continuous_scale="Reds",
            labels=dict(x="Seção", y="Zona", color="Abstenções"),
            height=600,
        )
        st.plotly_chart(fig_hm2, use_container_width=True)

# ---------------- Tab 4: comparison ----------------
with tab4:
    st.subheader(f"{nome_c1} vs {nome_c2} — votos por seção")
    df_melt = df.melt(
        id_vars=["zona", "secao", "local_votacao"],
        value_vars=[c1, c2], var_name="candidato", value_name="votos",
    )
    fig4 = px.histogram(
        df_melt, x="votos", color="candidato", barmode="overlay",
        nbins=40, opacity=0.7, height=450,
        labels={"votos": "Votos na seção", "candidato": "Candidato"},
    )
    st.plotly_chart(fig4, use_container_width=True)

    st.markdown("**Dispersão: votos cand1 vs cand2**")
    fig5 = px.scatter(
        df, x=c1, y=c2, color="abstencao_pct", size="aptos",
        hover_data=["zona", "secao", "local_votacao"],
        color_continuous_scale="Viridis",
        labels={c1: nome_c1, c2: nome_c2, "abstencao_pct": "Abstenção (%)"},
        height=500,
    )
    st.plotly_chart(fig5, use_container_width=True)

# ---------------- Tab 5: table ----------------
with tab5:
    st.subheader("Tabela completa")
    st.dataframe(df, use_container_width=True, hide_index=True)
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