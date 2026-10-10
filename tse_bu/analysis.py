"""Agregação, ranking de abstenção e cálculo de potencial de virada."""

import pandas as pd

TOP_N = 50


def _votos_validos(votos: dict) -> int:
    return sum(q for k, q in votos.items() if k not in ("Branco", "Nulo"))


def montar_tabela(secoes: dict, candidatos: dict, nr_cand1: str, nr_cand2: str) -> pd.DataFrame:
    """Monta o DataFrame consolidado por seção.

    Métricas principais:
      abstencao_pct          -> % de eleitores aptos que faltaram
      turnout_pct            -> % de comparecimento
      invalid_pct            -> % de brancos+nulos sobre comparecimentos
      validos_por_apto       -> % de votos válidos sobre eleitores aptos (métrica "dura")
      dif_pct_validos        -> diferença percentual entre cand1 e cand2
      potencial_virada       -> abstencao_rate * (1 - |dif_pp|)  (matemático)
      prioridade_mobilizacao -> abstencoes_absolutas * (1 - |dif_pp|)  (intuitivo)
    """
    linhas = []
    for (zona, secao), s in secoes.items():
        v = s["votos"]
        aptos = s["aptos"]
        comp = s["comparecimento"]
        abst = s["abstencoes"]
        validos = _votos_validos(v)
        v1, v2 = v.get(nr_cand1, 0), v.get(nr_cand2, 0)
        brancos, nulos = v.get("Branco", 0), v.get("Nulo", 0)

        abst_r = abst / aptos if aptos else 0.0
        turnout_r = comp / aptos if aptos else 0.0
        invalid_r = (brancos + nulos) / comp if comp else 0.0
        validos_por_apto_r = validos / aptos if aptos else 0.0
        dif_pp = abs(v1 - v2) / validos if validos else 0.0

        # Sanity check: candidate votes + others should equal valid votes
        consistente = (v1 + v2) <= validos

        linhas.append({
            "zona": zona,
            "secao": int(secao),
            "local_votacao": s["local"],
            "aptos": aptos,
            "comparecimentos": comp,
            "abstencoes": abst,
            "abstencao_pct": round(abst_r * 100, 2),
            "turnout_pct": round(turnout_r * 100, 2),
            "invalid_pct": round(invalid_r * 100, 2),
            "validos_por_apto": round(validos_por_apto_r * 100, 2),
            "votos_validos": validos,
            "brancos": brancos,
            "nulos": nulos,
            f"cand_{nr_cand1}": v1,
            f"cand_{nr_cand2}": v2,
            "outros_candidatos": max(validos - v1 - v2, 0),
            "dif_votos": v1 - v2,
            "dif_pct_validos": round(dif_pp * 100, 2),
            "potencial_virada": round(abst_r * (1 - dif_pp), 4),
            "prioridade_mobilizacao": round(abst * (1 - dif_pp), 2),
            "consistencia": consistente,
        })
    df = pd.DataFrame(linhas)
    return df.sort_values("potencial_virada", ascending=False).reset_index(drop=True)


def resumo_cidade(df: pd.DataFrame, col_c1: str, col_c2: str,
                  label_c1: str = None, label_c2: str = None) -> dict:
    """Resumo agregado da cidade.

    Args:
        df:      DataFrame produzido por montar_tabela.
        col_c1:  nome da coluna do candidato 1 no df (ex.: "cand_22").
        col_c2:  nome da coluna do candidato 2 no df (ex.: "cand_13").
        label_c1, label_c2: nomes de exibição (ex.: "FLAVIO BOLSONARO").
                            Se omitidos, usa col_c1 / col_c2.
    """
    label_c1 = label_c1 or col_c1
    label_c2 = label_c2 or col_c2

    aptos = int(df["aptos"].sum())
    comp = int(df["comparecimentos"].sum())
    abst = int(df["abstencoes"].sum())
    validos = int(df["votos_validos"].sum())
    brancos = int(df["brancos"].sum())
    nulos = int(df["nulos"].sum())

    return {
        "secoes": int(len(df)),
        "aptos": aptos,
        "comparecimentos": comp,
        "abstencoes": abst,
        "abstencao_pct": round(abst / aptos * 100, 2) if aptos else 0.0,
        "turnout_pct": round(comp / aptos * 100, 2) if aptos else 0.0,
        "invalid_pct": round((brancos + nulos) / comp * 100, 2) if comp else 0.0,
        "validos_por_apto": round(validos / aptos * 100, 2) if aptos else 0.0,
        "votos_validos": validos,
        "brancos": brancos,
        "nulos": nulos,
        label_c1: int(df[col_c1].sum()),
        label_c2: int(df[col_c2].sum()),
        "top10_potencial": df.head(TOP_N),
    }