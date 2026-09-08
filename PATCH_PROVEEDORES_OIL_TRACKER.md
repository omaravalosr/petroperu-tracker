# PATCH — Benchmarks de proveedores en Oil Tracker

## Objetivo

Extender el dashboard Streamlit del proyecto **petroperu-tracker** para comparar el precio real de Diesel B5 S-50 de PetroPerú contra el costo implícito de combustible de los tres proveedores de transporte: **HECARO, LMG y QOLPARO**.

Este parche NO modifica el scraper, el parser ni `data/precios.csv`. La fuente PetroPerú sigue funcionando exactamente como hoy. El cambio se limita a incorporar una segunda fuente de datos de negocio (`data/proveedores_sgal.csv`) y a enriquecer dos visuales de `app.py`.

## Reglas de negocio obligatorias

1. Las tarifas etiquetadas internamente como **2025** corresponden al período **enero, febrero y marzo de 2026**.
2. Las tarifas **ACTUALES** entran en vigencia desde **abril de 2026** y se mantienen vigentes hasta que exista una nueva actualización.
3. Los valores del CSV ya son **S/ por galón implícito** calculados previamente. `app.py` NO debe volver a recalcular distancias, rendimiento, porcentajes de combustible ni tarifas.
4. La serie PetroPerú sigue siendo la fuente oficial/observada del precio de combustible.
5. Los proveedores son benchmarks internos derivados de tarifas logísticas, no precios de venta de combustible. La UI debe etiquetarlos como **“S/gal implícito proveedor”** o equivalente para evitar confundirlos con el precio PetroPerú.

## Arquitectura propuesta

Mantener separado el dato oficial del dato de proveedores:

```text
data/precios.csv
    -> histórico PetroPerú por planta/lista

data/proveedores_sgal.csv
    -> benchmarks por proveedor/ruta/período tarifario

app.py
    -> carga ambos datasets
    -> calcula promedio nacional proveedor por período
    -> agrega líneas benchmark a visual nacional actual
    -> agrega líneas proveedor a visual mensual
```

No concatenar ambos datasets porque tienen granularidades distintas: PetroPerú es **planta/lista/fecha** y proveedores es **ruta/proveedor/vigencia**.

---

## 1. Nuevo archivo de datos

Agregar `data/proveedores_sgal.csv` con este esquema:

| campo | tipo | descripción |
|---|---|---|
| `periodo_tarifa` | string | `2025` o `ACTUAL` |
| `proveedor` | string | HECARO / LMG / QOLPARO |
| `ruta` | string | Ruta logística |
| `sol_galon` | float | costo implícito S/gal ya calculado |
| `vigencia_desde` | date ISO | inicio de vigencia |
| `vigencia_hasta` | date ISO nullable | fin; vacío = vigente |

Archivo adjunto a este parche: `proveedores_sgal.csv`.

### Promedios esperados como smoke test

Usando promedio simple de rutas disponibles por proveedor, ignorando nulos:

| período aplicado | HECARO | LMG | QOLPARO |
|---|---:|---:|---:|
| Ene-Mar 2026 | **25.18** | **22.02** | **21.12** |
| Abr 2026 en adelante | **31.24** | **27.54** | **25.94** |

Estos valores son controles de implementación. Si el cálculo de `app.py` no se aproxima a ellos (tolerancia ±0.02), revisar lectura del CSV, tipos numéricos o filtros.

---

## 2. Carga de datos en `app.py`

Agregar cerca de la carga de `data/precios.csv`:

```python
from pathlib import Path
import pandas as pd

PROVEEDORES_PATH = Path("data/proveedores_sgal.csv")

@st.cache_data
def cargar_proveedores_sgal(path=PROVEEDORES_PATH):
    df = pd.read_csv(path)
    df["sol_galon"] = pd.to_numeric(df["sol_galon"], errors="coerce")
    df["vigencia_desde"] = pd.to_datetime(df["vigencia_desde"], errors="coerce")
    df["vigencia_hasta"] = pd.to_datetime(df["vigencia_hasta"], errors="coerce")
    return df.dropna(subset=["proveedor", "sol_galon", "vigencia_desde"])

proveedores_df = cargar_proveedores_sgal()
```

