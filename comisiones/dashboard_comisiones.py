import re
import pandas as pd
import dash
from dash import html, dcc, Input, Output, dash_table
import plotly.express as px
from conexion_mysql import crear_conexion

# ======================================================
# === OBL DIGITAL DASHBOARD — COMISIONES POR AGENTE  ===
# ======================================================

def cargar_datos():
    """Carga datos desde MySQL o CSV local."""
    try:
        conexion = crear_conexion()
        if conexion:
            print("✅ Leyendo desde Railway MySQL...")
            query = "SELECT * FROM CMN_MASTER_CLEAN"
            df = pd.read_sql(query, conexion)
            conexion.close()
            return df
    except Exception as e:
        print(f"⚠️ Error conectando a SQL, leyendo CSV local: {e}")

    print("📁 Leyendo desde CSV local...")
    return pd.read_csv("CMN_MASTER_preview.csv", dtype=str)


# === 1️⃣ Cargar datos base ===
df = cargar_datos()
df.columns = [c.strip().lower() for c in df.columns]

if "source" not in df.columns:
    df["source"] = None

# === 2️⃣ Normalizar fechas ===
def convertir_fecha(valor):
    try:
        if "/" in valor:
            return pd.to_datetime(valor, format="%d/%m/%Y", errors="coerce")
        elif "-" in valor:
            return pd.to_datetime(str(valor).split(" ")[0], errors="coerce")
    except Exception:
        return pd.NaT
    return pd.NaT

df["date"] = df["date"].astype(str).str.strip().apply(convertir_fecha)
df = df[df["date"].notna()]
df["date"] = pd.to_datetime(df["date"], utc=False).dt.tz_localize(None)

# === 3️⃣ Limpieza USD ===
def limpiar_usd(valor):
    if pd.isna(valor):
        return 0.0
    s = str(valor).strip()
    if s == "":
        return 0.0
    s = re.sub(r"[^\d,.\-]", "", s)
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        partes = s.split(",")
        s = s.replace(",", ".") if len(partes[-1]) == 2 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except:
        return 0.0

df["usd"] = df["usd"].apply(limpiar_usd)

# === 4️⃣ Limpieza texto ===
for col in ["team", "agent", "country", "affiliate", "source", "id"]:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.title()
        df[col].replace({"Nan": None, "None": None, "": None}, inplace=True)

# === 5️⃣ Lógica comisión progresiva ===
def porcentaje_tramo_progresivo(n_venta):
    if 1 <= n_venta <= 3:
        return 0.10
    elif 4 <= n_venta <= 7:
        return 0.17
    elif 8 <= n_venta <= 12:
        return 0.19
    elif 13 <= n_venta <= 17:
        return 0.22
    elif 18 <= n_venta <= 21:
        return 0.25
    elif n_venta >= 22:
        return 0.30
    return 0.0

df = df.sort_values(["agent", "date"]).reset_index(drop=True)
df["ftd_num"] = df.groupby("agent").cumcount() + 1
df["comm_pct"] = df["ftd_num"].apply(porcentaje_tramo_progresivo)
df["commission_usd"] = df["usd"] * df["comm_pct"]

# === 6️⃣ Cálculo de BONUS SEMANAL acumulable ===
MXN_USD = 18.19  # tipo de cambio fijo
df["year"] = df["date"].dt.year
df["week"] = df["date"].dt.isocalendar().week

bonus_data = []

for (agent, year, week), grupo in df.groupby(["agent", "year", "week"]):
    ftds = len(grupo)
    bonus_mxn = 0
    bonus_usd = 0

    if ftds >= 15:
        prev_bonus = sum(b["bonus_usd"] for b in bonus_data if b["agent"] == agent)
        bonus_usd = 150 + prev_bonus
    elif ftds == 5:
        bonus_mxn = 1500
    elif ftds == 4:
        bonus_mxn = 1000
    elif ftds == 2:
        bonus_mxn = 500

    if bonus_mxn > 0:
        bonus_usd = bonus_mxn / MXN_USD
        prev_bonus = sum(b["bonus_usd"] for b in bonus_data if b["agent"] == agent)
        bonus_usd += prev_bonus

    bonus_data.append({
        "agent": agent,
        "year": year,
        "week": week,
        "bonus_usd": round(bonus_usd, 2)
    })

df_bonus = pd.DataFrame(bonus_data)
df_bonus_total = df_bonus.groupby("agent", as_index=False)["bonus_usd"].max()

# === 7️⃣ Función formato K/M ===
def formato_km(valor):
    if valor >= 1_000_000:
        return f"{valor/1_000_000:.2f}M"
    elif valor >= 1_000:
        return f"{valor/1_000:.1f}K"
    else:
        return f"{valor:.0f}"

