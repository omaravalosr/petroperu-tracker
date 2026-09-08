"""
parser.py — Parser para el formato de PDF de PetroPerú
(estructura verificada contra LISTA COMB-56-2026 a COMB-60-2026, ago. 2026)

Requiere: pip install pdfplumber

ESTRUCTURA DETECTADA:
- Página 1: Lista principal (bloque "costa/sierra" + bloque "Amazonía",
  ambos bloques comparten las MISMAS posiciones de columna x0)
- Página 2: Addendum N°1 (Diesel S-50 / Gasohol) — otra x0 de columnas
- Página 3: Addendum N°2 (combustibles para generadoras eléctricas G.E.)

Cada bloque se identifica por NOMBRE DE PLANTA (no por posición),
así que un mismo mapeo de columnas sirve para costa y Amazonía dentro
de la misma página.

IMPORTANTE: los límites de columna NO están hardcodeados. Distintos
PDFs (distintas fechas) traen la tabla corrida unos puntos a la
izquierda o derecha, y ese corrimiento no es el mismo en todas las
páginas del mismo PDF. Por eso `detectar_columnas()` ubica, PDF por
PDF y página por página, las palabras ancla del propio encabezado
(ej. la 1ª/2ª aparición de "DIESEL", "GASOLINA", "PETROLEO", "GASOHOL")
y calcula los límites de columna a partir de esas posiciones reales.
Si un PDF viene con un encabezado distinto al esperado, esa página
simplemente no aporta filas (en vez de asignar valores a la columna
equivocada).
"""

import pdfplumber
import re

# ── Plantas conocidas ──────────────────────────────────────────────
PLANTAS_COSTA_SIERRA = [
    "TALARA", "PIURA", "ETEN", "SALAVERRY", "CHIMBOTE", "SUPE", "CALLAO",
    "CONCHAN", "PISCO", "MOLLENDO", "JULIACA", "CUSCO", "ILO",
    "EL MILAGRO", "TARAPOTO",
]
PLANTAS_AMAZONIA = ["YURIMAGUAS", "IQUITOS", "PUCALLPA", "PTO. MALDONADO"]
TODAS_LAS_PLANTAS = PLANTAS_COSTA_SIERRA + PLANTAS_AMAZONIA

NUM_RE = re.compile(r"^\d{1,3}(\.\d{1,4})?$")


def es_numero(texto):
    return bool(NUM_RE.match(texto.replace(",", "")))


# ── Detección dinámica de columnas ──────────────────────────────────
# En vez de posiciones fijas (que se rompen si un PDF de otra fecha viene
# con la tabla corrida horizontal O verticalmente), ubicamos por cada PDF
# las palabras ancla del propio encabezado y calculamos los límites de
# columna a partir de sus posiciones reales:
#
#   - Horizontal (x0): punto medio entre anclas consecutivas.
#   - Vertical (top): la banda de búsqueda del encabezado se calcula
#     relativa a la posición real de la palabra "PLANTAS" en ESE pdf (que
#     encabeza la columna de nombres de planta), no a un rango de `top`
#     fijo — un PDF real (COMB-62-2026, 08.09.2026) trajo el encabezado de
#     la página 2 unos 28pt más arriba que lo habitual y rompía la banda
#     fija anterior.
#
# Cada entrada de "columnas" es (nombre_columna, texto_ancla, ocurrencia).
# "ocurrencia" desambigua encabezados con la misma palabra repetida (ej.
# "GASOLINA" aparece 3 veces: Premium/Regular/84, en ese orden de
# izquierda a derecha; "DIESEL" aparece 2 veces por página: la primera es
# la variante "UV", la segunda no).
ANCLAS_POR_PAGINA = {
    1: {  # Lista principal + Amazonía
        "columnas": [
            ("GLP_SOLES_KG", "SOLES/KG", 1),
            ("GASOLINA_PREMIUM", "GASOLINA", 1),
            ("GASOLINA_REGULAR", "GASOLINA", 2),
            ("GASOLINA_84", "GASOLINA", 3),
            ("DIESEL_B5_UV", "DIESEL", 1),
            ("DIESEL_B5", "DIESEL", 2),
            ("PETROLEO_INDUSTRIAL_N6", "PETROLEO", 1),
            ("PETROLEO_INDUSTRIAL_500", "PETROLEO", 2),
        ],
    },
    2: {  # Addendum N°1 — USO INTERNO
        "columnas": [
            ("DIESEL_B5_UV_S50", "DIESEL", 1),
            ("DIESEL_B5_S50", "DIESEL", 2),
            ("GASOHOL_PREMIUM", "GASOHOL", 1),
            ("GASOHOL_REGULAR", "GASOHOL", 2),
        ],
    },
    3: {  # Addendum N°2 — Combustibles eléctricos (G.E.)
        "columnas": [
            ("DIESEL_B5_GE", "DIESEL", 1),
            ("DIESEL_B5_S50_GE", "DIESEL", 2),
            ("PETROLEO_INDUSTRIAL_6_GE", "INDUSTRIAL", 1),
        ],
    },
}

