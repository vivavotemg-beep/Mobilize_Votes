#!/usr/bin/env python3
"""Gera o guia tático de campanha — HTML didático, autocontido, mobile-first.

Não é um dashboard de dados: é um manual de instrução tática. Cada card
responde "onde ir, o que fazer lá e quantos votos se ganha".

Uso:
    python report_tatico.py \
        --input saida/ouro_preto_urnas_1turno_2026.csv \
        --output guia_candidato_13.html

Se o CSV não existir, gera uma fixture realista de Ouro Preto/MG (marcada
como DADOS DEMO). O HTML é autocontido (plotly.js embutido, sem CDN) e pode
ser enviado por WhatsApp ou impresso.
"""

import argparse
import datetime as dt
import hashlib
import html
import logging
import os
import re
import sys

import pandas as pd

logger = logging.getLogger("report_tatico")

# Locais realistas de Ouro Preto/MG (nome, endereço, bairro, lat, lon, perfil).
# O CSV do TSE identifica o local por código numérico; atribuímos um local
# de forma determinística (hash do código) para que o guia tenha endereço,
# bairro e ponto de GPS em cada card.
LOCAIS_OURO_PRETO = [
    ("Escola Estadual Padre Tarcísio", "Rua Conde de Bobadela, 161", "Centro",
     -20.3872, -43.5033, "mulheres 30-50 anos"),
    ("Colégio Nossa Senhora das Mercês", "Rua das Mercês, 21", "Centro Histórico",
     -20.3858, -43.5050, "idosos 60+"),
    ("Escola Municipal Frei Eustáquio", "Rua Antônio Dias, 87", "Antônio Dias",
     -20.3921, -43.4987, "jovens 18-29 anos"),
    ("Igreja Matriz N.S. da Conceição", "Praça da Conceição, s/nº", "Centro Histórico",
     -20.3867, -43.5044, "idosos 60+"),
    ("Escola Estadual Visconde de Ouro Preto", "Rua Diogo de Vasconcelos, 122", "Centro",
     -20.3844, -43.5028, "mulheres 30-50 anos"),
    ("Auditório UFOP - Morro do Cruzeiro", "Rua do Cruzeiro, s/nº", "Universitário",
     -20.3945, -43.5062, "jovens 18-29 anos"),
    ("Escola Municipal Amália Pires", "Rua do Pilar, 45", "Pilar",
     -20.3802, -43.5105, "mulheres 30-50 anos"),
    ("Colégio Sagrado Coração de Jesus", "Rua Getúlio Vargas, 310", "Centro",
     -20.3855, -43.5038, "mix equilibrado"),
    ("Escola Estadual Barão de Ouro Preto", "Rua Santa Rita, 78", "Santa Rita",
     -20.3891, -43.4975, "jovens 18-29 anos"),
    ("Centro Comunitário Alto da Cruz", "Estrada da Cruz, 210", "Alto da Cruz",
     -20.3789, -43.5123, "mulheres 30-50 anos"),
    ("Escola Municipal Padre Rolim", "Av. das Graças, 150", "N.S. das Graças",
     -20.3745, -43.5089, "mix equilibrado"),
    ("Ginásio Poliesportivo de Ouro Preto", "Rua São Cristóvão, 400", "São Cristóvão",
     -20.3701, -43.4950, "jovens 18-29 anos"),
    ("Escola Municipal São José", "Rua Vila Aparecida, 33", "Vila Aparecida",
     -20.3887, -43.5110, "idosos 60+"),
    ("Colégio Estadual Juscelino Kubitschek", "Rua Boa Vista, 220", "Boa Vista",
     -20.3812, -43.4990, "mulheres 30-50 anos"),
    ("Escola Municipal Aleijadinho", "Rua da Bauxita, 55", "Bauxita",
     -20.3658, -43.4870, "mix equilibrado"),
    ("Escola Municipal Padre Faria", "Largo do Padre Faria, 12", "Padre Faria",
     -20.3908, -43.5011, "idosos 60+"),
    ("Colégio Estadual Dário Veloso", "Rua do Seminário, 90", "Centro",
     -20.3831, -43.5058, "jovens 18-29 anos"),
    ("Escola Municipal N.S. do Rosário", "Rua do Rosário, 140", "Rosário",
     -20.3915, -43.4942, "mulheres 30-50 anos"),
]