No hacer fallar toda la app si el CSV no existe. Si falta, mostrar warning y continuar con el dashboard PetroPerú:

```python
if PROVEEDORES_PATH.exists():
    proveedores_df = cargar_proveedores_sgal()
else:
    proveedores_df = pd.DataFrame()
    st.warning("No se encontró data/proveedores_sgal.csv; se muestran solo precios PetroPerú.")
```

---

## 3. Helpers de negocio

Agregar helpers en `app.py` o, preferiblemente, en un módulo nuevo `proveedores.py`.

### 3.1 Promedio por proveedor para una fecha

```python
def promedio_proveedor_en_fecha(df_prov: pd.DataFrame, fecha) -> pd.DataFrame:
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
```

### 3.2 Serie mensual de benchmarks

La serie debe ser una función escalón por vigencia, no interpolación.

```python
def serie_mensual_proveedores(df_prov: pd.DataFrame, meses: pd.DatetimeIndex) -> pd.DataFrame:
    filas = []
    for mes in meses:
        # usar cierre de mes para resolver la tarifa vigente de ese mes
        fecha_ref = mes + pd.offsets.MonthEnd(0)
        prom = promedio_proveedor_en_fecha(df_prov, fecha_ref)
        for _, r in prom.iterrows():
            filas.append({
                "mes": mes,
                "proveedor": r["proveedor"],
                "promedio_sol_galon": r["promedio_sol_galon"],
            })
    return pd.DataFrame(filas)
```

Resultado esperado en 2026:

```text
ENE HECARO 25.18 | LMG 22.02 | QOLPARO 21.12
FEB HECARO 25.18 | LMG 22.02 | QOLPARO 21.12
MAR HECARO 25.18 | LMG 22.02 | QOLPARO 21.12
ABR HECARO 31.24 | LMG 27.54 | QOLPARO 25.94
MAY HECARO 31.24 | LMG 27.54 | QOLPARO 25.94
...
```

No crear una pendiente artificial entre marzo y abril: hay un cambio de tarifa, por lo que el salto debe verse como cambio de benchmark.

---

## 4. Visual 1 — precio actual por planta / tracker nacional

### Objetivo

En la visual nacional que muestra el precio actual de PetroPerú por planta, agregar **tres líneas horizontales** con el promedio vigente actual de cada proveedor:

- HECARO — promedio S/gal implícito actual
- LMG — promedio S/gal implícito actual
- QOLPARO — promedio S/gal implícito actual

No intentar asignar cada ruta de transporte a una planta PetroPerú en esta visual. Una ruta y una planta no tienen granularidad equivalente y hacerlo sin un maestro explícito ruta→planta sería metodológicamente incorrecto.

### Implementación Plotly

Después de crear la figura actual por planta, obtener el benchmark con la fecha más reciente disponible del histórico completo PetroPerú:

```python
fecha_actual = df["fecha_vigencia"].max()
prom_actual = promedio_proveedor_en_fecha(proveedores_df, fecha_actual)
```

Agregar una línea horizontal por proveedor. Si la figura actual usa `plotly.graph_objects`:

```python
COLORES_PROVEEDOR = {
    "HECARO": "#FFB000",
    "LMG": "#7F7FFF",
    "QOLPARO": "#FF5C8A",
}

for _, r in prom_actual.iterrows():
    proveedor = r["proveedor"]
    valor = float(r["promedio_sol_galon"])

    fig_actual.add_hline(
        y=valor,
        line_dash="dash",
        line_width=2,
        line_color=COLORES_PROVEEDOR.get(proveedor),
        annotation_text=f"{proveedor}  S/{valor:.1f}/gal",
        annotation_position="top right",
    )
```

### Reglas visuales

