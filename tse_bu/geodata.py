"""Junta coordenadas (lat/long) dos locais de votação aos dados do bweb.

O CSV bweb não traz latitude/longitude. O TSE publica um dataset separado
com os locais de votação e suas coordenadas. Fazemos o join por
(CD_MUNICIPIO, NR_ZONA, NR_LOCAL_VOTACAO).

O dataset `eleitorado-<ano>` contém o Brasil inteiro; por isso filtramos
por UF e município antes de juntar.
"""

import io
import os
import sys
import tempfile
import zipfile
from typing import Optional

import pandas as pd

from . import config

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
    # Preferência explícita: nome contendo "local de votação" ou "locais_votacao"
    pref = [
        r for r in resources
        if ("local de votação" in r.get("name", "").lower()
            or "local_votacao" in r.get("url", "").lower()
            or "locais_votacao" in r.get("url", "").lower()
            or "local_votacao" in r.get("name", "").lower())
    ]
    if pref:
        return pref
    # Senão, qualquer coisa com "local"
    com_local = [
        r for r in resources
        if "local" in r.get("name", "").lower()
        or "local" in r.get("url", "").lower()
    ]
    return com_local or resources


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
        print(f"[geodata] nenhum dataset encontrado para {ano}/{uf}",
              file=sys.stderr)
        return None

    print(f"[geodata] usando dataset '{ds_usado}' "
          f"({len(resources)} recursos)", file=sys.stderr)

    recursos_filtrados = _filtrar_recursos_locais(resources, uf)

    # Prefere ZIPs; senão CSV
    zips = [r for r in recursos_filtrados
            if r.get("url", "").lower().endswith(".zip")]
    csvs = [r for r in recursos_filtrados
            if r.get("url", "").lower().endswith(".csv")]
    target = (zips or csvs or recursos_filtrados)[0]
    url = target["url"]
    print(f"[geodata] recurso escolhido: {target.get('name', '?')}",
          file=sys.stderr)
    print(f"[geodata]   url: {url}", file=sys.stderr)

    raw = config._get(url)

    if url.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            uf_up = uf.upper()
            matches = [n for n in csvs
                       if f"_{uf_up}." in n.upper() or n.upper().endswith(f"_{uf_up}.CSV")]
            escolhido = matches[0] if matches else csvs[0]
            print(f"[geodata] csv dentro do zip: {escolhido} "
                  f"(de {len(csvs)} disponíveis)", file=sys.stderr)
            with zf.open(escolhido) as fb:
                text = io.TextIOWrapper(fb, encoding="latin-1")
                return pd.read_csv(text, sep=";", dtype=str, low_memory=False)


