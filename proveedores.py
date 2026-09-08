"""
proveedores.py — Benchmarks de S/gal implícito de proveedores de transporte
(HECARO, LMG, QOLPARO), fuente independiente del pipeline PetroPerú.

Fuente: data/proveedores_sgal.csv (columnas: periodo_tarifa, proveedor,
ruta, sol_galon, vigencia_desde, vigencia_hasta). `sol_galon` YA viene
calculado en el CSV — este módulo no recalcula distancias, rendimiento ni
tarifas, solo carga/tipa y promedia lo que el CSV trae.

IMPORTANTE — esto NO es un precio de combustible: es un VALOR IMPLÍCITO
calculado a partir de la tarifa de transporte y su componente combustible.
No debe presentarse como si fuera el precio real que el proveedor paga por
diésel. Se usa solo como referencia comparativa frente al precio oficial de
PetroPerú, nunca mezclado en el mismo dataset (granularidades distintas:
PetroPerú es planta/lista/fecha, proveedores es ruta/proveedor/vigencia).

METODOLOGÍA DE CÁLCULO DEL CSV (trazabilidad — no se recalcula acá, se
documenta para referencia; el detalle completo vive en
Calculo_SGal_Actualizado_Nuevos_KM_v2.xlsx):
  - Origen: Hub Lurín. Rendimiento: 9.6 km/galón. Camión: 26 pallets.
  - KM_FINAL = KM_IDA × 2 (ida y vuelta) × 1.15 (factor operativo).
  - Si la ruta no se pudo reconstruir completa en el nuevo levantamiento:
    KM_FINAL = KM_TOTAL_ANTERIOR × 1.15 (sin duplicar el factor de vuelta,
    porque el KM anterior ya era total ida+vuelta).
  - GALONES_ESTIMADOS = KM_FINAL / 9.6
  - Componente combustible = Tarifa × % combustible del proveedor:
      HECARO: variable 50%-70% según ruta (metodología logística externa).
      LMG: 52% fijo.
      QOLPARO: 50% fijo.
  - S/GALÓN_IMPLÍCITO = Componente_combustible / GALONES_ESTIMADOS

Reglas de vigencia (fijas para 2026):
  - periodo_tarifa "2025"   -> vigente enero, febrero y marzo de 2026
    (el campo se llama "2025" pero es el tarifario que rigió en ese
    trimestre de 2026, no un valor del año 2025).
  - periodo_tarifa "ACTUAL" -> vigente desde el 1 de abril de 2026 en
    adelante, hasta la próxima actualización del CSV.

Valores faltantes: si un proveedor no tiene tarifa para una ruta en un
período, esa ruta simplemente no tiene fila en el CSV para esa
combinación — se excluye del promedio por construcción. Nunca se imputa
ni se convierte en 0 (un cero sesgaría el promedio nacional hacia abajo).
"""

from pathlib import Path

import pandas as pd

PROVEEDORES_PATH = Path("data/proveedores_sgal.csv")

COLORES_PROVEEDOR = {
    "HECARO": "#FFB000",
    "LMG": "#7F7FFF",
    "QOLPARO": "#FF5C8A",
}


def cargar_proveedores_sgal(path=PROVEEDORES_PATH):
    """Carga y tipa data/proveedores_sgal.csv. No recalcula nada del CSV
    (sol_galon ya viene calculado); solo tipa fechas/números."""
    df = pd.read_csv(path)
    df["sol_galon"] = pd.to_numeric(df["sol_galon"], errors="coerce")
    df["vigencia_desde"] = pd.to_datetime(df["vigencia_desde"], errors="coerce")
    df["vigencia_hasta"] = pd.to_datetime(df["vigencia_hasta"], errors="coerce")
    return df.dropna(subset=["proveedor", "sol_galon", "vigencia_desde"])


ETIQUETA_PERIODO = {
    "2025": "tarifario histórico (ene-mar 2026)",
    "ACTUAL": "tarifario actual (abr 2026 en adelante)",
}


def promedio_proveedor_en_fecha(df_prov: pd.DataFrame, fecha) -> pd.DataFrame:
    """Promedio simple de sol_galon por proveedor, entre las rutas cuya
    vigencia cubre `fecha` (vigencia_hasta vacío = sigue vigente).

    Las rutas sin tarifa para un proveedor en ese período simplemente no
    tienen fila en el CSV, así que quedan excluidas del promedio por
    construcción (nunca se imputan ni se convierten en 0). Devuelve también
    `n_rutas` (cuántas rutas entraron al promedio) y `periodo_tarifa`, para
    los tooltips.
    """
    fecha = pd.Timestamp(fecha)
    mask = (
        (df_prov["vigencia_desde"] <= fecha)
        & (
            df_prov["vigencia_hasta"].isna()
            | (df_prov["vigencia_hasta"] >= fecha)
        )
    )
    vigentes = df_prov.loc[mask]
    return vigentes.groupby("proveedor", as_index=False).agg(
        promedio_sol_galon=("sol_galon", "mean"),
        n_rutas=("sol_galon", "count"),
        periodo_tarifa=("periodo_tarifa", "first"),
    )


def serie_mensual_proveedores(df_prov: pd.DataFrame, meses: pd.DatetimeIndex) -> pd.DataFrame:
    """Serie mensual de benchmarks por proveedor: función ESCALÓN por
    vigencia (no interpolación) — cada mes usa la tarifa vigente al cierre
    de ese mes, así que el cambio de tarifa (ej. marzo->abril) se ve como
    salto, no como pendiente."""
    filas = []
    for mes in meses:
        fecha_ref = mes + pd.offsets.MonthEnd(0)
        prom = promedio_proveedor_en_fecha(df_prov, fecha_ref)
        for _, r in prom.iterrows():
            filas.append({
                "mes": mes,
                "proveedor": r["proveedor"],
                "promedio_sol_galon": r["promedio_sol_galon"],
                "n_rutas": r["n_rutas"],
                "periodo_tarifa": r["periodo_tarifa"],
                "periodo_label": ETIQUETA_PERIODO.get(r["periodo_tarifa"], r["periodo_tarifa"]),
            })
    return pd.DataFrame(filas)