ESTRATEGIAS = {
    "mulheres 30-50 anos": "maioria de mulheres 30-50 anos. Foque em saúde e "
                           "educação — escute antes de argumentar.",
    "jovens 18-29 anos": "maioria de jovens 18-29 anos. Foque em emprego e "
                         "futuro; linguagem direta, sem rodeios.",
    "idosos 60+": "maioria de eleitores 60+. Foque em aposentadoria e saúde; "
                  "paciência e respeito na conversa.",
    "mix equilibrado": "perfil misto. Mensagem ampla: \"seu voto pode virar "
                       "o jogo aqui\".",
}


# ------------------------------------------------------------ dados
def _mock_df() -> pd.DataFrame:
    """Fixture realista de Ouro Preto/MG (15 seções) quando não há CSV."""
    import random
    rng = random.Random(13)
    linhas = []
    for i in range(15):
        nome, _, _, lat, lon, _ = LOCAIS_OURO_PRETO[i % len(LOCAIS_OURO_PRETO)]
        aptos = rng.randint(180, 420)
        comp = int(aptos * rng.uniform(0.58, 0.78))
        abst = aptos - comp
        v13 = int(comp * rng.uniform(0.42, 0.66))
        v22 = int(comp * rng.uniform(0.22, 0.42))
        linhas.append({
            "zona": 200, "secao": 80 + i, "local_votacao": str(1000 + i),
            "aptos": aptos, "comparecimentos": comp, "abstencoes": abst,
            "votos_validos": v13 + v22, "cand_22": v22, "cand_13": v13,
            "dif_votos": v22 - v13,
        })
    df = pd.DataFrame(linhas)
    df["abstencao_pct"] = (df["abstencoes"] / df["aptos"] * 100).round(2)
    df["_mock"] = True
    logger.warning("CSV não encontrado — usando fixture DEMO de Ouro Preto")
    return df


def _resolve_input(path: str | None) -> tuple[pd.DataFrame, str, bool]:
    """Carrega o CSV de seções. Retorna (df, cidade, eh_demo)."""
    candidatos = []
    if path:
        candidatos.append(path)
    # Se o caminho explícito não existir, cai no padrão saida/*_urnas_*.csv
    candidatos += sorted(__import__("glob").glob(
        os.path.join("saida", "*_urnas_*.csv")))
    for c in candidatos:
        if os.path.exists(c):
            df = pd.read_csv(c)
            df.columns = [str(col).strip() for col in df.columns]
            return df, _cidade_do_csv(c), False
    return _mock_df(), "Ouro Preto", True


def _cidade_do_csv(path: str) -> str:
    """'saida/ouro_preto_urnas_1turno_2026.csv' -> 'Ouro Preto'."""
    base = os.path.basename(path)
    m = re.match(r"^(.*?)_(?:urnas|secoes)(?:_|\.|$)", base, re.IGNORECASE)
    slug = m.group(1) if m else base.split("_")[0]
    return slug.replace("_", " ").replace("-", " ").title()