MARGEN_BORDE = 40  # pt de margen para la primera/última columna de la página

# Ventana de búsqueda vertical del encabezado, relativa al "PLANTAS" más
# alto de la página (el que encabeza el bloque principal, no un bloque
# secundario repetido más abajo). Calibrado contra los 3 pesos observados:
# page1 (offsets 0 a -8.4), page2 (-11.4 a -19.2), page3 (-7.5 a -9.1).
MARGEN_HEADER_ARRIBA = 25
MARGEN_HEADER_ABAJO = 2


def detectar_columnas(page, num_pagina):
    """
    Ubica dinámicamente los límites (x_min, x_max) de cada columna para
    ESTA página de ESTE pdf, buscando las palabras ancla del encabezado
    en vez de asumir posiciones fijas (ni de x0 ni de top).

    Devuelve {nombre_columna: (x_min, x_max)}, o {} si no se pudo ubicar
    ninguna ancla (ej. página sin mapeo definido, sin "PLANTAS", o
    encabezado distinto al esperado).
    """
    config = ANCLAS_POR_PAGINA.get(num_pagina)
    if not config:
        return {}

    words = page.extract_words()

    tops_plantas = [w["top"] for w in words if w["text"].strip().upper() == "PLANTAS"]
    if not tops_plantas:
        return {}
    top_plantas = min(tops_plantas)  # el bloque principal, no un repetido más abajo

    words_header = [
        w for w in words
        if top_plantas - MARGEN_HEADER_ARRIBA <= w["top"] <= top_plantas + MARGEN_HEADER_ABAJO
    ]

    anclas = []
    for nombre_columna, texto_ancla, ocurrencia in config["columnas"]:
        candidatos = sorted(
            w["x0"] for w in words_header
            if w["text"].strip().upper() == texto_ancla
        )
        if len(candidatos) >= ocurrencia:
            anclas.append((nombre_columna, candidatos[ocurrencia - 1]))

    if not anclas:
        return {}

    anclas.sort(key=lambda a: a[1])

    columnas_x = {}
    for i, (nombre_columna, x0) in enumerate(anclas):
        x_min = (anclas[i - 1][1] + x0) / 2 if i > 0 else x0 - MARGEN_BORDE
        x_max = (anclas[i + 1][1] + x0) / 2 if i < len(anclas) - 1 else x0 + MARGEN_BORDE
        columnas_x[nombre_columna] = (x_min, x_max)

    return columnas_x


def inspeccionar_pdf(ruta_pdf):
    """Imprime cada palabra con su posición, página por página."""
    with pdfplumber.open(ruta_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"\n=== Página {i + 1} ===")
            for w in page.extract_words():
                print(f"top={w['top']:.1f}  x0={w['x0']:.1f}  texto='{w['text']}'")


def agrupar_en_filas(words, tolerancia_top=3):
    """Agrupa palabras que están en la misma línea visual."""
    filas = []
    fila_actual = []
    top_actual = None

    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if top_actual is None or abs(w["top"] - top_actual) <= tolerancia_top:
            fila_actual.append(w)
            top_actual = w["top"] if top_actual is None else top_actual
        else:
            filas.append(fila_actual)
            fila_actual = [w]
            top_actual = w["top"]
    if fila_actual:
        filas.append(fila_actual)
    return filas


