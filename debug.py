#!/usr/bin/env python3
"""Diagnóstico: mostra as colunas e amostras dos dois lados do join.

Uso:
    python debug_join.py --uf MG --cidade "OURO PRETO" --cand1 22 --cand2 13
"""

import argparse
import csv
import io
import os
import zipfile

from tse_bu import bu_data, config, geodata


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--uf", default="MG")
    p.add_argument("--cidade", default="OURO PRETO")
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--turno", type=int, default=1)
    p.add_argument("--cand1", default="22")
    p.add_argument("--cand2", default="13")
    args = p.parse_args()

    # 1) Descobre o ZIP do bweb e extrai as seções
    url = config.find_bu_zip_url(args.ano, args.uf, args.turno)
    cache = os.path.join("/tmp", "tse_bu_cache")
    zip_path = os.path.join(cache, os.path.basename(url))

    print("\n===== bweb (seções) =====")
    dados = bu_data.extrair_municipio(zip_path, args.cidade, "1")
    secoes = dados["secoes"]
    print(f"  total de seções: {len(secoes)}")
    print("  primeiras 5 chaves (zona, secao):")
    for k in list(secoes.keys())[:5]:
        s = secoes[k]
        print(f"    {k}  local={s['local']!r}")
    print("  campos disponíveis numa seção:")
    print(f"    {list(list(secoes.values())[0].keys())}")

    # 2) Inspeciona o CSV cru do bweb para ver os nomes das colunas
    print("\n===== bweb (colunas cruas) =====")
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(csv_name) as fb, io.TextIOWrapper(fb, encoding="latin-1") as text:
            reader = csv.reader(text, delimiter=";")
            header = next(reader)
            print(f"  colunas do bweb ({len(header)}): {header}")
            print("  primeira linha de dados:")
            row = next(reader)
            for h, v in zip(header, row):
                print(f"    {h:<30} = {v!r}")
            print("  mais 3 linhas (só zona, seção, local):")
            for _ in range(3):
                row = next(reader)
                ix = {c: i for i, c in enumerate(header)}
                for cand in ("NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO",
                             "CD_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO",
                             "DS_LOCAL_VOTACAO", "NR_LOCAL"):
                    if cand in ix:
                        print(f"    {cand:<22} = {row[ix[cand]]!r}")

    # 3) Baixa e inspeciona o dataset de locais
    print("\n===== locais de votação =====")
    locais_raw = geodata._download_locais(args.ano, args.uf)
    if locais_raw is None:
        print("  não foi possível baixar")
        return
    print(f"  linhas: {len(locais_raw)}")
    print(f"  colunas ({len(locais_raw.columns)}): {list(locais_raw.columns)}")
    print("  primeiras 3 linhas (colunas mais prováveis):")
    provaveis = [c for c in locais_raw.columns
                 if any(k in c.upper() for k in
                        ("ZONA", "LOCAL", "LAT", "LON", "MUNICIPIO"))]
    print(f"  colunas de interesse: {provaveis}")
    print(locais_raw[provaveis].head(3).to_string())

    # 4) Distribuição: quantas zonas/locais existem de cada lado
    print("\n===== chaves de join candidatas =====")
    zonas_bweb = sorted({k[0] for k in secoes.keys()})
    print(f"  zonas no bweb (amostra): {zonas_bweb[:10]}")
    if "NR_ZONA" in locais_raw.columns:
        zonas_locais = sorted(set(locais_raw["NR_ZONA"].astype(str)))
        print(f"  zonas nos locais (amostra): {zonas_locais[:10]}")
        inter = set(map(str, zonas_bweb)) & set(zonas_locais)
        print(f"  interseção de zonas: {len(inter)}")


if __name__ == "__main__":
    main()