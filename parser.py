"""
parser.py
Extrae la tabla de precios de un PDF de PetroPerú a filas limpias.

Requiere: pip install pdfplumber

ESTRATEGIA:
El PDF no tiene una tabla real (sin bordes de celda), así que
reconstruimos filas agrupando palabras por posición vertical (top)
y luego mapeamos cada valor numérico a una columna según su
posición horizontal (x0).

FLUJO DE TRABAJO EN CLAUDE CODE (con red disponible):
  1. Correr `inspeccionar_pdf(ruta)` primero. Esto imprime cada
     palabra con su (x0, top), para que puedas VER dónde caen
     los headers de columna y los nombres de planta.
  2. Con esos números, definir COLUMNAS_X (rangos de x0 -> nombre
     de columna) para cada uno de los 3 bloques del PDF
     (principal, Addendum N°1, Addendum N°2).
  3. Correr `parsear_pdf(ruta)` para obtener las filas limpias.

Este archivo trae la función de inspección lista para usar y un
esqueleto de mapeo que TIENES que calibrar con el PDF real -
los rangos de x0 abajo son ejemplos, no están confirmados.
"""

import pdfplumber
import re


def inspeccionar_pdf(ruta_pdf):
    """Imprime cada palabra con su posición para calibrar columnas."""
    with pdfplumber.open(ruta_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"\n=== Página {i + 1} ===")
            words = page.extract_words()
            for w in words:
                print(f"top={w['top']:.1f}  x0={w['x0']:.1f}  texto='{w['text']}'")


def agrupar_en_filas(words, tolerancia_top=3):
    """Agrupa palabras que están en la misma línea visual (mismo 'top' aprox)."""
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


# Lista de plantas conocidas (del PDF de muestra 25.08.2026).
# Puede que aparezcan/desaparezcan plantas en PDFs de otras fechas.
PLANTAS_CONOCIDAS = [
    "TALARA", "PIURA", "ETEN", "SALAVERRY", "CHIMBOTE", "SUPE", "CALLAO",
    "CONCHAN", "PISCO", "MOLLENDO", "JULIACA", "CUSCO", "ILO",
    "EL MILAGRO", "TARAPOTO", "YURIMAGUAS", "IQUITOS", "PUCALLPA",
    "PTO. MALDONADO",
]

NUM_RE = re.compile(r"^\d{1,3}(\.\d{1,4})?$")


def es_numero(texto):
    return bool(NUM_RE.match(texto.replace(",", "")))


def parsear_pdf(ruta_pdf, columnas_x):
    """
    columnas_x: dict {nombre_columna: (x_min, x_max)} calibrado a mano
    para el bloque de precios que quieras parsear.

    Devuelve lista de dicts: {planta, columna, valor}
    """
    filas_resultado = []

    with pdfplumber.open(ruta_pdf) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            filas = agrupar_en_filas(words)

            for fila in filas:
                texto_fila = " ".join(w["text"] for w in fila)
                planta_encontrada = None
                for planta in PLANTAS_CONOCIDAS:
                    if texto_fila.upper().startswith(planta):
                        planta_encontrada = planta
                        break

                if not planta_encontrada:
                    continue

                for w in fila:
                    if not es_numero(w["text"]):
                        continue
                    for col_nombre, (x_min, x_max) in columnas_x.items():
                        if x_min <= w["x0"] <= x_max:
                            filas_resultado.append({
                                "planta": planta_encontrada,
                                "columna": col_nombre,
                                "valor": float(w["text"]),
                            })
                            break

    return filas_resultado


if __name__ == "__main__":
    # PASO 1: calibrar. Descomenta y corre esto primero con tu PDF real:
    # inspeccionar_pdf("precios.pdf")

    # PASO 2: una vez tengas los x0 reales del PDF, define esto:
    columnas_x_ejemplo = {
        "GLP": (60, 100),
        "GASOLINA_DIESEL_UV": (100, 160),
        "DIESEL_B5": (160, 220),
        "IND_N6": (220, 280),
        "IND_500": (280, 340),
        # ... completar según inspeccion real
    }

    resultado = parsear_pdf("precios.pdf", columnas_x_ejemplo)
    for r in resultado[:20]:
        print(r)
