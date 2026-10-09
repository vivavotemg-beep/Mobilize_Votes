"""Integra dados do Censo 2022 (IBGE) aos locais de votação via geocensobr.

A biblioteca geocensobr baixa a malha de setores censitários do IBGE e
permite consultar, por (lat, lon), todos os atributos do setor.
"""

import os
import sys
from typing import Optional

import pandas as pd

# Cache local para não baixar o GPKG do IBGE a cada execução
# (o geocensobr já gerencia o cache dele internamente)
try:
    import geocensobr
    _GEOCENSOBR_DISPONIVEL = True
except ImportError:
    _GEOCENSOBR_DISPONIVEL = False
    print("[censo] geocensobr não instalado. Rode: pip install geocensobr",
          file=sys.stderr)


def enriquecer_com_censo(df: pd.DataFrame,
                          lat_col: str = "LATITUDE",
                          lon_col: str = "LONGITUDE") -> pd.DataFrame:
    """Adiciona colunas do Censo 2022 por setor censitário a cada linha.

    Requer que df tenha LATITUDE e LONGITUDE (o join do geodata já produz).
    Para cada ponto, consulta o setor censitário correspondente e extrai
    variáveis como:
      - V0001: total de pessoas
      - V0002: total de domicílios
      - CD_TIPO: tipo do setor (favela, indígena, quilombola, etc.)
      - NM_BAIRRO: nome do bairro
      - NM_MUN: nome do município (IBGE)
    """
    if not _GEOCENSOBR_DISPONIVEL:
        df["censo_total_pessoas"] = None
        df["censo_total_domicilios"] = None
        df["censo_tipo_setor"] = None
        df["censo_bairro"] = None
        return df

    df = df.copy()

    # geocensobr.buscar() aceita um ponto por chamada; iteramos.
    # O GPKG é carregado em memória no primeiro import, então cada
    # consulta é rápida (~ms).
    total = len(df)
    print(f"[censo] consultando setor censitário para {total} pontos...",
          file=sys.stderr)

    colunas = ["censo_total_pessoas", "censo_total_domicilios",
               "censo_tipo_setor", "censo_bairro", "censo_municipio"]
    for c in colunas:
        df[c] = None

    for i, (idx, row) in enumerate(df.iterrows()):
        lat, lon = row.get(lat_col), row.get(lon_col)
        if pd.isna(lat) or pd.isna(lon):
            continue
        try:
            resultado = geocensobr.buscar(lat=float(lat), lon=float(lon))
            if resultado is not None and not resultado.empty:
                r = resultado.iloc[0]
                df.at[idx, "censo_total_pessoas"] = r.get("V0001")
                df.at[idx, "censo_total_domicilios"] = r.get("V0002")
                df.at[idx, "censo_tipo_setor"] = r.get("CD_TIPO")
                df.at[idx, "censo_bairro"] = r.get("NM_BAIRRO")
                df.at[idx, "censo_municipio"] = r.get("NM_MUN")
        except Exception as exc:
            print(f"[censo] erro em ({lat}, {lon}): {exc}", file=sys.stderr)

        if (i + 1) % 100 == 0:
            print(f"[censo] {i+1}/{total} pontos processados", file=sys.stderr)

    # Converte para numérico
    for c in ["censo_total_pessoas", "censo_total_domicilios",
              "censo_tipo_setor"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    print(f"[censo] enriquecimento concluído.", file=sys.stderr)
    return df


def descrever_tipos_setor() -> pd.DataFrame:
    """Retorna o mapeamento dos códigos de tipo de setor censitário."""
    return pd.DataFrame([
        {"CD_TIPO": 1, "descricao": "Favela ou comunidade urbana"},
        {"CD_TIPO": 2, "descricao": "Quartel ou base militar"},
        {"CD_TIPO": 3, "descricao": "Alojamento ou acampamento"},
        {"CD_TIPO": 4, "descricao": "Baixo patamar domiciliar"},
        {"CD_TIPO": 5, "descricao": "Agrupamento indígena"},
        {"CD_TIPO": 6, "descricao": "Unidade prisional"},
        {"CD_TIPO": 7, "descricao": "Convento, hospital ou ILPI"},
        {"CD_TIPO": 8, "descricao": "Agrovila de assentamento"},
        {"CD_TIPO": 9, "descricao": "Agrupamento quilombola"},
    ])