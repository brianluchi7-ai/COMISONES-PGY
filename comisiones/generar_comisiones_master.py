import pandas as pd
from conexion_mysql import crear_conexion

# ======================================================
# === OBL DIGITAL — Generador RTN_MASTER_PGY (affiliate corregido)
# ======================================================

def limpiar_encabezados(df, tabla):
    try:
        columnas_basura = [c for c in df.columns if c.lower().startswith("col")]
        if columnas_basura:
            print(f"🧹 Eliminando columnas basura en {tabla}: {columnas_basura}")
            df = df.drop(columns=columnas_basura)

        primera_fila = df.iloc[0].astype(str).tolist()
        if all(len(str(x).strip()) > 0 for x in primera_fila):
            if not any("date" in str(x).lower() for x in df.columns):
                print(f"🔹 Aplicando primera fila como encabezado en {tabla}...")
                df.columns = primera_fila
                df = df.drop(df.index[0])

    except Exception as e:
        print(f"⚠️ Error limpiando encabezados en {tabla}: {e}")

    return df


def estandarizar_columnas(df, tabla):
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # 🔹 Mapeo actualizado: affiliate solo se toma si el encabezado original dice 'affiliate' o 'afiliado'
    rename_map = {
        "fecha": "date", "date": "date", "date_ftd": "date", "fechadep": "date",
        "fecha_dep": "date", "fecha_rtn": "date",

        "team": "team", "equipo": "team", "team_name": "team", "leader_team": "team",

        "agente": "agent", "agent": "agent", "agent_name": "agent",

        "id": "id", "usuario": "id", "id_user": "id", "id_usuario": "id",

        "pais": "country", "country_name": "country",

        # ✅ solo de 'affiliate' o 'afiliado'
        "affiliate": "affiliate",
        "afiliado": "affiliate",

        "monto": "usd", "usd": "usd", "usd_total": "usd", "amount_country": "usd", "ftd_day": "usd",

        "origen": "source", "source_name": "source"
    }

    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df.rename(columns={old: new}, inplace=True)

    vacias = [c for c in df.columns if df[c].isna().all()]
    if vacias:
        print(f"🧩 Eliminando columnas vacías: {vacias}")
        df = df.drop(columns=vacias)

    return df


def cargar_tabla(tabla, conexion):
    print(f"\n===> Leyendo tabla {tabla} ...")
    df = pd.read_sql(f"SELECT * FROM {tabla}", conexion)
    print(f"   🔸 Columnas detectadas: {list(df.columns)}")
    print(f"   🔸 Registros brutos: {len(df)}")

    df = limpiar_encabezados(df, tabla)
    df = estandarizar_columnas(df, tabla)

    month_raw = tabla.lower()
    if "sep" in month_raw:
        df["month_name"] = "Sep"
    elif "oct" in month_raw:
        df["month_name"] = "Oct"
    elif "nov" in month_raw:
        df["month_name"] = "Nov"
    else:
        df["month_name"] = "PGY"

    if "source" not in df.columns:
        df["source"] = None

    df = df.loc[:, ~df.columns.duplicated()]
    df = df.reset_index(drop=True)
    print(f"   ✅ Filas válidas: {len(df)}")
    return df


def obtener_datos():
    conexion = crear_conexion()
    if conexion is None:
        print("❌ No se pudo conectar a Railway.")
        return pd.DataFrame()

    tablas = [
        "dep_sep_rtn_PGY_2025",
        "dep_oct_rtn_PGY_2025",
        "dep_nov_rtn_PGY_2025",
        "dep_rtn_PGY_2025",
        "ftds_sep_PGY_2025",
        "ftds_oct_PGY_2025",
        "ftds_nov_PGY_2025",
        "ftds_PGY_2025"
    ]

    dataframes = []
    for tabla in tablas:
        try:
            df = cargar_tabla(tabla, conexion)
            if not df.empty:
                dataframes.append(df)
        except Exception as e:
            print(f"⚠️ Error procesando {tabla}: {e}")

    conexion.close()

    if not dataframes:
        print("❌ No se generó CMN_MASTER (sin datos).")
        return pd.DataFrame()

    for i in range(len(dataframes)):
        dataframes[i].columns = dataframes[i].columns.astype(str)
        dataframes[i] = dataframes[i].reset_index(drop=True)

    df_master = pd.concat(dataframes, ignore_index=True, sort=False)
    df_master.dropna(how="all", inplace=True)
    df_master = df_master.reset_index(drop=True)

    columnas_finales = ["date", "id", "team", "agent", "country", "affiliate", "usd", "month_name", "source"]
    for col in columnas_finales:
        if col not in df_master.columns:
            df_master[col] = None

    df_master = df_master[columnas_finales]

    # 🔹 Limpieza general
    df_master = df_master.applymap(lambda x: str(x).strip() if isinstance(x, str) else x)
    df_master = df_master.replace({"": None, "nan": None, "NaN": None, pd.NA: None, pd.NaT: None})
    df_master = df_master.where(pd.notnull(df_master), None)
    df_master.dropna(subset=["date"], how="any", inplace=True)
    df_master = df_master.reset_index(drop=True)

    # 🔹 Conversión numérica (solo enteros)
    for col in ["usd", "id"]:
        if col in df_master.columns:
            df_master[col] = (
                pd.to_numeric(df_master[col], errors="coerce")
                .fillna(0)
                .astype(int)
            )

    print(f"\n📊 CMN_MASTER alineado correctamente con {len(df_master)} registros.")
    df_master.to_csv("CMN_MASTER_preview.csv", index=False, encoding="utf-8-sig")
    print("💾 Vista previa guardada: CMN_MASTER_preview.csv")

    # ==========================================================
    # === CARGA DIRECTA A MYSQL RAILWAY ========================
    # ==========================================================
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()

            cursor.execute("DROP TABLE IF EXISTS CMN_MASTER_CLEAN;")
            cursor.execute("""
                CREATE TABLE CMN_MASTER_CLEAN (
                    date TEXT,
                    id INT,
                    team TEXT,
                    agent TEXT,
                    country TEXT,
                    affiliate TEXT,
                    usd INT,
                    month_name TEXT,
                    source TEXT
                );
            """)
            conexion.commit()

            columnas = ["date", "id", "team", "agent", "country", "affiliate", "usd", "month_name", "source"]

            insert_sql = f"""
                INSERT INTO CMN_MASTER_CLEAN
                ({", ".join(columnas)})
                VALUES ({", ".join(["%s"] * len(columnas))})
            """

            data = [
                tuple(row.get(c) for c in columnas)
                for _, row in df_master.iterrows()
            ]

            cursor.executemany(insert_sql, data)
            conexion.commit()
            conexion.close()

            print("✅ CMN_MASTER_CLEAN creada y poblada correctamente en Railway (affiliate corregido y enteros).")
        else:
            print("⚠️ No se pudo abrir conexión para escribir en Railway.")
    except Exception as e:
        print(f"⚠️ Error al crear CMN_MASTER_CLEAN: {e}")
    return df_master


if __name__ == "__main__":
    df = obtener_datos()
    print("\nPrimeras filas de CMN_MASTER:")
    print(df.head())
