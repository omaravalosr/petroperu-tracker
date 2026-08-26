"""
scraper.py
Lista todos los PDFs de la sección "Automotriz" en la página de PetroPerú.
Devuelve una lista de dicts: {"fecha": "2026-08-25", "url": "...", "lista_id": "COMB-60-2026"}

Requiere: pip install requests beautifulsoup4
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

URL_BASE = "https://www.petroperu.com.pe/productos/lista-de-precios-en-nuestras-plantas/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def obtener_lista_pdfs():
    """
    Descarga la página HTML y extrae todos los links de PDF dentro
    de la sección Automotriz, junto a su fecha de vigencia.

    NOTA IMPORTANTE (calibrar en Claude Code):
    No conozco todavía el HTML exacto de esa sección (solo vi el
    contenido ya renderizado/interpretado por mi herramienta de fetch).
    Tienes que:
      1. Correr este script con `resp.text` impreso o guardado en un .html
      2. Inspeccionar en el navegador (clic derecho > Inspeccionar) el
         bloque "Automotriz" para confirmar el selector CSS real
         (probablemente un <div> o <table> con una clase específica,
         y cada fila con un <a href="...pdf"> y un texto de fecha cerca).
      3. Ajustar el selector en la línea marcada como TODO abajo.
    """
    resp = requests.get(URL_BASE, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    resultados = []

    # TODO: ajustar este selector una vez inspecciones el HTML real.
    # Punto de partida razonable: buscar todos los <a> que terminen en .pdf
    links = soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE))

    for link in links:
        href = link.get("href")
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.petroperu.com.pe" + href

        # El texto visible del link o su contenedor suele traer la fecha
        # y a veces el número de lista (ej. "COMB-60-2026 - 25.08.2026")
        texto = link.get_text(strip=True)

        fecha_match = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", texto)
        fecha_iso = None
        if fecha_match:
            d, m, y = fecha_match.groups()
            try:
                fecha_iso = datetime(int(y), int(m), int(d)).date().isoformat()
            except ValueError:
                pass

        lista_match = re.search(r"COMB-(\d+)-(\d{4})", texto)
        lista_id = lista_match.group(0) if lista_match else None

        resultados.append({
            "fecha": fecha_iso,
            "texto_original": texto,
            "url": href,
            "lista_id": lista_id,
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
