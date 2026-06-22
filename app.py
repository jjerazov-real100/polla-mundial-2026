import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Polla Mundial 2026",
    page_icon="⚽",
    layout="wide",
)

# ── Estilos ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main { background: #0a0f1e; }

    .metric-card {
        background: linear-gradient(135deg, #1a1f3a 0%, #0d1226 100%);
        border: 1px solid #2a3060;
        border-radius: 12px;
        padding: 16px 12px;
        text-align: center;
    }
    .metric-card .label {
        color: #8891b4;
        font-size: 12px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 6px;
    }
    .metric-card .value {
        color: #ffffff;
        font-size: 28px;
        font-weight: 700;
    }

    .rank-table th {
        background: #1a1f3a !important;
        color: #8891b4 !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 12px 16px !important;
    }
    .rank-table td {
        padding: 14px 16px !important;
        border-bottom: 1px solid #1a1f3a !important;
        color: #e0e4f4 !important;
    }

    .pos-1 { color: #FFD700 !important; font-weight: 700; }
    .pos-2 { color: #C0C0C0 !important; font-weight: 700; }
    .pos-3 { color: #CD7F32 !important; font-weight: 700; }

    .pill {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
    }
    .pill-gold   { background: #3d3000; color: #FFD700; }
    .pill-silver { background: #2a2a2a; color: #C0C0C0; }
    .pill-bronze { background: #2d1a00; color: #CD7F32; }
    .pill-other  { background: #1a1f3a; color: #8891b4; }

    .score-chip {
        background: #0d1226;
        border: 1px solid #2a3060;
        border-radius: 6px;
        padding: 2px 8px;
        font-family: monospace;
        font-size: 13px;
        color: #e0e4f4;
    }
    .pts-badge {
        background: #0f2a1a;
        border: 1px solid #1a5c36;
        color: #4ade80;
        border-radius: 20px;
        padding: 2px 10px;
        font-size: 12px;
        font-weight: 600;
    }
    .pts-zero {
        background: #1a1520;
        border: 1px solid #2a1f35;
        color: #6b7280;
        border-radius: 20px;
        padding: 2px 10px;
        font-size: 12px;
    }

    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextInput"] label {
        color: #8891b4 !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }

    .stButton button {
        background: #1e3a8a !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        width: 100%;
    }
    .stButton button:hover {
        background: #2563eb !important;
    }

    h1, h2, h3 { color: #ffffff !important; }
    .stMarkdown p { color: #8891b4; }

    div[data-testid="stTab"] button {
        color: #8891b4 !important;
        font-weight: 500;
    }
    div[data-testid="stTab"] button[aria-selected="true"] {
        color: #ffffff !important;
        border-bottom-color: #3b82f6 !important;
    }
</style>
""", unsafe_allow_html=True)


# ── Conexión a Google Sheets ─────────────────────────────────────────────────
@st.cache_resource
def get_client():
    """Conecta con Google Sheets usando credenciales del secrets de Streamlit."""
    creds_dict = st.secrets["gcp_service_account"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


@st.cache_data(ttl=60)
def load_sheet(spreadsheet_id: str):
    """Carga todas las hojas del spreadsheet. Cache de 60 segundos."""
    client = get_client()
    sh = client.open_by_key(spreadsheet_id)

    predicciones_ws = sh.worksheet("Predicciones")
    resultados_ws   = sh.worksheet("Resultados")
    partidos_ws     = sh.worksheet("Partidos")

    pred_df = pd.DataFrame(predicciones_ws.get_all_records())
    res_df  = pd.DataFrame(resultados_ws.get_all_records())
    part_df = pd.DataFrame(partidos_ws.get_all_records())

    return pred_df, res_df, part_df


# ── Lógica de puntuación ─────────────────────────────────────────────────────
def _multiplicador_por_fase(fase):
    """
    A partir de 16avos en adelante, los puntos valen el doble.
    Fases: Grupos (x1), 16avos / Octavos / Cuartos / Semifinal /
    3er Puesto / Final (x2).
    """
    if not fase:
        return 1
    fase_norm = str(fase).strip().lower()
    if fase_norm in ("grupos",):
        return 1
    return 2


def _puntos_limpio(pl, pv, rl, rv, multiplicador=1):
    """
    Calcula puntos para una predicción vs resultado real
    (máximo 10 pts, o 20 pts si multiplicador=2).

      - Selección del ganador (o empate): 4 pts
      - Diferencia de gol exacta:          2 pts
      - Goles equipo local exactos:        1 pt
      - Goles equipo visita exactos:       1 pt
      - Marcador exacto (bono):            2 pts

    A partir de 16avos, todo el desglose se multiplica x2.
    """
    try:
        pl, pv, rl, rv = int(pl), int(pv), int(rl), int(rv)
    except (ValueError, TypeError):
        return 0

    pts = 0

    # Ganador/empate: 4 pts
    def resultado(l, v): return "L" if l > v else ("V" if l < v else "E")
    if resultado(pl, pv) == resultado(rl, rv):
        pts += 4

    # Diferencia de gol: 2 pts
    if (pl - pv) == (rl - rv):
        pts += 2

    # Goles equipo local: 1 pt
    if pl == rl:
        pts += 1

    # Goles equipo visita: 1 pt
    if pv == rv:
        pts += 1

    # Marcador exacto: 2 pts (adicionales)
    if pl == rl and pv == rv:
        pts += 2

    return min(pts, 10) * multiplicador


def _desglose_puntos(pl, pv, rl, rv, multiplicador=1):
    """
    Igual que _puntos_limpio, pero retorna el detalle componente por
    componente en vez de solo el total. Usado para mostrar el desglose
    expandible en la pestaña de Predicciones.

    Retorna una lista de tuplas (etiqueta, puntos, acertado: bool)
    Los puntos ya vienen multiplicados según la fase.
    """
    try:
        pl, pv, rl, rv = int(pl), int(pv), int(rl), int(rv)
    except (ValueError, TypeError):
        return []

    def resultado(l, v): return "L" if l > v else ("V" if l < v else "E")

    acierto_ganador  = resultado(pl, pv) == resultado(rl, rv)
    acierto_diferencia = (pl - pv) == (rl - rv)
    acierto_local    = pl == rl
    acierto_visita   = pv == rv
    acierto_exacto   = acierto_local and acierto_visita

    detalle = [
        ("Ganador o empate",      4 * multiplicador, acierto_ganador),
        ("Diferencia de gol",     2 * multiplicador, acierto_diferencia),
        ("Goles equipo local",    1 * multiplicador, acierto_local),
        ("Goles equipo visita",   1 * multiplicador, acierto_visita),
        ("Marcador exacto (bono)", 2 * multiplicador, acierto_exacto),
    ]
    return detalle


def calcular_ranking(pred_df, res_df, part_df=None):
    """
    Calcula el ranking general cruzando predicciones con resultados reales.
    Si se pasa part_df, se usa la columna 'fase' de cada partido para
    aplicar el multiplicador x2 a partir de 16avos.
    """
    if pred_df.empty or res_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # res_df debe tener: partido_id, goles_local, goles_visita
    resultados_dict = {
        row["partido_id"]: (row["goles_local"], row["goles_visita"])
        for _, row in res_df.iterrows()
        if row.get("goles_local") != "" and row.get("goles_visita") != ""
    }

    # Mapa partido_id -> fase, para saber el multiplicador de cada partido
    fase_dict = {}
    if part_df is not None and not part_df.empty:
        fase_col = [c for c in part_df.columns if "fase" in c.lower()]
        if fase_col:
            fase_dict = dict(zip(part_df["partido_id"], part_df[fase_col[0]]))

    ranking = {}
    detalles = []

    for _, row in pred_df.iterrows():
        participante = row["participante"]
        partido_id   = row["partido_id"]

        if partido_id not in resultados_dict:
            continue

        # Si el participante no llenó su predicción, no cuenta como jugado
        if row.get("pred_local") == "" or row.get("pred_visita") == "":
            continue

        rl, rv = resultados_dict[partido_id]
        multiplicador = _multiplicador_por_fase(fase_dict.get(partido_id))
        pts = _puntos_limpio(
            row["pred_local"], row["pred_visita"], rl, rv, multiplicador
        )

        if participante not in ranking:
            ranking[participante] = {"puntos": 0, "partidos": 0, "exactos": 0}

        ranking[participante]["puntos"]   += pts
        ranking[participante]["partidos"] += 1
        if pts == 10 * multiplicador:
            ranking[participante]["exactos"] += 1

        detalles.append({
            "participante": participante,
            "partido_id":   partido_id,
            "pred":         f"{row['pred_local']}-{row['pred_visita']}",
            "real":         f"{rl}-{rv}",
            "puntos":       pts,
        })

    if not ranking:
        return pd.DataFrame(), pd.DataFrame()

    rank_df = pd.DataFrame.from_dict(ranking, orient="index").reset_index()
    rank_df.columns = ["Participante", "Puntos", "Partidos jugados", "Marcadores exactos"]
    rank_df = rank_df.sort_values("Puntos", ascending=False).reset_index(drop=True)
    rank_df.index += 1

    det_df = pd.DataFrame(detalles)
    return rank_df, det_df


COMBINACIONES_495 = [
    {"grupos":["E","F","G","H","I","J","K","L"],"cruces":["3E","3J","3I","3F","3H","3G","3L","3K"]},
    {"grupos":["D","F","G","H","I","J","K","L"],"cruces":["3H","3G","3I","3D","3J","3F","3L","3K"]},
    {"grupos":["D","E","G","H","I","J","K","L"],"cruces":["3E","3J","3I","3D","3H","3G","3L","3K"]},
    {"grupos":["D","E","F","H","I","J","K","L"],"cruces":["3E","3J","3I","3D","3H","3F","3L","3K"]},
    {"grupos":["D","E","F","G","I","J","K","L"],"cruces":["3E","3G","3I","3D","3J","3F","3L","3K"]},
    {"grupos":["D","E","F","G","H","J","K","L"],"cruces":["3E","3G","3J","3D","3H","3F","3L","3K"]},
    {"grupos":["D","E","F","G","H","I","K","L"],"cruces":["3E","3G","3I","3D","3H","3F","3L","3K"]},
    {"grupos":["D","E","F","G","H","I","J","L"],"cruces":["3E","3G","3J","3D","3H","3F","3L","3I"]},
    {"grupos":["D","E","F","G","H","I","J","K"],"cruces":["3E","3G","3J","3D","3H","3F","3I","3K"]},
    {"grupos":["C","F","G","H","I","J","K","L"],"cruces":["3H","3G","3I","3C","3J","3F","3L","3K"]},
    {"grupos":["C","E","G","H","I","J","K","L"],"cruces":["3E","3J","3I","3C","3H","3G","3L","3K"]},
    {"grupos":["C","E","F","H","I","J","K","L"],"cruces":["3E","3J","3I","3C","3H","3F","3L","3K"]},
    {"grupos":["C","E","F","G","I","J","K","L"],"cruces":["3E","3G","3I","3C","3J","3F","3L","3K"]},
    {"grupos":["C","E","F","G","H","J","K","L"],"cruces":["3E","3G","3J","3C","3H","3F","3L","3K"]},
    {"grupos":["C","E","F","G","H","I","K","L"],"cruces":["3E","3G","3I","3C","3H","3F","3L","3K"]},
    {"grupos":["C","E","F","G","H","I","J","L"],"cruces":["3E","3G","3J","3C","3H","3F","3L","3I"]},
    {"grupos":["C","E","F","G","H","I","J","K"],"cruces":["3E","3G","3J","3C","3H","3F","3I","3K"]},
    {"grupos":["C","D","G","H","I","J","K","L"],"cruces":["3H","3G","3I","3C","3J","3D","3L","3K"]},
    {"grupos":["C","D","F","H","I","J","K","L"],"cruces":["3C","3J","3I","3D","3H","3F","3L","3K"]},
    {"grupos":["C","D","F","G","I","J","K","L"],"cruces":["3C","3G","3I","3D","3J","3F","3L","3K"]},
    {"grupos":["C","D","F","G","H","J","K","L"],"cruces":["3C","3G","3J","3D","3H","3F","3L","3K"]},
    {"grupos":["C","D","F","G","H","I","K","L"],"cruces":["3C","3G","3I","3D","3H","3F","3L","3K"]},
    {"grupos":["C","D","F","G","H","I","J","L"],"cruces":["3C","3G","3J","3D","3H","3F","3L","3I"]},
    {"grupos":["C","D","F","G","H","I","J","K"],"cruces":["3C","3G","3J","3D","3H","3F","3I","3K"]},
    {"grupos":["C","D","E","H","I","J","K","L"],"cruces":["3E","3J","3I","3C","3H","3D","3L","3K"]},
    {"grupos":["C","D","E","G","I","J","K","L"],"cruces":["3E","3G","3I","3C","3J","3D","3L","3K"]},
    {"grupos":["C","D","E","G","H","J","K","L"],"cruces":["3E","3G","3J","3C","3H","3D","3L","3K"]},
    {"grupos":["C","D","E","G","H","I","K","L"],"cruces":["3E","3G","3I","3C","3H","3D","3L","3K"]},
    {"grupos":["C","D","E","G","H","I","J","L"],"cruces":["3E","3G","3J","3C","3H","3D","3L","3I"]},
    {"grupos":["C","D","E","G","H","I","J","K"],"cruces":["3E","3G","3J","3C","3H","3D","3I","3K"]},
    {"grupos":["C","D","E","F","I","J","K","L"],"cruces":["3C","3J","3E","3D","3I","3F","3L","3K"]},
    {"grupos":["C","D","E","F","H","J","K","L"],"cruces":["3C","3J","3E","3D","3H","3F","3L","3K"]},
    {"grupos":["C","D","E","F","H","I","K","L"],"cruces":["3C","3E","3I","3D","3H","3F","3L","3K"]},
    {"grupos":["C","D","E","F","H","I","J","L"],"cruces":["3C","3J","3E","3D","3H","3F","3L","3I"]},
    {"grupos":["C","D","E","F","H","I","J","K"],"cruces":["3C","3J","3E","3D","3H","3F","3I","3K"]},
    {"grupos":["C","D","E","F","G","J","K","L"],"cruces":["3C","3G","3E","3D","3J","3F","3L","3K"]},
    {"grupos":["C","D","E","F","G","I","K","L"],"cruces":["3C","3G","3E","3D","3I","3F","3L","3K"]},
    {"grupos":["C","D","E","F","G","I","J","L"],"cruces":["3C","3G","3E","3D","3J","3F","3L","3I"]},
    {"grupos":["C","D","E","F","G","I","J","K"],"cruces":["3C","3G","3E","3D","3J","3F","3I","3K"]},
    {"grupos":["C","D","E","F","G","H","K","L"],"cruces":["3C","3G","3E","3D","3H","3F","3L","3K"]},
    {"grupos":["C","D","E","F","G","H","J","L"],"cruces":["3C","3G","3J","3D","3H","3F","3L","3E"]},
    {"grupos":["C","D","E","F","G","H","J","K"],"cruces":["3C","3G","3J","3D","3H","3F","3E","3K"]},
    {"grupos":["C","D","E","F","G","H","I","L"],"cruces":["3C","3G","3E","3D","3H","3F","3L","3I"]},
    {"grupos":["C","D","E","F","G","H","I","K"],"cruces":["3C","3G","3E","3D","3H","3F","3I","3K"]},
    {"grupos":["C","D","E","F","G","H","I","J"],"cruces":["3C","3G","3J","3D","3H","3F","3E","3I"]},
    {"grupos":["B","F","G","H","I","J","K","L"],"cruces":["3H","3J","3B","3F","3I","3G","3L","3K"]},
    {"grupos":["B","E","G","H","I","J","K","L"],"cruces":["3E","3J","3I","3B","3H","3G","3L","3K"]},
    {"grupos":["B","E","F","H","I","J","K","L"],"cruces":["3E","3J","3B","3F","3I","3H","3L","3K"]},
    {"grupos":["B","E","F","G","I","J","K","L"],"cruces":["3E","3J","3B","3F","3I","3G","3L","3K"]},
    {"grupos":["B","E","F","G","H","J","K","L"],"cruces":["3E","3J","3B","3F","3H","3G","3L","3K"]},
    {"grupos":["B","E","F","G","H","I","K","L"],"cruces":["3E","3G","3B","3F","3I","3H","3L","3K"]},
    {"grupos":["B","E","F","G","H","I","J","L"],"cruces":["3E","3J","3B","3F","3H","3G","3L","3I"]},
    {"grupos":["B","E","F","G","H","I","J","K"],"cruces":["3E","3J","3B","3F","3H","3G","3I","3K"]},
    {"grupos":["B","D","G","H","I","J","K","L"],"cruces":["3H","3J","3B","3D","3I","3G","3L","3K"]},
    {"grupos":["B","D","F","H","I","J","K","L"],"cruces":["3H","3J","3B","3D","3I","3F","3L","3K"]},
    {"grupos":["B","D","F","G","I","J","K","L"],"cruces":["3I","3G","3B","3D","3J","3F","3L","3K"]},
    {"grupos":["B","D","F","G","H","J","K","L"],"cruces":["3H","3G","3B","3D","3J","3F","3L","3K"]},
    {"grupos":["B","D","F","G","H","I","K","L"],"cruces":["3H","3G","3B","3D","3I","3F","3L","3K"]},
    {"grupos":["B","D","F","G","H","I","J","L"],"cruces":["3H","3G","3B","3D","3J","3F","3L","3I"]},
    {"grupos":["B","D","F","G","H","I","J","K"],"cruces":["3H","3G","3B","3D","3J","3F","3I","3K"]},
    {"grupos":["B","D","E","H","I","J","K","L"],"cruces":["3E","3J","3B","3D","3I","3H","3L","3K"]},
    {"grupos":["B","D","E","G","I","J","K","L"],"cruces":["3E","3J","3B","3D","3I","3G","3L","3K"]},
    {"grupos":["B","D","E","G","H","J","K","L"],"cruces":["3E","3J","3B","3D","3H","3G","3L","3K"]},
    {"grupos":["B","D","E","G","H","I","K","L"],"cruces":["3E","3G","3B","3D","3I","3H","3L","3K"]},
    {"grupos":["B","D","E","G","H","I","J","L"],"cruces":["3E","3J","3B","3D","3H","3G","3L","3I"]},
    {"grupos":["B","D","E","G","H","I","J","K"],"cruces":["3E","3J","3B","3D","3H","3G","3I","3K"]},
    {"grupos":["B","D","E","F","I","J","K","L"],"cruces":["3E","3J","3B","3D","3I","3F","3L","3K"]},
    {"grupos":["B","D","E","F","H","J","K","L"],"cruces":["3E","3J","3B","3D","3H","3F","3L","3K"]},
    {"grupos":["B","D","E","F","H","I","K","L"],"cruces":["3E","3I","3B","3D","3H","3F","3L","3K"]},
    {"grupos":["B","D","E","F","H","I","J","L"],"cruces":["3E","3J","3B","3D","3H","3F","3L","3I"]},
    {"grupos":["B","D","E","F","H","I","J","K"],"cruces":["3E","3J","3B","3D","3H","3F","3I","3K"]},
    {"grupos":["B","D","E","F","G","J","K","L"],"cruces":["3E","3G","3B","3D","3J","3F","3L","3K"]},
    {"grupos":["B","D","E","F","G","I","K","L"],"cruces":["3E","3G","3B","3D","3I","3F","3L","3K"]},
    {"grupos":["B","D","E","F","G","I","J","L"],"cruces":["3E","3G","3B","3D","3J","3F","3L","3I"]},
    {"grupos":["B","D","E","F","G","I","J","K"],"cruces":["3E","3G","3B","3D","3J","3F","3I","3K"]},
    {"grupos":["B","D","E","F","G","H","K","L"],"cruces":["3E","3G","3B","3D","3H","3F","3L","3K"]},
    {"grupos":["B","D","E","F","G","H","J","L"],"cruces":["3H","3G","3B","3D","3J","3F","3L","3E"]},
    {"grupos":["B","D","E","F","G","H","J","K"],"cruces":["3H","3G","3B","3D","3J","3F","3E","3K"]},
    {"grupos":["B","D","E","F","G","H","I","L"],"cruces":["3E","3G","3B","3D","3H","3F","3L","3I"]},
    {"grupos":["B","D","E","F","G","H","I","K"],"cruces":["3E","3G","3B","3D","3H","3F","3I","3K"]},
    {"grupos":["B","D","E","F","G","H","I","J"],"cruces":["3H","3G","3B","3D","3J","3F","3E","3I"]},
    {"grupos":["B","C","G","H","I","J","K","L"],"cruces":["3H","3J","3B","3C","3I","3G","3L","3K"]},
    {"grupos":["B","C","F","H","I","J","K","L"],"cruces":["3H","3J","3B","3C","3I","3F","3L","3K"]},
    {"grupos":["B","C","F","G","I","J","K","L"],"cruces":["3I","3G","3B","3C","3J","3F","3L","3K"]},
    {"grupos":["B","C","F","G","H","J","K","L"],"cruces":["3H","3G","3B","3C","3J","3F","3L","3K"]},
    {"grupos":["B","C","F","G","H","I","K","L"],"cruces":["3H","3G","3B","3C","3I","3F","3L","3K"]},
    {"grupos":["B","C","F","G","H","I","J","L"],"cruces":["3H","3G","3B","3C","3J","3F","3L","3I"]},
    {"grupos":["B","C","F","G","H","I","J","K"],"cruces":["3H","3G","3B","3C","3J","3F","3I","3K"]},
    {"grupos":["B","C","E","H","I","J","K","L"],"cruces":["3E","3J","3B","3C","3I","3H","3L","3K"]},
    {"grupos":["B","C","E","G","I","J","K","L"],"cruces":["3E","3J","3B","3C","3I","3G","3L","3K"]},
    {"grupos":["B","C","E","G","H","J","K","L"],"cruces":["3E","3J","3B","3C","3H","3G","3L","3K"]},
    {"grupos":["B","C","E","G","H","I","K","L"],"cruces":["3E","3G","3B","3C","3I","3H","3L","3K"]},
    {"grupos":["B","C","E","G","H","I","J","L"],"cruces":["3E","3J","3B","3C","3H","3G","3L","3I"]},
    {"grupos":["B","C","E","G","H","I","J","K"],"cruces":["3E","3J","3B","3C","3H","3G","3I","3K"]},
    {"grupos":["B","C","E","F","I","J","K","L"],"cruces":["3E","3J","3B","3C","3I","3F","3L","3K"]},
    {"grupos":["B","C","E","F","H","J","K","L"],"cruces":["3E","3J","3B","3C","3H","3F","3L","3K"]},
    {"grupos":["B","C","E","F","H","I","K","L"],"cruces":["3E","3I","3B","3C","3H","3F","3L","3K"]},
    {"grupos":["B","C","E","F","H","I","J","L"],"cruces":["3E","3J","3B","3C","3H","3F","3L","3I"]},
    {"grupos":["B","C","E","F","H","I","J","K"],"cruces":["3E","3J","3B","3C","3H","3F","3I","3K"]},
    {"grupos":["B","C","E","F","G","J","K","L"],"cruces":["3E","3G","3B","3C","3J","3F","3L","3K"]},
    {"grupos":["B","C","E","F","G","I","K","L"],"cruces":["3E","3G","3B","3C","3I","3F","3L","3K"]},
    {"grupos":["B","C","E","F","G","I","J","L"],"cruces":["3E","3G","3B","3C","3J","3F","3L","3I"]},
    {"grupos":["B","C","E","F","G","I","J","K"],"cruces":["3E","3G","3B","3C","3J","3F","3I","3K"]},
    {"grupos":["B","C","E","F","G","H","K","L"],"cruces":["3E","3G","3B","3C","3H","3F","3L","3K"]},
    {"grupos":["B","C","E","F","G","H","J","L"],"cruces":["3H","3G","3B","3C","3J","3F","3L","3E"]},
    {"grupos":["B","C","E","F","G","H","J","K"],"cruces":["3H","3G","3B","3C","3J","3F","3E","3K"]},
    {"grupos":["B","C","E","F","G","H","I","L"],"cruces":["3E","3G","3B","3C","3H","3F","3L","3I"]},
    {"grupos":["B","C","E","F","G","H","I","K"],"cruces":["3E","3G","3B","3C","3H","3F","3I","3K"]},
    {"grupos":["B","C","E","F","G","H","I","J"],"cruces":["3H","3G","3B","3C","3J","3F","3E","3I"]},
    {"grupos":["B","C","D","H","I","J","K","L"],"cruces":["3H","3J","3B","3C","3I","3D","3L","3K"]},
    {"grupos":["B","C","D","G","I","J","K","L"],"cruces":["3I","3G","3B","3C","3J","3D","3L","3K"]},
    {"grupos":["B","C","D","G","H","J","K","L"],"cruces":["3H","3G","3B","3C","3J","3D","3L","3K"]},
    {"grupos":["B","C","D","G","H","I","K","L"],"cruces":["3H","3G","3B","3C","3I","3D","3L","3K"]},
    {"grupos":["B","C","D","G","H","I","J","L"],"cruces":["3H","3G","3B","3C","3J","3D","3L","3I"]},
    {"grupos":["B","C","D","G","H","I","J","K"],"cruces":["3H","3G","3B","3C","3J","3D","3I","3K"]},
    {"grupos":["B","C","D","F","I","J","K","L"],"cruces":["3C","3J","3B","3D","3I","3F","3L","3K"]},
    {"grupos":["B","C","D","F","H","J","K","L"],"cruces":["3C","3J","3B","3D","3H","3F","3L","3K"]},
    {"grupos":["B","C","D","F","H","I","K","L"],"cruces":["3C","3I","3B","3D","3H","3F","3L","3K"]},
    {"grupos":["B","C","D","F","H","I","J","L"],"cruces":["3C","3J","3B","3D","3H","3F","3L","3I"]},
    {"grupos":["B","C","D","F","H","I","J","K"],"cruces":["3C","3J","3B","3D","3H","3F","3I","3K"]},
    {"grupos":["B","C","D","F","G","J","K","L"],"cruces":["3C","3G","3B","3D","3J","3F","3L","3K"]},
    {"grupos":["B","C","D","F","G","I","K","L"],"cruces":["3C","3G","3B","3D","3I","3F","3L","3K"]},
    {"grupos":["B","C","D","F","G","I","J","L"],"cruces":["3C","3G","3B","3D","3J","3F","3L","3I"]},
    {"grupos":["B","C","D","F","G","I","J","K"],"cruces":["3C","3G","3B","3D","3J","3F","3I","3K"]},
    {"grupos":["B","C","D","F","G","H","K","L"],"cruces":["3C","3G","3B","3D","3H","3F","3L","3K"]},
    {"grupos":["B","C","D","F","G","H","J","L"],"cruces":["3C","3G","3B","3D","3H","3F","3L","3J"]},
    {"grupos":["B","C","D","F","G","H","J","K"],"cruces":["3H","3G","3B","3C","3J","3F","3D","3K"]},
    {"grupos":["B","C","D","F","G","H","I","L"],"cruces":["3C","3G","3B","3D","3H","3F","3L","3I"]},
    {"grupos":["B","C","D","F","G","H","I","K"],"cruces":["3C","3G","3B","3D","3H","3F","3I","3K"]},
    {"grupos":["B","C","D","F","G","H","I","J"],"cruces":["3H","3G","3B","3C","3J","3F","3D","3I"]},
    {"grupos":["B","C","D","E","I","J","K","L"],"cruces":["3E","3J","3B","3C","3I","3D","3L","3K"]},
    {"grupos":["B","C","D","E","H","J","K","L"],"cruces":["3E","3J","3B","3C","3H","3D","3L","3K"]},
    {"grupos":["B","C","D","E","H","I","K","L"],"cruces":["3E","3I","3B","3C","3H","3D","3L","3K"]},
    {"grupos":["B","C","D","E","H","I","J","L"],"cruces":["3E","3J","3B","3C","3H","3D","3L","3I"]},
    {"grupos":["B","C","D","E","H","I","J","K"],"cruces":["3E","3J","3B","3C","3H","3D","3I","3K"]},
    {"grupos":["B","C","D","E","G","J","K","L"],"cruces":["3E","3G","3B","3C","3J","3D","3L","3K"]},
    {"grupos":["B","C","D","E","G","I","K","L"],"cruces":["3E","3G","3B","3C","3I","3D","3L","3K"]},
    {"grupos":["B","C","D","E","G","I","J","L"],"cruces":["3E","3G","3B","3C","3J","3D","3L","3I"]},
    {"grupos":["B","C","D","E","G","I","J","K"],"cruces":["3E","3G","3B","3C","3J","3D","3I","3K"]},
    {"grupos":["B","C","D","E","G","H","K","L"],"cruces":["3E","3G","3B","3C","3H","3D","3L","3K"]},
    {"grupos":["B","C","D","E","G","H","J","L"],"cruces":["3H","3G","3B","3C","3J","3D","3L","3E"]},
    {"grupos":["B","C","D","E","G","H","J","K"],"cruces":["3H","3G","3B","3C","3J","3D","3E","3K"]},
    {"grupos":["B","C","D","E","G","H","I","L"],"cruces":["3E","3G","3B","3C","3H","3D","3L","3I"]},
    {"grupos":["B","C","D","E","G","H","I","K"],"cruces":["3E","3G","3B","3C","3H","3D","3I","3K"]},
    {"grupos":["B","C","D","E","G","H","I","J"],"cruces":["3H","3G","3B","3C","3J","3D","3E","3I"]},
    {"grupos":["B","C","D","E","F","J","K","L"],"cruces":["3C","3J","3B","3D","3E","3F","3L","3K"]},
    {"grupos":["B","C","D","E","F","I","K","L"],"cruces":["3C","3E","3B","3D","3I","3F","3L","3K"]},
    {"grupos":["B","C","D","E","F","I","J","L"],"cruces":["3C","3J","3B","3D","3E","3F","3L","3I"]},
    {"grupos":["B","C","D","E","F","I","J","K"],"cruces":["3C","3J","3B","3D","3E","3F","3I","3K"]},
    {"grupos":["B","C","D","E","F","H","K","L"],"cruces":["3C","3E","3B","3D","3H","3F","3L","3K"]},
    {"grupos":["B","C","D","E","F","H","J","L"],"cruces":["3C","3J","3B","3D","3H","3F","3L","3E"]},
    {"grupos":["B","C","D","E","F","H","J","K"],"cruces":["3C","3J","3B","3D","3H","3F","3E","3K"]},
    {"grupos":["B","C","D","E","F","H","I","L"],"cruces":["3C","3E","3B","3D","3H","3F","3L","3I"]},
    {"grupos":["B","C","D","E","F","H","I","K"],"cruces":["3C","3E","3B","3D","3H","3F","3I","3K"]},
    {"grupos":["B","C","D","E","F","H","I","J"],"cruces":["3C","3J","3B","3D","3H","3F","3E","3I"]},
    {"grupos":["B","C","D","E","F","G","K","L"],"cruces":["3C","3G","3B","3D","3E","3F","3L","3K"]},
    {"grupos":["B","C","D","E","F","G","J","L"],"cruces":["3C","3G","3B","3D","3J","3F","3L","3E"]},
    {"grupos":["B","C","D","E","F","G","J","K"],"cruces":["3C","3G","3B","3D","3J","3F","3E","3K"]},
    {"grupos":["B","C","D","E","F","G","I","L"],"cruces":["3C","3G","3B","3D","3E","3F","3L","3I"]},
    {"grupos":["B","C","D","E","F","G","I","K"],"cruces":["3C","3G","3B","3D","3E","3F","3I","3K"]},
    {"grupos":["B","C","D","E","F","G","I","J"],"cruces":["3C","3G","3B","3D","3J","3F","3E","3I"]},
    {"grupos":["B","C","D","E","F","G","H","L"],"cruces":["3C","3G","3B","3D","3H","3F","3L","3E"]},
    {"grupos":["B","C","D","E","F","G","H","K"],"cruces":["3C","3G","3B","3D","3H","3F","3E","3K"]},
    {"grupos":["B","C","D","E","F","G","H","J"],"cruces":["3H","3G","3B","3C","3J","3F","3D","3E"]},
    {"grupos":["B","C","D","E","F","G","H","I"],"cruces":["3C","3G","3B","3D","3H","3F","3E","3I"]},
    {"grupos":["A","F","G","H","I","J","K","L"],"cruces":["3H","3J","3I","3F","3A","3G","3L","3K"]},
    {"grupos":["A","E","G","H","I","J","K","L"],"cruces":["3E","3J","3I","3A","3H","3G","3L","3K"]},
    {"grupos":["A","E","F","H","I","J","K","L"],"cruces":["3E","3J","3I","3F","3A","3H","3L","3K"]},
    {"grupos":["A","E","F","G","I","J","K","L"],"cruces":["3E","3J","3I","3F","3A","3G","3L","3K"]},
    {"grupos":["A","E","F","G","H","J","K","L"],"cruces":["3E","3G","3J","3F","3A","3H","3L","3K"]},
    {"grupos":["A","E","F","G","H","I","K","L"],"cruces":["3E","3G","3I","3F","3A","3H","3L","3K"]},
    {"grupos":["A","E","F","G","H","I","J","L"],"cruces":["3E","3G","3J","3F","3A","3H","3L","3I"]},
    {"grupos":["A","E","F","G","H","I","J","K"],"cruces":["3E","3G","3J","3F","3A","3H","3I","3K"]},
    {"grupos":["A","D","G","H","I","J","K","L"],"cruces":["3H","3J","3I","3D","3A","3G","3L","3K"]},
    {"grupos":["A","D","F","H","I","J","K","L"],"cruces":["3H","3J","3I","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","F","G","I","J","K","L"],"cruces":["3I","3G","3J","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","F","G","H","J","K","L"],"cruces":["3H","3G","3J","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","F","G","H","I","K","L"],"cruces":["3H","3G","3I","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","F","G","H","I","J","L"],"cruces":["3H","3G","3J","3D","3A","3F","3L","3I"]},
    {"grupos":["A","D","F","G","H","I","J","K"],"cruces":["3H","3G","3J","3D","3A","3F","3I","3K"]},
    {"grupos":["A","D","E","H","I","J","K","L"],"cruces":["3E","3J","3I","3D","3A","3H","3L","3K"]},
    {"grupos":["A","D","E","G","I","J","K","L"],"cruces":["3E","3J","3I","3D","3A","3G","3L","3K"]},
    {"grupos":["A","D","E","G","H","J","K","L"],"cruces":["3E","3G","3J","3D","3A","3H","3L","3K"]},
    {"grupos":["A","D","E","G","H","I","K","L"],"cruces":["3E","3G","3I","3D","3A","3H","3L","3K"]},
    {"grupos":["A","D","E","G","H","I","J","L"],"cruces":["3E","3G","3J","3D","3A","3H","3L","3I"]},
    {"grupos":["A","D","E","G","H","I","J","K"],"cruces":["3E","3G","3J","3D","3A","3H","3I","3K"]},
    {"grupos":["A","D","E","F","I","J","K","L"],"cruces":["3E","3J","3I","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","E","F","H","J","K","L"],"cruces":["3H","3J","3E","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","E","F","H","I","K","L"],"cruces":["3H","3E","3I","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","E","F","H","I","J","L"],"cruces":["3H","3J","3E","3D","3A","3F","3L","3I"]},
    {"grupos":["A","D","E","F","H","I","J","K"],"cruces":["3H","3J","3E","3D","3A","3F","3I","3K"]},
    {"grupos":["A","D","E","F","G","J","K","L"],"cruces":["3E","3G","3J","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","E","F","G","I","K","L"],"cruces":["3E","3G","3I","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","E","F","G","I","J","L"],"cruces":["3E","3G","3J","3D","3A","3F","3L","3I"]},
    {"grupos":["A","D","E","F","G","I","J","K"],"cruces":["3E","3G","3J","3D","3A","3F","3I","3K"]},
    {"grupos":["A","D","E","F","G","H","K","L"],"cruces":["3H","3G","3E","3D","3A","3F","3L","3K"]},
    {"grupos":["A","D","E","F","G","H","J","L"],"cruces":["3H","3G","3J","3D","3A","3F","3L","3E"]},
    {"grupos":["A","D","E","F","G","H","J","K"],"cruces":["3H","3G","3J","3D","3A","3F","3E","3K"]},
    {"grupos":["A","D","E","F","G","H","I","L"],"cruces":["3H","3G","3E","3D","3A","3F","3L","3I"]},
    {"grupos":["A","D","E","F","G","H","I","K"],"cruces":["3H","3G","3E","3D","3A","3F","3I","3K"]},
    {"grupos":["A","D","E","F","G","H","I","J"],"cruces":["3H","3G","3J","3D","3A","3F","3E","3I"]},
    {"grupos":["A","C","G","H","I","J","K","L"],"cruces":["3H","3J","3I","3C","3A","3G","3L","3K"]},
    {"grupos":["A","C","F","H","I","J","K","L"],"cruces":["3H","3J","3I","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","F","G","I","J","K","L"],"cruces":["3I","3G","3J","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","F","G","H","J","K","L"],"cruces":["3H","3G","3J","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","F","G","H","I","K","L"],"cruces":["3H","3G","3I","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","F","G","H","I","J","L"],"cruces":["3H","3G","3J","3C","3A","3F","3L","3I"]},
    {"grupos":["A","C","F","G","H","I","J","K"],"cruces":["3H","3G","3J","3C","3A","3F","3I","3K"]},
    {"grupos":["A","C","E","H","I","J","K","L"],"cruces":["3E","3J","3I","3C","3A","3H","3L","3K"]},
    {"grupos":["A","C","E","G","I","J","K","L"],"cruces":["3E","3J","3I","3C","3A","3G","3L","3K"]},
    {"grupos":["A","C","E","G","H","J","K","L"],"cruces":["3E","3G","3J","3C","3A","3H","3L","3K"]},
    {"grupos":["A","C","E","G","H","I","K","L"],"cruces":["3E","3G","3I","3C","3A","3H","3L","3K"]},
    {"grupos":["A","C","E","G","H","I","J","L"],"cruces":["3E","3G","3J","3C","3A","3H","3L","3I"]},
    {"grupos":["A","C","E","G","H","I","J","K"],"cruces":["3E","3G","3J","3C","3A","3H","3I","3K"]},
    {"grupos":["A","C","E","F","I","J","K","L"],"cruces":["3E","3J","3I","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","E","F","H","J","K","L"],"cruces":["3H","3J","3E","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","E","F","H","I","K","L"],"cruces":["3H","3E","3I","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","E","F","H","I","J","L"],"cruces":["3H","3J","3E","3C","3A","3F","3L","3I"]},
    {"grupos":["A","C","E","F","H","I","J","K"],"cruces":["3H","3J","3E","3C","3A","3F","3I","3K"]},
    {"grupos":["A","C","E","F","G","J","K","L"],"cruces":["3E","3G","3J","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","E","F","G","I","K","L"],"cruces":["3E","3G","3I","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","E","F","G","I","J","L"],"cruces":["3E","3G","3J","3C","3A","3F","3L","3I"]},
    {"grupos":["A","C","E","F","G","I","J","K"],"cruces":["3E","3G","3J","3C","3A","3F","3I","3K"]},
    {"grupos":["A","C","E","F","G","H","K","L"],"cruces":["3H","3G","3E","3C","3A","3F","3L","3K"]},
    {"grupos":["A","C","E","F","G","H","J","L"],"cruces":["3H","3G","3J","3C","3A","3F","3L","3E"]},
    {"grupos":["A","C","E","F","G","H","J","K"],"cruces":["3H","3G","3J","3C","3A","3F","3E","3K"]},
    {"grupos":["A","C","E","F","G","H","I","L"],"cruces":["3H","3G","3E","3C","3A","3F","3L","3I"]},
    {"grupos":["A","C","E","F","G","H","I","K"],"cruces":["3H","3G","3E","3C","3A","3F","3I","3K"]},
    {"grupos":["A","C","E","F","G","H","I","J"],"cruces":["3H","3G","3J","3C","3A","3F","3E","3I"]},
    {"grupos":["A","C","D","H","I","J","K","L"],"cruces":["3H","3J","3I","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","G","I","J","K","L"],"cruces":["3I","3G","3J","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","G","H","J","K","L"],"cruces":["3H","3G","3J","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","G","H","I","K","L"],"cruces":["3H","3G","3I","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","G","H","I","J","L"],"cruces":["3H","3G","3J","3C","3A","3D","3L","3I"]},
    {"grupos":["A","C","D","G","H","I","J","K"],"cruces":["3H","3G","3J","3C","3A","3D","3I","3K"]},
    {"grupos":["A","C","D","F","I","J","K","L"],"cruces":["3C","3J","3I","3D","3A","3F","3L","3K"]},
    {"grupos":["A","C","D","F","H","J","K","L"],"cruces":["3H","3J","3F","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","F","H","I","K","L"],"cruces":["3H","3F","3I","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","F","H","I","J","L"],"cruces":["3H","3J","3F","3C","3A","3D","3L","3I"]},
    {"grupos":["A","C","D","F","H","I","J","K"],"cruces":["3H","3J","3F","3C","3A","3D","3I","3K"]},
    {"grupos":["A","C","D","F","G","J","K","L"],"cruces":["3C","3G","3J","3D","3A","3F","3L","3K"]},
    {"grupos":["A","C","D","F","G","I","K","L"],"cruces":["3C","3G","3I","3D","3A","3F","3L","3K"]},
    {"grupos":["A","C","D","F","G","I","J","L"],"cruces":["3C","3G","3J","3D","3A","3F","3L","3I"]},
    {"grupos":["A","C","D","F","G","I","J","K"],"cruces":["3C","3G","3J","3D","3A","3F","3I","3K"]},
    {"grupos":["A","C","D","F","G","H","K","L"],"cruces":["3H","3G","3F","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","F","G","H","J","L"],"cruces":["3C","3G","3J","3D","3A","3F","3L","3H"]},
    {"grupos":["A","C","D","F","G","H","J","K"],"cruces":["3H","3G","3J","3C","3A","3F","3D","3K"]},
    {"grupos":["A","C","D","F","G","H","I","L"],"cruces":["3H","3G","3F","3C","3A","3D","3L","3I"]},
    {"grupos":["A","C","D","F","G","H","I","K"],"cruces":["3H","3G","3F","3C","3A","3D","3I","3K"]},
    {"grupos":["A","C","D","F","G","H","I","J"],"cruces":["3H","3G","3J","3C","3A","3F","3D","3I"]},
    {"grupos":["A","C","D","E","I","J","K","L"],"cruces":["3E","3J","3I","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","E","H","J","K","L"],"cruces":["3H","3J","3E","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","E","H","I","K","L"],"cruces":["3H","3E","3I","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","E","H","I","J","L"],"cruces":["3H","3J","3E","3C","3A","3D","3L","3I"]},
    {"grupos":["A","C","D","E","H","I","J","K"],"cruces":["3H","3J","3E","3C","3A","3D","3I","3K"]},
    {"grupos":["A","C","D","E","G","J","K","L"],"cruces":["3E","3G","3J","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","E","G","I","K","L"],"cruces":["3E","3G","3I","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","E","G","I","J","L"],"cruces":["3E","3G","3J","3C","3A","3D","3L","3I"]},
    {"grupos":["A","C","D","E","G","I","J","K"],"cruces":["3E","3G","3J","3C","3A","3D","3I","3K"]},
    {"grupos":["A","C","D","E","G","H","K","L"],"cruces":["3H","3G","3E","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","E","G","H","J","L"],"cruces":["3H","3G","3J","3C","3A","3D","3L","3E"]},
    {"grupos":["A","C","D","E","G","H","J","K"],"cruces":["3H","3G","3J","3C","3A","3D","3E","3K"]},
    {"grupos":["A","C","D","E","G","H","I","L"],"cruces":["3H","3G","3E","3C","3A","3D","3L","3I"]},
    {"grupos":["A","C","D","E","G","H","I","K"],"cruces":["3H","3G","3E","3C","3A","3D","3I","3K"]},
    {"grupos":["A","C","D","E","G","H","I","J"],"cruces":["3H","3G","3J","3C","3A","3D","3E","3I"]},
    {"grupos":["A","C","D","E","F","J","K","L"],"cruces":["3C","3J","3E","3D","3A","3F","3L","3K"]},
    {"grupos":["A","C","D","E","F","I","K","L"],"cruces":["3C","3E","3I","3D","3A","3F","3L","3K"]},
    {"grupos":["A","C","D","E","F","I","J","L"],"cruces":["3C","3J","3E","3D","3A","3F","3L","3I"]},
    {"grupos":["A","C","D","E","F","I","J","K"],"cruces":["3C","3J","3E","3D","3A","3F","3I","3K"]},
    {"grupos":["A","C","D","E","F","H","K","L"],"cruces":["3H","3E","3F","3C","3A","3D","3L","3K"]},
    {"grupos":["A","C","D","E","F","H","J","L"],"cruces":["3H","3J","3F","3C","3A","3D","3L","3E"]},
    {"grupos":["A","C","D","E","F","H","J","K"],"cruces":["3H","3J","3E","3C","3A","3F","3D","3K"]},
    {"grupos":["A","C","D","E","F","H","I","L"],"cruces":["3H","3E","3F","3C","3A","3D","3L","3I"]},
    {"grupos":["A","C","D","E","F","H","I","K"],"cruces":["3H","3E","3F","3C","3A","3D","3I","3K"]},
    {"grupos":["A","C","D","E","F","H","I","J"],"cruces":["3H","3J","3E","3C","3A","3F","3D","3I"]},
    {"grupos":["A","C","D","E","F","G","K","L"],"cruces":["3C","3G","3E","3D","3A","3F","3L","3K"]},
    {"grupos":["A","C","D","E","F","G","J","L"],"cruces":["3C","3G","3J","3D","3A","3F","3L","3E"]},
    {"grupos":["A","C","D","E","F","G","J","K"],"cruces":["3C","3G","3J","3D","3A","3F","3E","3K"]},
    {"grupos":["A","C","D","E","F","G","I","L"],"cruces":["3C","3G","3E","3D","3A","3F","3L","3I"]},
    {"grupos":["A","C","D","E","F","G","I","K"],"cruces":["3C","3G","3E","3D","3A","3F","3I","3K"]},
    {"grupos":["A","C","D","E","F","G","I","J"],"cruces":["3C","3G","3J","3D","3A","3F","3E","3I"]},
    {"grupos":["A","C","D","E","F","G","H","L"],"cruces":["3H","3G","3F","3C","3A","3D","3L","3E"]},
    {"grupos":["A","C","D","E","F","G","H","K"],"cruces":["3H","3G","3E","3C","3A","3F","3D","3K"]},
    {"grupos":["A","C","D","E","F","G","H","J"],"cruces":["3H","3G","3J","3C","3A","3F","3D","3E"]},
    {"grupos":["A","C","D","E","F","G","H","I"],"cruces":["3H","3G","3E","3C","3A","3F","3D","3I"]},
    {"grupos":["A","B","G","H","I","J","K","L"],"cruces":["3H","3J","3B","3A","3I","3G","3L","3K"]},
    {"grupos":["A","B","F","H","I","J","K","L"],"cruces":["3H","3J","3B","3A","3I","3F","3L","3K"]},
    {"grupos":["A","B","F","G","I","J","K","L"],"cruces":["3I","3J","3B","3F","3A","3G","3L","3K"]},
    {"grupos":["A","B","F","G","H","J","K","L"],"cruces":["3H","3J","3B","3F","3A","3G","3L","3K"]},
    {"grupos":["A","B","F","G","H","I","K","L"],"cruces":["3H","3G","3B","3A","3I","3F","3L","3K"]},
    {"grupos":["A","B","F","G","H","I","J","L"],"cruces":["3H","3J","3B","3F","3A","3G","3L","3I"]},
    {"grupos":["A","B","F","G","H","I","J","K"],"cruces":["3H","3J","3B","3F","3A","3G","3I","3K"]},
    {"grupos":["A","B","E","H","I","J","K","L"],"cruces":["3E","3J","3B","3A","3I","3H","3L","3K"]},
    {"grupos":["A","B","E","G","I","J","K","L"],"cruces":["3E","3J","3B","3A","3I","3G","3L","3K"]},
    {"grupos":["A","B","E","G","H","J","K","L"],"cruces":["3E","3J","3B","3A","3H","3G","3L","3K"]},
    {"grupos":["A","B","E","G","H","I","K","L"],"cruces":["3E","3G","3B","3A","3I","3H","3L","3K"]},
    {"grupos":["A","B","E","G","H","I","J","L"],"cruces":["3E","3J","3B","3A","3H","3G","3L","3I"]},
    {"grupos":["A","B","E","G","H","I","J","K"],"cruces":["3E","3J","3B","3A","3H","3G","3I","3K"]},
    {"grupos":["A","B","E","F","I","J","K","L"],"cruces":["3E","3J","3B","3A","3I","3F","3L","3K"]},
    {"grupos":["A","B","E","F","H","J","K","L"],"cruces":["3E","3J","3B","3F","3A","3H","3L","3K"]},
    {"grupos":["A","B","E","F","H","I","K","L"],"cruces":["3E","3I","3B","3F","3A","3H","3L","3K"]},
    {"grupos":["A","B","E","F","H","I","J","L"],"cruces":["3E","3J","3B","3F","3A","3H","3L","3I"]},
    {"grupos":["A","B","E","F","H","I","J","K"],"cruces":["3E","3J","3B","3F","3A","3H","3I","3K"]},
    {"grupos":["A","B","E","F","G","J","K","L"],"cruces":["3E","3J","3B","3F","3A","3G","3L","3K"]},
    {"grupos":["A","B","E","F","G","I","K","L"],"cruces":["3E","3G","3B","3A","3I","3F","3L","3K"]},
    {"grupos":["A","B","E","F","G","I","J","L"],"cruces":["3E","3J","3B","3F","3A","3G","3L","3I"]},
    {"grupos":["A","B","E","F","G","I","J","K"],"cruces":["3E","3J","3B","3F","3A","3G","3I","3K"]},
    {"grupos":["A","B","E","F","G","H","K","L"],"cruces":["3E","3G","3B","3F","3A","3H","3L","3K"]},
    {"grupos":["A","B","E","F","G","H","J","L"],"cruces":["3H","3J","3B","3F","3A","3G","3L","3E"]},
    {"grupos":["A","B","E","F","G","H","J","K"],"cruces":["3H","3J","3B","3F","3A","3G","3E","3K"]},
    {"grupos":["A","B","E","F","G","H","I","L"],"cruces":["3E","3G","3B","3F","3A","3H","3L","3I"]},
    {"grupos":["A","B","E","F","G","H","I","K"],"cruces":["3E","3G","3B","3F","3A","3H","3I","3K"]},
    {"grupos":["A","B","E","F","G","H","I","J"],"cruces":["3H","3J","3B","3F","3A","3G","3E","3I"]},
    {"grupos":["A","B","D","H","I","J","K","L"],"cruces":["3I","3J","3B","3D","3A","3H","3L","3K"]},
    {"grupos":["A","B","D","G","I","J","K","L"],"cruces":["3I","3J","3B","3D","3A","3G","3L","3K"]},
    {"grupos":["A","B","D","G","H","J","K","L"],"cruces":["3H","3J","3B","3D","3A","3G","3L","3K"]},
    {"grupos":["A","B","D","G","H","I","K","L"],"cruces":["3I","3G","3B","3D","3A","3H","3L","3K"]},
    {"grupos":["A","B","D","G","H","I","J","L"],"cruces":["3H","3J","3B","3D","3A","3G","3L","3I"]},
    {"grupos":["A","B","D","G","H","I","J","K"],"cruces":["3H","3J","3B","3D","3A","3G","3I","3K"]},
    {"grupos":["A","B","D","F","I","J","K","L"],"cruces":["3I","3J","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","F","H","J","K","L"],"cruces":["3H","3J","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","F","H","I","K","L"],"cruces":["3H","3I","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","F","H","I","J","L"],"cruces":["3H","3J","3B","3D","3A","3F","3L","3I"]},
    {"grupos":["A","B","D","F","H","I","J","K"],"cruces":["3H","3J","3B","3D","3A","3F","3I","3K"]},
    {"grupos":["A","B","D","F","G","J","K","L"],"cruces":["3F","3J","3B","3D","3A","3G","3L","3K"]},
    {"grupos":["A","B","D","F","G","I","K","L"],"cruces":["3I","3G","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","F","G","I","J","L"],"cruces":["3F","3J","3B","3D","3A","3G","3L","3I"]},
    {"grupos":["A","B","D","F","G","I","J","K"],"cruces":["3F","3J","3B","3D","3A","3G","3I","3K"]},
    {"grupos":["A","B","D","F","G","H","K","L"],"cruces":["3H","3G","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","F","G","H","J","L"],"cruces":["3H","3G","3B","3D","3A","3F","3L","3J"]},
    {"grupos":["A","B","D","F","G","H","J","K"],"cruces":["3H","3G","3B","3D","3A","3F","3J","3K"]},
    {"grupos":["A","B","D","F","G","H","I","L"],"cruces":["3H","3G","3B","3D","3A","3F","3L","3I"]},
    {"grupos":["A","B","D","F","G","H","I","K"],"cruces":["3H","3G","3B","3D","3A","3F","3I","3K"]},
    {"grupos":["A","B","D","F","G","H","I","J"],"cruces":["3H","3G","3B","3D","3A","3F","3I","3J"]},
    {"grupos":["A","B","D","E","I","J","K","L"],"cruces":["3E","3J","3B","3A","3I","3D","3L","3K"]},
    {"grupos":["A","B","D","E","H","J","K","L"],"cruces":["3E","3J","3B","3D","3A","3H","3L","3K"]},
    {"grupos":["A","B","D","E","H","I","K","L"],"cruces":["3E","3I","3B","3D","3A","3H","3L","3K"]},
    {"grupos":["A","B","D","E","H","I","J","L"],"cruces":["3E","3J","3B","3D","3A","3H","3L","3I"]},
    {"grupos":["A","B","D","E","H","I","J","K"],"cruces":["3E","3J","3B","3D","3A","3H","3I","3K"]},
    {"grupos":["A","B","D","E","G","J","K","L"],"cruces":["3E","3J","3B","3D","3A","3G","3L","3K"]},
    {"grupos":["A","B","D","E","G","I","K","L"],"cruces":["3E","3G","3B","3A","3I","3D","3L","3K"]},
    {"grupos":["A","B","D","E","G","I","J","L"],"cruces":["3E","3J","3B","3D","3A","3G","3L","3I"]},
    {"grupos":["A","B","D","E","G","I","J","K"],"cruces":["3E","3J","3B","3D","3A","3G","3I","3K"]},
    {"grupos":["A","B","D","E","G","H","K","L"],"cruces":["3E","3G","3B","3D","3A","3H","3L","3K"]},
    {"grupos":["A","B","D","E","G","H","J","L"],"cruces":["3H","3J","3B","3D","3A","3G","3L","3E"]},
    {"grupos":["A","B","D","E","G","H","J","K"],"cruces":["3H","3J","3B","3D","3A","3G","3E","3K"]},
    {"grupos":["A","B","D","E","G","H","I","L"],"cruces":["3E","3G","3B","3D","3A","3H","3L","3I"]},
    {"grupos":["A","B","D","E","G","H","I","K"],"cruces":["3E","3G","3B","3D","3A","3H","3I","3K"]},
    {"grupos":["A","B","D","E","G","H","I","J"],"cruces":["3H","3J","3B","3D","3A","3G","3E","3I"]},
    {"grupos":["A","B","D","E","F","J","K","L"],"cruces":["3E","3J","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","E","F","I","K","L"],"cruces":["3E","3I","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","E","F","I","J","L"],"cruces":["3E","3J","3B","3D","3A","3F","3L","3I"]},
    {"grupos":["A","B","D","E","F","I","J","K"],"cruces":["3E","3J","3B","3D","3A","3F","3I","3K"]},
    {"grupos":["A","B","D","E","F","H","K","L"],"cruces":["3H","3E","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","E","F","H","J","L"],"cruces":["3H","3J","3B","3D","3A","3F","3L","3E"]},
    {"grupos":["A","B","D","E","F","H","J","K"],"cruces":["3H","3J","3B","3D","3A","3F","3E","3K"]},
    {"grupos":["A","B","D","E","F","H","I","L"],"cruces":["3H","3E","3B","3D","3A","3F","3L","3I"]},
    {"grupos":["A","B","D","E","F","H","I","K"],"cruces":["3H","3E","3B","3D","3A","3F","3I","3K"]},
    {"grupos":["A","B","D","E","F","H","I","J"],"cruces":["3H","3J","3B","3D","3A","3F","3E","3I"]},
    {"grupos":["A","B","D","E","F","G","K","L"],"cruces":["3E","3G","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","D","E","F","G","J","L"],"cruces":["3E","3G","3B","3D","3A","3F","3L","3J"]},
    {"grupos":["A","B","D","E","F","G","J","K"],"cruces":["3E","3G","3B","3D","3A","3F","3J","3K"]},
    {"grupos":["A","B","D","E","F","G","I","L"],"cruces":["3E","3G","3B","3D","3A","3F","3L","3I"]},
    {"grupos":["A","B","D","E","F","G","I","K"],"cruces":["3E","3G","3B","3D","3A","3F","3I","3K"]},
    {"grupos":["A","B","D","E","F","G","I","J"],"cruces":["3E","3G","3B","3D","3A","3F","3I","3J"]},
    {"grupos":["A","B","D","E","F","G","H","L"],"cruces":["3H","3G","3B","3D","3A","3F","3L","3E"]},
    {"grupos":["A","B","D","E","F","G","H","K"],"cruces":["3H","3G","3B","3D","3A","3F","3E","3K"]},
    {"grupos":["A","B","D","E","F","G","H","J"],"cruces":["3H","3G","3B","3D","3A","3F","3E","3J"]},
    {"grupos":["A","B","D","E","F","G","H","I"],"cruces":["3H","3G","3B","3D","3A","3F","3E","3I"]},
    {"grupos":["A","B","C","H","I","J","K","L"],"cruces":["3I","3J","3B","3C","3A","3H","3L","3K"]},
    {"grupos":["A","B","C","G","I","J","K","L"],"cruces":["3I","3J","3B","3C","3A","3G","3L","3K"]},
    {"grupos":["A","B","C","G","H","J","K","L"],"cruces":["3H","3J","3B","3C","3A","3G","3L","3K"]},
    {"grupos":["A","B","C","G","H","I","K","L"],"cruces":["3I","3G","3B","3C","3A","3H","3L","3K"]},
    {"grupos":["A","B","C","G","H","I","J","L"],"cruces":["3H","3J","3B","3C","3A","3G","3L","3I"]},
    {"grupos":["A","B","C","G","H","I","J","K"],"cruces":["3H","3J","3B","3C","3A","3G","3I","3K"]},
    {"grupos":["A","B","C","F","I","J","K","L"],"cruces":["3I","3J","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","F","H","J","K","L"],"cruces":["3H","3J","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","F","H","I","K","L"],"cruces":["3H","3I","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","F","H","I","J","L"],"cruces":["3H","3J","3B","3C","3A","3F","3L","3I"]},
    {"grupos":["A","B","C","F","H","I","J","K"],"cruces":["3H","3J","3B","3C","3A","3F","3I","3K"]},
    {"grupos":["A","B","C","F","G","J","K","L"],"cruces":["3C","3J","3B","3F","3A","3G","3L","3K"]},
    {"grupos":["A","B","C","F","G","I","K","L"],"cruces":["3I","3G","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","F","G","I","J","L"],"cruces":["3C","3J","3B","3F","3A","3G","3L","3I"]},
    {"grupos":["A","B","C","F","G","I","J","K"],"cruces":["3C","3J","3B","3F","3A","3G","3I","3K"]},
    {"grupos":["A","B","C","F","G","H","K","L"],"cruces":["3H","3G","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","F","G","H","J","L"],"cruces":["3H","3G","3B","3C","3A","3F","3L","3J"]},
    {"grupos":["A","B","C","F","G","H","J","K"],"cruces":["3H","3G","3B","3C","3A","3F","3J","3K"]},
    {"grupos":["A","B","C","F","G","H","I","L"],"cruces":["3H","3G","3B","3C","3A","3F","3L","3I"]},
    {"grupos":["A","B","C","F","G","H","I","K"],"cruces":["3H","3G","3B","3C","3A","3F","3I","3K"]},
    {"grupos":["A","B","C","F","G","H","I","J"],"cruces":["3H","3G","3B","3C","3A","3F","3I","3J"]},
    {"grupos":["A","B","C","E","I","J","K","L"],"cruces":["3E","3J","3B","3A","3I","3C","3L","3K"]},
    {"grupos":["A","B","C","E","H","J","K","L"],"cruces":["3E","3J","3B","3C","3A","3H","3L","3K"]},
    {"grupos":["A","B","C","E","H","I","K","L"],"cruces":["3E","3I","3B","3C","3A","3H","3L","3K"]},
    {"grupos":["A","B","C","E","H","I","J","L"],"cruces":["3E","3J","3B","3C","3A","3H","3L","3I"]},
    {"grupos":["A","B","C","E","H","I","J","K"],"cruces":["3E","3J","3B","3C","3A","3H","3I","3K"]},
    {"grupos":["A","B","C","E","G","J","K","L"],"cruces":["3E","3J","3B","3C","3A","3G","3L","3K"]},
    {"grupos":["A","B","C","E","G","I","K","L"],"cruces":["3E","3G","3B","3A","3I","3C","3L","3K"]},
    {"grupos":["A","B","C","E","G","I","J","L"],"cruces":["3E","3J","3B","3C","3A","3G","3L","3I"]},
    {"grupos":["A","B","C","E","G","I","J","K"],"cruces":["3E","3J","3B","3C","3A","3G","3I","3K"]},
    {"grupos":["A","B","C","E","G","H","K","L"],"cruces":["3E","3G","3B","3C","3A","3H","3L","3K"]},
    {"grupos":["A","B","C","E","G","H","J","L"],"cruces":["3H","3J","3B","3C","3A","3G","3L","3E"]},
    {"grupos":["A","B","C","E","G","H","J","K"],"cruces":["3H","3J","3B","3C","3A","3G","3E","3K"]},
    {"grupos":["A","B","C","E","G","H","I","L"],"cruces":["3E","3G","3B","3C","3A","3H","3L","3I"]},
    {"grupos":["A","B","C","E","G","H","I","K"],"cruces":["3E","3G","3B","3C","3A","3H","3I","3K"]},
    {"grupos":["A","B","C","E","G","H","I","J"],"cruces":["3H","3J","3B","3C","3A","3G","3E","3I"]},
    {"grupos":["A","B","C","E","F","J","K","L"],"cruces":["3E","3J","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","E","F","I","K","L"],"cruces":["3E","3I","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","E","F","I","J","L"],"cruces":["3E","3J","3B","3C","3A","3F","3L","3I"]},
    {"grupos":["A","B","C","E","F","I","J","K"],"cruces":["3E","3J","3B","3C","3A","3F","3I","3K"]},
    {"grupos":["A","B","C","E","F","H","K","L"],"cruces":["3H","3E","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","E","F","H","J","L"],"cruces":["3H","3J","3B","3C","3A","3F","3L","3E"]},
    {"grupos":["A","B","C","E","F","H","J","K"],"cruces":["3H","3J","3B","3C","3A","3F","3E","3K"]},
    {"grupos":["A","B","C","E","F","H","I","L"],"cruces":["3H","3E","3B","3C","3A","3F","3L","3I"]},
    {"grupos":["A","B","C","E","F","H","I","K"],"cruces":["3H","3E","3B","3C","3A","3F","3I","3K"]},
    {"grupos":["A","B","C","E","F","H","I","J"],"cruces":["3H","3J","3B","3C","3A","3F","3E","3I"]},
    {"grupos":["A","B","C","E","F","G","K","L"],"cruces":["3E","3G","3B","3C","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","E","F","G","J","L"],"cruces":["3E","3G","3B","3C","3A","3F","3L","3J"]},
    {"grupos":["A","B","C","E","F","G","J","K"],"cruces":["3E","3G","3B","3C","3A","3F","3J","3K"]},
    {"grupos":["A","B","C","E","F","G","I","L"],"cruces":["3E","3G","3B","3C","3A","3F","3L","3I"]},
    {"grupos":["A","B","C","E","F","G","I","K"],"cruces":["3E","3G","3B","3C","3A","3F","3I","3K"]},
    {"grupos":["A","B","C","E","F","G","I","J"],"cruces":["3E","3G","3B","3C","3A","3F","3I","3J"]},
    {"grupos":["A","B","C","E","F","G","H","L"],"cruces":["3H","3G","3B","3C","3A","3F","3L","3E"]},
    {"grupos":["A","B","C","E","F","G","H","K"],"cruces":["3H","3G","3B","3C","3A","3F","3E","3K"]},
    {"grupos":["A","B","C","E","F","G","H","J"],"cruces":["3H","3G","3B","3C","3A","3F","3E","3J"]},
    {"grupos":["A","B","C","E","F","G","H","I"],"cruces":["3H","3G","3B","3C","3A","3F","3E","3I"]},
    {"grupos":["A","B","C","D","I","J","K","L"],"cruces":["3I","3J","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","H","J","K","L"],"cruces":["3H","3J","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","H","I","K","L"],"cruces":["3H","3I","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","H","I","J","L"],"cruces":["3H","3J","3B","3C","3A","3D","3L","3I"]},
    {"grupos":["A","B","C","D","H","I","J","K"],"cruces":["3H","3J","3B","3C","3A","3D","3I","3K"]},
    {"grupos":["A","B","C","D","G","J","K","L"],"cruces":["3C","3J","3B","3D","3A","3G","3L","3K"]},
    {"grupos":["A","B","C","D","G","I","K","L"],"cruces":["3I","3G","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","G","I","J","L"],"cruces":["3C","3J","3B","3D","3A","3G","3L","3I"]},
    {"grupos":["A","B","C","D","G","I","J","K"],"cruces":["3C","3J","3B","3D","3A","3G","3I","3K"]},
    {"grupos":["A","B","C","D","G","H","K","L"],"cruces":["3H","3G","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","G","H","J","L"],"cruces":["3H","3G","3B","3C","3A","3D","3L","3J"]},
    {"grupos":["A","B","C","D","G","H","J","K"],"cruces":["3H","3G","3B","3C","3A","3D","3J","3K"]},
    {"grupos":["A","B","C","D","G","H","I","L"],"cruces":["3H","3G","3B","3C","3A","3D","3L","3I"]},
    {"grupos":["A","B","C","D","G","H","I","K"],"cruces":["3H","3G","3B","3C","3A","3D","3I","3K"]},
    {"grupos":["A","B","C","D","G","H","I","J"],"cruces":["3H","3G","3B","3C","3A","3D","3I","3J"]},
    {"grupos":["A","B","C","D","F","J","K","L"],"cruces":["3C","3J","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","D","F","I","K","L"],"cruces":["3C","3I","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","D","F","I","J","L"],"cruces":["3C","3J","3B","3D","3A","3F","3L","3I"]},
    {"grupos":["A","B","C","D","F","I","J","K"],"cruces":["3C","3J","3B","3D","3A","3F","3I","3K"]},
    {"grupos":["A","B","C","D","F","H","K","L"],"cruces":["3H","3F","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","F","H","J","L"],"cruces":["3C","3J","3B","3D","3A","3F","3L","3H"]},
    {"grupos":["A","B","C","D","F","H","J","K"],"cruces":["3H","3J","3B","3C","3A","3F","3D","3K"]},
    {"grupos":["A","B","C","D","F","H","I","L"],"cruces":["3H","3F","3B","3C","3A","3D","3L","3I"]},
    {"grupos":["A","B","C","D","F","H","I","K"],"cruces":["3H","3F","3B","3C","3A","3D","3I","3K"]},
    {"grupos":["A","B","C","D","F","H","I","J"],"cruces":["3H","3J","3B","3C","3A","3F","3D","3I"]},
    {"grupos":["A","B","C","D","F","G","K","L"],"cruces":["3C","3G","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","D","F","G","J","L"],"cruces":["3C","3G","3B","3D","3A","3F","3L","3J"]},
    {"grupos":["A","B","C","D","F","G","J","K"],"cruces":["3C","3G","3B","3D","3A","3F","3J","3K"]},
    {"grupos":["A","B","C","D","F","G","I","L"],"cruces":["3C","3G","3B","3D","3A","3F","3L","3I"]},
    {"grupos":["A","B","C","D","F","G","I","K"],"cruces":["3C","3G","3B","3D","3A","3F","3I","3K"]},
    {"grupos":["A","B","C","D","F","G","I","J"],"cruces":["3C","3G","3B","3D","3A","3F","3I","3J"]},
    {"grupos":["A","B","C","D","F","G","H","L"],"cruces":["3C","3G","3B","3D","3A","3F","3L","3H"]},
    {"grupos":["A","B","C","D","F","G","H","K"],"cruces":["3H","3G","3B","3C","3A","3F","3D","3K"]},
    {"grupos":["A","B","C","D","F","G","H","J"],"cruces":["3H","3G","3B","3C","3A","3F","3D","3J"]},
    {"grupos":["A","B","C","D","F","G","H","I"],"cruces":["3H","3G","3B","3C","3A","3F","3D","3I"]},
    {"grupos":["A","B","C","D","E","J","K","L"],"cruces":["3E","3J","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","E","I","K","L"],"cruces":["3E","3I","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","E","I","J","L"],"cruces":["3E","3J","3B","3C","3A","3D","3L","3I"]},
    {"grupos":["A","B","C","D","E","I","J","K"],"cruces":["3E","3J","3B","3C","3A","3D","3I","3K"]},
    {"grupos":["A","B","C","D","E","H","K","L"],"cruces":["3H","3E","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","E","H","J","L"],"cruces":["3H","3J","3B","3C","3A","3D","3L","3E"]},
    {"grupos":["A","B","C","D","E","H","J","K"],"cruces":["3H","3J","3B","3C","3A","3D","3E","3K"]},
    {"grupos":["A","B","C","D","E","H","I","L"],"cruces":["3H","3E","3B","3C","3A","3D","3L","3I"]},
    {"grupos":["A","B","C","D","E","H","I","K"],"cruces":["3H","3E","3B","3C","3A","3D","3I","3K"]},
    {"grupos":["A","B","C","D","E","H","I","J"],"cruces":["3H","3J","3B","3C","3A","3D","3E","3I"]},
    {"grupos":["A","B","C","D","E","G","K","L"],"cruces":["3E","3G","3B","3C","3A","3D","3L","3K"]},
    {"grupos":["A","B","C","D","E","G","J","L"],"cruces":["3E","3G","3B","3C","3A","3D","3L","3J"]},
    {"grupos":["A","B","C","D","E","G","J","K"],"cruces":["3E","3G","3B","3C","3A","3D","3J","3K"]},
    {"grupos":["A","B","C","D","E","G","I","L"],"cruces":["3E","3G","3B","3C","3A","3D","3L","3I"]},
    {"grupos":["A","B","C","D","E","G","I","K"],"cruces":["3E","3G","3B","3C","3A","3D","3I","3K"]},
    {"grupos":["A","B","C","D","E","G","I","J"],"cruces":["3E","3G","3B","3C","3A","3D","3I","3J"]},
    {"grupos":["A","B","C","D","E","G","H","L"],"cruces":["3H","3G","3B","3C","3A","3D","3L","3E"]},
    {"grupos":["A","B","C","D","E","G","H","K"],"cruces":["3H","3G","3B","3C","3A","3D","3E","3K"]},
    {"grupos":["A","B","C","D","E","G","H","J"],"cruces":["3H","3G","3B","3C","3A","3D","3E","3J"]},
    {"grupos":["A","B","C","D","E","G","H","I"],"cruces":["3H","3G","3B","3C","3A","3D","3E","3I"]},
    {"grupos":["A","B","C","D","E","F","K","L"],"cruces":["3C","3E","3B","3D","3A","3F","3L","3K"]},
    {"grupos":["A","B","C","D","E","F","J","L"],"cruces":["3C","3J","3B","3D","3A","3F","3L","3E"]},
    {"grupos":["A","B","C","D","E","F","J","K"],"cruces":["3C","3J","3B","3D","3A","3F","3E","3K"]},
    {"grupos":["A","B","C","D","E","F","I","L"],"cruces":["3C","3E","3B","3D","3A","3F","3L","3I"]},
    {"grupos":["A","B","C","D","E","F","I","K"],"cruces":["3C","3E","3B","3D","3A","3F","3I","3K"]},
    {"grupos":["A","B","C","D","E","F","I","J"],"cruces":["3C","3J","3B","3D","3A","3F","3E","3I"]},
    {"grupos":["A","B","C","D","E","F","H","L"],"cruces":["3H","3F","3B","3C","3A","3D","3L","3E"]},
    {"grupos":["A","B","C","D","E","F","H","K"],"cruces":["3H","3E","3B","3C","3A","3F","3D","3K"]},
    {"grupos":["A","B","C","D","E","F","H","J"],"cruces":["3H","3J","3B","3C","3A","3F","3D","3E"]},
    {"grupos":["A","B","C","D","E","F","H","I"],"cruces":["3H","3E","3B","3C","3A","3F","3D","3I"]},
    {"grupos":["A","B","C","D","E","F","G","L"],"cruces":["3C","3G","3B","3D","3A","3F","3L","3E"]},
    {"grupos":["A","B","C","D","E","F","G","K"],"cruces":["3C","3G","3B","3D","3A","3F","3E","3K"]},
    {"grupos":["A","B","C","D","E","F","G","J"],"cruces":["3C","3G","3B","3D","3A","3F","3E","3J"]},
    {"grupos":["A","B","C","D","E","F","G","I"],"cruces":["3C","3G","3B","3D","3A","3F","3E","3I"]},
    {"grupos":["A","B","C","D","E","F","G","H"],"cruces":["3H","3G","3B","3C","3A","3F","3D","3E"]},
]# ── Lógica de clasificación: fase de grupos y eliminatorias ──────────────────
#
# Fuente verificada: Wikipedia (en) "2026 FIFA World Cup knockout stage",
# que cita el Reglamento Oficial FIFA World Cup 26 (Annex C).
#
# Estructura de 16avos (orden = índice en LIDERES_DEPENDIENTES):
#   Match 73: 2A vs 2B
#   Match 74: 1E vs Mejor 3° (A/B/C/D/F)
#   Match 75: 1F vs 2C
#   Match 76: 1C vs 2F
#   Match 77: 1I vs Mejor 3° (C/D/F/G/H)
#   Match 78: 2E vs 2I
#   Match 79: 1A vs Mejor 3° (C/E/F/H/I)
#   Match 80: 1L vs Mejor 3° (E/H/I/J/K)
#   Match 81: 1D vs Mejor 3° (B/E/F/I/J)
#   Match 82: 1G vs Mejor 3° (A/E/H/I/J)
#   Match 83: 2K vs 2L
#   Match 84: 1H vs 2J
#   Match 85: 1B vs Mejor 3° (E/F/G/I/J)
#   Match 86: 1J vs 2H
#   Match 87: 1K vs Mejor 3° (D/E/I/J/L)
#   Match 88: 2D vs 2G

# Los 8 líderes de grupo que dependen de la matriz de 495 combinaciones,
# en el ORDEN exacto en que aparecen las columnas "cruces" de cada combinación:
LIDERES_DEPENDIENTES = ["A", "B", "D", "E", "G", "I", "K", "L"]

# Mapeo de cada líder dependiente a su partido_id de 16avos
PARTIDO_POR_LIDER = {
    "A": "P079",
    "B": "P085",
    "D": "P081",
    "E": "P074",
    "G": "P082",
    "I": "P077",
    "K": "P087",
    "L": "P080",
}

# Partidos de 16avos con cruces ESTRUCTURALMENTE FIJOS (no dependen de terceros)
CRUCES_FIJOS_16AVOS = {
    "P073": ("2°", "A", "2°", "B"),
    "P075": ("1°", "F", "2°", "C"),
    "P076": ("1°", "C", "2°", "F"),
    "P078": ("2°", "E", "2°", "I"),
    "P083": ("2°", "K", "2°", "L"),
    "P084": ("1°", "H", "2°", "J"),
    "P086": ("1°", "J", "2°", "H"),
    "P088": ("2°", "D", "2°", "G"),
}

# Bracket completo de octavos en adelante (gana_de = partido_id del que sale el ganador)
BRACKET_OCTAVOS = {
    "P089": ("P074", "P077"),
    "P090": ("P073", "P075"),
    "P091": ("P076", "P078"),
    "P092": ("P079", "P080"),
    "P093": ("P083", "P084"),
    "P094": ("P081", "P082"),
    "P095": ("P086", "P088"),
    "P096": ("P085", "P087"),
}
BRACKET_CUARTOS = {
    "P097": ("P089", "P090"),
    "P098": ("P093", "P094"),
    "P099": ("P091", "P092"),
    "P100": ("P095", "P096"),
}
BRACKET_SEMIS = {
    "P101": ("P097", "P098"),
    "P102": ("P099", "P100"),
}
BRACKET_FINAL = {
    "P103": ("perdedor", "P101", "P102"),  # 3er puesto
    "P104": ("ganador", "P101", "P102"),   # final
}


def calcular_tabla_grupo(part_df, res_df, grupo):
    """
    Calcula la tabla de un grupo específico: PJ, G, E, P, GF, GC, DG, Pts.
    Solo considera partidos de fase 'Grupos' ya jugados.
    Retorna lista de dicts ordenada por los criterios FIFA de desempate
    INTRA-GRUPO (puntos, luego enfrentamientos directos, luego DG/GF general).
    """
    partidos_grupo = part_df[
        (part_df.get("grupo") == grupo) &
        (part_df.get("fase", "Grupos") == "Grupos")
    ] if "grupo" in part_df.columns else part_df.iloc[0:0]

    equipos = set()
    if not partidos_grupo.empty:
        equipos = set(partidos_grupo["local"]) | set(partidos_grupo["visita"])

    tabla = {
        eq: {"equipo": eq, "PJ": 0, "G": 0, "E": 0, "P": 0,
             "GF": 0, "GC": 0, "DG": 0, "Pts": 0}
        for eq in equipos
    }

    resultados_dict = {}
    if not res_df.empty:
        for _, r in res_df.iterrows():
            if r.get("goles_local") != "" and str(r.get("goles_local")) != "nan":
                resultados_dict[r["partido_id"]] = (
                    int(float(r["goles_local"])), int(float(r["goles_visita"]))
                )

    for _, p in partidos_grupo.iterrows():
        pid = p["partido_id"]
        if pid not in resultados_dict:
            continue
        gl, gv = resultados_dict[pid]
        local, visita = p["local"], p["visita"]

        tabla[local]["PJ"] += 1
        tabla[visita]["PJ"] += 1
        tabla[local]["GF"] += gl
        tabla[local]["GC"] += gv
        tabla[visita]["GF"] += gv
        tabla[visita]["GC"] += gl

        if gl > gv:
            tabla[local]["G"] += 1
            tabla[local]["Pts"] += 3
            tabla[visita]["P"] += 1
        elif gl < gv:
            tabla[visita]["G"] += 1
            tabla[visita]["Pts"] += 3
            tabla[local]["P"] += 1
        else:
            tabla[local]["E"] += 1
            tabla[visita]["E"] += 1
            tabla[local]["Pts"] += 1
            tabla[visita]["Pts"] += 1

    for eq in tabla:
        tabla[eq]["DG"] = tabla[eq]["GF"] - tabla[eq]["GC"]

    filas = list(tabla.values())

    # Desempate simplificado: Pts -> DG -> GF -> alfabético (estable)
    # (enfrentamientos directos requerirían más granularidad; se documenta
    # la limitación en la UI)
    filas.sort(key=lambda x: (-x["Pts"], -x["DG"], -x["GF"], x["equipo"]))

    return filas


def calcular_todas_las_tablas(part_df, res_df):
    """Retorna dict {grupo: [tabla ordenada]} para todos los grupos detectados."""
    if "grupo" not in part_df.columns:
        return {}
    grupos = sorted(g for g in part_df["grupo"].dropna().unique() if g)
    return {g: calcular_tabla_grupo(part_df, res_df, g) for g in grupos}


def calcular_terceros(tablas_grupos):
    """
    Construye la tabla general de los 12 terceros lugares, ordenada con
    los criterios oficiales: Pts -> DG -> GF -> (Fair Play y Ranking FIFA
    no disponibles con los datos de la app, se documenta la limitación).
    Solo incluye grupos con al menos 3 equipos y datos completos.
    """
    terceros = []
    for grupo, tabla in tablas_grupos.items():
        if len(tabla) >= 3:
            tercero = dict(tabla[2])
            tercero["grupo"] = grupo
            terceros.append(tercero)

    terceros.sort(key=lambda x: (-x["Pts"], -x["DG"], -x["GF"], x["grupo"]))
    return terceros


def mejores_ocho_terceros(terceros):
    """Retorna (mejores_8, grupos_ordenados_alfabeticamente)."""
    mejores = terceros[:8]
    grupos = sorted(t["grupo"] for t in mejores)
    return mejores, grupos


def resolver_combinacion(grupos_terceros_clasificados):
    """
    Busca en las 495 combinaciones cuál corresponde a la lista de 8 grupos
    cuyo tercer lugar avanzó. Retorna el dict de la combinación o None.
    """
    objetivo = sorted(grupos_terceros_clasificados)
    for combo in COMBINACIONES_495:
        if sorted(combo["grupos"]) == objetivo:
            return combo
    return None


def construir_cruces_16avos(tablas_grupos, terceros_clasificados_grupos, combinacion):
    """
    Construye el diccionario partido_id -> (equipo_local, equipo_visita)
    usando los primeros/segundos reales (si ya están definidos) y la
    combinación de terceros resuelta.

    Si un grupo aún no tiene 3 partidos jugados, el primer/segundo lugar
    se muestra como provisional con la etiqueta correspondiente.
    """
    cruces = {}

    def equipo_1ro(grupo):
        t = tablas_grupos.get(grupo, [])
        return t[0]["equipo"] if len(t) >= 1 else f"1° Grupo {grupo}"

    def equipo_2do(grupo):
        t = tablas_grupos.get(grupo, [])
        return t[1]["equipo"] if len(t) >= 2 else f"2° Grupo {grupo}"

    # Cruces fijos
    for pid, (pos_l, grp_l, pos_v, grp_v) in CRUCES_FIJOS_16AVOS.items():
        local = equipo_1ro(grp_l) if pos_l == "1°" else equipo_2do(grp_l)
        visita = equipo_1ro(grp_v) if pos_v == "1°" else equipo_2do(grp_v)
        cruces[pid] = (local, visita, f"{pos_l}{grp_l}", f"{pos_v}{grp_v}")

    # Cruces dependientes de terceros
    if combinacion:
        for i, lider_grupo in enumerate(LIDERES_DEPENDIENTES):
            pid = PARTIDO_POR_LIDER[lider_grupo]
            rival_tag = combinacion["cruces"][i]  # ej "3E"
            grupo_tercero = rival_tag[1:]  # "E"

            local = equipo_1ro(lider_grupo)
            visita_label = f"3° Grupo {grupo_tercero}"

            # Si tenemos el equipo real del tercero clasificado
            tabla_g = tablas_grupos.get(grupo_tercero, [])
            if len(tabla_g) >= 3:
                visita_label = tabla_g[2]["equipo"]

            cruces[pid] = (local, visita_label, f"1°{lider_grupo}", f"3°{grupo_tercero}")
    else:
        # Combinación no resuelta aún (terceros incompletos): mostrar genérico
        for lider_grupo in LIDERES_DEPENDIENTES:
            pid = PARTIDO_POR_LIDER[lider_grupo]
            local = equipo_1ro(lider_grupo)
            cruces[pid] = (local, "Mejor 3° (pendiente)", f"1°{lider_grupo}", "3°?")

    return cruces


def nombre_ganador(partido_id, res_df, cruces_16avos=None, etiquetas_bracket=None):
    """
    Dado un partido_id de cualquier ronda, retorna el nombre del equipo
    ganador si el partido ya tiene resultado, o None si no se ha jugado.
    """
    if res_df.empty:
        return None
    fila = res_df[res_df["partido_id"] == partido_id]
    if fila.empty:
        return None
    gl, gv = fila.iloc[0].get("goles_local"), fila.iloc[0].get("goles_visita")
    if gl == "" or str(gl) == "nan":
        return None
    # En eliminatorias no hay empate (se asume que el dato ya refleja
    # el resultado final, incluyendo penales si aplicó)
    try:
        gl, gv = int(float(gl)), int(float(gv))
    except (ValueError, TypeError):
        return None
    if gl == gv:
        return None  # dato incompleto para eliminatoria

    if etiquetas_bracket and partido_id in etiquetas_bracket:
        local_nombre, visita_nombre = etiquetas_bracket[partido_id]
    else:
        return None

    return local_nombre if gl > gv else visita_nombre


# ── UI helpers ───────────────────────────────────────────────────────────────
def medal(pos):
    if pos == 1: return "🥇"
    if pos == 2: return "🥈"
    if pos == 3: return "🥉"
    return f"{pos}°"


def pill_class(pos):
    if pos == 1: return "pill pill-gold"
    if pos == 2: return "pill pill-silver"
    if pos == 3: return "pill pill-bronze"
    return "pill pill-other"


# ── App principal ────────────────────────────────────────────────────────────
def main():
    # Header
    st.markdown("""
    <div style="text-align:center; padding: 2rem 0 1rem;">
        <div style="font-size: 48px; margin-bottom: 8px;">⚽</div>
        <h1 style="font-size: 2.4rem; font-weight: 700; letter-spacing: -1px; margin: 0;">
            Polla Mundial 2026
        </h1>
        <p style="color: #8891b4; margin-top: 8px; font-size: 15px;">
            Tablero de resultados y ranking
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ID del spreadsheet (configurar en secrets o aquí directamente)
    spreadsheet_id = st.secrets.get("spreadsheet_id", "")

    if not spreadsheet_id:
        st.warning("⚙️ Configura el `spreadsheet_id` en los secrets de Streamlit.")
        st.code("""
# En .streamlit/secrets.toml:
spreadsheet_id = "tu_id_aqui"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN RSA PRIVATE KEY-----\\n..."
client_email = "..."
# (resto de campos del JSON de la cuenta de servicio)
        """)
        return

    try:
        pred_df, res_df, part_df = load_sheet(spreadsheet_id)
    except Exception as e:
        st.error(f"❌ Error al conectar con Google Sheets: {e}")
        return

    rank_df, det_df = calcular_ranking(pred_df, res_df, part_df)

    # ── Métricas superiores ───────────────────────────────────────────────
    partidos_jugados = len(
        res_df[(res_df["goles_local"] != "") & (res_df["goles_local"].notna())]
    ) if not res_df.empty else 0
    total_partidos   = len(part_df) if not part_df.empty else 0
    total_participantes = pred_df["participante"].nunique() if not pred_df.empty else 0

    # % de puntos jugados vs el total posible del mundial.
    # "Puntaje máximo por partido" = 10 (Grupos) o 20 (16avos en adelante).
    # Jugados = suma de máximos de partidos con resultado cargado.
    # Total   = suma de máximos de TODOS los partidos del torneo.
    pct_puntos_jugados = 0.0
    puntos_jugados_max = 0
    puntos_totales_max = 0
    if not part_df.empty:
        fase_col_metric = [c for c in part_df.columns if "fase" in c.lower()]
        fase_series = part_df[fase_col_metric[0]] if fase_col_metric else pd.Series([None] * len(part_df))
        maximos_por_partido = fase_series.apply(lambda f: 10 * _multiplicador_por_fase(f))
        puntos_totales_max = int(maximos_por_partido.sum())

        if not res_df.empty:
            ids_jugados = set(
                res_df[(res_df["goles_local"] != "") & (res_df["goles_local"].notna())]["partido_id"]
            )
            mask_jugados = part_df["partido_id"].isin(ids_jugados)
            puntos_jugados_max = int(maximos_por_partido[mask_jugados].sum())

        if puntos_totales_max > 0:
            pct_puntos_jugados = (puntos_jugados_max / puntos_totales_max) * 100

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Participantes</div>
            <div class="value">{total_participantes}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Partidos jugados</div>
            <div class="value">{partidos_jugados} / {total_partidos}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        lider = rank_df.iloc[0]["Participante"] if not rank_df.empty else "—"
        st.markdown(f"""<div class="metric-card">
            <div class="label">Líder actual</div>
            <div class="value" style="font-size:20px;">{lider}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        top_pts = int(rank_df.iloc[0]["Puntos"]) if not rank_df.empty else 0
        st.markdown(f"""<div class="metric-card">
            <div class="label">Puntos del líder</div>
            <div class="value">{top_pts}</div>
        </div>""", unsafe_allow_html=True)
    with c5:
        st.markdown(f"""<div class="metric-card">
            <div class="label">% puntos jugados</div>
            <div class="value">{pct_puntos_jugados:.1f}%</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(["🏆 Ranking", "⚽ Detalle por partido", "📋 Predicciones", "🔍 Pronósticos por partido", "📅 Calendario", "🗓️ Pronósticos por día", "📊 Fase de Grupos", "🏟️ Eliminatorias", "🪦 Peores"])

    with tab1:
        st.markdown("### Clasificación general")
        if rank_df.empty:
            st.info("Aún no hay resultados cargados.")
        else:
            rows_html = ""
            for pos, row in rank_df.iterrows():
                rows_html += f"""
                <tr>
                    <td><span class="{pill_class(pos)}">{medal(pos)}</span></td>
                    <td style="font-weight:600; color:#ffffff;">{row['Participante']}</td>
                    <td style="text-align:center;">
                        <span style="font-size:20px; font-weight:700; color:#3b82f6;">
                            {int(row['Puntos'])}
                        </span>
                    </td>
                    <td style="text-align:center; color:#8891b4;">{int(row['Partidos jugados'])}</td>
                    <td style="text-align:center;">{'⭐ ' * int(row['Marcadores exactos']) if row['Marcadores exactos'] > 0 else '<span style="color:#4b5563">—</span>'}</td>
                </tr>"""

            st.markdown(f"""
            <table style="width:100%; border-collapse:collapse;">
                <thead>
                    <tr style="border-bottom: 1px solid #2a3060;">
                        <th style="padding:12px 16px; text-align:left; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">#</th>
                        <th style="padding:12px 16px; text-align:left; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Participante</th>
                        <th style="padding:12px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Puntos</th>
                        <th style="padding:12px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Partidos</th>
                        <th style="padding:12px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Marcadores exactos</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            """, unsafe_allow_html=True)

    with tab2:
        st.markdown("### Resultado por partido")
        if det_df.empty:
            st.info("Aún no hay resultados cargados.")
        else:
            # Merge con nombres de partidos
            if not part_df.empty and "partido_id" in part_df.columns:
                hora_col = [c for c in part_df.columns if "hora" in c.lower()]
                cols_merge = ["partido_id", "local", "visita"] + hora_col
                det_df = det_df.merge(
                    part_df[cols_merge],
                    on="partido_id", how="left"
                )
                hora_col2 = [c for c in det_df.columns if "hora" in c.lower()]
                if hora_col2:
                    det_df["Partido"] = det_df["local"] + " vs " + det_df["visita"] + " (" + det_df[hora_col2[0]].fillna("").astype(str) + ")"
                else:
                    det_df["Partido"] = det_df["local"] + " vs " + det_df["visita"]
            else:
                det_df["Partido"] = det_df["partido_id"]

            partidos_lista = ["Todos"] + sorted(det_df["Partido"].unique().tolist())
            filtro = st.selectbox("Filtrar partido", partidos_lista)

            df_filtrado = det_df if filtro == "Todos" else det_df[det_df["Partido"] == filtro]

            rows_html = ""
            for _, row in df_filtrado.sort_values(["Partido", "puntos"], ascending=[True, False]).iterrows():
                badge = f'<span class="pts-badge">{int(row["puntos"])} pts</span>' \
                        if row["puntos"] > 0 else \
                        f'<span class="pts-zero">0 pts</span>'
                rows_html += f"""
                <tr>
                    <td>{row['Partido']}</td>
                    <td style="font-weight:500; color:#ffffff;">{row['participante']}</td>
                    <td style="text-align:center;"><span class="score-chip">{row['pred']}</span></td>
                    <td style="text-align:center;"><span class="score-chip">{row['real']}</span></td>
                    <td style="text-align:center;">{badge}</td>
                </tr>"""

            st.markdown(f"""
            <table style="width:100%; border-collapse:collapse; margin-top:16px;">
                <thead>
                    <tr style="border-bottom: 1px solid #2a3060;">
                        <th style="padding:12px 16px; text-align:left; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Partido</th>
                        <th style="padding:12px 16px; text-align:left; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Participante</th>
                        <th style="padding:12px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Predicción</th>
                        <th style="padding:12px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Real</th>
                        <th style="padding:12px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Puntos</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            """, unsafe_allow_html=True)

    with tab3:
        st.markdown("### Predicciones por participante")
        if pred_df.empty:
            st.info("Aún no hay predicciones cargadas.")
        else:
            from zoneinfo import ZoneInfo
            tz_col = ZoneInfo("America/Bogota")
            ahora = datetime.now(tz_col).replace(tzinfo=None)
            # Identificar qué partido_ids ya están desbloqueados
            # (faltan ≤10 min para el partido o ya pasó)
            def partido_desbloqueado(partido_id):
                if part_df.empty or "partido_id" not in part_df.columns:
                    return False
                fila = part_df[part_df["partido_id"] == partido_id]
                if fila.empty:
                    return False
                try:
                    fecha = fila.iloc[0]["fecha"]
                    hora  = fila.iloc[0].get("hora (COL)", "00:00")
                    hora  = hora if hora else "00:00"
                    dt_partido = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
                    return ahora >= dt_partido - timedelta(minutes=10)
                except Exception:
                    return False

            participantes = sorted(pred_df["participante"].unique().tolist())
            sel = st.selectbox("Ver predicciones de", participantes)
            df_p = pred_df[pred_df["participante"] == sel].copy()

            if not part_df.empty and "partido_id" in part_df.columns:
                fase_col_p3 = [c for c in part_df.columns if "fase" in c.lower()]
                cols_merge_p3 = ["partido_id", "local", "visita", "fecha",
                                  part_df.columns[part_df.columns.str.contains("hora")].tolist()[0]
                                  if any(part_df.columns.str.contains("hora")) else "fecha"]
                cols_merge_p3 += fase_col_p3
                df_p = df_p.merge(
                    part_df[cols_merge_p3],
                    on="partido_id", how="left"
                )

            st.markdown(
                "<p style='color:#8891b4; font-size:13px;'>🔒 Las predicciones se revelan 10 minutos antes de cada partido.</p>",
                unsafe_allow_html=True
            )

            # Diccionario de resultados reales para calcular puntos
            resultados_dict_p3 = {}
            if not res_df.empty:
                for _, r in res_df.iterrows():
                    if r.get("goles_local") != "" and r.get("goles_visita") != "" and str(r.get("goles_local")) != "nan":
                        resultados_dict_p3[r["partido_id"]] = (r["goles_local"], r["goles_visita"])

            rows_html = ""
            for _, row in df_p.iterrows():
                desbloqueado = partido_desbloqueado(row["partido_id"])
                local   = row.get("local",   row["partido_id"])
                visita  = row.get("visita",  "")
                fecha   = row.get("fecha",   "")

                puntos_html = '<span style="color:#6b7280;">—</span>'
                resultado_html = '<span style="color:#6b7280;">—</span>'

                if desbloqueado:
                    if row.get("pred_local") == "" or row.get("pred_visita") == "":
                        pred = '<span style="color:#6b7280;">Sin enviar</span>'
                        estado = '<span style="color:#f97316; font-size:12px;">⚠️ No registró</span>'
                    else:
                        pred = f'<span class="score-chip">{int(row["pred_local"])}-{int(row["pred_visita"])}</span>'
                        estado = '<span style="color:#4ade80; font-size:12px;">🔓 Visible</span>'

                        if row["partido_id"] in resultados_dict_p3:
                            rl, rv = resultados_dict_p3[row["partido_id"]]
                            resultado_html = f'<span class="score-chip">{int(rl)}-{int(rv)}</span>'
                            mult_p3 = _multiplicador_por_fase(row.get("fase"))
                            pts = _puntos_limpio(row["pred_local"], row["pred_visita"], rl, rv, mult_p3)
                            sufijo_x2 = " ⚡" if mult_p3 == 2 else ""
                            puntos_html = f'<span class="pts-badge">{pts} pts{sufijo_x2}</span>' if pts > 0 else '<span class="pts-zero">0 pts</span>'
                        else:
                            resultado_html = '<span style="color:#6b7280; font-size:12px;">Sin jugar</span>'
                else:
                    pred = '<span style="color:#6b7280; font-size:18px;">🔒</span>'
                    estado = '<span style="color:#6b7280; font-size:12px;">Bloqueado</span>'

                rows_html += f"""
                <tr>
                    <td style="color:#8891b4;">{fecha}</td>
                    <td style="color:#ffffff; font-weight:500;">{local} vs {visita}</td>
                    <td style="text-align:center;">{pred}</td>
                    <td style="text-align:center;">{resultado_html}</td>
                    <td style="text-align:center;">{estado}</td>
                    <td style="text-align:center;">{puntos_html}</td>
                </tr>"""

            st.markdown(f"""
            <table style="width:100%; border-collapse:collapse; margin-top:12px;">
                <thead>
                    <tr style="border-bottom: 1px solid #2a3060;">
                        <th style="padding:10px 16px; text-align:left; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Fecha</th>
                        <th style="padding:10px 16px; text-align:left; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Partido</th>
                        <th style="padding:10px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Predicción</th>
                        <th style="padding:10px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Resultado</th>
                        <th style="padding:10px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Estado</th>
                        <th style="padding:10px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Puntos</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            """, unsafe_allow_html=True)

    with tab4:
        st.markdown("### Pronósticos por partido")
        st.markdown(
            "<p style='color:#8891b4; font-size:13px;'>Solo se muestran partidos cuyas predicciones ya están desbloqueadas (faltan menos de 10 min o ya se jugaron).</p>",
            unsafe_allow_html=True
        )

        if pred_df.empty or part_df.empty:
            st.info("Aún no hay datos cargados.")
        else:
            from zoneinfo import ZoneInfo
            ahora_t4 = datetime.now(ZoneInfo("America/Bogota")).replace(tzinfo=None)

            def desbloqueado_t4(row):
                try:
                    hora = row.get("hora (COL)", "00:00") or "00:00"
                    dt = datetime.strptime(f"{row['fecha']} {hora}", "%Y-%m-%d %H:%M")
                    return ahora_t4 >= dt - timedelta(minutes=10)
                except Exception:
                    return False

            partidos_desbloqueados = part_df[part_df.apply(desbloqueado_t4, axis=1)]

            if partidos_desbloqueados.empty:
                st.info("Aún no hay partidos desbloqueados. Las predicciones se revelan 10 minutos antes de cada partido.")
            else:
                opciones = partidos_desbloqueados.apply(
                    lambda r: f"{r['partido_id']} · {r['local']} vs {r['visita']} ({r['fecha']})", axis=1
                ).tolist()
                seleccion = st.selectbox("Selecciona un partido", opciones)
                partido_id_sel = seleccion.split(" · ")[0]

                pred_partido = pred_df[pred_df["partido_id"] == partido_id_sel].copy()
                part_info = part_df[part_df["partido_id"] == partido_id_sel].iloc[0]
                res_info = res_df[res_df["partido_id"] == partido_id_sel] if not res_df.empty else pd.DataFrame()

                resultado_real = ""
                if not res_info.empty and res_info.iloc[0]["goles_local"] != "" and str(res_info.iloc[0]["goles_local"]) != "nan":
                    gl = res_info.iloc[0]["goles_local"]
                    gv = res_info.iloc[0]["goles_visita"]
                    resultado_real = f"{int(float(gl))}-{int(float(gv))}"

                st.markdown(f"""
                <div style="background:#1a1f3a; border:1px solid #2a3060; border-radius:12px;
                            padding:20px; text-align:center; margin-bottom:20px;">
                    <div style="font-size:22px; font-weight:700; color:#ffffff;">
                        {part_info['local']} vs {part_info['visita']}
                    </div>
                    <div style="color:#8891b4; font-size:13px; margin-top:4px;">
                        {part_info['fecha']}
                    </div>
                    {f'<div style="margin-top:12px; font-size:28px; font-weight:700; color:#4ade80;">Resultado: {resultado_real}</div>' if resultado_real else '<div style="margin-top:8px; color:#6b7280; font-size:13px;">Partido aún no jugado</div>'}
                </div>
                """, unsafe_allow_html=True)

                if pred_partido.empty:
                    st.info("Nadie ha ingresado predicciones para este partido.")
                else:
                    mult_t4 = _multiplicador_por_fase(part_info.get("fase"))
                    rows_html_t4 = ""
                    for _, row in pred_partido.sort_values("participante").iterrows():
                        if row.get("pred_local") == "" or row.get("pred_visita") == "":
                            pred = '<span style="color:#6b7280;">Sin enviar</span>'
                            pts_badge = ""
                        else:
                            pred = f"{int(row['pred_local'])}-{int(row['pred_visita'])}"
                            pred = f'<span class="score-chip">{pred}</span>'
                            pts_badge = ""
                            if resultado_real:
                                rl, rv = resultado_real.split("-")
                                p = _puntos_limpio(row["pred_local"], row["pred_visita"], rl, rv, mult_t4)
                                pts_badge = f'<span class="pts-badge">{p} pts</span>' if p > 0 else '<span class="pts-zero">0 pts</span>'

                        rows_html_t4 += f"""
                        <tr>
                            <td style="font-weight:500; color:#ffffff;">{row['participante']}</td>
                            <td style="text-align:center;">{pred}</td>
                            <td style="text-align:center;">{pts_badge}</td>
                        </tr>"""

                    st.markdown(f"""
                    <table style="width:100%; border-collapse:collapse;">
                        <thead>
                            <tr style="border-bottom: 1px solid #2a3060;">
                                <th style="padding:10px 16px; text-align:left; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Participante</th>
                                <th style="padding:10px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Pronóstico</th>
                                <th style="padding:10px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Puntos</th>
                            </tr>
                        </thead>
                        <tbody>{rows_html_t4}</tbody>
                    </table>
                    """, unsafe_allow_html=True)

    with tab5:
        st.markdown("### Calendario Mundial 2026")
        if part_df.empty:
            st.info("No hay partidos cargados.")
        else:
            from zoneinfo import ZoneInfo
            ahora_cal = datetime.now(ZoneInfo("America/Bogota")).replace(tzinfo=None)

            fases_orden = ["Grupos", "16avos", "Octavos", "Cuartos", "Semifinal", "3er Puesto", "Final"]
            fase_col = [c for c in part_df.columns if "fase" in c.lower()]
            hora_col_cal = [c for c in part_df.columns if "hora" in c.lower()]

            filtro_fase = st.selectbox("Filtrar por fase", ["Todas"] + fases_orden)

            df_cal = part_df.copy()
            if filtro_fase != "Todas" and fase_col:
                df_cal = df_cal[df_cal[fase_col[0]] == filtro_fase]

            if not res_df.empty:
                df_cal = df_cal.merge(
                    res_df[["partido_id", "goles_local", "goles_visita"]],
                    on="partido_id", how="left"
                )

            fechas = sorted(df_cal["fecha"].unique())

            for fecha in fechas:
                partidos_dia = df_cal[df_cal["fecha"] == fecha]
                st.markdown(f"""
                <div style="margin-top:20px; margin-bottom:8px;">
                    <span style="background:#1e3a8a; color:#93c5fd; padding:4px 14px;
                                 border-radius:20px; font-size:12px; font-weight:600;">
                        📅 {fecha}
                    </span>
                </div>
                """, unsafe_allow_html=True)

                rows_html = ""
                for _, p in partidos_dia.iterrows():
                    hora = p[hora_col_cal[0]] if hora_col_cal and p.get(hora_col_cal[0]) else ""
                    grupo = p.get("grupo", "")
                    sede = p.get("sede", "")

                    try:
                        dt_p = datetime.strptime(f"{p['fecha']} {hora}", "%Y-%m-%d %H:%M") if hora else None
                        jugado = dt_p and ahora_cal > dt_p
                        en_curso = dt_p and timedelta(0) <= ahora_cal - dt_p <= timedelta(hours=2)
                    except:
                        jugado = False
                        en_curso = False

                    gl = p.get("goles_local", "")
                    gv = p.get("goles_visita", "")
                    resultado_html = ""
                    if gl != "" and gv != "" and str(gl) != "nan":
                        resultado_html = f'<span style="background:#0f2a1a; border:1px solid #1a5c36; color:#4ade80; border-radius:6px; padding:2px 10px; font-family:monospace; font-size:14px; font-weight:700;">{int(float(gl))}-{int(float(gv))}</span>'
                    elif en_curso:
                        resultado_html = '<span style="background:#3d1a00; color:#f97316; border-radius:6px; padding:2px 10px; font-size:12px; font-weight:600;">EN VIVO</span>'
                    else:
                        resultado_html = f'<span style="color:#6b7280; font-size:13px;">{hora} COL</span>'

                    grupo_badge = f'<span style="background:#1a1f3a; color:#8891b4; border-radius:4px; padding:1px 7px; font-size:11px;">Grupo {grupo}</span>' if grupo else ""

                    rows_html += f"""
                    <tr>
                        <td style="color:#8891b4; font-size:12px; white-space:nowrap;">{hora}</td>
                        <td style="font-weight:600; color:#ffffff;">{p['local']}</td>
                        <td style="text-align:center; color:#8891b4;">vs</td>
                        <td style="font-weight:600; color:#ffffff;">{p['visita']}</td>
                        <td style="text-align:center;">{resultado_html}</td>
                        <td style="text-align:right; color:#6b7280; font-size:11px;">{sede}</td>
                        <td style="text-align:right;">{grupo_badge}</td>
                    </tr>"""

                st.markdown(f"""
                <table style="width:100%; border-collapse:collapse; margin-bottom:8px;">
                    <tbody>{rows_html}</tbody>
                </table>
                """, unsafe_allow_html=True)

    with tab6:
        st.markdown("### Pronósticos por día")
        st.markdown(
            "<p style='color:#8891b4; font-size:13px;'>Selecciona una fecha para ver todos los partidos de ese día junto con los pronósticos de todos los participantes (solo partidos ya desbloqueados).</p>",
            unsafe_allow_html=True
        )

        if pred_df.empty or part_df.empty:
            st.info("Aún no hay datos cargados.")
        else:
            from zoneinfo import ZoneInfo
            ahora_t6 = datetime.now(ZoneInfo("America/Bogota")).replace(tzinfo=None)

            def desbloqueado_t6(row):
                try:
                    hora = row.get("hora (COL)", "00:00") or "00:00"
                    dt = datetime.strptime(f"{row['fecha']} {hora}", "%Y-%m-%d %H:%M")
                    return ahora_t6 >= dt - timedelta(minutes=10)
                except Exception:
                    return False

            fechas_t6 = sorted(part_df["fecha"].unique().tolist())
            fecha_sel = st.selectbox("Selecciona una fecha", fechas_t6)

            partidos_dia_t6 = part_df[part_df["fecha"] == fecha_sel].copy()
            partidos_dia_t6 = partidos_dia_t6[partidos_dia_t6.apply(desbloqueado_t6, axis=1)]

            if partidos_dia_t6.empty:
                st.info("No hay partidos desbloqueados para este día todavía.")
            else:
                hora_col_t6 = [c for c in part_df.columns if "hora" in c.lower()]
                orden_col = hora_col_t6[0] if hora_col_t6 else "fecha"
                partidos_dia_t6 = partidos_dia_t6.sort_values(orden_col)

                for _, part_info in partidos_dia_t6.iterrows():
                    partido_id_t6 = part_info["partido_id"]
                    hora_t6 = part_info.get(orden_col, "")

                    res_info_t6 = res_df[res_df["partido_id"] == partido_id_t6] if not res_df.empty else pd.DataFrame()
                    resultado_real_t6 = ""
                    if not res_info_t6.empty and res_info_t6.iloc[0]["goles_local"] != "" and str(res_info_t6.iloc[0]["goles_local"]) != "nan":
                        gl = res_info_t6.iloc[0]["goles_local"]
                        gv = res_info_t6.iloc[0]["goles_visita"]
                        resultado_real_t6 = f"{int(float(gl))}-{int(float(gv))}"

                    st.markdown(f"""
                    <div style="background:#1a1f3a; border:1px solid #2a3060; border-radius:12px;
                                padding:16px 20px; text-align:center; margin-top:24px; margin-bottom:12px;">
                        <div style="font-size:18px; font-weight:700; color:#ffffff;">
                            {part_info['local']} vs {part_info['visita']}
                        </div>
                        <div style="color:#8891b4; font-size:12px; margin-top:2px;">
                            {hora_t6} COL
                        </div>
                        {f'<div style="margin-top:8px; font-size:22px; font-weight:700; color:#4ade80;">Resultado: {resultado_real_t6}</div>' if resultado_real_t6 else '<div style="margin-top:6px; color:#6b7280; font-size:12px;">Partido aún no jugado</div>'}
                    </div>
                    """, unsafe_allow_html=True)

                    pred_partido_t6 = pred_df[pred_df["partido_id"] == partido_id_t6]

                    if pred_partido_t6.empty:
                        st.markdown(
                            "<p style='color:#6b7280; font-size:13px; margin-left:4px;'>Nadie ha ingresado predicciones para este partido.</p>",
                            unsafe_allow_html=True
                        )
                        continue

                    rows_html_t6 = ""
                    mult_t6 = _multiplicador_por_fase(part_info.get("fase"))
                    for _, row in pred_partido_t6.sort_values("participante").iterrows():
                        if row.get("pred_local") == "" or row.get("pred_visita") == "":
                            pred = '<span style="color:#6b7280;">Sin enviar</span>'
                            pts_badge = ""
                        else:
                            pred = f"{int(row['pred_local'])}-{int(row['pred_visita'])}"
                            pred = f'<span class="score-chip">{pred}</span>'
                            pts_badge = ""
                            if resultado_real_t6:
                                rl, rv = resultado_real_t6.split("-")
                                p = _puntos_limpio(row["pred_local"], row["pred_visita"], rl, rv, mult_t6)
                                pts_badge = f'<span class="pts-badge">{p} pts</span>' if p > 0 else '<span class="pts-zero">0 pts</span>'

                        rows_html_t6 += f"""
                        <tr>
                            <td style="font-weight:500; color:#ffffff;">{row['participante']}</td>
                            <td style="text-align:center;">{pred}</td>
                            <td style="text-align:center;">{pts_badge}</td>
                        </tr>"""

                    st.markdown(f"""
                    <table style="width:100%; border-collapse:collapse; margin-bottom:8px;">
                        <thead>
                            <tr style="border-bottom: 1px solid #2a3060;">
                                <th style="padding:8px 16px; text-align:left; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Participante</th>
                                <th style="padding:8px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Pronóstico</th>
                                <th style="padding:8px 16px; text-align:center; color:#8891b4; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Puntos</th>
                            </tr>
                        </thead>
                        <tbody>{rows_html_t6}</tbody>
                    </table>
                    """, unsafe_allow_html=True)

    with tab7:
        st.markdown("### Fase de Grupos")
        st.markdown(
            "<p style='color:#8891b4; font-size:13px;'>Clasificación calculada con los resultados cargados. "
            "Desempate: Puntos → Diferencia de gol → Goles a favor. "
            "<span style='color:#f97316;'>No incluye enfrentamientos directos, Fair Play ni Ranking FIFA</span> "
            "(no disponibles con los datos de esta app) — en empates muy cerrados el orden real de FIFA podría variar.</p>",
            unsafe_allow_html=True
        )

        if part_df.empty or "grupo" not in part_df.columns:
            st.info("No hay datos de grupos cargados.")
        else:
            tablas_grupos = calcular_todas_las_tablas(part_df, res_df)

            if not tablas_grupos:
                st.info("No hay grupos detectados en la hoja Partidos.")
            else:
                grupos_lista = sorted(tablas_grupos.keys())
                cols_por_fila = 2
                for i in range(0, len(grupos_lista), cols_por_fila):
                    cols = st.columns(cols_por_fila)
                    for j, grupo in enumerate(grupos_lista[i:i+cols_por_fila]):
                        with cols[j]:
                            tabla = tablas_grupos[grupo]
                            st.markdown(f"""
                            <div style="background:#1a1f3a; border:1px solid #2a3060; border-radius:10px;
                                        padding:6px 14px 12px; margin-bottom:16px;">
                                <div style="font-size:14px; font-weight:700; color:#ffffff; margin:8px 0 8px;">
                                    Grupo {grupo}
                                </div>
                            """, unsafe_allow_html=True)

                            rows_html_g = ""
                            for pos, eq in enumerate(tabla, 1):
                                color_pos = "#4ade80" if pos <= 2 else ("#fbbf24" if pos == 3 else "#6b7280")
                                rows_html_g += f"""
                                <tr>
                                    <td style="color:{color_pos}; font-weight:700; width:20px;">{pos}</td>
                                    <td style="color:#ffffff; font-weight:500;">{eq['equipo']}</td>
                                    <td style="text-align:center; color:#8891b4;">{eq['PJ']}</td>
                                    <td style="text-align:center; color:#8891b4;">{eq['G']}</td>
                                    <td style="text-align:center; color:#8891b4;">{eq['E']}</td>
                                    <td style="text-align:center; color:#8891b4;">{eq['P']}</td>
                                    <td style="text-align:center; color:#8891b4;">{eq['GF']}</td>
                                    <td style="text-align:center; color:#8891b4;">{eq['GC']}</td>
                                    <td style="text-align:center; color:#8891b4;">{eq['DG']:+d}</td>
                                    <td style="text-align:center; color:#3b82f6; font-weight:700;">{eq['Pts']}</td>
                                </tr>"""

                            st.markdown(f"""
                                <table style="width:100%; border-collapse:collapse; font-size:12px;">
                                    <thead>
                                        <tr style="border-bottom:1px solid #2a3060; color:#6b7280; font-size:10px; text-transform:uppercase;">
                                            <th></th><th style="text-align:left;">Equipo</th>
                                            <th>PJ</th><th>G</th><th>E</th><th>P</th>
                                            <th>GF</th><th>GC</th><th>DG</th><th>Pts</th>
                                        </tr>
                                    </thead>
                                    <tbody>{rows_html_g}</tbody>
                                </table>
                            </div>
                            """, unsafe_allow_html=True)

    with tab8:
        st.markdown("### Eliminatorias")
        st.markdown(
            "<p style='color:#8891b4; font-size:13px;'>Estructura oficial verificada del Mundial 2026 "
            "(Reglamento FIFA, Anexo C). Los cruces con terceros lugares se resuelven automáticamente "
            "usando las 495 combinaciones oficiales una vez que se conocen los 8 mejores terceros.</p>",
            unsafe_allow_html=True
        )

        if part_df.empty or "grupo" not in part_df.columns:
            st.info("No hay datos de grupos cargados.")
        else:
            tablas_grupos = calcular_todas_las_tablas(part_df, res_df)
            terceros = calcular_terceros(tablas_grupos)

            if not terceros:
                st.info("Aún no hay suficientes partidos jugados para calcular terceros lugares.")
            else:
                st.markdown("#### Tabla general de terceros lugares")
                st.markdown(
                    "<p style='color:#8891b4; font-size:12px;'>Los 8 mejores (✅) clasifican a 16avos. "
                    "Desempate disponible: Puntos → DG → GF (no incluye Fair Play ni Ranking FIFA).</p>",
                    unsafe_allow_html=True
                )

                rows_html_3 = ""
                for i, t in enumerate(terceros, 1):
                    clasifica = i <= 8
                    badge = '<span style="color:#4ade80;">✅</span>' if clasifica else '<span style="color:#6b7280;">❌</span>'
                    rows_html_3 += f"""
                    <tr style="{'opacity:0.5;' if not clasifica else ''}">
                        <td style="text-align:center;">{badge}</td>
                        <td style="color:#8891b4;">{i}</td>
                        <td style="color:#ffffff; font-weight:600;">{t['equipo']}</td>
                        <td style="text-align:center; color:#8891b4;">Grupo {t['grupo']}</td>
                        <td style="text-align:center; color:#8891b4;">{t['Pts']}</td>
                        <td style="text-align:center; color:#8891b4;">{t['DG']:+d}</td>
                        <td style="text-align:center; color:#8891b4;">{t['GF']}</td>
                    </tr>"""

                st.markdown(f"""
                <table style="width:100%; border-collapse:collapse; margin-bottom:24px;">
                    <thead>
                        <tr style="border-bottom:1px solid #2a3060; color:#6b7280; font-size:11px; text-transform:uppercase;">
                            <th></th><th>#</th><th style="text-align:left;">Equipo</th>
                            <th>Grupo</th><th>Pts</th><th>DG</th><th>GF</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html_3}</tbody>
                </table>
                """, unsafe_allow_html=True)

                mejores, grupos_clasif = mejores_ocho_terceros(terceros)
                grupos_completos = all(len(tablas_grupos.get(g, [])) >= 3 and
                                         tablas_grupos[g][0].get("PJ", 0) == 3
                                         for g in tablas_grupos)

                combo = resolver_combinacion(grupos_clasif) if len(grupos_clasif) == 8 else None

                if len(grupos_clasif) < 8:
                    st.warning(f"⚠️ Solo hay {len(grupos_clasif)} grupos con tabla de terceros calculable todavía. "
                               "Faltan resultados para definir los 8 mejores terceros.")
                elif combo is None:
                    st.error("No se encontró una combinación válida en el Anexo C para estos grupos — "
                             "verifica que los datos de la fase de grupos estén completos.")
                else:
                    st.markdown(f"""
                    <div style="background:#0f2a1a; border:1px solid #1a5c36; border-radius:8px;
                                padding:10px 16px; margin-bottom:20px; font-size:13px; color:#4ade80;">
                        ✅ Combinación de terceros resuelta: grupos {', '.join(grupos_clasif)} avanzan.
                        Cruces de 16avos calculados automáticamente.
                    </div>
                    """, unsafe_allow_html=True)

                cruces_16avos = construir_cruces_16avos(tablas_grupos, grupos_clasif, combo)

                # Construir etiquetas para resolver ganadores en rondas siguientes
                etiquetas_bracket = {pid: (local, visita) for pid, (local, visita, *_ ) in cruces_16avos.items()}

                st.markdown("#### 🏟️ Dieciseisavos de final")
                hora_col_e = [c for c in part_df.columns if "hora" in c.lower()]
                orden_pids_16 = ["P073","P074","P075","P076","P077","P078","P079","P080",
                                  "P081","P082","P083","P084","P085","P086","P087","P088"]

                cols_16 = st.columns(2)
                for idx, pid in enumerate(orden_pids_16):
                    if pid not in cruces_16avos:
                        continue
                    local, visita, tag_l, tag_v = cruces_16avos[pid]
                    info_partido = part_df[part_df["partido_id"] == pid]
                    fecha_p = info_partido.iloc[0]["fecha"] if not info_partido.empty else ""
                    sede_p = info_partido.iloc[0].get("sede", "") if not info_partido.empty else ""

                    ganador = nombre_ganador(pid, res_df, etiquetas_bracket=etiquetas_bracket)
                    res_fila = res_df[res_df["partido_id"] == pid] if not res_df.empty else pd.DataFrame()
                    marcador = ""
                    if not res_fila.empty and res_fila.iloc[0].get("goles_local") not in ("", None) and str(res_fila.iloc[0].get("goles_local")) != "nan":
                        gl_e = res_fila.iloc[0]["goles_local"]
                        gv_e = res_fila.iloc[0]["goles_visita"]
                        marcador = f"{int(float(gl_e))}-{int(float(gv_e))}"

                    with cols_16[idx % 2]:
                        local_style = "color:#4ade80; font-weight:700;" if ganador == local else "color:#ffffff; font-weight:500;"
                        visita_style = "color:#4ade80; font-weight:700;" if ganador == visita else "color:#ffffff; font-weight:500;"
                        st.markdown(f"""
                        <div style="background:#1a1f3a; border:1px solid #2a3060; border-radius:8px;
                                    padding:10px 14px; margin-bottom:8px; font-size:13px;">
                            <div style="color:#6b7280; font-size:10px; margin-bottom:4px;">{pid} · {fecha_p} {sede_p}</div>
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="{local_style}">{local}</span>
                                <span style="color:#8891b4; font-family:monospace;">{marcador if marcador else 'vs'}</span>
                                <span style="{visita_style}">{visita}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                # Rondas siguientes: Octavos, Cuartos, Semis, Final
                def render_ronda(titulo, bracket_dict, pid_origenes):
                    st.markdown(f"#### {titulo}")
                    cols_r = st.columns(2)
                    for idx, (pid, origenes) in enumerate(bracket_dict.items()):
                        local = nombre_ganador(origenes[0], res_df, etiquetas_bracket=etiquetas_bracket) or f"Ganador {origenes[0]}"
                        visita = nombre_ganador(origenes[1], res_df, etiquetas_bracket=etiquetas_bracket) or f"Ganador {origenes[1]}"
                        etiquetas_bracket[pid] = (local, visita)

                        ganador = nombre_ganador(pid, res_df, etiquetas_bracket=etiquetas_bracket)
                        res_fila = res_df[res_df["partido_id"] == pid] if not res_df.empty else pd.DataFrame()
                        marcador = ""
                        if not res_fila.empty and res_fila.iloc[0].get("goles_local") not in ("", None) and str(res_fila.iloc[0].get("goles_local")) != "nan":
                            gl_e = res_fila.iloc[0]["goles_local"]
                            gv_e = res_fila.iloc[0]["goles_visita"]
                            marcador = f"{int(float(gl_e))}-{int(float(gv_e))}"

                        local_style = "color:#4ade80; font-weight:700;" if ganador == local else "color:#ffffff; font-weight:500;"
                        visita_style = "color:#4ade80; font-weight:700;" if ganador == visita else "color:#ffffff; font-weight:500;"

                        with cols_r[idx % 2]:
                            st.markdown(f"""
                            <div style="background:#1a1f3a; border:1px solid #2a3060; border-radius:8px;
                                        padding:10px 14px; margin-bottom:8px; font-size:13px;">
                                <div style="color:#6b7280; font-size:10px; margin-bottom:4px;">{pid}</div>
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <span style="{local_style}">{local}</span>
                                    <span style="color:#8891b4; font-family:monospace;">{marcador if marcador else 'vs'}</span>
                                    <span style="{visita_style}">{visita}</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                render_ronda("⚔️ Octavos de final", BRACKET_OCTAVOS, orden_pids_16)
                render_ronda("🔥 Cuartos de final", BRACKET_CUARTOS, list(BRACKET_OCTAVOS.keys()))
                render_ronda("🌟 Semifinales", BRACKET_SEMIS, list(BRACKET_CUARTOS.keys()))

                # Final y 3er puesto
                st.markdown("#### 🏆 Final y 3er Puesto")
                cols_f = st.columns(2)

                ganador_101 = nombre_ganador("P101", res_df, etiquetas_bracket=etiquetas_bracket)
                ganador_102 = nombre_ganador("P102", res_df, etiquetas_bracket=etiquetas_bracket)
                local_101, visita_101 = etiquetas_bracket.get("P101", ("Ganador P97", "Ganador P98"))
                local_102, visita_102 = etiquetas_bracket.get("P102", ("Ganador P99", "Ganador P100"))

                perdedor_101 = (visita_101 if ganador_101 == local_101 else local_101) if ganador_101 else "Perdedor SF1"
                perdedor_102 = (visita_102 if ganador_102 == local_102 else local_102) if ganador_102 else "Perdedor SF2"
                final_local = ganador_101 or "Ganador SF1"
                final_visita = ganador_102 or "Ganador SF2"

                with cols_f[0]:
                    st.markdown(f"""
                    <div style="background:#1a1f3a; border:1px solid #2a3060; border-radius:8px;
                                padding:10px 14px; margin-bottom:8px; font-size:13px;">
                        <div style="color:#6b7280; font-size:10px; margin-bottom:4px;">P103 · 3er Puesto · Miami</div>
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:#ffffff;">{perdedor_101}</span>
                            <span style="color:#8891b4;">vs</span>
                            <span style="color:#ffffff;">{perdedor_102}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with cols_f[1]:
                    st.markdown(f"""
                    <div style="background:linear-gradient(135deg,#3d3000,#1a1f3a); border:1px solid #fbbf24; border-radius:8px;
                                padding:10px 14px; margin-bottom:8px; font-size:13px;">
                        <div style="color:#fbbf24; font-size:10px; margin-bottom:4px;">P104 · 🏆 FINAL · Nueva Jersey</div>
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:#ffffff; font-weight:600;">{final_local}</span>
                            <span style="color:#8891b4;">vs</span>
                            <span style="color:#ffffff; font-weight:600;">{final_visita}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    with tab9:
        st.markdown("### Farolitos del Mundial")
        st.markdown(
            "<p style='color:#8891b4; font-size:13px;'>El último lugar de cada grupo, ordenado de peor a mejor. "
            "El #1 es el equipo con el rendimiento más flojo de todo el torneo (entre los últimos de su grupo).</p>",
            unsafe_allow_html=True
        )

        if part_df.empty or "grupo" not in part_df.columns:
            st.info("No hay datos de grupos cargados.")
        else:
            tablas_grupos = calcular_todas_las_tablas(part_df, res_df)

            ultimos = []
            for grupo, tabla in tablas_grupos.items():
                if len(tabla) >= 4 and tabla[3].get("PJ", 0) > 0:
                    ultimo = dict(tabla[3])
                    ultimo["grupo"] = grupo
                    ultimos.append(ultimo)

            if not ultimos:
                st.info("Aún no hay suficientes partidos jugados para calcular los últimos lugares.")
            else:
                # Peor a mejor: menos puntos primero, luego peor DG, luego menos GF
                ultimos.sort(key=lambda x: (x["Pts"], x["DG"], x["GF"]))

                rows_html_9 = ""
                for i, eq in enumerate(ultimos, 1):
                    medalla = "🪦" if i == 1 else ("💀" if i <= 3 else "")
                    rows_html_9 += f"""
                    <tr>
                        <td style="text-align:center; font-size:18px;">{medalla if medalla else i}</td>
                        <td style="color:#ffffff; font-weight:600;">{eq['equipo']}</td>
                        <td style="text-align:center; color:#8891b4;">Grupo {eq['grupo']}</td>
                        <td style="text-align:center; color:#8891b4;">{eq['PJ']}</td>
                        <td style="text-align:center; color:#8891b4;">{eq['G']}</td>
                        <td style="text-align:center; color:#8891b4;">{eq['E']}</td>
                        <td style="text-align:center; color:#8891b4;">{eq['P']}</td>
                        <td style="text-align:center; color:#8891b4;">{eq['GF']}</td>
                        <td style="text-align:center; color:#8891b4;">{eq['GC']}</td>
                        <td style="text-align:center; color:#e24b4a; font-weight:600;">{eq['DG']:+d}</td>
                        <td style="text-align:center; color:#fbbf24; font-weight:700;">{eq['Pts']}</td>
                    </tr>"""

                st.markdown(f"""
                <table style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr style="border-bottom:1px solid #2a3060; color:#6b7280; font-size:11px; text-transform:uppercase;">
                            <th>#</th><th style="text-align:left;">Equipo</th><th>Grupo</th>
                            <th>PJ</th><th>G</th><th>E</th><th>P</th>
                            <th>GF</th><th>GC</th><th>DG</th><th>Pts</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html_9}</tbody>
                </table>
                """, unsafe_allow_html=True)

                if len(ultimos) < len(tablas_grupos):
                    st.markdown(
                        f"<p style='color:#6b7280; font-size:12px; margin-top:12px;'>"
                        f"Mostrando {len(ultimos)} de {len(tablas_grupos)} grupos — "
                        f"los grupos restantes todavía no tienen partidos jugados.</p>",
                        unsafe_allow_html=True
                    )

    # Footer
    st.markdown(f"""
    <div style="text-align:center; margin-top:3rem; color:#4b5563; font-size:12px;">
        Actualizado cada 60 seg · {datetime.now().strftime('%d/%m/%Y %H:%M')}
        &nbsp;·&nbsp; <a href="#" onclick="window.location.reload()" style="color:#3b82f6;">Actualizar ahora</a>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