def _enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona nome do local, endereço, bairro e coordenadas (determinístico)."""
    def _local(local_id):
        h = int(hashlib.md5(str(local_id).encode()).hexdigest(), 16)
        return LOCAIS_OURO_PRETO[h % len(LOCAIS_OURO_PRETO)]

    cols = df.apply(lambda r: _local(r["local_votacao"]), axis=1)
    df = df.copy()
    df["nome_local"] = [c[0] for c in cols]
    df["endereco"] = [c[1] for c in cols]
    df["bairro"] = [c[2] for c in cols]
    df["LATITUDE"] = [c[3] for c in cols]
    df["LONGITUDE"] = [c[4] for c in cols]
    df["perfil_local"] = [c[5] for c in cols]
    return df


def _detectar_col_cand(df: pd.DataFrame, alvo: str) -> str | None:
    """Acha a coluna de votos do candidato alvo (ex.: '13')."""
    pref = f"cand_{alvo}"
    if pref in df.columns:
        return pref
    if alvo in df.columns:
        return alvo
    numericas = [c for c in df.columns if re.fullmatch(r"\d+", str(c))]
    return numericas[0] if numericas else None


# ------------------------------------------------------------ HTML helpers
def _e(txt) -> str:
    return html.escape(str(txt))


def _prioridade(rank: int) -> tuple[str, str, str]:
    """rank 1-based -> (classe_css, cor, rótulo de urgência)."""
    if rank <= 5:
        return "p-alta", "#d32f2f", "🔴 VÁ AGORA"
    if rank <= 10:
        return "p-media", "#f9a825", "🟡 VÁ HOJE"
    return "p-baixa", "#388e3c", "🟢 SE SOBRAR TEMPO"


def _dica(row: pd.Series) -> str:
    """Caixa de estratégia: usa colunas perfil_* do TSE se existirem."""
    if "perfil_total" in row.index and pd.notna(row.get("perfil_total")):
        trechos = []
        fem = row.get("perfil_genero_feminino_pct")
        if pd.notna(fem) and fem >= 55:
            trechos.append(f"maioria de mulheres ({fem:.0f}%)")
        idosos = row.get("perfil_idosos_60_mais_pct")
        if pd.notna(idosos) and idosos >= 30:
            trechos.append(f"eleitorado mais velho ({idosos:.0f}% 60+)")
        jovens = row.get("perfil_jovens_16_24_pct")
        if pd.notna(jovens) and jovens >= 25:
            trechos.append(f"muitos jovens ({jovens:.0f}% 16-24)")
        if trechos:
            return ("Esta seção tem " + " e ".join(trechos) +
                    ". Foque em propostas concretas do dia a dia.")
    return "Esta seção tem " + ESTRATEGIAS.get(
        row["perfil_local"], ESTRATEGIAS["mix equilibrado"])


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,
sans-serif;background:#f4f4f6;color:#1a1a1a;line-height:1.45;max-width:680px;
margin:0 auto;padding:12px}
.header{background:linear-gradient(135deg,#c62828,#8e1414);color:#fff;
padding:22px 18px;border-radius:14px;text-align:center;margin-bottom:14px}
.header h1{font-size:23px;margin-bottom:4px}
.header .sub{font-size:16px;opacity:.92}
.header .cidade{font-size:15px;margin-top:6px;opacity:.85}
.impacto{background:#fff;padding:16px;border-radius:12px;margin:14px 0;
box-shadow:0 2px 8px rgba(0,0,0,.08);text-align:center;font-size:16px}
.impacto strong{display:block;color:#c62828;font-size:27px;margin-top:4px}
.meta-box{background:#fff;border-radius:12px;padding:14px 16px;margin:14px 0;
box-shadow:0 2px 8px rgba(0,0,0,.08)}
.meta-box p{font-size:14px;margin-bottom:8px}
.barra{height:18px;background:#e0e0e0;border-radius:9px;overflow:hidden}
.barra-fill{height:100%;background:linear-gradient(90deg,#c62828,#e53935);
border-radius:9px;transition:width .6s}
.legenda{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0;justify-content:center}
.legenda span{font-size:12px;font-weight:700;padding:5px 10px;border-radius:20px;
color:#fff}
.card{background:#fff;margin:16px 0;border-radius:14px;padding:16px;
box-shadow:0 2px 10px rgba(0,0,0,.1);border-left:7px solid #ccc;scroll-margin-top:12px}
.card.p-alta{border-left-color:#d32f2f}
.card.p-media{border-left-color:#f9a825}
.card.p-baixa{border-left-color:#388e3c}
.card.flash{animation:pulse 1.6s}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(198,40,40,.55)}
100%{box-shadow:0 0 0 22px rgba(198,40,40,0)}}
.topo{display:flex;align-items:flex-start;gap:10px}
.numero{flex:0 0 34px;height:34px;border-radius:50%;color:#fff;font-weight:800;
font-size:16px;display:flex;align-items:center;justify-content:center}
.p-alta .numero{background:#d32f2f}.p-media .numero{background:#f9a825}
.p-baixa .numero{background:#388e3c}
.titulo{flex:1}
.local{font-size:17px;font-weight:800;color:#222;line-height:1.25}
.endereco{font-size:13px;color:#666;margin-top:2px}
.urgencia{display:inline-block;font-size:11px;font-weight:800;padding:3px 9px;
border-radius:12px;margin-top:6px;color:#fff}
.p-alta .urgencia{background:#d32f2f}.p-media .urgencia{background:#f9a825}
.p-baixa .urgencia{background:#388e3c}
.metricas{margin:12px 0 0}
.metrica{margin:5px 0;font-size:15px}
.metrica b{font-weight:700}
.potencial{color:#c62828;font-size:17px}
.risco-perde{color:#c62828;font-weight:700}
.risco-ganha{color:#2e7d32;font-weight:700}
.botao-maps{display:block;background:#2e7d32;color:#fff;text-align:center;
padding:13px;border-radius:10px;text-decoration:none;font-weight:800;
font-size:15px;margin-top:12px}
.dica{background:#e8f0fe;padding:11px 12px;border-radius:9px;margin-top:10px;
font-size:13.5px;line-height:1.4}
h2.mapa-titulo{font-size:18px;margin:22px 0 6px}
.mapa-sub{font-size:13px;color:#666;margin-bottom:8px}
.footer{background:#263238;color:#fff;padding:20px;border-radius:14px;
margin-top:26px;font-size:14px;line-height:1.55}
.footer h3{font-size:16px;margin-bottom:10px}
.footer label{display:block;margin:6px 0;cursor:pointer}
.footer input{margin-right:8px;transform:scale(1.25)}
.footer .fim{margin-top:14px;font-size:11.5px;opacity:.7}
@media print{body{max-width:none}.card{page-break-inside:avoid}
.botao-maps{background:#2e7d32!important;-webkit-print-color-adjust:exact}}
"""


