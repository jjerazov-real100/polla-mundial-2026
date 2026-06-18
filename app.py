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
        padding: 20px;
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
def calcular_puntos(pred_local, pred_visita, real_local, real_visita):
    """
    Retorna el total de puntos para una predicción vs resultado real.

    Reglas (acumulables, máximo 10):
      - Selección del ganador (o empate): 4 pts
      - Diferencia de gol exacta:         2 pts
      - Goles equipo local exactos:        1 pt
      - Goles equipo visita exactos:       1 pt
      - Marcador exacto (ambos):           2 pts  ← ya incluye los 2×1 de arriba
    """
    try:
        pl, pv = int(pred_local), int(pred_visita)
        rl, rv = int(real_local), int(real_visita)
    except (ValueError, TypeError):
        return 0

    puntos = 0

    # 4 pts — ganador / empate
    pred_resultado = "L" if pl > pv else ("V" if pl < pv else "E")
    real_resultado = "L" if rl > rv else ("V" if rl < rv else "E")
    if pred_resultado == real_resultado:
        puntos += 4

    # 2 pts — diferencia de gol
    if (pl - pv) == (rl - rv):
        puntos += 2

    # 1 pt por equipo con goles exactos
    if pl == rl:
        puntos += 1
    if pv == rv:
        puntos += 1

    # 2 pts — marcador exacto (reemplaza el cálculo anterior de 1+1)
    # Solo si no los sumamos ya individualmente y el marcador es idéntico
    if pl == rl and pv == rv:
        # Los 2 pts de marcador exacto SUSTITUYEN los 2×1 pt de goles
        # ya sumados arriba, entonces añadimos los 2 pts y restamos los
        # 2×1 que ya contabilizamos → neto +0 extra sobre los 1+1.
        # La regla real: exacto da 2 pts ADEMÁS de ganador+diferencia.
        # Reemplazamos los 1+1 por un bono de 2 para llegar a 10 máx.
        puntos = puntos  # 4 + 2 + 1 + 1 = 8, marcador exacto ya incluido
        # Ajuste: bono extra de marcador exacto para llegar a 10
        # (el enunciado dice máximo 10 = 4+2+2+1+1, así que marcador exacto
        #  vale 2 pts independientes de los goles individuales)
        pass  # ya tenemos 8; los 2 de marcador se suman a continuación

    # Recalculamos limpio para evitar confusión:
    return _puntos_limpio(pl, pv, rl, rv)


def _puntos_limpio(pl, pv, rl, rv):
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

    return min(pts, 10)


def calcular_ranking(pred_df, res_df):
    """Calcula el ranking general cruzando predicciones con resultados reales."""
    if pred_df.empty or res_df.empty:
        return pd.DataFrame()

    # res_df debe tener: partido_id, goles_local, goles_visita
    resultados_dict = {
        row["partido_id"]: (row["goles_local"], row["goles_visita"])
        for _, row in res_df.iterrows()
        if row.get("goles_local") != "" and row.get("goles_visita") != ""
    }

    ranking = {}
    detalles = []

    for _, row in pred_df.iterrows():
        participante = row["participante"]
        partido_id   = row["partido_id"]

        if partido_id not in resultados_dict:
            continue

        rl, rv = resultados_dict[partido_id]
        pts = _puntos_limpio(
            row["pred_local"], row["pred_visita"], rl, rv
        )

        if participante not in ranking:
            ranking[participante] = {"puntos": 0, "partidos": 0, "exactos": 0}

        ranking[participante]["puntos"]   += pts
        ranking[participante]["partidos"] += 1
        if pts == 10:
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

    rank_df, det_df = calcular_ranking(pred_df, res_df)

    # ── Métricas superiores ───────────────────────────────────────────────
    partidos_jugados = len(res_df[res_df["goles_local"] != ""]) if not res_df.empty else 0
    total_partidos   = len(part_df) if not part_df.empty else 0
    total_participantes = pred_df["participante"].nunique() if not pred_df.empty else 0

    c1, c2, c3, c4 = st.columns(4)
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

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏆 Ranking", "⚽ Detalle por partido", "📋 Predicciones", "🔍 Pronósticos por partido", "📅 Calendario"])

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
                df_p = df_p.merge(
                    part_df[["partido_id", "local", "visita", "fecha",
                              part_df.columns[part_df.columns.str.contains("hora")].tolist()[0]
                              if any(part_df.columns.str.contains("hora")) else "fecha"]],
                    on="partido_id", how="left"
                )

            # Máscara: ocultar predicciones de partidos aún bloqueados
            # para participantes que no son el seleccionado por "uno mismo"
            # (aquí mostramos un candado en lugar del marcador)
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

                if desbloqueado:
                    pred = f'<span class="score-chip">{int(row["pred_local"])}-{int(row["pred_visita"])}</span>'
                    estado = '<span style="color:#4ade80; font-size:12px;">🔓 Visible</span>'

                    if row["partido_id"] in resultados_dict_p3:
                        rl, rv = resultados_dict_p3[row["partido_id"]]
                        pts = _puntos_limpio(int(row["pred_local"]), int(row["pred_visita"]), int(rl), int(rv))
                        puntos_html = f'<span class="pts-badge">{pts} pts</span>' if pts > 0 else '<span class="pts-zero">0 pts</span>'
                else:
                    pred = '<span style="color:#6b7280; font-size:18px;">🔒</span>'
                    estado = '<span style="color:#6b7280; font-size:12px;">Bloqueado</span>'

                rows_html += f"""
                <tr>
                    <td style="color:#8891b4;">{fecha}</td>
                    <td style="color:#ffffff; font-weight:500;">{local} vs {visita}</td>
                    <td style="text-align:center;">{pred}</td>
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
                    rows_html_t4 = ""
                    for _, row in pred_partido.sort_values("participante").iterrows():
                        pred = f"{int(row['pred_local'])}-{int(row['pred_visita'])}"
                        pts_badge = ""
                        if resultado_real:
                            rl, rv = resultado_real.split("-")
                            p = _puntos_limpio(int(row["pred_local"]), int(row["pred_visita"]), int(rl), int(rv))
                            pts_badge = f'<span class="pts-badge">{p} pts</span>' if p > 0 else '<span class="pts-zero">0 pts</span>'

                        rows_html_t4 += f"""
                        <tr>
                            <td style="font-weight:500; color:#ffffff;">{row['participante']}</td>
                            <td style="text-align:center;"><span class="score-chip">{pred}</span></td>
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

        # Footer
    st.markdown(f"""
    <div style="text-align:center; margin-top:3rem; color:#4b5563; font-size:12px;">
        Actualizado cada 60 seg · {datetime.now().strftime('%d/%m/%Y %H:%M')}
        &nbsp;·&nbsp; <a href="#" onclick="window.location.reload()" style="color:#3b82f6;">Actualizar ahora</a>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
