"""Configurações e descoberta de datasets no portal de dados abertos do TSE."""

import json
import re
import urllib.request

CKAN_API = "https://dadosabertos.tse.jus.br/api/3/action"
CDN_BASE = "https://cdn.tse.jus.br"

# Códigos de cargo mais usuais
CARGOS = {
    "presidente": "1",
    "governador": "3",
    "senador": "5",
    "deputado-federal": "6",
    "deputado-estadual": "7",
    "deputado-distrital": "8",
    "prefeito": "11",
    "vereador": "13",
}

USER_AGENT = "tse-bu-collector/1.0 (dados abertos TSE)"


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def dataset_resources(dataset_id: str) -> list[dict]:
    """Lista os recursos (arquivos) de um dataset CKAN do TSE."""
    data = json.loads(_get(f"{CKAN_API}/package_show?id={dataset_id}"))
    return data["result"]["resources"]


def find_bu_zip_url(ano: int, uf: str, turno: int) -> str:
    """Localiza a URL do ZIP 'bweb' (Boletim de Urna web) da UF/turno/ano.

    Ex.: bweb_1t_MG_051020261403.zip
    """
    ds = f"resultados-{ano}-boletim-de-urna"
    try:
        resources = dataset_resources(ds)
    except Exception as exc:  # dataset ainda não publicado
        raise RuntimeError(
            f"Dataset '{ds}' não encontrado. Verifique se o TSE já publicou "
            f"os boletins de urna de {ano} (dadosabertos.tse.jus.br)."
        ) from exc
    uf = uf.upper()
    pat = re.compile(rf"bweb_{turno}t_{uf}_\d+\.zip$", re.IGNORECASE)
    for r in resources:
        if pat.search(r.get("url", "")):
            return r["url"]
    raise RuntimeError(f"Arquivo bweb não localizado para {uf} turno {turno} em {ano}.")
