#!/usr/bin/env python3
"""Coletor de Boletins de Urna do TSE — uso geral.

Exemplos:
    python main.py --uf MG --cidade "OURO PRETO" --ano 2026 --turno 1 \
        --cand1 22 --cand2 13

    python main.py --uf BA --cidade "SALVADOR" --ano 2026 --turno 1 \
        --cand1 13 --cand2 22 --cargo governador
"""

import argparse
import os
import tempfile

from tse_bu import analysis, bu_data, config, downloader, pdfgen


def parse_args():
    p = argparse.ArgumentParser(description="Coleta boletins de urna (bweb) do TSE por município.")
    p.add_argument("--uf", required=True, help="UF de 2 letras (ex.: MG)")
    p.add_argument("--cidade", required=True, help="Nome do município (ex.: OURO PRETO)")
    p.add_argument("--ano", type=int, default=2026, help="Ano da eleição (default: 2026)")
    p.add_argument("--turno", type=int, default=1, choices=[1, 2], help="Turno (default: 1)")
    p.add_argument("--cargo", default="presidente",
                   choices=list(config.CARGOS.keys()) + ["outro"],
                   help="Cargo em disputa (default: presidente)")
    p.add_argument("--cargo-codigo", help="Código numérico do cargo (se --cargo outro)")
    p.add_argument("--cand1", required=True, help="Número do candidato 1 do 2º turno (ex.: 22)")
    p.add_argument("--cand2", required=True, help="Número do candidato 2 do 2º turno (ex.: 13)")
    p.add_argument("--saida", default="saida", help="Pasta de saída (default: ./saida)")
    p.add_argument("--workers", type=int, default=16, help="Conexões paralelas no download")
    p.add_argument("--cache", help="Pasta de cache do ZIP da UF (default: temp do sistema)")
    p.add_argument("--somente-csv", action="store_true", help="Pula a geração dos PDFs")
    return p.parse_args()


def main():
    args = parse_args()
    cargo_codigo = (args.cargo_codigo if args.cargo == "outro"
                    else config.CARGOS[args.cargo])
    os.makedirs(args.saida, exist_ok=True)

    print(f"[1/4] Localizando dataset bweb {args.ano}, {args.uf.upper()}, {args.turno}º turno...")
    url = config.find_bu_zip_url(args.ano, args.uf, args.turno)

    # Cache do ZIP da UF: pasta do usuário, em disco local (arquivos de
    # centenas de MB podem falhar em mounts de rede/restritos)
    cache = args.cache or os.path.join(tempfile.gettempdir(), "tse_bu_cache")
    os.makedirs(cache, exist_ok=True)
    zip_local = os.path.join(cache, os.path.basename(url))
    print(f"[2/4] Baixando {os.path.basename(url)} (pode levar alguns minutos)...")
    downloader.download(url, zip_local, workers=args.workers)

    print(f"[3/4] Filtrando município '{args.cidade}' (cargo {args.cargo}, código {cargo_codigo})...")
    dados = bu_data.extrair_municipio(zip_local, args.cidade, cargo_codigo)
    secoes, candidatos = dados["secoes"], dados["candidatos"]
    cidade = dados["municipio_encontrado"]

    print(f"[4/4] {len(secoes)} seções encontradas. Gerando análise...")
    df = analysis.montar_tabela(secoes, candidatos, args.cand1, args.cand2)

    # Nomes de exibição (podem ser "FLAVIO BOLSONARO", "LULA", etc.)
    nome_c1_display = candidatos.get(args.cand1, args.cand1)
    nome_c2_display = candidatos.get(args.cand2, args.cand2)

    # Nomes de coluna no DataFrame (formato cand_<nr>)
    col_c1 = f"cand_{args.cand1}"
    col_c2 = f"cand_{args.cand2}"
    # Compatibilidade: se o analysis.py voltar a gravar nomes numéricos ou
    # nomes de exibição, cai para o que existir de fato.
    if col_c1 not in df.columns:
        col_c1 = args.cand1 if args.cand1 in df.columns else nome_c1_display
    if col_c2 not in df.columns:
        col_c2 = args.cand2 if args.cand2 in df.columns else nome_c2_display

    slug = cidade.lower().replace(" ", "_")
    csv_path = os.path.join(args.saida, f"{slug}_urnas_{args.turno}turno_{args.ano}.csv")
    df.sort_values("abstencao_pct", ascending=False).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  -> CSV: {csv_path}")

    if not args.somente_csv:
        pasta_pdf = os.path.join(args.saida, f"boletins_{slug}")
        pdfgen.gerar_todos(cidade, args.uf, secoes, candidatos,
                           args.cargo.upper(), args.ano, args.turno, pasta_pdf)
        zip_pdf = os.path.join(args.saida, f"boletins_{slug}_{args.turno}turno_{args.ano}.zip")
        pdfgen.compactar(pasta_pdf, zip_pdf)
        print(f"  -> PDFs: {zip_pdf}")

    resumo = analysis.resumo_cidade(df, col_c1, col_c2,label_c1=nome_c1_display,label_c2=nome_c2_display,)
    print("\n================ RESUMO ================")
    print(f"Município: {cidade} - {args.uf.upper()} | {resumo['secoes']} urnas | "
          f"abstenção {resumo['abstencao_pct']}% ({resumo['abstencoes']} de {resumo['aptos']})")
    print(f"Válidos: {resumo['votos_validos']} | "
        f"{nome_c1_display}: {resumo[nome_c1_display]} | "
        f"{nome_c2_display}: {resumo[nome_c2_display]}")
    cols = ["zona", "secao", "abstencao_pct", col_c1, col_c2,
            "dif_pct_validos", "potencial_virada"]
    print(f"\nTop {analysis.TOP_N} seções por potencial de virada:")
    print(resumo["top10_potencial"][cols].to_string(index=False))
    print("\nDica: rode `streamlit run dashboard.py` para abrir o painel interativo.")


if __name__ == "__main__":
    main()
