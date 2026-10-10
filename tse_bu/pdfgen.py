"""Geração de um PDF de Boletim de Urna por seção, a partir dos dados bweb.

Observação: o TSE só disponibiliza imagem escaneada do BU para urnas de
contingência. Para urnas normais, o "boletim" é a totalização dos dados —
que é o que estes PDFs reproduzem.
"""

import os
import zipfile

from fpdf import FPDF


def gerar_bu_pdf(cidade: str, uf: str, zona: str, secao: str, sec: dict,
                 candidatos: dict, cargo: str, ano: int, turno: int) -> FPDF:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, 12)
    pdf.add_page()
    pdf.set_font("helvetica", "B", 13)
    pdf.cell(0, 7, "JUSTICA ELEITORAL", align="C", ln=1)
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 6, f"Boletim de Urna - {ano} - {turno}o Turno", align="C", ln=1)
    pdf.ln(2)
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, f"Municipio: {cidade} - {uf.upper()}    Zona: {zona}    "
                   f"Secao: {secao}    Local: {sec['local']}", ln=1)
    pdf.cell(0, 5, f"Cargo: {cargo}    Urna: {sec['tipo_urna']}    "
                   f"BU emitido em: {sec['dt_bu']}", ln=1)
    pdf.ln(2)
    itens = sorted(sec["votos"].items(), key=lambda kv: -kv[1])
    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(15, 6, "Numero", border=1, fill=True)
    pdf.cell(105, 6, "Candidato", border=1, fill=True)
    pdf.cell(25, 6, "Votos", border=1, fill=True, ln=1)
    pdf.set_font("helvetica", "", 9)
    for nr, qtd in itens:
        pdf.cell(15, 5.4, str(nr), border=1)
        pdf.cell(105, 5.4, candidatos.get(nr, nr), border=1)
        pdf.cell(25, 5.4, str(qtd), border=1, ln=1)
    pdf.ln(3)
    pdf.set_font("helvetica", "B", 10)
    v = sec["votos"]
    brancos, nulos = v.get("Branco", 0), v.get("Nulo", 0)
    validos = sum(q for k, q in v.items() if k not in ("Branco", "Nulo"))
    for rotulo, valor in [("Eleitores aptos", sec["aptos"]),
                          ("Comparecimentos", sec["comparecimento"]),
                          ("Abstencoes", sec["abstencoes"]),
                          ("Votos validos", validos),
                          ("Votos brancos", brancos),
                          ("Votos nulos", nulos)]:
        pdf.cell(120, 6, rotulo, border=1)
        pdf.cell(25, 6, str(valor), border=1, ln=1)
    pdf.ln(2)
    pdf.set_font("helvetica", "I", 7)
    pdf.multi_cell(0, 4, "Documento gerado a partir dos dados oficiais de "
                         "Boletim de Urna do TSE (arquivo bweb, portal de "
                         "dados abertos). Urnas sem contingencia nao possuem "
                         "imagem escaneada do BU; os dados acima sao a "
                         "totalizacao oficial da urna.")
    return pdf


def gerar_todos(cidade: str, uf: str, secoes: dict, candidatos: dict,
                cargo: str, ano: int, turno: int, saida_dir: str) -> str:
    """Gera os PDFs em `saida_dir` e devolve o caminho."""
    os.makedirs(saida_dir, exist_ok=True)
    slug = cidade.lower().replace(" ", "_")
    for (zona, secao), sec in secoes.items():
        pdf = gerar_bu_pdf(cidade, uf, zona, secao, sec, candidatos,
                           cargo, ano, turno)
        nome = f"{slug}_z{zona}_s{int(secao):04d}_bu.pdf"
        pdf.output(os.path.join(saida_dir, nome))
    return saida_dir


def compactar(pasta: str, zip_saida: str) -> str:
    with zipfile.ZipFile(zip_saida, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(pasta)):
            z.write(os.path.join(pasta, fn), fn)
    return zip_saida
