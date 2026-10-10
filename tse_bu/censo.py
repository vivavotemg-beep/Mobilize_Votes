"""Integra dados do Censo 2022 (IBGE) aos locais de votação via geocensobr.

A biblioteca geocensobr baixa automaticamente a malha de setores censitários
do IBGE na primeira importação e permite consultar, por (lat, lon), os
atributos do setor correspondente.

Este módulo enriquece o DataFrame de urnas com variáveis do Censo por
local de votação. Cobre todo o Brasil.
"""

import sys
from typing import Optional

import pandas as pd

try:
    import geocensobr
    _GEOCENSOBR_DISPONIVEL = True
except ImportError:
    _GEOCENSOBR_DISPONIVEL = False
    print("[censo] geocensobr não instalado. Rode: pip install geocensobr",
          file=sys.stderr)


# Mapeamento dos códigos de tipo de setor censitário do IBGE
TIPOS_SETOR = {
    0: "Comum",
    1: "Favela ou comunidade urbana",
    2: "Quartel ou base militar",
    3: "Alojamento ou acampamento",
    4: "Baixo patamar domiciliar",
    5: "Agrupamento indígena",
    6: "Unidade prisional",
    7: "Convento, hospital ou ILPI",
    8: "Agrovila de assentamento",
    9: "Agrupamento quilombola",
}


def _buscar_setor(lat: float, lon: float) -> Optional[dict]:
    """Consulta o setor censitário para um ponto. Retorna dict ou None."""
    if not _GEOCENSOBR_DISPONIVEL:
        return None
    try:
        resultado = geocensobr.buscar(lat=float(lat), lon=float(lon))
        if resultado is None:
            return None
        # geocensobr pode retornar GeoDataFrame, DataFrame ou Series
        if hasattr(resultado, "empty"):
            if resultado.empty:
                return None
            return resultado.iloc[0].to_dict()
        if isinstance(resultado, dict):
            return resultado
        # Fallback: tenta converter
        import pandas as pd
        if isinstance(resultado, pd.Series):
            return resultado.to_dict()
        return None
    except Exception as exc:
        print(f"[censo] erro em ({lat}, {lon}): "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return None

def enriquecer_com_censo(df: pd.DataFrame,
                          lat_col: str = "LATITUDE",
                          lon_col: str = "LONGITUDE") -> pd.DataFrame:
    """Adiciona colunas do Censo 2022 por setor censitário a cada linha.

    Requer que df tenha LATITUDE e LONGITUDE. Para cada ponto, consulta o
    setor censitário e extrai as variáveis do Censo.

    Colunas adicionadas:
      censo_total_pessoas     — V0001
      censo_total_domicilios  — V0002
      censo_media_moradores   — V0005
      censo_tipo_setor        — CD_TIPO (numérico)
      censo_tipo_setor_desc   — descrição legível
      censo_bairro            — NM_BAIRRO
      censo_municipio         — NM_MUN
      censo_uf                — NM_UF
      censo_cod_setor         — CD_SETOR
    """
    df = df.copy()

    colunas_novas = [
        "censo_total_pessoas", "censo_total_domicilios",
        "censo_media_moradores", "censo_tipo_setor",
        "censo_tipo_setor_desc", "censo_bairro", "censo_municipio",
        "censo_uf", "censo_cod_setor",
    ]
    for c in colunas_novas:
        if c not in df.columns:
            df[c] = None

    if not _GEOCENSOBR_DISPONIVEL:
        print("[censo] geocensobr indisponível; colunas ficarão vazias",
              file=sys.stderr)
        return df

    if lat_col not in df.columns or lon_col not in df.columns:
        print(f"[censo] colunas {lat_col}/{lon_col} ausentes; "
              f"rode o geodata primeiro", file=sys.stderr)
        return df

    total = len(df)
    print(f"[censo] consultando setor censitário para {total} pontos...",
          file=sys.stderr)

    # Cache local para não repetir consultas
    cache_busca: dict = {}

    for i, (idx, row) in enumerate(df.iterrows()):
        lat, lon = row.get(lat_col), row.get(lon_col)
        if pd.isna(lat) or pd.isna(lon):
            continue

        chave = (round(float(lat), 6), round(float(lon), 6))
        if chave in cache_busca:
            resultado = cache_busca[chave]
        else:
            resultado = _buscar_setor(lat, lon)
            cache_busca[chave] = resultado

        if resultado is None:
            continue

        # Extrai as variáveis (nomes variam ligeiramente; tenta alternativas)
        def _get(*chaves):
            for k in chaves:
                if k in resultado and resultado[k] is not None:
                    return resultado[k]
            return None

        df.at[idx, "censo_total_pessoas"] = _get("v0001", "V0001")
        df.at[idx, "censo_total_domicilios"] = _get("v0002", "V0002")
        df.at[idx, "censo_media_moradores"] = _get("v0005", "V0005")
        df.at[idx, "censo_tipo_setor"] = _get("CD_TIPO", "cd_tipo")
        df.at[idx, "censo_bairro"] = _get("NM_BAIRRO", "nm_bairro")
        df.at[idx, "censo_municipio"] = _get("NM_MUN", "nm_mun")
        df.at[idx, "censo_uf"] = _get("NM_UF", "nm_uf")
        df.at[idx, "censo_cod_setor"] = _get("CD_SETOR", "cd_setor")

        if (i + 1) % 100 == 0:
            print(f"[censo] {i+1}/{total} pontos processados", file=sys.stderr)

    # Converte para numérico onde faz sentido
    for c in ["censo_total_pessoas", "censo_total_domicilios",
              "censo_media_moradores", "censo_tipo_setor"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Traduz o tipo do setor
    if "censo_tipo_setor" in df.columns:
        df["censo_tipo_setor_desc"] = df["censo_tipo_setor"].map(
            lambda v: TIPOS_SETOR.get(int(v), "Outro") if pd.notna(v) else None)

    n_ok = df["censo_total_pessoas"].notna().sum() if "censo_total_pessoas" in df else 0
    if n_ok == 0:
        print("[censo] NENHUM ponto retornou setor. Diagnóstico: rode "
              "`python -c \"import geocensobr; print(geocensobr.buscar("
              "lat=-20.3856, lon=-43.5035))\"` para checar a lib.", file=sys.stderr)
    print(f"[censo] {n_ok}/{total} pontos com dados do Censo", file=sys.stderr)
    return df


def descrever_tipos_setor() -> pd.DataFrame:
    """Retorna o mapeamento dos códigos de tipo de setor censitário."""
    return pd.DataFrame([
        {"CD_TIPO": k, "descricao": v} for k, v in TIPOS_SETOR.items()
    ])