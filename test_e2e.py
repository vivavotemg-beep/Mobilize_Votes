#!/usr/bin/env python3
"""Teste ponta-a-ponta do TSE BU Collector.

Roda as camadas em ordem, do mais barato ao mais caro:

  1. Imports e versões
  2. config.find_bu_zip_url         (rede leve)
  3. downloader (HEAD only)         (rede leve)
  4. bu_data.extrair_municipio      (requer ZIP baixado)
  5. analysis.montar_tabela         (CPU)
  6. geodata.juntar_coordenadas     (rede leve, opcional)
  7. pdfgen.gerar_todos             (CPU, ~segundos)
  8. dashboard.py importa?         (import only, sem rodar Streamlit)

Uso:
    python test_e2e.py                        # defaults: MG / OURO PRETO / 2026 / 1T / 22 x 13
    python test_e2e.py --uf BA --cidade SALVADOR --ano 2026 --turno 1 --cand1 13 --cand2 44
    python test_e2e.py --skip-download        # usa ZIP já em cache
    python test_e2e.py --only 1,2,3           # só os passos 1..3
    python test_e2e.py --skip-geo             # não testa geodata
    python test_e2e.py --skip-pdf             # não gera PDFs
"""

import argparse
import importlib
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

# ---------------------------------------------------------------- helpers
RESET = "\033[0m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"


class Step:
    def __init__(self, n, label):
        self.n = n
        self.label = label
        self.t0 = None

    def __enter__(self):
        self.t0 = time.time()
        print(f"\n{BOLD}[{self.n}] {self.label}{RESET}")
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.time() - self.t0
        if exc_type is None:
            print(f"  {GREEN}OK{RESET} ({dt:.2f}s)")
            return False
        print(f"  {RED}FAIL{RESET} ({dt:.2f}s): {exc_type.__name__}: {exc}")
        traceback.print_exception(exc_type, exc, tb)
        return False  # não engole a exceção


def banner(txt):
    line = "=" * 60
    print(f"\n{BOLD}{line}\n{txt}\n{line}{RESET}")


# ---------------------------------------------------------------- steps
def step_1_imports():
    """Verifica que todas as dependências importam."""
    import pandas, plotly, streamlit  # noqa
    from tse_bu import analysis, bu_data, config, downloader, pdfgen  # noqa
    from tse_bu import geodata  # noqa
    print(f"  pandas   {pandas.__version__}")
    print(f"  plotly   {plotly.__version__}")
    print(f"  streamlit {streamlit.__version__}")


def step_2_config(ano, uf, turno):
    """Descobre a URL do bweb no portal CKAN."""
    from tse_bu import config
    url = config.find_bu_zip_url(ano, uf, turno)
    print(f"  URL: {url}")
    assert url.startswith("http"), "URL suspeita"
    assert url.lower().endswith(".zip"), "não é ZIP"
    return url


def step_3_download_head(url):
    """Só um HEAD para conferir tamanho — não baixa nada."""
    import urllib.request
    from tse_bu.config import USER_AGENT
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        size = int(r.headers.get("Content-Length", 0))
    print(f"  Content-Length: {size/1e6:.1f} MB")
    assert size > 1_000_000, "arquivo pequeno demais, algo errado"


def step_4_download(url, cache_dir, skip_download):
    """Baixa o ZIP (ou reutiliza do cache)."""
    from tse_bu import downloader
    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, os.path.basename(url))
    if skip_download and os.path.exists(dest):
        size = os.path.getsize(dest)
        print(f"  reutilizando {dest} ({size/1e6:.1f} MB)")
        return dest
    if skip_download:
        raise RuntimeError(f"--skip-download pedido, mas {dest} não existe")
    downloader.download(url, dest, workers=16)
    return dest