- Barras PetroPerú deben conservar el estilo actual.
- Proveedores = líneas discontinuas, no barras.
- Cada línea debe mostrar **proveedor + valor**.
- Usar máximo 1 decimal en etiqueta visual; tooltip puede usar 2 decimales.
- Mantener eje Y en `S/ Galón`.
- Si una línea supera el máximo actual de las barras, Plotly debe ampliar automáticamente el rango Y. No fijar `range_y` a 0–30 porque HECARO puede superar 30.
- Leyenda: mostrar las tres líneas como benchmarks de proveedor.

### Importante

`add_hline` puede no crear una leyenda útil según la versión de Plotly. Si la leyenda es requisito visual, preferir `go.Scatter` horizontal:

```python
x_vals = fig_actual.data[0].x
fig_actual.add_trace(go.Scatter(
    x=x_vals,
    y=[valor] * len(x_vals),
    mode="lines",
    name=f"{proveedor} — S/{valor:.1f}/gal",
    line=dict(
        color=COLORES_PROVEEDOR.get(proveedor),
        width=2,
        dash="dash",
    ),
    hovertemplate=f"{proveedor}<br>S/{valor:.2f}/gal<extra></extra>",
))
```

Preferir esta segunda opción si el gráfico debe tener una leyenda consistente.

---

## 5. Visual 2 — “Promedio mensual a nivel país”

### Estado actual

La documentación indica que actualmente la visual muestra **una barra por mes** con el promedio de todas las plantas seleccionadas en ese mes.

### Cambio requerido

Mantener las barras PetroPerú y superponer tres líneas:

- HECARO
- LMG
- QOLPARO

Cada línea representa el **promedio simple del S/gal implícito de todas las rutas disponibles para ese proveedor cuya tarifa esté vigente en ese mes**.

Para 2026:

- Enero, febrero y marzo → usar dataset `periodo_tarifa = 2025`.
- Abril en adelante → usar dataset `periodo_tarifa = ACTUAL`.

### Implementación

Suponiendo que el dataframe de barras mensuales actual se llama `mensual` y tiene una columna fecha mensual `mes`:

```python
meses = pd.DatetimeIndex(sorted(pd.to_datetime(mensual["mes"]).unique()))
prov_mensual = serie_mensual_proveedores(proveedores_df, meses)
```

Agregar trazas:

```python
for proveedor in ["HECARO", "LMG", "QOLPARO"]:
    d = prov_mensual[prov_mensual["proveedor"] == proveedor].sort_values("mes")
    if d.empty:
        continue

    fig_mensual.add_trace(go.Scatter(
        x=d["mes"],
        y=d["promedio_sol_galon"],
        mode="lines+markers+text",
        name=f"{proveedor} — S/gal implícito",
        line=dict(
            color=COLORES_PROVEEDOR[proveedor],
            width=2.5,
            shape="hv",  # escalón: evita interpolar tarifas entre períodos
        ),
        marker=dict(size=7),
        text=d["promedio_sol_galon"].map(lambda x: f"{x:.1f}"),
        textposition="top center",
        hovertemplate=(
            "%{x|%b %Y}<br>"
            + proveedor
            + ": S/%{y:.2f}/gal implícito<extra></extra>"
        ),
    ))
```

Si `shape="hv"` hace que la visual quede demasiado cargada, mantener línea recta dentro de cada período, pero NO suavizar (`spline`) el salto marzo→abril.

### Título sugerido

Cambiar:

`Promedio mensual a nivel país`

por:

`Precio nacional PetroPerú vs. S/gal implícito de proveedores`

Subtítulo/caption:

`Barras: precio promedio PetroPerú | Líneas: benchmark implícito promedio de tarifas de transporte`

---

## 6. Comportamiento con filtros

### Filtro de fechas

- Las barras/series PetroPerú siguen respetando el filtro de fechas actual.
- Las líneas mensuales de proveedor se construyen únicamente para los meses visibles en la gráfica PetroPerú.
- Si el usuario selecciona enero-marzo, solo debe verse el benchmark 2025.
- Si selecciona abril-septiembre, solo debe verse benchmark ACTUAL.
- Si cruza marzo/abril, debe observarse el salto de tarifa.

### Filtro de plantas

El filtro de plantas NO debe modificar el promedio de proveedores.

