"""Junta coordenadas (lat/long) dos locais de votação aos dados do bweb.

O CSV bweb não traz latitude/longitude. O TSE publica um dataset separado
com os locais de votação e suas coordenadas. Fazemos o join por
(CD_MUNICIPIO, NR_ZONA, NR_LOCAL_VOTACAO).

O dataset `eleitorado-<ano>` contém o Brasil inteiro; por isso filtramos
por UF e município antes de juntar.
"""

import io
import logging
import os
import re
import tempfile
import zipfile
from typing import Optional

import pandas as pd

from . import config

logger = logging.getLogger(__name__)

# Dataset ids candidatos, tentados em ordem.
_DATASET_IDS = [
    "eleitorado-{ano}",
    "eleitorado-local-de-votacao-{ano}",
    "eleicoes-{ano}-locais-de-votacao",
    "locais-de-votacao-{ano}",
    "eleitorado-locais-de-votacao-{ano}",
    "local-de-votacao-{ano}",
    "locais-votacao-{ano}",
    "eleitorado-local-votacao-{ano}",
    # fallback para 2022 caso o ano alvo não exista
    "eleitorado-local-de-votacao-2022",
    "locais-de-votacao-2022",
]

CACHE_DIR_DEFAULT = os.path.join(tempfile.gettempdir(), "tse_bu_cache")
CACHE_FILE = "locais_votacao_{ano}_{uf}.csv"


def _cache_path(ano: int, uf: str, cache_dir: Optional[str] = None) -> str:
    d = cache_dir or CACHE_DIR_DEFAULT
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, CACHE_FILE.format(ano=ano, uf=uf.upper()))


def _filtrar_recursos_locais(resources: list, uf: str) -> list:
    """Escolhe o recurso 'Eleitorado por local de votação' do dataset."""
    pref = [
        r for r in resources
        if ("local de votação" in r.get("name", "").lower()
            or "local_votacao" in r.get("url", "").lower()
            or "locais_votacao" in r.get("url", "").lower()
            or "local_votacao" in r.get("name", "").lower())
    ]
    if pref:
        return pref
    com_local = [
        r for r in resources
        if "local" in r.get("name", "").lower()
        or "local" in r.get("url", "").lower()
    ]
    return com_local or resources


def _ufs_disponiveis(nomes: list) -> list:
    """Extrai as UF finais dos nomes de CSV (ex.: '..._MG.csv' -> 'MG')."""
    ufs = set()
    for n in nomes:
        m = re.search(r"_([A-Z]{2})\.CSV$", n.upper())
        if m:
            ufs.add(m.group(1))
    return sorted(ufs)


def _download_locais(ano: int, uf: str) -> Optional[pd.DataFrame]:
    """Baixa o dataset de locais de votação e devolve DataFrame cru (Brasil).

    Retorna None se nenhum dataset id resolver.
    """
    resources = None
    ds_usado = None
    for tmpl in _DATASET_IDS:
        ds = tmpl.format(ano=ano)
        try:
            resources = config.dataset_resources(ds)
            ds_usado = ds
            break
        except Exception:
            continue
    if not resources:
        logger.error("nenhum dataset encontrado para %s/%s", ano, uf)
        return None

    logger.info("usando dataset '%s' (%d recursos)", ds_usado, len(resources))

    recursos_filtrados = _filtrar_recursos_locais(resources, uf)

    zips = [r for r in recursos_filtrados
            if r.get("url", "").lower().endswith(".zip")]
    csvs = [r for r in recursos_filtrados
            if r.get("url", "").lower().endswith(".csv")]
    target = (zips or csvs or recursos_filtrados)[0]
    url = target["url"]
    logger.info("recurso escolhido: %s", target.get("name", "?"))
    logger.info("  url: %s", url)

    raw = config._get(url)

    if url.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csvs_in_zip = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            uf_up = uf.upper()
            matches = [n for n in csvs_in_zip
                       if f"_{uf_up}." in n.upper()
                       or n.upper().endswith(f"_{uf_up}.CSV")]
            if not matches:
                raise ValueError(
                    f"UF {uf_up} não encontrada. "
                    f"Disponíveis: {_ufs_disponiveis(csvs_in_zip)}"
                )
            escolhido = matches[0]
            logger.info("csv dentro do zip: %s (de %d disponíveis)",
                        escolhido, len(csvs_in_zip))
            with zf.open(escolhido) as fb:
                text = io.TextIOWrapper(fb, encoding="latin-1")
                return pd.read_csv(text, sep=";", dtype=str, low_memory=False)

    return pd.read_csv(io.BytesIO(raw), sep=";", dtype=str, low_memory=False)