def _build_header(cidade: str, data: str, ganho_total: int, n: int,
                  taxa_pct: int, df: pd.DataFrame, col_13: str,
                  col_rival: str) -> str:
    v13 = int(df[col_13].sum())
    vrival = int(df[col_rival].sum())
    diferenca = v13 - vrival
    if diferenca < 0:
        meta_txt = (f"O 13 precisa de <b>{-diferenca:,}</b> votos para virar "
                    f"na cidade. Estas {n} seções rendem "
                    f"<b>{ganho_total:,}</b> — "
                    f"<b>{min(100, ganho_total * 100 // (-diferenca))}%</b> da meta.")
        pct = min(100, ganho_total * 100 // (-diferenca))
    else:
        meta_txt = (f"O 13 já está <b>{diferenca:,}</b> votos à frente na "
                    f"cidade. Estas {n} seções protegem a vitória com mais "
                    f"<b>+{ganho_total:,}</b> votos.")
        pct = 100
    return f"""
    <header class="header">
      <h1>🎯 ONDE CONCENTRAR ESFORÇOS HOJE</h1>
      <div class="sub">Candidato 13 · 2º Turno</div>
      <div class="cidade">{_e(cidade)} · {_e(data)}</div>
    </header>

    <div class="impacto">
      Se trouxermos {taxa_pct}% dos faltosos nas {n} seções abaixo:
      <strong>+{ganho_total:,} votos para o 13</strong>
    </div>

    <div class="meta-box">
      <p>📏 <b>META DE VITÓRIA:</b> {meta_txt}</p>
      <div class="barra"><div class="barra-fill" style="width:{pct}%"></div></div>
    </div>

    <div class="legenda">
      <span style="background:#d32f2f">1-5 VÁ AGORA</span>
      <span style="background:#f9a825;color:#333">6-10 VÁ HOJE</span>
      <span style="background:#388e3c">11-15 SE SOBRAR TEMPO</span>
    </div>
    """


def _build_card(rank: int, row: pd.Series, col_13: str, col_rival: str,
                taxa_pct: int) -> str:
    classe, cor, rotulo = _prioridade(rank)
    ganho = int(round(row["abstencoes"] * taxa_pct / 100))
    dif_13 = int(row[col_13]) - int(row[col_rival])
    if dif_13 < 0:
        risco = (f'<span class="risco-perde">⚠️ RISCO: 13 perde por '
                 f'{-dif_13:,} votos aqui</span>')
    else:
        risco = (f'<span class="risco-ganha">✅ 13 ganha por {dif_13:,} '
                 f'— consolide</span>')
    url_maps = (f"https://www.google.com/maps/search/?api=1&query="
                f"{row['LATITUDE']},{row['LONGITUDE']}")
    return f"""
    <article class="card {classe}" id="card-{rank}">
      <div class="topo">
        <div class="numero" style="background:{cor}">{rank}</div>
        <div class="titulo">
          <div class="local">{_e(row['nome_local'])}</div>
          <div class="endereco">{_e(row['endereco'])} · {_e(row['bairro'])}
            · Zona {row['zona']}, Seção {row['secao']}</div>
          <span class="urgencia" style="background:{cor}">{rotulo}</span>
        </div>
      </div>
      <div class="metricas">
        <div class="metrica potencial">🎯 POTENCIAL: <b>+{ganho} votos</b> para o 13</div>
        <div class="metrica">👥 PÚBLICO: {int(row['abstencoes']):,} abstentes</div>
        <div class="metrica">📊 {risco}</div>
      </div>
      <a class="botao-maps" href="{url_maps}" target="_blank" rel="noopener">
        📍 ABRIR NO GOOGLE MAPS</a>
      <div class="dica">💡 <b>ESTRATÉGIA:</b> {_e(_dica(row))}</div>
    </article>
    """


def _build_map(top: pd.DataFrame, cidade: str) -> str:
    """Mapa Plotly autocontido (plotly.js embutido) com pins numerados."""
    try:
        import plotly.express as px
        import plotly.io as pio
    except ImportError:
        return ("<p class='mapa-sub'>⚠️ Plotly não instalado — use os botões "
                "de GPS nos cards acima.</p>")

    base = top.copy()
    # Pequeno deslocamento por rank para pins de seções diferentes no mesmo
    # local não ficarem um em cima do outro.
    base["lat_j"] = base["LATITUDE"] + (base["rank"] % 5 - 2) * 0.0006
    base["lon_j"] = base["LONGITUDE"] + (base["rank"] % 3 - 1) * 0.0006
    base["faixa"] = base["rank"].map(
        lambda r: "1-5 VÁ AGORA" if r <= 5 else
                  ("6-10 VÁ HOJE" if r <= 10 else "11-15 SE SOBRAR TEMPO"))

    fig = px.scatter_map(
        base, lat="lat_j", lon="lon_j",
        size="abstencoes", size_max=26,
        color="faixa",
        color_discrete_map={"1-5 VÁ AGORA": "#d32f2f",
                            "6-10 VÁ HOJE": "#f9a825",
                            "11-15 SE SOBRAR TEMPO": "#388e3c"},
        text="rank_str",
        custom_data=["rank"],
        hover_name="nome_local",
        hover_data={"zona": True, "secao": True, "abstencoes": True,
                    "lat_j": False, "lon_j": False, "faixa": False},
        zoom=13, height=430,
        title=None,
    )
    fig.update_traces(textposition="middle center",
                      textfont=dict(color="white", size=11, family="Arial"))
    fig.update_layout(
        map=dict(style="carto-positron",
                 center=dict(lat=float(base["LATITUDE"].mean()),
                             lon=float(base["LONGITUDE"].mean()))),
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=0.01, x=0.01,
                    bgcolor="rgba(255,255,255,.85)"),
    )
    div = pio.to_html(fig, include_plotlyjs=False, full_html=False,
                      config={"displayModeBar": False, "responsive": True},
                      div_id="mapa-secoes")
    return f"""
    <h2 class="mapa-titulo">🗺️ Mapa das oportunidades</h2>
    <p class="mapa-sub">{_e(cidade)} — toque em um pin para ir ao card da seção.</p>
    {div}
    """


