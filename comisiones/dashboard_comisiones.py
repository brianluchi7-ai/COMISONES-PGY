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

# Si no existe la columna 'source', la creamos vacía para evitar error
if "source" not in df.columns:
    df["source"] = None
    print("⚠️ Columna 'source' no encontrada en DB — se agregó vacía temporalmente.")

# === 2️⃣ Normalizar fechas ===
def convertir_fecha(valor):
    try:
        if "/" in valor:
            return pd.to_datetime(valor, format="%d/%m/%Y", errors="coerce")
        elif "-" in valor:
            # por si viene con hora: "2025-01-02 13:22:11"
            return pd.to_datetime(str(valor).split(" ")[0], errors="coerce")
    except Exception:
        return pd.NaT
    return pd.NaT

df["date"] = df["date"].astype(str).str.strip().apply(convertir_fecha)
df = df[df["date"].notna()]
df["date"] = pd.to_datetime(df["date"], utc=False).dt.tz_localize(None)

# === 3️⃣ Limpieza de USD (igual que en tu dashboard original) ===
def limpiar_usd(valor):
    if pd.isna(valor):
        return 0.0
    s = str(valor).strip()
    if s == "":
        return 0.0
    # quitar símbolos no numéricos
    s = re.sub(r"[^\d,.\-]", "", s)
    # manejo de separadores , y .
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

# === 4️⃣ Limpieza de texto ===
for col in ["team", "agent", "country", "affiliate", "source", "id"]:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.title()
        df[col].replace({"Nan": None, "None": None, "": None}, inplace=True)

# === 5️⃣ Lógica de comisión progresiva (traducción de tus macros) ===
def porcentaje_tramo_progresivo(n_venta):
    """
    Emula el Select Case de Calcular_Total_Comision_Progresiva:
        1-3   -> 10%
        4-7   -> 17%
        8-12  -> 19%
        13-17 -> 22%
        18-21 -> 25%
        >=22  -> 30%
    """
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

# Ordenar por agente y fecha, y numerar las ventas por agente
df = df.sort_values(["agent", "date"]).reset_index(drop=True)
df["ftd_num"] = df.groupby("agent").cumcount() + 1

# Calcular porcentaje de comisión por venta y comisión en USD
df["comm_pct"] = df["ftd_num"].apply(porcentaje_tramo_progresivo)
df["commission_usd"] = df["usd"] * df["comm_pct"]

# === 6️⃣ Función para mostrar valores en K/M ===
def formato_km(valor):
    if valor >= 1_000_000:
        return f"{valor/1_000_000:.2f}M"
    elif valor >= 1_000:
        return f"{valor/1_000:.1f}K"
    else:
        return f"{valor:.0f}"

# === 7️⃣ Inicializar app ===
external_scripts = [
    "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/pptxgenjs/3.10.0/pptxgen.bundle.js"
]

app = dash.Dash(__name__, external_scripts=external_scripts)
server = app.server
app.title = "OBL Digital — Dashboard Comisiones"

# === 8️⃣ Layout: único filtro = Agent ===
app.layout = html.Div(
    style={
        "backgroundColor": "#0d0d0d",
        "color": "#000000",
        "fontFamily": "Arial",
        "padding": "20px",
    },
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
                # --- Panel de filtro (solo Agent) ---
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
                        html.H4("Filtros", style={"color": "#D4AF37", "textAlign": "center"}),

                        html.Label("Agent", style={"color": "#D4AF37", "fontWeight": "bold"}),
                        dcc.Dropdown(
                            sorted(df["agent"].dropna().unique()),
                            [],
                            multi=True,
                            id="filtro-agent",
                            placeholder="Selecciona uno o varios agentes"
                        ),
                    ],
                ),

                # --- Panel principal ---
                html.Div(
                    style={"width": "72%"},
                    children=[
                        # Tarjetas
                        html.Div(
                            style={"display": "flex", "justifyContent": "space-around", "flexWrap": "wrap"},
                            children=[
                                html.Div(id="card-porcentaje", style={"width": "23%", "minWidth": "220px", "marginBottom": "15px"}),
                                html.Div(id="card-usd-ventas", style={"width": "23%", "minWidth": "220px", "marginBottom": "15px"}),
                                html.Div(id="card-usd-comision", style={"width": "23%", "minWidth": "220px", "marginBottom": "15px"}),
                                html.Div(id="card-total-ftd", style={"width": "23%", "minWidth": "220px", "marginBottom": "15px"}),
                            ],
                        ),
                        html.Br(),

                        # Gráficos
                        html.Div(
                            style={"display": "flex", "flexWrap": "wrap", "gap": "20px"},
                            children=[
                                dcc.Graph(id="grafico-comision-country", style={"width": "48%", "height": "340px"}),
                                dcc.Graph(id="grafico-comision-affiliate", style={"width": "48%", "height": "340px"}),
                                dcc.Graph(id="grafico-comision-team", style={"width": "48%", "height": "340px"}),
                                dcc.Graph(id="grafico-comision-date", style={"width": "48%", "height": "340px"}),
                            ],
                        ),
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
                            style_header={
                                "backgroundColor": "#D4AF37",
                                "color": "#000",
                                "fontWeight": "bold"
                            },
                            sort_action="native",
                        ),
                    ],
                ),
            ],
        ),
    ],
)