def obter_coordenadas(ano: int, uf: str,
                      cache_dir: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Retorna DataFrame com CD_MUNICIPIO, NR_ZONA, NR_LOCAL_VOTACAO,
    NR_LATITUDE, NR_LONGITUDE — já filtrado pela UF.

    Faz cache em disco. Retorna None se não conseguir obter o dataset.
    """
    path = _cache_path(ano, uf, cache_dir)
    if os.path.exists(path):
        df = pd.read_csv(path, dtype=str)
        print(f"[geodata] cache hit: {path} ({len(df)} locais)",
              file=sys.stderr)
        return df

    df = _download_locais(ano, uf)

    # Se falhou e não é 2022, tenta 2022 como aproximação
    if df is None and ano != 2022:
        print(f"[geodata] {ano} falhou, tentando 2022 como fallback...",
              file=sys.stderr)
        df = _download_locais(2022, uf)
        if df is not None:
            print(f"[geodata] usando coordenadas de 2022 para {uf}.",
                  file=sys.stderr)

    if df is None:
        return None

    # ---- Filtra pela UF ----
    if "SG_UF" in df.columns:
        uf_up = uf.upper()
        antes = len(df)
        df = df[df["SG_UF"].astype(str).str.upper() == uf_up].copy()
        print(f"[geodata] filtro UF={uf_up}: {len(df)}/{antes} linhas",
              file=sys.stderr)
    else:
        print(f"[geodata] aviso: coluna SG_UF não encontrada, "
              f"não filtrei por UF", file=sys.stderr)

    # ---- Normaliza nomes de coluna ----
    colmap = {
        "CD_MUNICIPIO": ["CD_MUNICIPIO"],
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
    keep = {}
    for canonical, options in colmap.items():
        found = next((o for o in options if o in df.columns), None)
        if not found:
            if canonical in ("NM_LOCAL_VOTACAO", "DS_ENDERECO", "NM_BAIRRO"):
                continue  # opcionais
            print(f"[geodata] coluna '{canonical}' não encontrada "
                  f"(tentei {options})", file=sys.stderr)
            print(f"[geodata] colunas disponíveis: {list(df.columns)}",
                  file=sys.stderr)
            return None
        keep[canonical] = df[found].astype(str)

    out = pd.DataFrame(keep)
    # Normaliza vírgula decimal nas coordenadas
    for c in ("NR_LATITUDE", "NR_LONGITUDE"):
        out[c] = out[c].str.replace(",", ".", regex=False)
        out[c] = pd.to_numeric(out[c], errors="coerce")

    antes = len(out)
    out = out.dropna(subset=["NR_LATITUDE", "NR_LONGITUDE"])
    print(f"[geodata] {len(out)}/{antes} linhas com lat/long válidos",
          file=sys.stderr)
    if out.empty:
        return None

    out.to_csv(path, index=False)
    return out


def juntar_coordenadas(df: pd.DataFrame, ano: int, uf: str,
                       cd_municipio: Optional[str] = None,
                       cache_dir: Optional[str] = None) -> pd.DataFrame:
    """Adiciona NR_LATITUDE / NR_LONGITUDE ao DataFrame de seções.

    Args:
        df:            DataFrame produzido por analysis.montar_tabela.
        ano, uf:       usados para buscar o dataset.
        cd_municipio:  código TSE do município (para filtrar o dataset,
                       que cobre o Brasil inteiro). Se None, tenta inferir
                       cruzando zona/local com o dataset completo.
        cache_dir:     pasta de cache opcional.
    """
    df = df.copy()
    df["zona"] = df["zona"].astype(str)
    df["local_votacao_id"] = df["local_votacao"].astype(str)

    coords = obter_coordenadas(ano, uf, cache_dir)
    if coords is None or coords.empty:
        df["NR_LATITUDE"] = None
        df["NR_LONGITUDE"] = None
        return df

    coords = coords.rename(columns={
        "NR_ZONA": "zona",
        "NR_LOCAL_VOTACAO": "local_votacao_id",
        "NR_LATITUDE": "LATITUDE",
        "NR_LONGITUDE": "LONGITUDE",
    })
    coords["zona"] = coords["zona"].astype(str)
    coords["local_votacao_id"] = coords["local_votacao_id"].astype(str)

    # Se soubermos o CD_MUNICIPIO, filtra antes do merge — evita colisões
    # entre municípios que por acaso compartilham (zona, local).
    if cd_municipio is not None and "CD_MUNICIPIO" in coords.columns:
        antes = len(coords)
        coords = coords[coords["CD_MUNICIPIO"].astype(str)
                        == str(cd_municipio)].copy()
        print(f"[geodata] filtro CD_MUNICIPIO={cd_municipio}: "
              f"{len(coords)}/{antes} locais", file=sys.stderr)

    merged = df.merge(coords, on=["zona", "local_votacao_id"], how="left")

    if "NR_LATITUDE" in merged.columns:
        com = merged["NR_LATITUDE"].notna().sum()
        print(f"[geodata] join: {com}/{len(merged)} seções com coordenadas",
              file=sys.stderr)

    return merged