Motivo: el promedio proveedor está calculado por **rutas**, mientras que el filtro Streamlit es por **plantas PetroPerú**. Aplicar el filtro de plantas sobre los proveedores sin maestro ruta→planta introduciría una relación falsa.

Agregar un caption corto debajo de la gráfica si es necesario:

`Los benchmarks de proveedor son promedios nacionales de rutas y no cambian con el filtro de plantas.`

---

## 7. No romper lógica existente

Este parche no debe modificar:

- `scraper.py`
- `parser.py`
- `update.py`
- esquema ni deduplicación de `data/precios.csv`
- fusión Callao + Conchán → LIMA
- regla Amazonía Diesel B5 equivalente
- cálculo semanal existente
- cálculo de “valor actual” sobre histórico completo

La documentación actual establece que el valor actual por planta se calcula sobre el histórico completo, independientemente del filtro de fecha. Mantener ese comportamiento.

---

## 8. Tests mínimos

Agregar tests para helpers de proveedor (por ejemplo `tests/test_proveedores.py`).

### Test 1 — cambio de vigencia

```python
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
```

### Test 2 — enero/febrero/marzo iguales

```python
def test_tarifa_2025_aplica_enero_a_marzo(proveedores_df):
    valores = []
    for fecha in ["2026-01-31", "2026-02-28", "2026-03-31"]:
        x = promedio_proveedor_en_fecha(proveedores_df, fecha)
        valores.append(x.set_index("proveedor")["promedio_sol_galon"].round(2).to_dict())

    assert valores[0] == valores[1] == valores[2]
```

### Test 3 — abril en adelante usa ACTUAL

```python
def test_actual_desde_abril(proveedores_df):
    abr = promedio_proveedor_en_fecha(proveedores_df, "2026-04-01")
    sep = promedio_proveedor_en_fecha(proveedores_df, "2026-09-30")
    assert abr.set_index("proveedor")["promedio_sol_galon"].round(2).to_dict() == \
           sep.set_index("proveedor")["promedio_sol_galon"].round(2).to_dict()
```

### Test 4 — nulos no se convierten en cero

Validar que rutas sin tarifa para un proveedor sean `NaN`/ausentes y no `0`, porque cero sesgaría el promedio nacional.

---

## 9. Criterios de aceptación

El parche se considera completo solo si:

1. La app inicia con `streamlit run app.py` sin errores.
2. El dashboard sigue funcionando aunque `data/proveedores_sgal.csv` no exista.
3. La visual actual por planta muestra tres benchmarks horizontales con nombre y S/gal.
4. La visual mensual mantiene barras PetroPerú y añade tres líneas proveedor.
5. Enero-marzo usan los promedios del set “2025”; abril en adelante usan “ACTUAL”.
6. El salto marzo→abril no se suaviza/interpola.
7. El filtro de plantas no altera los benchmarks de proveedores.
8. El filtro de fechas sí limita los meses visibles de proveedores.
9. Los promedios de smoke test coinciden ±0.02 con 25.18/22.02/21.12 y 31.24/27.54/25.94.
10. No se modifica la lógica de scraping/parsing/actualización PetroPerú existente.

---

## 10. Nota metodológica visible en dashboard

Agregar en un `st.caption` o expander:

> **Benchmark proveedores:** los valores de HECARO, LMG y QOLPARO representan S/gal implícito estimado a partir de tarifas logísticas y no equivalen al precio de compra de combustible. Se muestran como referencia comparativa frente al precio oficial PetroPerú.

Esta aclaración es obligatoria para evitar una lectura incorrecta del gráfico.

---

## 11. Actualización de documentación

Al finalizar implementación, actualizar `Oil Tracker.md` agregando:

- nueva fuente `data/proveedores_sgal.csv`;
- reglas de vigencia Ene-Mar / Abr+;
- definición de benchmark implícito;
- cambios en las dos visuales;
- regla de que filtro de plantas no afecta benchmarks proveedor;
- smoke tests de promedios.

No reemplazar ni alterar las secciones de scraping/parser salvo para agregar una referencia explícita de que esta nueva fuente es independiente.
