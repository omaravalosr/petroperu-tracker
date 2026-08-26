"""
scraper.py
Lista los PDFs de la sección "Automotriz" en la página de PetroPerú.
Devuelve una lista de dicts: {"fecha": "2026-08-25", "url": "...", "lista_id": "COMB-60-2026"}

Requiere: pip install requests beautifulsoup4
"""

import os
import re
import requests
from bs4 import BeautifulSoup

URL_BASE = "https://www.petroperu.com.pe/productos/lista-de-precios-en-nuestras-plantas/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Convención de guardado: precios/<año>/<mes_abrev><día>.pdf
# (ej. 25.08.2026 -> precios/2026/agos25.pdf)
MESES_ABREV = {
    1: "ener", 2: "febr", 3: "marz", 4: "abri", 5: "mayo", 6: "juni",
    7: "juli", 8: "agos", 9: "sept", 10: "octu", 11: "novi", 12: "dici",
}


def ruta_destino(fecha_iso, carpeta_base="precios"):
    """Ruta local 'precios/<año>/<mesabrev><día>.pdf' para una fecha ISO (YYYY-MM-DD)."""
    anio, mes, dia = fecha_iso.split("-")
    nombre_archivo = f"{MESES_ABREV[int(mes)]}{dia}.pdf"
    return os.path.join(carpeta_base, anio, nombre_archivo)


def descargar_pdf(pdf_info, carpeta_base="precios"):
    """
    Descarga el PDF de precios de pdf_info (dict con 'url' y 'fecha' ISO)
    y lo guarda en precios/<año>/<mesabrev><día>.pdf.
    Devuelve la ruta local donde quedó guardado.
    """
    if not pdf_info.get("fecha"):
        raise ValueError("pdf_info necesita una 'fecha' ISO para poder nombrar el archivo")

    destino = ruta_destino(pdf_info["fecha"], carpeta_base)
    os.makedirs(os.path.dirname(destino), exist_ok=True)

    resp = requests.get(pdf_info["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()

    with open(destino, "wb") as f:
        f.write(resp.content)

    return destino


def obtener_lista_pdfs(categoria="Automotriz"):
    """
    Descarga la página HTML y extrae los PDFs de la categoría dada.

    La web publica esta lista de precios como un calendario segmentado
    por tipo de combustible: Automotriz, Marino, Aviación, Asfaltos y
    Productos químicos (5 categorías, cada PDF marcado con su
    data-eng-text real en el HTML). Solo nos interesa "Automotriz"
    (combustibles de plantas de venta al público) — las otras traen
    tablas totalmente distintas y romperían el parser si se procesan
    igual.

    Cada entrada del calendario ya trae su fecha en
    data-date="YYYY-MM-DD", así que no hace falta parsear el texto
    visible (que viene en español, ej. "25-Ago-2026").
    """
    resp = requests.get(URL_BASE, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    resultados = []

    for li in soup.select("ul.segmented-calendar li[data-date]"):
        titulo = li.select_one(".title")
        if not titulo or titulo.get_text(strip=True) != categoria:
            continue

        link = li.find("a", href=re.compile(r"\.pdf$", re.IGNORECASE))
        if not link:
            continue

        href = link.get("href")
        if href.startswith("/"):
            href = "https://www.petroperu.com.pe" + href

        texto = link.get_text(strip=True)
        lista_match = re.search(r"COMB-(\d+)-(\d{4})", texto)

        resultados.append({
            "fecha": li.get("data-date"),
            "texto_original": texto,
            "url": href,
            "lista_id": lista_match.group(0) if lista_match else None,
        })

    # Deduplicar por URL, ordenar por fecha descendente
    vistos = set()
    unicos = []
    for r in resultados:
        if r["url"] not in vistos:
            vistos.add(r["url"])
            unicos.append(r)

    unicos.sort(key=lambda r: r["fecha"] or "", reverse=True)
    return unicos


if __name__ == "__main__":
    pdfs = obtener_lista_pdfs()
    print(f"Encontrados {len(pdfs)} PDFs")
    for p in pdfs[:5]:
        print(p)
