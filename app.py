"""
app.py — Dashboard Streamlit del tracker de precio "Diesel B5 S-50"
por planta, PetroPerú (histórico 2026, enero en adelante).

Correr localmente:
    streamlit run app.py

Deploy: conectar este repo en https://share.streamlit.io (Streamlit Cloud),
apuntando a este archivo como entrypoint.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Tracker Diesel B5 S-50 — PetroPerú", layout="wide")

RUTA_CSV = "data/precios.csv"


@st.cache_data(ttl=3600)
def cargar_datos():
    df = pd.read_csv(RUTA_CSV)
    df["fecha_vigencia"] = pd.to_datetime(df["fecha_vigencia"], format="%d.%m.%Y", errors="coerce")
    return df.sort_values("fecha_vigencia")


st.title("⛽ Tracker Diesel B5 S-50 — PetroPerú")
st.caption("Precio por planta, extraído automáticamente de las listas oficiales de PetroPerú")

try:
    df = cargar_datos()
except FileNotFoundError:
    st.error(
        "Todavía no existe data/precios.csv. Corre `python update.py` "
        "al menos una vez para generar el histórico."
    )
    st.stop()

if df.empty:
    st.warning("El CSV existe pero está vacío.")
    st.stop()

# ── Sidebar: filtros ────────────────────────────────────────────
st.sidebar.header("Filtros")

plantas = sorted(df["planta"].unique())
# Vacío = todas las plantas. Con default=[] el widget queda colapsado como
# un dropdown compacto en vez de mostrar los 18 chips ya seleccionados.
plantas_sel_raw = st.sidebar.multiselect(
    "Plantas (vacío = todas)", plantas, default=[]
)
plantas_sel = plantas_sel_raw if plantas_sel_raw else plantas

fecha_min, fecha_max = df["fecha_vigencia"].min(), df["fecha_vigencia"].max()
rango_fechas = st.sidebar.date_input(
    "Rango de fechas", value=(fecha_min, fecha_max),
    min_value=fecha_min, max_value=fecha_max,
)

# ── Filtrado ─────────────────────────────────────────────────────
# df_plantas: solo filtrado por planta (sin recorte de fechas) — lo usamos
# para la comparación "valor actual vs. promedio de enero", donde el valor
# actual SIEMPRE debe ser el dato más reciente del histórico, sin importar
# qué rango de fechas esté seleccionado en el sidebar.
df_plantas = df[df["planta"].isin(plantas_sel)] if plantas_sel else df.iloc[0:0]

df_filtrado = df_plantas.copy()
if len(rango_fechas) == 2:
    inicio, fin = rango_fechas
    df_filtrado = df_filtrado[
        (df_filtrado["fecha_vigencia"] >= pd.Timestamp(inicio))
        & (df_filtrado["fecha_vigencia"] <= pd.Timestamp(fin))
    ]

# ── Métricas rápidas ─────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
ultima_fecha = df["fecha_vigencia"].max()
col1.metric("Última actualización", ultima_fecha.strftime("%d/%m/%Y") if pd.notna(ultima_fecha) else "—")
col2.metric("Plantas en el dataset", df["planta"].nunique())
col3.metric("Listas históricas procesadas", df["lista_id"].nunique())

# ── Evolución semanal + promedio mensual ─────────────────────────
st.subheader("Evolución del precio Diesel B5 S-50")

if df_filtrado.empty:
    st.info("No hay datos para esta combinación de filtros.")
else:
    col_linea, col_barras = st.columns([3, 2])

    with col_linea:
        st.markdown("**Evolución semanal**")
        # Las listas de precios no salen todos los días (son ~2-3 por mes),
        # así que agrupamos por semana (lunes de cada semana ISO) en vez de
        # graficar cada fecha exacta de vigencia como un punto en el eje x.
        df_semanal = df_filtrado.copy()
        df_semanal["semana"] = df_semanal["fecha_vigencia"].dt.to_period("W-SUN").dt.start_time
        df_semanal = df_semanal.groupby(["planta", "semana"], as_index=False)["valor"].mean()

        fig_linea = px.line(
            df_semanal, x="semana", y="valor", color="planta",
            markers=True,
            labels={"semana": "Semana", "valor": "Precio (S/ Galón)"},
        )
        fig_linea.update_xaxes(
            dtick="M1",  # los PUNTOS son semanales; las etiquetas se muestran una vez al mes
            tickformat="%d %b",
            tickangle=-45,
        )
        fig_linea.update_layout(height=480)
        st.plotly_chart(fig_linea, use_container_width=True)

    with col_barras:
        st.markdown("**Promedio mensual a nivel país**")
        # Promedio de TODAS las plantas seleccionadas por mes (no una barra
        # por planta) — evolución del precio promedio nacional, mes a mes.
        df_mensual = df_filtrado.copy()
        df_mensual["mes"] = df_mensual["fecha_vigencia"].dt.to_period("M").dt.to_timestamp()
        df_mensual = df_mensual.groupby("mes", as_index=False)["valor"].mean()

        fig_barras = px.bar(
            df_mensual, x="mes", y="valor",
            text_auto=".1f",
            labels={"mes": "Mes", "valor": "Precio promedio nacional (S/ Galón)"},
        )
        fig_barras.update_traces(textposition="inside")
        fig_barras.update_xaxes(tickformat="%b %Y", dtick="M1", tickangle=-45)
        fig_barras.update_layout(height=480)
        st.plotly_chart(fig_barras, use_container_width=True)

    st.subheader("Último precio por planta")
    ultimo_por_planta = (
        df_filtrado.sort_values("fecha_vigencia")
        .groupby("planta")
        .tail(1)[["planta", "fecha_vigencia", "valor"]]
        .sort_values("valor")
    )
    st.dataframe(ultimo_por_planta, use_container_width=True, hide_index=True)

# ── Valor actual vs. promedio de enero ───────────────────────────
st.subheader("Valor actual vs. promedio de enero")

if df_plantas.empty:
    st.info("No hay plantas seleccionadas.")
else:
    # "Valor actual" = la fila más reciente por planta en TODO el histórico
    # (df_plantas, sin el recorte de fecha del sidebar) — así este número
    # nunca queda "viejo" por un filtro de fecha que el usuario haya dejado puesto.
    anio_referencia = df_plantas["fecha_vigencia"].max().year

    valor_actual = (
        df_plantas.sort_values("fecha_vigencia")
        .groupby("planta")
        .tail(1)
        .set_index("planta")["valor"]
    )

    df_enero = df_plantas[
        (df_plantas["fecha_vigencia"].dt.year == anio_referencia)
        & (df_plantas["fecha_vigencia"].dt.month == 1)
    ]
    promedio_enero = df_enero.groupby("planta")["valor"].mean()

    etiqueta_enero = f"Promedio enero {anio_referencia}"
    comparativo = (
        pd.DataFrame({"Valor actual": valor_actual, etiqueta_enero: promedio_enero})
        .dropna(how="all")
        .rename_axis("planta")
        .reset_index()
    )

    if comparativo.empty:
        st.info("No hay suficiente historial para esta comparación (falta enero o datos recientes).")
    else:
        comparativo_largo = comparativo.melt(
            id_vars="planta", var_name="periodo", value_name="valor"
        )
        fig_comparativo = px.bar(
            comparativo_largo.sort_values("planta"),
            x="planta", y="valor", color="periodo",
            barmode="group",
            text_auto=".1f",
            labels={"planta": "Planta", "valor": "Precio (S/ Galón)", "periodo": ""},
        )
        fig_comparativo.update_traces(textposition="inside")
        fig_comparativo.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_comparativo, use_container_width=True)

# ── Tabla cruda (opcional) ────────────────────────────────────────
with st.expander("Ver datos crudos"):
    st.dataframe(df_filtrado, use_container_width=True)