# === 8️⃣ App Dash ===
app = dash.Dash(__name__)
server = app.server
app.title = "OBL Digital — Dashboard Comisiones"

# === 9️⃣ Layout ===
app.layout = html.Div(
    style={"backgroundColor": "#0d0d0d", "color": "#000000", "fontFamily": "Poppins, Arial", "padding": "20px"},
    children=[
        html.H1("💰 DASHBOARD COMISIONES POR AGENTE", style={
            "textAlign": "center",
            "color": "#D4AF37",
            "marginBottom": "30px",
            "fontWeight": "bold"
        }),

        html.Div(
            style={"display": "flex", "justifyContent": "space-between"},
            children=[
                # Filtros
                html.Div(
                    style={
                        "width": "25%",
                        "backgroundColor": "#1a1a1a",
                        "padding": "20px",
                        "borderRadius": "12px",
                        "boxShadow": "0 0 15px rgba(212,175,55,0.3)",
                        "textAlign": "center"
                    },
                    children=[
                        html.Label("Date", style={"color": "#D4AF37", "fontWeight": "bold", "textAlign": "center", "display": "block"}),
                        dcc.DatePickerRange(
                            id="filtro-fecha",
                            start_date=df["date"].min(),
                            end_date=df["date"].max(),
                            display_format="YYYY-MM-DD",
                            minimum_nights=0
                        ),
                        html.Br(), html.Br(),
                        html.Label("Agent", style={"color": "#D4AF37", "fontWeight": "bold", "textAlign": "center", "display": "block"}),
                        dcc.Dropdown(
                            sorted(df["agent"].dropna().unique()),
                            [],
                            multi=True,
                            id="filtro-agent",
                            placeholder="Selecciona uno o varios agentes"
                        ),
                    ],
                ),

                # Panel principal
                html.Div(
                    style={"width": "72%"},
                    children=[
                        # Tarjetas
                        html.Div(
                            style={"display": "flex", "justifyContent": "space-around", "flexWrap": "wrap", "gap": "10px"},
                            children=[
                                html.Div(id="card-porcentaje", style={"flex": "1 1 18%", "minWidth": "200px"}),
                                html.Div(id="card-usd-ventas", style={"flex": "1 1 18%", "minWidth": "200px"}),
                                html.Div(id="card-usd-bonus", style={"flex": "1 1 18%", "minWidth": "200px"}),
                                html.Div(id="card-usd-comision", style={"flex": "1 1 18%", "minWidth": "200px"}),
                                html.Div(id="card-total-ftd", style={"flex": "1 1 18%", "minWidth": "200px"}),
                            ],
                        ),
                        html.Br(),
                        dcc.Graph(id="grafico-comision-agent", style={"width": "100%", "height": "400px"}),
                        html.Br(),
                        html.H4("📋 Detalle de transacciones y comisiones", style={"color": "#D4AF37"}),
                        dash_table.DataTable(
                            id="tabla-detalle",
                            columns=[
                                {"name": "DATE", "id": "date"},
                                {"name": "AGENT", "id": "agent"},
                                {"name": "TEAM", "id": "team"},
                                {"name": "COUNTRY", "id": "country"},
                                {"name": "AFFILIATE", "id": "affiliate"},
                                {"name": "USD", "id": "usd"},
                                {"name": "FTD_NUM", "id": "ftd_num"},
                                {"name": "COMM_PCT", "id": "comm_pct"},
                                {"name": "COMMISSION_USD", "id": "commission_usd"},
                            ],
                            style_table={"overflowX": "auto", "backgroundColor": "#0d0d0d"},
                            page_size=10,
                            style_cell={
                                "textAlign": "center",
                                "color": "#f2f2f2",
                                "backgroundColor": "#1a1a1a",
                                "fontSize": "12px",
                            },
                            style_header={"backgroundColor": "#D4AF37", "color": "#000", "fontWeight": "bold"},
                            sort_action="native",
                        ),
                    ],
                ),
            ],
        ),
    ],
)

