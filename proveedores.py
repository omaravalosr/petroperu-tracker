"""
proveedores.py — Benchmarks de S/gal implícito de proveedores de transporte
(HECARO, LMG, QOLPARO), fuente independiente del pipeline PetroPerú.

Fuente: data/proveedores_sgal.csv (columnas: periodo_tarifa, proveedor,
ruta, sol_galon, vigencia_desde, vigencia_hasta).

IMPORTANTE — esto NO es un precio de combustible: son tarifas logísticas ya
convertidas a un S/gal implícito. Se usan solo como referencia comparativa
frente al precio oficial de PetroPerú, nunca mezcladas en el mismo dataset
(granularidades distintas: PetroPerú es planta/lista/fecha, proveedores es
ruta/proveedor/vigencia).

Reglas de vigencia (fijas para 2026, ver PATCH_PROVEEDORES_OIL_TRACKER.md):
  - Tarifas "2025"   -> vigentes enero, febrero y marzo de 2026.
  - Tarifas "ACTUAL" -> vigentes desde abril de 2026 en adelante.
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


def promedio_proveedor_en_fecha(df_prov: pd.DataFrame, fecha) -> pd.DataFrame:
    """Promedio simple de sol_galon por proveedor, entre las rutas cuya
    vigencia cubre `fecha` (vigencia_hasta vacío = sigue vigente)."""
    fecha = pd.Timestamp(fecha)
    mask = (
        (df_prov["vigencia_desde"] <= fecha)
        & (
            df_prov["vigencia_hasta"].isna()
            | (df_prov["vigencia_hasta"] >= fecha)
        )
    )
    vigentes = df_prov.loc[mask]
    return (
        vigentes.groupby("proveedor", as_index=False)["sol_galon"]
        .mean()
        .rename(columns={"sol_galon": "promedio_sol_galon"})
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
            })
    return pd.DataFrame(filas)