def step_5_parse(zip_path, cidade, cargo_codigo):
    """Filtra o município e o cargo no CSV bweb."""
    from tse_bu import bu_data
    dados = bu_data.extrair_municipio(zip_path, cidade, cargo_codigo)
    secoes = dados["secoes"]
    candidatos = dados["candidatos"]
    print(f"  município encontrado: {dados['municipio_encontrado']}")
    print(f"  seções: {len(secoes)}")
    print(f"  candidatos: {len(candidatos)}")
    if not secoes:
        raise RuntimeError("nenhuma seção")
    if len(candidatos) < 2:
        raise RuntimeError(f"só {len(candidatos)} candidato(s) — "
                           "confira --cargo / --cargo-codigo")
    return dados


def step_6_analysis(secoes, candidatos, cand1, cand2):
    """Monta o DataFrame com as novas métricas e valida o resumo."""
    from tse_bu import analysis

    df = analysis.montar_tabela(secoes, candidatos, cand1, cand2)

    # ---- colunas obrigatórias ----
    obrigatorias = [
        "zona", "secao", "local_votacao", "aptos", "comparecimentos",
        "abstencoes", "abstencao_pct", "turnout_pct", "invalid_pct",
        "validos_por_apto", "votos_validos", "brancos", "nulos",
        "outros_candidatos", "dif_votos", "dif_pct_validos",
        "potencial_virada", "prioridade_mobilizacao", "consistencia",
    ]
    faltando = [c for c in obrigatorias if c not in df.columns]
    if faltando:
        raise RuntimeError(f"colunas faltando no DataFrame: {faltando}")

    # ---- colunas de candidatos: aceita cand_<nr> OU nome numérico ----
    col_c1 = f"cand_{cand1}"
    col_c2 = f"cand_{cand2}"
    if col_c1 not in df.columns and cand1 in df.columns:
        col_c1 = cand1
    if col_c2 not in df.columns and cand2 in df.columns:
        col_c2 = cand2
    if col_c1 not in df.columns or col_c2 not in df.columns:
        raise RuntimeError(
            f"colunas de candidatos não encontradas. "
            f"Esperado '{col_c1}' e '{col_c2}'. "
            f"Colunas disponíveis: {list(df.columns)}"
        )
    print(f"  colunas de candidatos: {col_c1}, {col_c2}")

    print(f"  linhas: {len(df)}  colunas: {len(df.columns)}")
    print(f"  colunas: {list(df.columns)}")

    # ---- sanidade das métricas percentuais ----
    for col in ("abstencao_pct", "turnout_pct", "invalid_pct", "validos_por_apto"):
        s = df[col]
        if not ((s >= 0) & (s <= 100)).all():
            raise RuntimeError(f"{col} fora de [0,100]")
        print(f"  {col}: média {s.mean():.2f}%  "
              f"min {s.min():.2f}  max {s.max():.2f}")

    # ---- resumo usa as chaves corretas (cand_<nr>) ----
    nome_c1_exibicao = candidatos.get(cand1, cand1)
    nome_c2_exibicao = candidatos.get(cand2, cand2)
    resumo = analysis.resumo_cidade(df, col_c1, col_c2)
    print(f"  resumo: {resumo['secoes']} urnas  "
          f"abstenção {resumo['abstencao_pct']}%  "
          f"inválidos {resumo['invalid_pct']}%  "
          f"válidos/apto {resumo['validos_por_apto']}%")
    print(f"  {nome_c1_exibicao}: {resumo[col_c1]} votos  |  "
          f"{nome_c2_exibicao}: {resumo[col_c2]} votos")
    return df, resumo

def step_7_geodata(df, ano, uf):
    """Tenta juntar coordenadas (opcional — falha de rede é OK)."""
    from tse_bu import geodata
    try:
        df_geo = geodata.juntar_coordenadas(df, ano, uf)
    except Exception as exc:
        print(f"  {YELLOW}WARN{RESET}: geodata falhou ({exc}). "
              "Isso NÃO quebra o app — o dashboard cai para o heatmap "
              "por seção.")
        return False
    if "LATITUDE" not in df_geo.columns or df_geo["LATITUDE"].isna().all():
        print(f"  {YELLOW}WARN{RESET}: sem coordenadas para {ano}/{uf}. "
              "Mapa geográfico não vai render — heatmap por seção sim.")
        return False
    com_coord = df_geo["LATITUDE"].notna().sum()
    print(f"  seções com coordenadas: {com_coord}/{len(df_geo)} "
          f"({com_coord/len(df_geo)*100:.1f}%)")
    return True