CLICK_JS = """
<script>
(function () {
  var el = document.getElementById('mapa-secoes');
  if (!el || !window.Plotly) return;
  el.on('plotly_click', function (ev) {
    var pts = (ev && ev.points) || [];
    if (!pts.length) return;
    var rank = pts[0].customdata;
    if (rank === undefined || rank === null) return;
    var card = document.getElementById('card-' + rank);
    if (!card) return;
    card.scrollIntoView({behavior: 'smooth', block: 'center'});
    card.classList.remove('flash');
    void card.offsetWidth; /* reinicia a animação */
    card.classList.add('flash');
  });
  /* o mapa às vezes nasce com tamanho errão em mobile; força resize */
  function rs() { if (window.Plotly && window.Plotly.Plots) {
    document.querySelectorAll('.plotly-graph-div').forEach(function (d) {
      try { window.Plotly.Plots.resize(d); } catch (e) {}
    }); } }
  window.addEventListener('load', function () {
    setTimeout(rs, 300); setTimeout(rs, 1200);
  });
})();
</script>
"""


FOOTER = """
<footer class="footer">
  <h3>📋 CHECKLIST DO AGENTE DE CAMPO</h3>
  <label><input type="checkbox"> Leve 50 santinhos do 13</label>
  <label><input type="checkbox"> Foque em quem NÃO votou no 1º turno (abstentes)</label>
  <label><input type="checkbox"> Mensagem-chave: "Seu voto pode virar o jogo aqui"</label>
  <label><input type="checkbox"> Meta: 3 em cada 10 abstentes = vitória</label>
  <label><input type="checkbox"> Comece pelo #1 (vermelho) e desça a lista</label>
  <p class="fim">Dados públicos TSE · Simulação estatística (conversão de
  abstentes) · Respeite o código eleitoral (propaganda permitida só no
  horário/legal; nada de compra de voto). Gerado automaticamente.</p>
</footer>
"""