def obter_coordenadas(ano: int, uf: str,
                      cache_dir: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Retorna DataFrame com CD_MUNICIPIO, NM_MUNICIPIO, NR_ZONA,
    NR_LOCAL_VOTACAO, NR_LATITUDE, NR_LONGITUDE — já filtrado pela UF.

    Faz cache em disco. Retorna None se não conseguir obter o dataset.
    """
    path = _cache_path(ano, uf, cache_dir)
    if os.path.exists(path):
        df = pd.read_csv(path, dtype=str)
        # Reconverte as coordenadas para numérico — o dtype=str acima é
        # necessário para preservar zeros à esquerda em NR_ZONA e
        # NR_LOCAL_VOTACAO, mas deixa LATITUDE/LONGITUDE como string.
        for c in ("NR_LATITUDE", "NR_LONGITUDE", "LATITUDE", "LONGITUDE"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        logger.info("cache hit: %s (%d locais)", path, len(df))
        return df

    df = _download_locais(ano, uf)

    if df is None and ano != 2022:
        logger.warning("%d falhou, tentando 2022 como fallback...", ano)
        df = _download_locais(2022, uf)
        if df is not None:
            logger.warning("usando coordenadas de 2022 para %s.", uf)

    if df is None:
        return None

    # ---- Filtra pela UF ----
    if "SG_UF" in df.columns:
        uf_up = uf.upper()
        antes = len(df)
        df = df[df["SG_UF"].astype(str).str.upper() == uf_up].copy()
        logger.info("filtro UF=%s: %d/%d linhas", uf_up, len(df), antes)
    else:
        logger.warning("coluna SG_UF não encontrada, não filtrei por UF")

    # ---- Normaliza nomes de coluna ----
    colmap = {
        "CD_MUNICIPIO": ["CD_MUNICIPIO"],
        "NM_MUNICIPIO": ["NM_MUNICIPIO"],           # <- novo
        "NR_ZONA": ["NR_ZONA", "ZONA"],
        "NR_LOCAL_VOTACAO": ["NR_LOCAL_VOTACAO", "NR_LOCAL", "COD_LOCAL",
                             "CD_LOCAL_VOTACAO"],
        "NR_LATITUDE": ["NR_LATITUDE", "LATITUDE", "LAT", "NM_LATITUDE"],
        "NR_LONGITUDE": ["NR_LONGITUDE", "LONGITUDE", "LON", "LNG",
                         "NM_LONGITUDE"],
        "NM_LOCAL_VOTACAO": ["NM_LOCAL_VOTACAO"],
        "DS_ENDERECO": ["DS_ENDERECO"],
        "NM_BAIRRO": ["NM_BAIRRO"],
    }
    # Colunas que podem faltar sem quebrar
    opcionais = {
        "NM_LOCAL_VOTACAO", "DS_ENDERECO", "NM_BAIRRO",
        "CD_MUNICIPIO", "NM_MUNICIPIO",
    }

    keep = {}
    for canonical, options in colmap.items():
        found = next((o for o in options if o in df.columns), None)
        if not found:
            if canonical in opcionais:
                continue
            logger.error("coluna '%s' não encontrada (tentei %s)",
                         canonical, options)
            logger.error("colunas disponíveis: %s", list(df.columns))
            return None
        keep[canonical] = df[found].astype(str)

    out = pd.DataFrame(keep)
    for c in ("NR_LATITUDE", "NR_LONGITUDE"):
        if c in out.columns:
            out[c] = out[c].str.replace(",", ".", regex=False)
            out[c] = pd.to_numeric(out[c], errors="coerce")

    antes = len(out)
    out = out.dropna(subset=["NR_LATITUDE", "NR_LONGITUDE"])
    logger.info("%d/%d linhas com lat/long válidos", len(out), antes)
    if out.empty:
        return None

    out.to_csv(path, index=False)
    return out


def juntar_coordenadas(df: pd.DataFrame, ano: int, uf: str,
                       municipio: Optional[str] = None,
                       cd_municipio: Optional[str] = None,
                       cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Adiciona LATITUDE / LONGITUDE ao DataFrame de seções.

    Aceita filtrar por nome do município (`municipio`) ou por código TSE
    (`cd_municipio`). Se nenhum for passado, faz o join com todos os locais
    da UF — pode gerar linhas duplicadas se houver códigos de local
    repetidos entre municípios.

    Args:
        df:            DataFrame produzido por analysis.montar_tabela.
        ano, uf:       usados para buscar o dataset.
        municipio:     nome do município (ex.: "OURO PRETO"), case-insensitive.
        cd_municipio:  código TSE do município (ex.: "46698").
        cache_dir:     pasta de cache opcional.
    """
    df = df.copy()
    df["zona"] = df["zona"].astype(str)
    df["local_votacao_id"] = df["local_votacao"].astype(str)

    coords = obter_coordenadas(ano, uf, cache_dir)
    if coords is None or coords.empty:
        df["LATITUDE"] = None
        df["LONGITUDE"] = None
        return df

    coords = coords.rename(columns={
        "NR_ZONA": "zona",
        "NR_LOCAL_VOTACAO": "local_votacao_id",
        "NR_LATITUDE": "LATITUDE",
        "NR_LONGITUDE": "LONGITUDE",
    })
    coords["zona"] = coords["zona"].astype(str)
    coords["local_votacao_id"] = coords["local_votacao_id"].astype(str)

    # ---- filtra por município (nome) ----
    if municipio and "NM_MUNICIPIO" in coords.columns:
        alvo = municipio.strip().upper()
        antes = len(coords)
        coords = coords[
            coords["NM_MUNICIPIO"].astype(str).str.upper() == alvo
        ].copy()
        logger.info("filtro NM_MUNICIPIO='%s': %d/%d locais",
                    alvo, len(coords), antes)

    # ---- filtra por município (código TSE) ----
    if cd_municipio is not None and "CD_MUNICIPIO" in coords.columns:
        antes = len(coords)
        coords = coords[
            coords["CD_MUNICIPIO"].astype(str) == str(cd_municipio)
        ].copy()
        logger.info("filtro CD_MUNICIPIO=%s: %d/%d locais",
                    cd_municipio, len(coords), antes)

    if coords.empty:
        logger.warning("filtro de município esvaziou os locais; "
                       "o join não vai produzir coordenadas.")
        df["LATITUDE"] = None
        df["LONGITUDE"] = None
        return df

    # O dataset de locais tem uma linha por SEÇÃO; várias linhas com a
    # mesma (zona, local). Deduplica para uma linha por local antes do
    # merge — senão o join vira produto cartesiano.
    antes = len(coords)
    coords = (coords
              .sort_values(["zona", "local_votacao_id"])
              .drop_duplicates(subset=["zona", "local_votacao_id"],
                               keep="first"))
    logger.info("dedupe por (zona, local): %d/%d linhas",
                len(coords), antes)


    # Garante que as coordenadas são numéricas antes do merge
    for c in ("LATITUDE", "LONGITUDE"):
        if c in coords.columns:
            coords[c] = pd.to_numeric(coords[c], errors="coerce")

    merged = df.merge(coords, on=["zona", "local_votacao_id"], how="left")

    if "LATITUDE" in merged.columns:
        com = merged["LATITUDE"].notna().sum()
        logger.info("join: %d/%d seções com coordenadas", com, len(merged))

    return merged