def step_8_pdf(cidade, uf, secoes, candidatos, cargo, ano, turno, out_dir):
    """Gera PDFs de amostra (3 seções) e um ZIP."""
    from tse_bu import pdfgen
    amostra = dict(list(secoes.items())[:3])
    if not amostra:
        raise RuntimeError("sem seções para gerar PDF")
    pasta = os.path.join(out_dir, f"_test_pdf_{cidade.lower().replace(' ', '_')}")
    pdfgen.gerar_todos(cidade, uf, amostra, candidatos, cargo, ano, turno, pasta)
    pdfs = [f for f in os.listdir(pasta) if f.endswith(".pdf")]
    print(f"  PDFs gerados: {len(pdfs)} em {pasta}")
    assert pdfs, "nenhum PDF gerado"
    for p in pdfs[:3]:
        size = os.path.getsize(os.path.join(pasta, p))
        print(f"    {p}  ({size/1024:.1f} KB)")
    zip_path = os.path.join(out_dir, "_test_pdfs.zip")
    pdfgen.compactar(pasta, zip_path)
    print(f"  ZIP: {zip_path} ({os.path.getsize(zip_path)/1024:.1f} KB)")


def step_9_dashboard_import():
    """Verifica sintaxe/estrutura de dashboard.py SEM rodar Streamlit.

    Compila o arquivo (py_compile) e checa os padrões estruturais que já
    quebraram antes (tabs duplicadas / fora de ordem). Não executa o
    módulo, para não disparar st.stop()/st.error() fora do runtime.
    """
    import ast
    import py_compile

    path = "dashboard.py"
    if not os.path.exists(path):
        raise RuntimeError(f"{path} não encontrado no cwd")

    # 1) sintaxe
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as exc:
        raise RuntimeError(f"sintaxe inválida em {path}: {exc}") from exc
    print("  sintaxe OK")

    # 2) estrutura mínima esperada
    with open(path, encoding="utf-8") as f:
        src = f.read()

    expected_markers = [
        "with tab1:", "with tab2:", "with tab3:", "with tab4:", "with tab5:",
        'st.tabs(',
        '"🎯 Onde mobilizar"',
        '"🗺️ Mapa geográfico"',
        '"🔥 Heatmap por seção"',
        '"📊 Comparação"',
        '"📋 Tabela"',
        "from tse_bu import geodata",
    ]
    faltando = [m for m in expected_markers if m not in src]
    if faltando:
        raise RuntimeError(f"marcadores faltando em dashboard.py: {faltando}")
    print("  marcadores estruturais OK")

    # 3) tabs únicos (o bug clássico do copy-paste)
    for n in range(1, 6):
        needle = f"with tab{n}:"
        cnt = src.count(needle)
        if cnt != 1:
            raise RuntimeError(
                f"esperado 1× '{needle}' em dashboard.py, encontrado {cnt}×")
    print("  tabs únicos OK (1× cada)")

    # 4) AST: confirma que as chamadas obrigatórias existem
    tree = ast.parse(src)
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    for must in ("set_page_config", "tabs", "scatter", "imshow"):
        if must not in calls:
            raise RuntimeError(f"dashboard.py não chama st.{must}()")
    print(f"  chamadas essenciais OK: {sorted(must for must in calls if must in {'set_page_config','tabs','scatter','imshow'})}")


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="Teste ponta-a-ponta do TSE BU.")
    p.add_argument("--uf", default="MG")
    p.add_argument("--cidade", default="OURO PRETO")
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--cargo", default="presidente")
    p.add_argument("--cargo-codigo", default=None)
    p.add_argument("--cand1", default="22")
    p.add_argument("--cand2", default="13")
    p.add_argument("--cache", default=None,
                   help="pasta do ZIP (default: tempdir/tse_bu_cache)")
    p.add_argument("--saida", default="saida_test")
    p.add_argument("--only", default=None,
                   help="ex.: 1,2,3 — roda só esses passos")
    p.add_argument("--skip-download", action="store_true",
                   help="não baixa; exige ZIP já em cache")
    p.add_argument("--skip-geo", action="store_true")
    p.add_argument("--skip-pdf", action="store_true")
    args = p.parse_args()

    from tse_bu import config
    cargo_codigo = (args.cargo_codigo if args.cargo == "outro"
                    else config.CARGOS[args.cargo])

    cache = args.cache or os.path.join(tempfile.gettempdir(), "tse_bu_cache")
    os.makedirs(args.saida, exist_ok=True)

    only = set(int(x) for x in args.only.split(",")) if args.only else None

    def should(n):
        return only is None or n in only

    banner(f"E2E  uf={args.uf}  cidade={args.cidade}  ano={args.ano}  "
           f"turno={args.turno}  cargo={args.cargo}({cargo_codigo})  "
           f"cand1={args.cand1}  cand2={args.cand2}")

    url = None
    zip_path = None
    secoes = None
    candidatos = None
    df = None

    try:
        if should(1):
            with Step(1, "Imports e versões"):
                step_1_imports()

        if should(2):
            with Step(2, "config.find_bu_zip_url"):
                url = step_2_config(args.ano, args.uf, args.turno)

        if should(3) and url:
            with Step(3, "HEAD do ZIP (só tamanho)"):
                step_3_download_head(url)

        if should(4) and url:
            with Step(4, "Download do ZIP (paralelo)"):
                zip_path = step_4_download(url, cache, args.skip_download)

        # Passos 5+ precisam do ZIP; se foi pulado, tenta achar em cache
        if zip_path is None and url is not None:
            cand = os.path.join(cache, os.path.basename(url))
            if os.path.exists(cand):
                zip_path = cand
        if zip_path is None:
            # tenta achar qualquer bweb do UF na cache
            import glob as _g
            hits = _g.glob(os.path.join(cache, f"bweb_{args.turno}t_"
                                        f"{args.uf.upper()}_*.zip"))
            if hits:
                zip_path = hits[0]
                print(f"  usando ZIP em cache: {zip_path}")

        if should(5) and zip_path:
            with Step(5, "bu_data.extrair_municipio"):
                d = step_5_parse(zip_path, args.cidade, cargo_codigo)
                secoes, candidatos = d["secoes"], d["candidatos"]

        if should(6) and secoes is not None:
            with Step(6, "analysis.montar_tabela (novas métricas)"):
                df, resumo = step_6_analysis(secoes, candidatos,
                                             args.cand1, args.cand2)

        if should(7) and df is not None and not args.skip_geo:
            with Step(7, "geodata.juntar_coordenadas"):
                step_7_geodata(df, args.ano, args.uf)
        elif args.skip_geo:
            print(f"\n{BOLD}[7] geodata{RESET} — pulado (--skip-geo)")

        if should(8) and secoes is not None and not args.skip_pdf:
            with Step(8, "pdfgen (amostra de 3 seções)"):
                step_8_pdf(args.cidade, args.uf, secoes, candidatos,
                           args.cargo.upper(), args.ano, args.turno,
                           args.saida)
        elif args.skip_pdf:
            print(f"\n{BOLD}[8] pdfgen{RESET} — pulado (--skip-pdf)")

        if should(9):
            with Step(9, "importar dashboard.py"):
                step_9_dashboard_import()

        banner(f"{GREEN}TODOS OS PASSOS OK{RESET}")
        print("\nPróximos passos:")
        print("  1. Rode o pipeline real:")
        print(f"     python main.py --uf {args.uf} --cidade \"{args.cidade}\" "
              f"--ano {args.ano} --turno {args.turno} "
              f"--cand1 {args.cand1} --cand2 {args.cand2} --somente-csv")
        print("  2. Suba o dashboard:")
        print(f"     streamlit run dashboard.py")
        print("     Na barra lateral, configure ano "
              f"({args.ano}) e UF ({args.uf.upper()}) para o mapa.")
        return 0

    except KeyboardInterrupt:
        print(f"\n{YELLOW}interrompido pelo usuário{RESET}")
        return 130
    except Exception as exc:
        banner(f"{RED}FALHOU{RESET}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())