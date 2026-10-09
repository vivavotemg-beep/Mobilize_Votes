"""Integra indicadores socioeconômicos contextuais ao CSV de urnas.

Fase 1: IDHM, IVS municipal, Bolsa Família, CadÚnico.
Todos por município — merge direto.
"""

import io
import os
import sys
import tempfile
import urllib.request
from typing import Optional

import pandas as pd

from .config import USER_AGENT

CACHE_DIR = os.path.join(tempfile.gettempdir(), "tse_bu_cache")

# URLs de fontes públicas
URL_IDHM = "http://www.atlasbrasil.org.br/2013/data/rawdata/radar_idhm_2010.csv"
URL_BOLSA = "https://aplicacoes.cidadania.gov.br/vis/tabelas/tabela.php"
# (API do Portal da Transparência precisa de chave — usaremos CSV público do MDS)


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cache_path(nome: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, nome)


def carregar_idhm() -> Optional[pd.DataFrame]:
    """Retorna DataFrame com CD_MUNICIPIO (7 dígitos) e IDHM."""
    path = _cache_path("idhm_municipios.csv")
    if os.path.exists(path):
        return pd.read_csv(path, dtype=str)

    # Fonte alternativa: IDHM por município (dados abertos)
    # Nota: o Atlas do Desenvolvimento Humano tem uma API/CSV; aqui usamos
    # uma cópia pública consolidada.
    try:
        # CSV com código IBGE de 7 dígitos e IDHM 2010
        url = "https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/main/csv/municipios.csv"
        raw = _get(url)
        df = pd.read_csv(io.BytesIO(raw), dtype=str)
        # Este CSV tem codigo_ibge, nome, etc., mas NÃO IDHM.
        # Precisamos cruzar com outra fonte.
        return None  # Placeholder — ver nota abaixo
    except Exception as exc:
        print(f"[contexto] IDHM: {exc}", file=sys.stderr)
        return None


def carregar_bolsa_familia(ano: int = 2025) -> Optional[pd.DataFrame]:
    """Retorna DataFrame com CD_MUNICIPIO e número de famílias no Bolsa Família.

    Fonte: Portal da Transparência / MDS. Requer download manual do CSV
    ou uso da API com chave.
    """
    # O Portal da Transparência tem API, mas exige cadastro.
    # Alternativa: dados abertos do MDS em CSV.
    path = _cache_path(f"bolsa_familia_{ano}.csv")
    if os.path.exists(path):
        return pd.read_csv(path, dtype=str)
    return None


def juntar_contexto(df: pd.DataFrame, ano: int = 2026) -> pd.DataFrame:
    """Adiciona colunas de contexto socioeconômico ao DataFrame.

    Colunas adicionadas (se disponíveis):
      - idhm_municipal
      - ivs_municipal
      - bolsa_familia_familias
      - cadunico_familias
    """
    df = df.copy()

    # IDHM
    idhm = carregar_idhm()
    if idhm is not None and "idhm" in idhm.columns:
        # df precisa ter CD_MUNICIPIO — não temos no CSV atual!
        # Solução alternativa: usar nome do município
        pass

    return df