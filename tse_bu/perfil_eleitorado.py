"""Baixa e agrega o 'Perfil do eleitorado por seção eleitoral' do TSE.

O CSV do TSE tem uma linha por combinação de gênero × estado civil × faixa
etária × grau de instrução × raça × identidade de gênero × quilombola ×
intérprete de libras, com QT_ELEITORES dizendo quantos eleitores daquela
seção caem naquela combinação.

Este módulo agrega por (NR_ZONA, NR_SECAO) e devolve uma linha por seção
com totais e percentuais por dimensão.

Cobre todas as UFs. O cache é por (ano, uf).
"""

import io
import os
import sys
import tempfile
import zipfile
from typing import Optional

import pandas as pd

from . import config

CACHE_DIR = os.path.join(tempfile.gettempdir(), "tse_bu_cache")

# Mapeamentos de faixa etária em "jovem / adulto / idoso" a partir do
# texto de DS_FAIXA_ETARIA. Cobre 16-17, 18-24, 25-59, 60+.
FAIXAS_JOVEM = {
    "16 anos", "17 anos", "18 anos", "19 anos", "20 anos", "21 anos",
    "22 anos", "23 anos", "24 anos",
    "16 a 17 anos", "18 a 19 anos", "20 a 24 anos",
}
FAIXAS_ADULTO = {
    "25 anos", "26 anos", "27 anos", "28 anos", "29 anos",
    "30 a 34 anos", "35 a 39 anos", "40 a 44 anos", "45 a 49 anos",
    "50 a 54 anos", "55 a 59 anos",
    "25 a 29 anos",
}
FAIXAS_IDOSO = {
    "60 a 64 anos", "65 a 69 anos", "70 a 74 anos", "75 a 79 anos",
    "80 a 84 anos", "85 a 89 anos", "90 a 94 anos", "95 a 99 anos",
    "100 anos ou mais",
}


def _cache_path(ano: int, uf: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"perfil_eleitorado_{ano}_{uf.upper()}_agg.csv")


def _url_perfil(ano: int, uf: str) -> Optional[str]:
    """Descobre a URL do ZIP de perfil do eleitorado para a UF/ano."""
    ds = f"eleitorado-{ano}"
    try:
        resources = config.dataset_resources(ds)
    except Exception as exc:
        print(f"[perfil] dataset '{ds}' indisponível: {exc}", file=sys.stderr)
        return None

    uf_up = uf.upper()
    # Nome típico: "MG - Perfil do eleitorado por seção eleitoral - 2026"
    alvo = [
        r for r in resources
        if "perfil do eleitorado por seção" in r.get("name", "").lower()
        and r.get("name", "").upper().startswith(f"{uf_up} ")
    ]
    if not alvo:
        print(f"[perfil] recurso não encontrado para {ano}/{uf}; "
              f"tentando qualquer coisa com 'perfil_eleitor_secao'",
              file=sys.stderr)
        alvo = [
            r for r in resources
            if "perfil_eleitor_secao" in r.get("url", "").lower()
            and f"_{uf_up}.zip" in r.get("url", "").upper()
        ]
    if not alvo:
        return None
    return alvo[0]["url"]