# === 9️⃣ Callback principal ===
@app.callback(
    [
        Output("card-porcentaje", "children"),
        Output("card-usd-ventas", "children"),
        Output("card-usd-comision", "children"),
        Output("card-total-ftd", "children"),
        Output("grafico-comision-country", "figure"),
        Output("grafico-comision-affiliate", "figure"),
        Output("grafico-comision-team", "figure"),
        Output("grafico-comision-date", "figure"),
        Output("tabla-detalle", "data"),
    ],
    [
        Input("filtro-agent", "value"),
    ],
)
def actualizar_dashboard(agent):
    df_filtrado = df.copy()

    # Filtro por agente (único filtro del dashboard)
    if agent:
        df_filtrado = df_filtrado[df_filtrado["agent"].isin(agent)]

    # Si no hay datos después del filtro, devolver vacíos controlados
    if df_filtrado.empty:
        fig_vacio = px.scatter(title="Sin datos para mostrar")
        fig_vacio.update_layout(
            paper_bgcolor="#0d0d0d",
            plot_bgcolor="#0d0d0d",
            font_color="#f2f2f2",
            title_font_color="#D4AF37",
        )
        card_style = {
            "backgroundColor": "#1a1a1a",
            "borderRadius": "10px",
            "padding": "20px",
            "textAlign": "center",
            "boxShadow": "0 0 10px rgba(212,175,55,0.3)",
        }
        vacio = html.Div([
            html.H4("Sin datos", style={"color": "#D4AF37", "fontWeight": "bold"}),
            html.H2("--", style={"color": "#FFFFFF", "fontSize": "26px"})
        ], style=card_style)

        return vacio, vacio, vacio, vacio, fig_vacio, fig_vacio, fig_vacio, fig_vacio, []

    # --- Métricas base ---
    total_usd = df_filtrado["usd"].sum()
    total_commission = df_filtrado["commission_usd"].sum()
    total_ftd = len(df_filtrado)

    if total_usd > 0:
        promedio_pct = total_commission / total_usd  # % efectivo sobre todas las ventas filtradas
    else:
        promedio_pct = 0.0

    # --- Estilo de cards ---
    card_style = {
        "backgroundColor": "#1a1a1a",
        "borderRadius": "10px",
        "padding": "20px",
        "width": "100%",
        "textAlign": "center",
        "boxShadow": "0 0 10px rgba(212,175,55,0.3)",
    }

    # 1️⃣ Porcentaje de comisión
    card_porcentaje = html.Div([
        html.H4("PORCENTAJE COMISIÓN", style={"color": "#D4AF37", "fontWeight": "bold"}),
        html.H2(f"{promedio_pct*100:,.2f}%", style={"color": "#FFFFFF", "fontSize": "30px"})
    ], style=card_style)

    # 2️⃣ Monto USD (ventas totales)
    card_usd_ventas = html.Div([
        html.H4("VENTAS USD", style={"color": "#D4AF37", "fontWeight": "bold"}),
        html.H2(formato_km(total_usd), style={"color": "#FFFFFF", "fontSize": "30px"})
    ], style=card_style)

    # 3️⃣ Comisión en dólares
    card_usd_comision = html.Div([
        html.H4("COMISIÓN USD", style={"color": "#D4AF37", "fontWeight": "bold"}),
        html.H2(formato_km(total_commission), style={"color": "#FFFFFF", "fontSize": "30px"})
    ], style=card_style)

    # 4️⃣ Total de ventas (FTDs)
    card_total_ftd = html.Div([
        html.H4("TOTAL VENTAS (FTDs)", style={"color": "#D4AF37", "fontWeight": "bold"}),
        html.H2(f"{total_ftd:,}", style={"color": "#FFFFFF", "fontSize": "30px"})
    ], style=card_style)

    # --- Gráficos (todas las métricas usan commission_usd) ---
    # Comisión por Country
    fig_country = px.pie(
        df_filtrado,
        names="country",
        values="commission_usd",
        title="Comisión USD by Country",
        color_discrete_sequence=px.colors.sequential.YlOrBr
    )

    # Comisión por Affiliate
    fig_affiliate = px.pie(
        df_filtrado,
        names="affiliate",
        values="commission_usd",
        title="Comisión USD by Affiliate",
        color_discrete_sequence=px.colors.sequential.YlOrBr
    )

    # Comisión por Team
    df_team = df_filtrado.groupby("team", as_index=False)["commission_usd"].sum()
    fig_team = px.bar(
        df_team,
        x="team",
        y="commission_usd",
        title="Comisión USD by Team",
        color="commission_usd",
        color_continuous_scale="YlOrBr"
    )

    # Comisión por Date
    df_fecha = df_filtrado.sort_values("date")
    fig_date = px.line(
        df_fecha,
        x="date",
        y="commission_usd",
        title="Comisión USD by Date",
        markers=True,
        color_discrete_sequence=["#D4AF37"]
    )

    for fig in [fig_country, fig_affiliate, fig_team, fig_date]:
        fig.update_layout(
            paper_bgcolor="#0d0d0d",
            plot_bgcolor="#0d0d0d",
            font_color="#f2f2f2",
            title_font_color="#D4AF37"
        )

    # --- Tabla detalle ---
    df_tabla = df_filtrado[[
        "date", "agent", "team", "country", "affiliate",
        "usd", "ftd_num", "comm_pct", "commission_usd"
    ]].copy()
    df_tabla["comm_pct"] = df_tabla["comm_pct"].apply(lambda x: f"{x*100:.2f}%")
    df_tabla["commission_usd"] = df_tabla["commission_usd"].round(2)

    return (
        card_porcentaje,
        card_usd_ventas,
        card_usd_comision,
        card_total_ftd,
        fig_country,
        fig_affiliate,
        fig_team,
        fig_date,
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
    app.run_server(host="0.0.0.0", port=8050, debug=True)
