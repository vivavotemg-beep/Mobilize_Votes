#!/usr/bin/env python3
"""Descobre, no portal CKAN do TSE, os datasets de locais de votação.

Uso:
    python probe_locais.py --ano 2026 --uf MG
    python probe_locais.py --ano 2022 --uf MG
    python probe_locais.py --search "local"      # busca textual
"""

import argparse
import json
import urllib.request
import urllib.parse

CKAN_API = "https://dadosabertos.tse.jus.br/api/3/action"
UA = "tse-bu-collector-probe/1.0"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def package_show(ds):
    try:
        data = _get(f"{CKAN_API}/package_show?id={ds}")
        return data["result"]
    except Exception as exc:
        return {"_error": str(exc)}


def package_search(q, rows=20):
    url = f"{CKAN_API}/package_search?q={urllib.parse.quote(q)}&rows={rows}"
    data = _get(url)
    return data["result"]["results"]


def probe_dataset(ds):
    print(f"\n=== package_show: {ds} ===")
    r = package_show(ds)
    if "_error" in r:
        print(f"  NAO ENCONTRADO ({r['_error']})")
        return
    print(f"  titulo: {r.get('title')}")
    print(f"  nome:   {r.get('name')}")
    print(f"  notas:  {(r.get('notes') or '')[:160]}")
    resources = r.get("resources", [])
    print(f"  recursos: {len(resources)}")
    for res in resources[:20]:
        name = res.get("name", "")
        url = res.get("url", "")
        fmt = res.get("format", "")
        size = res.get("size", "")
        print(f"    - [{fmt:>6}] {name[:70]}")
        print(f"      {url}")


def search(q):
    print(f"\n=== package_search: '{q}' ===")
    results = package_search(q)
    if not results:
        print("  nenhum resultado")
        return
    for r in results:
        print(f"  - {r.get('name')}  |  {r.get('title')}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--uf", default="MG")
    p.add_argument("--search", default=None)
    args = p.parse_args()

    if args.search:
        search(args.search)
        return

    ano, uf = args.ano, args.uf.upper()

    # Palpites de ids, variando por ano e por padrão de nome do TSE.
    ids = [
        f"eleitorado-local-de-votacao-{ano}",
        f"eleicoes-{ano}-locais-de-votacao",
        f"locais-de-votacao-{ano}",
        f"eleitorado-locais-de-votacao-{ano}",
        f"local-de-votacao-{ano}",
        f"locais-votacao-{ano}",
        f"eleitorado-local-votacao-{ano}",
        f"perfil-eleitorado-{ano}",
    ]
    for ds in ids:
        probe_dataset(ds)

    # Buscas textuais amplas para descobrir o nome certo
    for q in ["locais de votação", "local de votação", f"locais votação {ano}"]:
        search(q)


if __name__ == "__main__":
    main()