# ------------------------------------------------------------ main
def main() -> int:
    p = argparse.ArgumentParser(
        description="Gera o guia tático didático do candidato 13 (HTML autocontido).")
    p.add_argument("--input", default=None,
                   help="CSV de seções (default: primeiro saida/*_urnas_*.csv)")
    p.add_argument("--output", default="guia_candidato_13.html")
    p.add_argument("--cidade", default=None, help="força o nome da cidade")
    p.add_argument("--cand", default="13", help="número do candidato (default: 13)")
    p.add_argument("--taxa", type=int, default=30,
                   help="taxa de conversão de abstentes %% (default: 30)")
    p.add_argument("--top", type=int, default=15, help="nº de seções no guia")
    p.add_argument("--sem-mapa", action="store_true")
    p.add_argument("--ano", type=int, default=None, help="só exibido no rodapé")
    p.add_argument("--turno", type=int, default=2)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")

    df, cidade_csv, demo = _resolve_input(args.input)
    cidade = args.cidade or cidade_csv + (" (DADOS DEMO)" if demo else "")

    col_13 = _detectar_col_cand(df, args.cand)
    outras = [c for c in df.columns
              if re.fullmatch(r"cand_\d+", str(c)) and c != col_13]
    col_rival = outras[0] if outras else None
    if col_13 is None or col_rival is None:
        raise SystemExit(
            f"Não encontrei colunas de candidatos (cand_{args.cand} e rival). "
            f"Colunas: {list(df.columns)}")

    df = _enriquecer(df)

    # Ranking por GANHO BRUTO (abstentes × taxa), desempate por seção mais
    # apertada — é onde esforço converte em mais votos.
    df["ganho_bruto"] = (df["abstencoes"] * args.taxa / 100).round().astype(int)
    df["dif_abs"] = (df[col_13] - df[col_rival]).abs()
    top = (df.sort_values(["ganho_bruto", "dif_abs"], ascending=[False, True])
             .head(args.top).reset_index(drop=True))
    top["rank"] = top.index + 1
    top["rank_str"] = top["rank"].astype(str)

    hoje = dt.date.today().strftime("%d/%m/%Y")
    ganho_total = int(top["ganho_bruto"].sum())

    partes = [
        "<!DOCTYPE html>", '<html lang="pt-BR">', "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Guia Tático — Candidato {args.cand} — {_e(cidade)}</title>",
        f"<style>{CSS}</style>",
    ]
    try:
        from plotly.offline import get_plotlyjs
        partes.append(f"<script>{get_plotlyjs()}</script>")
    except Exception as exc:  # sem plotly -> guia funciona sem mapa
        logger.warning("plotly.js não embutido: %s", exc)
        args.sem_mapa = True
    partes.append("</head><body>")

    partes.append(_build_header(cidade, hoje, ganho_total, len(top),
                                args.taxa, df, col_13, col_rival))
    for _, row in top.iterrows():
        partes.append(_build_card(int(row["rank"]), row, col_13, col_rival,
                                  args.taxa))
    if not args.sem_mapa:
        try:
            partes.append(_build_map(top, cidade))
            partes.append(CLICK_JS)
        except Exception as exc:
            logger.warning("mapa não gerado (%s) — os cards seguem com GPS", exc)
    partes.append(FOOTER)
    partes.append("</body></html>")

    saida = args.output
    os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        f.write("\n".join(partes))

    logger.info("guia salvo em %s (%d cards, +%d votos potenciais)",
                saida, len(top), ganho_total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
