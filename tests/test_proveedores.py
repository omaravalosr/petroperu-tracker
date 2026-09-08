"""
Tests mínimos para los helpers de benchmarks de proveedores (proveedores.py).

Correr desde la raíz del repo (usa la ruta relativa data/proveedores_sgal.csv):
    pytest tests/test_proveedores.py
"""

import pytest

from proveedores import cargar_proveedores_sgal, promedio_proveedor_en_fecha


@pytest.fixture
def proveedores_df():
    return cargar_proveedores_sgal()


def test_vigencia_marzo_vs_abril(proveedores_df):
    mar = promedio_proveedor_en_fecha(proveedores_df, "2026-03-31")
    abr = promedio_proveedor_en_fecha(proveedores_df, "2026-04-30")

    mar = mar.set_index("proveedor")["promedio_sol_galon"]
    abr = abr.set_index("proveedor")["promedio_sol_galon"]

    assert round(mar["HECARO"], 2) == 25.18
    assert round(mar["LMG"], 2) == 22.02
    assert round(mar["QOLPARO"], 2) == 21.12

    assert round(abr["HECARO"], 2) == 31.24
    assert round(abr["LMG"], 2) == 27.54
    assert round(abr["QOLPARO"], 2) == 25.94


def test_tarifa_2025_aplica_enero_a_marzo(proveedores_df):
    valores = []
    for fecha in ["2026-01-31", "2026-02-28", "2026-03-31"]:
        x = promedio_proveedor_en_fecha(proveedores_df, fecha)
        valores.append(x.set_index("proveedor")["promedio_sol_galon"].round(2).to_dict())

    assert valores[0] == valores[1] == valores[2]


def test_actual_desde_abril(proveedores_df):
    abr = promedio_proveedor_en_fecha(proveedores_df, "2026-04-01")
    sep = promedio_proveedor_en_fecha(proveedores_df, "2026-09-30")
    assert abr.set_index("proveedor")["promedio_sol_galon"].round(2).to_dict() == \
           sep.set_index("proveedor")["promedio_sol_galon"].round(2).to_dict()


def test_nulos_no_se_convierten_en_cero(proveedores_df):
    # Ninguna fila del CSV debe tener sol_galon == 0: una ruta sin tarifa
    # para un proveedor debe estar simplemente ausente (NaN se descarta al
    # cargar), no en cero — un cero sesgaría el promedio nacional hacia abajo.
    assert (proveedores_df["sol_galon"] > 0).all()

    # Fecha sin ninguna vigencia (antes de 2026) -> sin filas, no ceros.
    vacio = promedio_proveedor_en_fecha(proveedores_df, "2025-12-31")
    assert vacio.empty
