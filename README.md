# Tracker Diesel B5 S-50 — PetroPerú

Pipeline que scrapea las listas oficiales de precios de PetroPerú, extrae el
precio del **Diesel B5 S-50 por planta**, lo acumula en un histórico (CSV) y
lo visualiza en un dashboard de Streamlit. El dashboard además superpone,
como referencia comparativa, benchmarks de S/gal implícito de proveedores de
transporte — ver [sección 7](#7-benchmarks-de-proveedores-dataproveedores_sgalcsv);
esa fuente es completamente independiente del scraping/parsing de PetroPerú
(no lo modifica ni se mezcla con `data/precios.csv`).

Repo: https://github.com/omaravalosr/petroperu-tracker

---

## 1. Flujo de datos

```
petroperu.com.pe (web)
        │  scraper.py: obtener_lista_pdfs()
        ▼
lista de PDFs "Automotriz" (fecha ISO + url)
        │  update.py: descarga el PDF si no existe localmente
        ▼
raw/<fecha>.pdf
        │  parser.py: extraer_diesel_b5_s50_filas()
        ▼
filas {fecha_vigencia, lista_id, planta, valor}
        │  update.py: dedup + concat con el CSV existente
        ▼
data/precios.csv   (histórico acumulado, una fila por planta por lista)
        │  app.py: pandas + plotly
        ▼
Dashboard Streamlit (http://localhost:8501)
```

`update.py` es el orquestador: junta `scraper.py` (qué PDFs existen) con
`parser.py` (qué dice cada PDF) y mantiene `data/precios.csv` actualizado de
forma **idempotente** — correrlo dos veces sin PDFs nuevos no duplica nada.

---

## 2. Componentes

### `scraper.py` — descubrir PDFs

`obtener_lista_pdfs(categoria="Automotriz")` descarga el HTML de la página
de listas de precios y extrae los links a PDF.

**Por qué no es un simple "buscar todos los `<a href=*.pdf>`":** la página
publica el histórico como un calendario segmentado por tipo de combustible
(`<ul class="segmented-calendar">`), con 5 categorías: Automotriz, Marino,
Aviación, Asfaltos y Productos químicos. Cada `<li>` trae su categoría en un
`<div class="title">` y su fecha ya resuelta en `data-date="YYYY-MM-DD"`.
Solo nos interesa **Automotriz** — las otras categorías traen tablas con
estructura totalmente distinta y romperían el parser si se procesaran igual.

Se filtra por el texto exacto de esa categoría (no por posición ni por
adivinar el formato de fecha del texto visible, que viene en español:
"25-Ago-2026").

### `parser.py` — leer un PDF

Función principal usada por el pipeline: `extraer_diesel_b5_s50_filas(ruta_pdf)`.

El PDF de PetroPerú no tiene tablas reales (sin bordes de celda): es texto
posicionado por coordenadas (`x0`, `top`) que `pdfplumber` expone palabra por
palabra. Reconstruir la tabla implica tres problemas, cada uno resuelto por
una pieza distinta del parser:

| Problema | Función | Cómo lo resuelve |
|---|---|---|
| ¿Qué página es cuál? | `identificar_paginas(pdf)` | Busca el texto "ADDENDUM N° 1" / "N° 2" en cada página. No asume que la página 2 es siempre el Addendum N°1 — al menos un PDF real (COMB-24-2026) trae el orden invertido. |
| ¿Dónde empieza/termina cada columna? | `detectar_columnas(page, num_pagina)` | Busca palabras ancla del encabezado (ej. la 1ª y 2ª aparición de "DIESEL", "GASOLINA", "PETROLEO", "GASOHOL") y calcula los límites de columna como el punto medio entre anclas consecutivas. Distintos PDFs traen la tabla corrida unos puntos a la izquierda/derecha (y el corrimiento no es igual entre páginas del mismo PDF) — por eso no hay rangos de `x0` hardcodeados. |
| ¿Qué palabras forman una fila/planta? | `agrupar_en_filas(words)` | Agrupa palabras cuyo `top` cae dentro de una tolerancia (misma línea visual), y las reordena por `x0` antes de armar el texto de la fila — el orden que da `pdfplumber` puede poner el nombre de la planta *después* de sus números si el `top` del nombre es unos décimos mayor. |

**Regla de negocio — plantas de Lima:** Callao y Conchán son ambas "Lima" en
la práctica. `tabla_diesel_b5_s50()` promedia sus dos valores y los reemplaza
por una sola planta `"LIMA"`. Esto se aplica en el momento de extraer cada
PDF, así que es automático para cualquier lista pasada o futura, no un
parche sobre el CSV.

**Fuente mixta para "Diesel B5 S-50":** las 15 plantas costa/sierra + Puerto
Maldonado reportan esta columna en la página del Addendum N°1. Yurimaguas,
Iquitos y Pucallpa (Amazonía) no aparecen ahí — su equivalente está en la
página principal, columna "Diesel B5" (sin "S-50"). `tabla_diesel_b5_s50()`
combina ambas fuentes en un solo resultado por planta.

`parsear_pdf()` e `inspeccionar_pdf()` son utilidades más generales (extraen
*todas* las columnas de precios, no solo Diesel B5 S-50) que quedaron del
desarrollo inicial; el pipeline de producción (`update.py`) solo usa
`extraer_diesel_b5_s50_filas()`.

### `update.py` — orquestador

```bash
python update.py                    # solo el mes/año por defecto (2026-08)
python update.py --year 2026 --month all   # todo 2026
python update.py --year all                # todo el histórico (lento)
python update.py --limit 3                 # prueba rápida
```

Lógica:
1. Carga `data/precios.csv` (si existe) y arma el set de `lista_id` ya
   procesados.
2. Pide a `scraper.py` la lista completa de PDFs Automotriz, filtra por
   año/mes.
3. Descarta los que ya tienen su `lista_id` en el CSV.
4. Para cada PDF pendiente: descarga a `raw/<fecha>.pdf` (si no existe ya),
   parsea, y si el `lista_id` real (leído del *contenido* del PDF, no del
   nombre de archivo ni del link) no estaba procesado, agrega sus filas.
5. Concatena con el CSV existente, deduplica por `(lista_id, planta)` y
   reescribe `data/precios.csv`.

**Nota sobre el filtro por defecto:** `--year 2026 --month 08` es el default
histórico del desarrollo inicial. Para mantener el dataset al día en
cualquier mes hay que correr con `--month all` (o el mes correspondiente)
explícitamente — si no, `update.py` no verá PDFs de meses fuera de agosto.

### `app.py` — dashboard Streamlit

```bash
streamlit run app.py
```

Secciones:
- **Métricas rápidas**: última actualización, # plantas, # listas procesadas.
- **Evolución semanal** (línea, por planta): las listas no salen todos los
  días (~2-3 por mes), así que los puntos se agrupan por semana ISO
  (`to_period("W-SUN")`) en vez de graficar cada fecha exacta de vigencia.
- **Promedio mensual a nivel país** (barras): una barra por mes = promedio
  de **todas** las plantas seleccionadas ese mes (no una barra por planta) —
  evolución del precio promedio nacional. Con etiqueta de valor (1 decimal)
  dentro de cada barra.
- **Último precio por planta** (tabla): fila más reciente por planta dentro
  del filtro de fechas activo.
- **Valor actual vs. promedio de enero** (barras agrupadas por planta): el
  "valor actual" se calcula sobre el histórico completo *sin* el recorte de
  fechas del sidebar, para que nunca quede desactualizado por un filtro de
  fecha que el usuario haya dejado puesto.
- **Datos crudos** (expander): tabla sin agregar, respeta todos los filtros.

Filtro de plantas: `st.multiselect` con `default=[]` — vacío se interpreta
como "todas". Esto lo mantiene colapsado como un dropdown compacto en vez de
mostrar los 18 chips ya seleccionados.

### `proveedores.py` — benchmarks de proveedores (fuente independiente)

Carga y expone helpers sobre `data/proveedores_sgal.csv`. No toca
`scraper.py`, `parser.py`, `update.py` ni `data/precios.csv` — ver
[sección 7](#7-benchmarks-de-proveedores-dataproveedores_sgalcsv) para el
detalle completo.

---

## 3. Esquema de `data/precios.csv`

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha_vigencia` | `DD.MM.YYYY` | Fecha de vigencia de la lista, leída del contenido del PDF |
| `lista_id` | string | Código de lista, ej. `COMB-60-2026` (también admite sufijo de revisión, ej. `COMB-14B-2026`) |
| `planta` | string | Nombre de planta (18 valores: las 19 originales del PDF menos Callao/Conchán fusionadas en "LIMA") |
| `valor` | float | Precio Diesel B5 S-50 (o su equivalente Diesel B5 para Amazonía) en S/ Galón |

Deduplicación: `(lista_id, planta)` — si el mismo PDF se procesa dos veces,
la segunda pasada gana (`keep="last"`).

---

## 4. Bugs de extracción encontrados y su fix (por si aparecen de nuevo)

Estos quedaron resueltos en el código, documentados acá como referencia:

1. **Orden de palabras dentro de una fila**: `pdfplumber` puede devolver el
   nombre de planta después de sus valores numéricos si el `top` del nombre
   es unos décimos de punto mayor al de los números → se reordena por `x0`
   antes de armar `texto_fila`.
2. **Rangos de columna fijos rotos entre PDFs**: distintas fechas traen la
   tabla corrida horizontalmente, y el corrimiento difiere entre páginas del
   mismo PDF → reemplazado por detección dinámica basada en palabras ancla
   del encabezado (`detectar_columnas`).
3. **Orden de páginas no garantizado**: un PDF real trae el Addendum N°2
   antes que el N°1 → identificación de página por contenido
   (`identificar_paginas`), no por índice.
4. **Fechas del scraper**: el regex original esperaba `25.08.2026`, pero el
   sitio usa `25-Ago-2026` (mes abreviado en español) → resuelto usando el
   atributo `data-date` (ISO) del propio HTML en vez de parsear texto.
5. **`lista_id` con sufijo de revisión**: `COMB-14B-2026` no matcheaba el
   regex `COMB-\d+-\d{4}` → se agregó `[A-Z]?` opcional.
6. **PDFs de otras categorías mezclados**: el scraper original traía todos
   los `<a href=*.pdf>` de la página, incluyendo Asfaltos/Marino/Aviación →
   filtrado por categoría real del HTML.

---

## 5. Cómo correr todo desde cero

```bash
pip install -r requirements.txt
python update.py --year 2026 --month all   # backfill del histórico disponible
streamlit run app.py
pytest tests/test_proveedores.py           # opcional: valida los benchmarks de proveedor
```

## 7. Benchmarks de proveedores (`data/proveedores_sgal.csv`)

Fuente de datos **independiente** del pipeline PetroPerú, agregada para
comparar el precio oficial de Diesel B5 S-50 contra el costo implícito de
combustible de tres proveedores de transporte: **HECARO, LMG y QOLPARO**.

> **Importante:** estos NO son precios de venta de combustible. Son tarifas
> logísticas ya convertidas a un S/gal implícito, calculadas fuera de este
> proyecto. Se usan solo como referencia comparativa — de ahí que el
> dashboard los etiquete siempre como "S/gal implícito" y nunca como
> "precio".

### Esquema de `data/proveedores_sgal.csv`

| Campo | Tipo | Descripción |
|---|---|---|
| `periodo_tarifa` | string | `2025` o `ACTUAL` |
| `proveedor` | string | HECARO / LMG / QOLPARO |
| `ruta` | string | Ruta logística |
| `sol_galon` | float | Costo implícito S/gal, ya calculado (la app NO recalcula distancias, rendimiento ni tarifas) |
| `vigencia_desde` | date ISO | Inicio de vigencia |
| `vigencia_hasta` | date ISO, nullable | Fin de vigencia; vacío = sigue vigente |

### Origen del benchmark y fórmula (trazabilidad)

`sol_galon` viene **ya calculado** en el CSV — el dashboard nunca recalcula
distancias, rendimiento ni tarifas, solo carga y promedia. El cálculo en sí
(versión vigente: `proveedores_sgal_actualizado_v2.csv`, validado contra
`Calculo_SGal_Actualizado_Nuevos_KM_v2.xlsx`) sigue esta metodología:

- **Origen**: Hub Lurín. **Rendimiento**: 9.6 km/galón. **Camión estándar**: 26 pallets.
- `KM_FINAL = KM_IDA × 2 (ida y vuelta) × 1.15 (factor operativo)` — para
  rutas reconstruidas completas en el levantamiento de kilometraje.
- **Fallback** para rutas que no se pudieron reconstruir completas:
  `KM_FINAL = KM_TOTAL_ANTERIOR × 1.15` (el KM anterior ya era ida+vuelta,
  por eso acá no se multiplica por 2 de nuevo).
- `GALONES_ESTIMADOS = KM_FINAL / 9.6`
- Componente de combustible = `Tarifa × % combustible`:
  - **HECARO**: variable, 50%-70% según la ruta (metodología logística externa).
  - **LMG**: 52% fijo.
  - **QOLPARO**: 50% fijo.
- `S/GALÓN_IMPLÍCITO = Componente_combustible / GALONES_ESTIMADOS`

> **S/gal de proveedor es un valor implícito**, no el precio real que el
> proveedor paga por diésel — es la tarifa de transporte "traducida" a un
> costo de combustible equivalente, para poder compararla contra el precio
> oficial de PetroPerú en las mismas unidades (S/ por galón).

### Reglas de vigencia (fijas para 2026)

- Tarifas `2025` → vigentes en **enero, febrero y marzo de 2026**.
- Tarifas `ACTUAL` → vigentes **desde abril de 2026** en adelante.

`promedio_proveedor_en_fecha()` resuelve, para una fecha dada, qué filas
están vigentes (`vigencia_desde <= fecha <= vigencia_hasta`, o
`vigencia_hasta` vacío = sigue vigente) y promedia `sol_galon` por
proveedor. `serie_mensual_proveedores()` arma una serie mensual usando el
**cierre de cada mes** como fecha de referencia — es una función **escalón**
por diseño: no interpola entre marzo y abril, el cambio de tarifa se ve
como salto.

### Por qué no se concatena con `data/precios.csv`

Granularidades distintas: PetroPerú es planta/lista/fecha, proveedores es
ruta/proveedor/vigencia. No existe un maestro ruta→planta, así que mezclar
ambos introduciría una relación falsa. Se mantienen como datasets separados
y solo se combinan visualmente (líneas sobre las mismas gráficas).

### Cambios en el dashboard

- **"Valor actual vs. promedio de enero"**: se agregan 3 líneas horizontales
  (`go.Scatter`, no `add_hline`, para que aparezcan en la leyenda) con el
  promedio vigente **más reciente** de cada proveedor — calculado sobre la
  fecha máxima del histórico completo de PetroPerú, igual criterio que
  "valor actual" (no se ve afectado por el filtro de fechas del sidebar).
  No se intenta asignar cada ruta a una planta.
- **"Promedio mensual a nivel país"** (renombrada a *"Precio nacional
  PetroPerú vs. S/gal implícito de proveedores"*): mantiene las barras
  PetroPerú y agrega 3 líneas escalón (una por proveedor), calculadas solo
  para los meses que ya están visibles en las barras (respeta el filtro de
  fechas).
- Ambas gráficas muestran una nota metodológica (caption o expander)
  aclarando que los proveedores son un benchmark implícito, no un precio de
  combustible.
- Los tooltips de las líneas de proveedor muestran, calculado dinámicamente
  desde el CSV (nada escrito a mano): proveedor, mes/período, S/gal
  promedio y número de rutas consideradas en ese promedio.

### Regla de filtros

- **Filtro de fechas**: sí limita qué meses de proveedor se calculan (las
  líneas mensuales solo cubren los meses visibles en PetroPerú).
- **Filtro de plantas**: **no** afecta los benchmarks de proveedor — son
  promedios nacionales de rutas, no de plantas PetroPerú.

### Smoke test / tests automatizados

`tests/test_proveedores.py` (correr con `pytest tests/test_proveedores.py`)
valida, contra el CSV vigente (`proveedores_sgal_actualizado_v2.csv`, KM
actualizados desde Hub Lurín):
1. El promedio Ene-Mar 2026 es HECARO 20.46, LMG 17.96, QOLPARO 17.22.
2. El promedio Abr-en-adelante es HECARO 25.22, LMG 23.29, QOLPARO 21.30.
3. Enero, febrero y marzo dan exactamente el mismo promedio (misma tarifa vigente).
4. Abril y septiembre dan exactamente el mismo promedio (ambos usan `ACTUAL`).
5. Ninguna fila tiene `sol_galon == 0` (una ruta sin tarifa queda ausente, no en cero — un cero sesgaría el promedio nacional).
6. No hay filas duplicadas por `(periodo_tarifa, proveedor, ruta)`.
7. El número de rutas consideradas por proveedor/período (`n_rutas`, el
   mismo dato que se muestra en los tooltips) es el esperado — ej. LMG solo
   tiene tarifa `ACTUAL` en 13 rutas, contra 24 (HECARO) y 23 (QOLPARO).

Si el CSV no existe, el dashboard sigue funcionando con un `st.warning` y
sin los benchmarks — no rompe el flujo de PetroPerú.

**Nota de validación (2026-09, actualización a `_v2`):** al recalcular
`S/gal = Componente_combustible / Galones` con las columnas intermedias del
propio `Calculo_SGal_Actualizado_Nuevos_KM_v2.xlsx`, el resultado coincide
exacto con `proveedores_sgal_actualizado_v2.csv` en las 141 filas. La
columna final "S/gal" *mostrada dentro del propio xlsx* tiene un desfase de
+1.00 respecto a sus propias columnas de Tarifa/Galones (un bug de fórmula
del Excel) — el CSV usado por el dashboard es el valor correcto.

---

## 8. Limitaciones conocidas

- El pipeline de producción (`update.py`) solo extrae **Diesel B5 S-50**
  (y su equivalente Amazonía). Las demás columnas (GLP, gasolinas,
  industrial, gasohol, combustibles eléctricos) sí las sabe leer
  `parser.py` (`parsear_pdf`, `COLUMNAS_POR_PAGINA` vía `detectar_columnas`),
  pero no están conectadas al CSV/dashboard.
- `detectar_columnas` depende de que el encabezado use exactamente las
  palabras ancla esperadas ("DIESEL", "GASOLINA", "PETROLEO", "GASOHOL",
  "SOLES/KG", "INDUSTRIAL"). Un rediseño del PDF que cambie esas palabras
  requeriría actualizar `ANCLAS_POR_PAGINA`.
- No hay tarea programada (cron) — `update.py` hay que correrlo a mano (o
  agendarlo) para mantener el CSV al día.