def _baixar_perfil_cru(ano: int, uf: str) -> Optional[pd.DataFrame]:
    """Baixa e lê o CSV cru do perfil (uma linha por célula)."""
    url = _url_perfil(ano, uf)
    if url is None:
        return None
    print(f"[perfil] baixando {url}", file=sys.stderr)
    raw = config._get(url)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            return None
        with zf.open(csvs[0]) as fb:
            texto = io.TextIOWrapper(fb, encoding="latin-1")
            df = pd.read_csv(texto, sep=";", dtype=str, low_memory=False)
    # Remove aspas dos nomes das colunas e dos valores (o TSE às vezes
    # exporta com quotechar ausente)
    df.columns = [c.strip().strip('"') for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.strip('"')
    return df


def _slug(texto: str) -> str:
    """Normaliza um texto para virar parte de um nome de coluna."""
    return (str(texto).lower()
            .replace(" ", "_").replace("/", "_")
            .replace("á", "a").replace("ã", "a").replace("â", "a")
            .replace("é", "e").replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o").replace("ô", "o").replace("õ", "o")
            .replace("ú", "u").replace("ü", "u")
            .replace("ç", "c")
            .replace("+", "mais")
            .replace("-", "_"))


def _agregar_perfil(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Transforma o perfil granular em uma linha por (zona, secao)."""
    df_raw = df_raw.copy()
    df_raw["NR_ZONA"] = df_raw["NR_ZONA"].astype(str)
    df_raw["NR_SECAO"] = df_raw["NR_SECAO"].astype(str)

    # Numéricos
    for c in ["QT_ELEITORES", "QT_ELEITORES_BIOMETRIA",
              "QT_ELEITORES_DEFICIENCIA", "QT_ELEITORES_NOME_SOCIAL"]:
        if c in df_raw.columns:
            df_raw[c] = pd.to_numeric(df_raw[c], errors="coerce").fillna(0)
        else:
            df_raw[c] = 0

    # Total e contadores auxiliares por seção
    g = df_raw.groupby(["NR_ZONA", "NR_SECAO"], as_index=False)
    out = g["QT_ELEITORES"].sum().rename(columns={"QT_ELEITORES": "perfil_total"})
    out = out.merge(
        g["QT_ELEITORES_BIOMETRIA"].sum().rename(
            columns={"QT_ELEITORES_BIOMETRIA": "perfil_biometria"}),
        on=["NR_ZONA", "NR_SECAO"],
    )
    out = out.merge(
        g["QT_ELEITORES_DEFICIENCIA"].sum().rename(
            columns={"QT_ELEITORES_DEFICIENCIA": "perfil_pcd"}),
        on=["NR_ZONA", "NR_SECAO"],
    )
    out = out.merge(
        g["QT_ELEITORES_NOME_SOCIAL"].sum().rename(
            columns={"QT_ELEITORES_NOME_SOCIAL": "perfil_nome_social"}),
        on=["NR_ZONA", "NR_SECAO"],
    )

    # Agrega por dimensão e pivota
    def _pivot(dim_col: str, prefixo: str) -> pd.DataFrame:
        piv = (df_raw
               .groupby(["NR_ZONA", "NR_SECAO", dim_col], as_index=False)
               ["QT_ELEITORES"].sum()
               .pivot(index=["NR_ZONA", "NR_SECAO"],
                      columns=dim_col, values="QT_ELEITORES")
               .fillna(0).reset_index())
        piv.columns.name = None
        ren = {}
        for c in piv.columns:
            if c in ("NR_ZONA", "NR_SECAO"):
                continue
            ren[c] = f"{prefixo}_{_slug(c)}"
        return piv.rename(columns=ren)

    dims = [
        ("DS_GENERO", "perfil_genero"),
        ("DS_FAIXA_ETARIA", "perfil_idade"),
        ("DS_GRAU_ESCOLARIDADE", "perfil_instrucao"),
        ("DS_RACA_COR", "perfil_raca"),
        ("DS_ESTADO_CIVIL", "perfil_estado_civil"),
        ("DS_IDENTIDADE_GENERO", "perfil_identidade"),
        ("DS_QUILOMBOLA", "perfil_quilombola"),
        ("DS_INTERPRETE_LIBRAS", "perfil_libras"),
    ]
    for col, pref in dims:
        if col not in df_raw.columns:
            continue
        out = out.merge(_pivot(col, pref), on=["NR_ZONA", "NR_SECAO"], how="left")

    # Percentuais
    total_safe = out["perfil_total"].replace(0, pd.NA)
    for c in list(out.columns):
        if c in ("NR_ZONA", "NR_SECAO", "perfil_total"):
            continue
        if c.startswith("perfil_") and not c.endswith("_pct"):
            out[c + "_pct"] = (out[c] / total_safe * 100).round(2).fillna(0)

    # Agregados simplificados: jovem / adulto / idoso
    def _soma_por_faixas(conjunto):
        cols = [c for c in out.columns
                if c.startswith("perfil_idade_") and not c.endswith("_pct")]
        selecionadas = []
        for c in cols:
            texto = c.replace("perfil_idade_", "").replace("_", " ")
            for faixa in conjunto:
                if faixa.lower() in texto.lower() or texto.lower().startswith(
                        faixa.lower()[:5]):
                    selecionadas.append(c)
                    break
        if not selecionadas:
            return 0
        return out[selecionadas].sum(axis=1)

    out["perfil_jovens_16_24"] = _soma_por_faixas(FAIXAS_JOVEM)
    out["perfil_adultos_25_59"] = _soma_por_faixas(FAIXAS_ADULTO)
    out["perfil_idosos_60_mais"] = _soma_por_faixas(FAIXAS_IDOSO)
    for c in ["perfil_jovens_16_24", "perfil_adultos_25_59",
              "perfil_idosos_60_mais"]:
        out[c + "_pct"] = (out[c] / total_safe * 100).round(2).fillna(0)

    return out


def obter_perfil(ano: int, uf: str) -> Optional[pd.DataFrame]:
    """Retorna o perfil agregado por (zona, secao), com cache em disco."""
    path = _cache_path(ano, uf)
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"NR_ZONA": str, "NR_SECAO": str})
        print(f"[perfil] cache hit: {path} ({len(df)} seções)", file=sys.stderr)
        return df

    cru = _baixar_perfil_cru(ano, uf)
    if cru is None or cru.empty:
        return None

    agg = _agregar_perfil(cru)
    agg.to_csv(path, index=False)
    print(f"[perfil] {len(agg)} seções agregadas salvas em {path}",
          file=sys.stderr)
    return agg


def juntar_perfil(df: pd.DataFrame, ano: int, uf: str) -> pd.DataFrame:
    """Adiciona as colunas de perfil ao DataFrame de urnas.

    O join é por (zona, secao). Colunas de perfil vêm prefixadas com
    'perfil_' para não colidir com as colunas de urnas.
    """
    df = df.copy()
    df["zona"] = df["zona"].astype(str)
    df["secao"] = df["secao"].astype(str)

    perfil = obter_perfil(ano, uf)
    if perfil is None or perfil.empty:
        print(f"[perfil] sem dados para {ano}/{uf}; colunas não adicionadas",
              file=sys.stderr)
        return df

    perfil = perfil.rename(columns={"NR_ZONA": "zona", "NR_SECAO": "secao"})
    perfil["zona"] = perfil["zona"].astype(str)
    perfil["secao"] = perfil["secao"].astype(str)

    merged = df.merge(perfil, on=["zona", "secao"], how="left")
    n_match = (merged["perfil_total"].notna().sum()
               if "perfil_total" in merged else 0)
    print(f"[perfil] join: {n_match}/{len(merged)} seções com perfil",
          file=sys.stderr)
    return merged