# === 🔟 Callback ===
@app.callback(
    [
        Output("card-porcentaje", "children"),
        Output("card-usd-ventas", "children"),
        Output("card-usd-bonus", "children"),
        Output("card-usd-comision", "children"),
        Output("card-total-ftd", "children"),
        Output("grafico-comision-agent", "figure"),
        Output("tabla-detalle", "data"),
    ],
    [Input("filtro-agent", "value"), Input("filtro-fecha", "start_date"), Input("filtro-fecha", "end_date")],
)
def actualizar_dashboard(agent, start_date, end_date):
    df_filtrado = df.copy()

    if agent:
        df_filtrado = df_filtrado[df_filtrado["agent"].isin(agent)]
    if start_date and end_date:
        df_filtrado = df_filtrado[
            (df_filtrado["date"] >= pd.to_datetime(start_date)) &
            (df_filtrado["date"] <= pd.to_datetime(end_date))
        ]

    if df_filtrado.empty:
        fig_vacio = px.scatter(title="Sin datos para mostrar")
        fig_vacio.update_layout(paper_bgcolor="#0d0d0d", plot_bgcolor="#0d0d0d", font_color="#f2f2f2")
        vacio = html.Div("Sin datos", style={"color": "#D4AF37", "textAlign": "center"})
        return vacio, vacio, vacio, vacio, vacio, fig_vacio, []

    total_usd = df_filtrado["usd"].sum()
    total_commission = df_filtrado["commission_usd"].sum()
    total_ftd = len(df_filtrado)

    # Bonus por agente filtrado
    bonus_filtrado = df_bonus[df_bonus["agent"].isin(df_filtrado["agent"].unique())]
    total_bonus = bonus_filtrado["bonus_usd"].max() if not bonus_filtrado.empty else 0
    total_commission_final = total_commission + total_bonus

    promedio_pct = total_commission / total_usd if total_usd > 0 else 0.0

    card_style = {
        "backgroundColor": "#1a1a1a",
        "borderRadius": "10px",
        "padding": "20px",
        "textAlign": "center",
        "boxShadow": "0 0 10px rgba(212,175,55,0.3)",
    }

    card_porcentaje = html.Div([
        html.H4("PORCENTAJE COMISIÓN", style={"color": "#D4AF37"}),
        html.H2(f"{promedio_pct*100:,.2f}%", style={"color": "#FFFFFF"})
    ], style=card_style)

    card_usd_ventas = html.Div([
        html.H4("VENTAS USD", style={"color": "#D4AF37"}),
        html.H2(formato_km(total_usd), style={"color": "#FFFFFF"})
    ], style=card_style)

    card_usd_bonus = html.Div([
        html.H4("BONUS SEMANAL USD", style={"color": "#D4AF37"}),
        html.H2(formato_km(total_bonus), style={"color": "#FFFFFF"})
    ], style=card_style)

    card_usd_comision = html.Div([
        html.H4("COMISIÓN USD (TOTAL)", style={"color": "#D4AF37"}),
        html.H2(formato_km(total_commission_final), style={"color": "#FFFFFF"})
    ], style=card_style)

    card_total_ftd = html.Div([
        html.H4("TOTAL VENTAS (FTDs)", style={"color": "#D4AF37"}),
        html.H2(f"{total_ftd:,}", style={"color": "#FFFFFF"})
    ], style=card_style)

    df_agent = df_filtrado.groupby("agent", as_index=False)["commission_usd"].sum()
    fig_agent = px.bar(
        df_agent,
        x="agent",
        y="commission_usd",
        title="Comisión USD by Agent",
        color="commission_usd",
        color_continuous_scale="YlOrBr"
    )
    fig_agent.update_layout(paper_bgcolor="#0d0d0d", plot_bgcolor="#0d0d0d", font_color="#f2f2f2", title_font_color="#D4AF37")

    df_tabla = df_filtrado[[
        "date", "agent", "team", "country", "affiliate", "usd", "ftd_num", "comm_pct", "commission_usd"
    ]].copy()
    df_tabla["comm_pct"] = df_tabla["comm_pct"].apply(lambda x: f"{x*100:.2f}%")
    df_tabla["commission_usd"] = df_tabla["commission_usd"].round(2)

    return (
        card_porcentaje,
        card_usd_ventas,
        card_usd_bonus,
        card_usd_comision,
        card_total_ftd,
        fig_agent,
        df_tabla.to_dict("records")
    )

# === 🔟 Index string para capturar imagen (igual que el otro dashboard) ===
app.index_string = '''
<!DOCTYPE html>
<html>
<head>
  {%metas%}
  <title>OBL Digital — Dashboard Comisiones</title>
  {%favicon%}
  {%css%}
  <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
</head>
<body>
  {%app_entry%}
  <footer>
    {%config%}
    {%scripts%}
    {%renderer%}
  </footer>

  <script>
    window.addEventListener("message", async (event) => {
      if (!event.data || event.data.action !== "capture_dashboard") return;

      try {
        const canvas = await html2canvas(document.body, { useCORS: true, scale: 2, backgroundColor: "#0d0d0d" });
        const imgData = canvas.toDataURL("image/png");

        window.parent.postMessage({
          action: "capture_image",
          img: imgData,
          filetype: event.data.type
        }, "*");
      } catch (err) {
        console.error("Error al capturar dashboard:", err);
        window.parent.postMessage({ action: "capture_done" }, "*");
      }
    });
  </script>
</body>
</html>
'''

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8060, debug=True)