def extraer_metadata(pdf):
    """Extrae fecha de vigencia y código de lista (ej. COMB-60-2026)."""
    texto_pagina1 = pdf.pages[0].extract_text() or ""
    fecha_match = re.search(r"VIGENCIA A PARTIR DEL\s+(\d{2}\.\d{2}\.\d{4})", texto_pagina1)
    lista_match = re.search(r"LISTA\s+(COMB-\d+[A-Z]?-\d{4})", texto_pagina1)
    return {
        "fecha_vigencia": fecha_match.group(1) if fecha_match else None,
        "lista_id": lista_match.group(1) if lista_match else None,
    }


def identificar_paginas(pdf):
    """
    Identifica el ROL de cada página (1=lista principal, 2=Addendum N°1,
    3=Addendum N°2) por su contenido, no por su posición.

    La mayoría de los PDFs traen las páginas en ese orden, pero al menos
    uno (COMB-24-2026, 25.04.2026) trae el Addendum N°2 antes que el N°1 —
    si asumimos el orden por índice, se lee la página equivocada y se
    pierden casi todas las plantas.

    Devuelve {num_pagina: objeto_page}. Si un rol no aparece en el PDF,
    simplemente no está presente en el dict (el resto del código ya
    trata "sin mapeo para esta página" como "ignorar").
    """
    paginas = {}
    for page in pdf.pages:
        texto = page.extract_text() or ""
        if re.search(r"ADDENDUM\s*N[°º]\s*1", texto):
            paginas[2] = page
        elif re.search(r"ADDENDUM\s*N[°º]\s*2", texto):
            paginas[3] = page
        else:
            paginas.setdefault(1, page)
    return paginas


def parsear_pdf(ruta_pdf):
    """
    Devuelve lista de dicts:
    {fecha_vigencia, lista_id, planta, region, columna, valor, pagina}
    """
    filas_resultado = []

    with pdfplumber.open(ruta_pdf) as pdf:
        metadata = extraer_metadata(pdf)
        paginas = identificar_paginas(pdf)

        for num_pagina, page in paginas.items():
            columnas_x = detectar_columnas(page, num_pagina)
            if not columnas_x:
                continue  # página sin mapeo definido, o encabezado no reconocido

            words = page.extract_words()
            filas = agrupar_en_filas(words)

            for fila in filas:
                fila_ordenada = sorted(fila, key=lambda w: w["x0"])
                texto_fila = " ".join(w["text"] for w in fila_ordenada).upper()
                planta_encontrada = None
                for planta in TODAS_LAS_PLANTAS:
                    if texto_fila.startswith(planta):
                        planta_encontrada = planta
                        break
                if not planta_encontrada:
                    continue

                region = "Amazonía" if planta_encontrada in PLANTAS_AMAZONIA else "Costa/Sierra"

                for w in fila:
                    if not es_numero(w["text"]):
                        continue
                    for col_nombre, (x_min, x_max) in columnas_x.items():
                        if x_min <= w["x0"] <= x_max:
                            filas_resultado.append({
                                "fecha_vigencia": metadata["fecha_vigencia"],
                                "lista_id": metadata["lista_id"],
                                "planta": planta_encontrada,
                                "region": region,
                                "columna": col_nombre,
                                "valor": float(w["text"]),
                                "pagina": num_pagina,
                            })
                            break

    return filas_resultado


if __name__ == "__main__":
    resultado = parsear_pdf("precios.pdf")
    print(f"Total de valores extraídos: {len(resultado)}")
    for r in resultado[:15]:
        print(r)


# ─────────────────────────────────────────────────────────────────
# FUNCIÓN ESPECÍFICA: tabla "Diesel B5 S-50" por planta
# Regla de negocio confirmada con Omar:
#   - 15 plantas costa/sierra + Puerto Maldonado -> pág 2 (Addendum N°1),
#     columna "DIESEL_B5_S50" (límites ubicados dinámicamente por PDF,
#     ver detectar_columnas())
#   - Yurimaguas, Iquitos, Pucallpa -> pág 1, bloque Amazonía,
#     columna "DIESEL_B5" — OJO: NO es la misma columna que las de
#     costa (ahí se llama "Diesel B5" a secas, sin "S-50")
# ─────────────────────────────────────────────────────────────────

PLANTAS_DESDE_PAGINA2 = PLANTAS_COSTA_SIERRA + ["PTO. MALDONADO"]
PLANTAS_DESDE_PAGINA1_AMAZONIA = ["YURIMAGUAS", "IQUITOS", "PUCALLPA"]


