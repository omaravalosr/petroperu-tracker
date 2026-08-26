"""
update.py — Orquesta scraper + parser para mantener data/precios.csv
actualizado con el precio "Diesel B5 S-50" por planta (agosto 2026).

Guarda SOLO lo que se necesita: fecha_vigencia, lista_id, planta, valor.
(fecha_vigencia y lista_id salen del CONTENIDO del PDF, no del link web)

Uso:
    python update.py                    # solo agosto 2026 (default)
    python update.py --year 2026 --month 8
    python update.py --limit 3           # prueba rápida, primeros 3 PDFs
    python update.py --year all           # todo el histórico (lento)

Idempotente: si corre 2 veces seguidas sin PDFs nuevos, no duplica nada
(dedup por lista_id + planta).
"""

import argparse
import os
import sys
import requests
import pandas as pd

from scraper import obtener_lista_pdfs
from parser import extraer_diesel_b5_s50_filas

CARPETA_RAW = "raw"
CARPETA_DATA = "data"
RUTA_CSV = os.path.join(CARPETA_DATA, "precios.csv")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def cargar_csv_existente():
    if os.path.exists(RUTA_CSV):
        return pd.read_csv(RUTA_CSV)
    return pd.DataFrame(columns=["fecha_vigencia", "lista_id", "planta", "valor"])


def lista_ids_ya_procesados(df):
    if df.empty:
        return set()
    return set(df["lista_id"].dropna().unique())


def descargar_pdf(url, destino):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    with open(destino, "wb") as f:
        f.write(resp.content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                     help="Máximo de PDFs nuevos a procesar en esta corrida")
    ap.add_argument("--year", type=str, default="2026",
                     help="Año a filtrar (del texto del link). 'all' = todo el histórico.")
    ap.add_argument("--month", type=str, default="08",
                     help="Mes a filtrar, 2 dígitos (ej. 08). 'all' = todos los meses del año.")
    args = ap.parse_args()

    os.makedirs(CARPETA_RAW, exist_ok=True)
    os.makedirs(CARPETA_DATA, exist_ok=True)

    df_existente = cargar_csv_existente()
    ya_procesados = lista_ids_ya_procesados(df_existente)
    print(f"PDFs ya procesados en el CSV: {len(ya_procesados)}")

    pdfs = obtener_lista_pdfs()
    print(f"PDFs encontrados en la web: {len(pdfs)}")

    if args.year != "all":
        prefijo = args.year if args.month == "all" else f"{args.year}-{args.month}"
        antes = len(pdfs)
        pdfs = [p for p in pdfs if (p.get("fecha") or "").startswith(prefijo)]
        print(f"Filtrado a {prefijo}: {len(pdfs)} de {antes} PDFs")

    pendientes = [p for p in pdfs if p.get("lista_id") not in ya_procesados]
    print(f"PDFs nuevos por procesar: {len(pendientes)}")

    if args.limit:
        pendientes = pendientes[:args.limit]

    filas_nuevas = []

    for pdf_info in pendientes:
        url = pdf_info["url"]
        fecha = pdf_info.get("fecha") or "sin-fecha"
        # Nombre de archivo local basado en FECHA (única por PDF de la web),
        # no en lista_id (que a veces el scraper no logra leer del link
        # y puede colisionar entre PDFs distintos).
        nombre_archivo = f"{fecha}.pdf"
        ruta_local = os.path.join(CARPETA_RAW, nombre_archivo)

        print(f"\nProcesando PDF del {fecha} ...")
        try:
            if not os.path.exists(ruta_local):
                descargar_pdf(url, ruta_local)

            filas = extraer_diesel_b5_s50_filas(ruta_local)

            if not filas:
                print("  !! ADVERTENCIA: 0 filas extraídas, revisar PDF manualmente")
                continue

            lista_id_real = filas[0]["lista_id"]
            if lista_id_real in ya_procesados:
                print(f"  -> {lista_id_real} ya estaba en el CSV (mismo lista_id), se omite")
                continue

            filas_nuevas.extend(filas)
            ya_procesados.add(lista_id_real)
            print(f"  -> {lista_id_real} | vigencia {filas[0]['fecha_vigencia']} | {len(filas)} plantas")

        except Exception as e:
            print(f"  !! ERROR procesando PDF del {fecha}: {e}", file=sys.stderr)
            continue

    if not filas_nuevas:
        print("\nNo hay datos nuevos. CSV sin cambios.")
        return

    df_nuevo = pd.DataFrame(filas_nuevas)
    df_final = pd.concat([df_existente, df_nuevo], ignore_index=True)
    df_final = df_final.drop_duplicates(subset=["lista_id", "planta"], keep="last")
    df_final = df_final.sort_values(["fecha_vigencia", "planta"])

    df_final.to_csv(RUTA_CSV, index=False)
    print(f"\nCSV actualizado: {RUTA_CSV} ({len(df_final)} filas totales)")


if __name__ == "__main__":
    main()
