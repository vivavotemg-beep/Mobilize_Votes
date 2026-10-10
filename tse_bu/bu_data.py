"""Leitura e filtragem do CSV 'bweb' (Boletim de Urna web) do TSE.

O arquivo é grande (GB por UF), então a leitura é feita em streaming,
sem carregar o CSV inteiro em memória.
"""

import csv
import io
import zipfile


def extrair_municipio(zip_path: str, cidade: str, cargo_codigo: str) -> dict:
    """Filtra o bweb da UF para um município + cargo.

    Args:
        zip_path:     ZIP bweb da UF baixado do portal de dados abertos.
        cidade:       nome do município (ex.: "OURO PRETO"). Case-insensitive.
        cargo_codigo: código numérico do cargo (1=Presidente, 3=Governador...).

    Returns:
        {
          "secoes": {(zona, secao): {aptos, comparecimento, abstencoes,
                                     tipo_urna, local, dt_bu, votos{...}}},
          "candidatos": {nr_votavel: nome},
          "municipio_encontrado": str,
        }
    """
    cidade = cidade.strip().upper()
    secoes: dict = {}
    candidatos: dict = {}

    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(csv_name) as fb, io.TextIOWrapper(fb, encoding="latin-1") as text:
            reader = csv.reader(text, delimiter=";")
            header = next(reader)
            ix = {c: i for i, c in enumerate(header)}

            municipio = None
            for row in reader:
                if row[ix["NM_MUNICIPIO"]].upper() != cidade:
                    continue
                if row[ix["CD_CARGO_PERGUNTA"]] != str(cargo_codigo):
                    continue
                municipio = row[ix["NM_MUNICIPIO"]]
                key = (row[ix["NR_ZONA"]], row[ix["NR_SECAO"]])
                sec = secoes.setdefault(key, {
                    "aptos": int(row[ix["QT_APTOS"]]),
                    "comparecimento": int(row[ix["QT_COMPARECIMENTO"]]),
                    "abstencoes": int(row[ix["QT_ABSTENCOES"]]),
                    "tipo_urna": row[ix["DS_TIPO_URNA"]],
                    "local": row[ix["NR_LOCAL_VOTACAO"]],
                    "dt_bu": row[ix["DT_EMISSAO_BU"]],
                    "votos": {},
                })
                tipo = row[ix["CD_TIPO_VOTAVEL"]]
                nr = row[ix["NR_VOTAVEL"]]
                qtd = int(row[ix["QT_VOTOS"]])
                label = nr if tipo == "1" else {"2": "Branco", "3": "Nulo"}.get(tipo, f"tipo{tipo}")
                sec["votos"][label] = qtd
                if tipo == "1":
                    candidatos[nr] = row[ix["NM_VOTAVEL"]]

    if not secoes:
        raise RuntimeError(
            f"Nenhuma seção encontrada para '{cidade}' (cargo {cargo_codigo}). "
            "Confira o nome do município, a UF e se a cidade tem esse cargo em disputa."
        )
    return {"secoes": secoes, "candidatos": candidatos,
            "municipio_encontrado": municipio}