def tabla_diesel_b5_s50(ruta_pdf):
    """
    Devuelve dict {planta: valor} con el precio "Diesel B5 S-50"
    (o su equivalente "Diesel B5" para Yurimaguas/Iquitos/Pucallpa)
    aplicando la regla de fuente mixta descrita arriba.
    """
    resultado = {}

    with pdfplumber.open(ruta_pdf) as pdf:
        paginas = identificar_paginas(pdf)

        # --- Página 1: Yurimaguas, Iquitos, Pucallpa (columna DIESEL_B5) ---
        page1 = paginas.get(1)
        if page1 is not None:
            columnas_x_p1 = detectar_columnas(page1, 1)
            rango_p1 = columnas_x_p1.get("DIESEL_B5")

            filas = agrupar_en_filas(page1.extract_words()) if rango_p1 else []
            if rango_p1:
                x_min, x_max = rango_p1

            for fila in filas:
                texto_fila = " ".join(w["text"] for w in sorted(fila, key=lambda w: w["x0"])).upper()
                planta = next(
                    (p for p in PLANTAS_DESDE_PAGINA1_AMAZONIA if texto_fila.startswith(p)),
                    None,
                )
                if not planta:
                    continue
                for w in fila:
                    if es_numero(w["text"]) and x_min <= w["x0"] <= x_max:
                        resultado[planta] = float(w["text"])
                        break

        # --- Página 2 (Addendum N°1): las 15 de costa/sierra + Pto. Maldonado ---
        page2 = paginas.get(2)
        if page2 is not None:
            columnas_x_p2 = detectar_columnas(page2, 2)
            rango_p2 = columnas_x_p2.get("DIESEL_B5_S50")

            filas = agrupar_en_filas(page2.extract_words()) if rango_p2 else []
            if rango_p2:
                x_min, x_max = rango_p2

            for fila in filas:
                texto_fila = " ".join(w["text"] for w in sorted(fila, key=lambda w: w["x0"])).upper()
                planta = next(
                    (p for p in PLANTAS_DESDE_PAGINA2 if texto_fila.startswith(p)),
                    None,
                )
                if not planta:
                    continue
                for w in fila:
                    if es_numero(w["text"]) and x_min <= w["x0"] <= x_max:
                        resultado[planta] = float(w["text"])
                        break

    # Regla de negocio: Callao y Conchán son ambas plantas de Lima —
    # se unifican en una sola planta "LIMA" con el promedio de las dos.
    valores_lima = [resultado[p] for p in ("CALLAO", "CONCHAN") if p in resultado]
    if valores_lima:
        resultado["LIMA"] = sum(valores_lima) / len(valores_lima)
        resultado.pop("CALLAO", None)
        resultado.pop("CONCHAN", None)

    return resultado


def extraer_diesel_b5_s50_filas(ruta_pdf):
    """
    Versión "lista para CSV" de tabla_diesel_b5_s50(): devuelve una lista
    de dicts {fecha_vigencia, lista_id, planta, valor}, con fecha_vigencia
    y lista_id sacados del CONTENIDO del PDF (no del nombre del archivo
    ni del texto del link en la web, que son menos confiables).
    """
    with pdfplumber.open(ruta_pdf) as pdf:
        metadata = extraer_metadata(pdf)

    tabla = tabla_diesel_b5_s50(ruta_pdf)

    return [
        {
            "fecha_vigencia": metadata["fecha_vigencia"],
            "lista_id": metadata["lista_id"],
            "planta": planta,
            "valor": valor,
        }
        for planta, valor in tabla.items()
    ]


if __name__ == "__main__":
    import sys
    if "--diesel-b5-s50" in sys.argv:
        # CALLAO y CONCHAN se unifican en "LIMA" dentro de tabla_diesel_b5_s50()
        plantas_esperadas = [
            p for p in (PLANTAS_DESDE_PAGINA2 + PLANTAS_DESDE_PAGINA1_AMAZONIA)
            if p not in ("CALLAO", "CONCHAN")
        ] + ["LIMA"]
        tabla = tabla_diesel_b5_s50("precios.pdf")
        print(f"Plantas encontradas: {len(tabla)} / {len(plantas_esperadas)}")
        for planta in plantas_esperadas:
            valor = tabla.get(planta, "❌ NO ENCONTRADO")
            print(f"  {planta}: {valor}")
