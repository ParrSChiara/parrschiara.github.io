#!/usr/bin/env python3
"""
Scarica le informazioni liturgiche da lachiesa.it e le salva come JSON puliti
in assets/liturgia/YYYYMMDD.json.

Utilizzo:
  python scraper.py                          # solo oggi
  python scraper.py 2026-01-01               # da oggi a quella data
  python scraper.py 2026-01-01 2026-12-31    # intervallo specifico
"""

import json
import requests
import sys
import time
from bs4 import BeautifulSoup
from datetime import date, timedelta
from pathlib import Path

BASE_URL = "https://www.lachiesa.it/calendario/Detailed/{}.shtml"
OUTPUT_DIR = Path("assets/liturgia")
PAUSE = 1.5  # secondi tra una richiesta e l'altra (rispetto al server)


def scrape_day(date_str: str) -> dict:
    url = BASE_URL.format(date_str)
    resp = requests.get(url, timeout=15, headers={"Accept-Charset": "utf-8"})
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.find(id="content")
    if not content:
        raise ValueError(f"Struttura HTML non trovata per {date_str}")

    # Titolo del giorno liturgico
    title_el = content.find(class_="section-title")
    settimana = title_el.get_text(strip=True) if title_el else ""

    # Grado e colore: si leggono dai tag <b> dentro font[size="-1"] (i valori
    # sono in bold, non inline con la chiave, quindi get_text() non funziona)
    celebrazione = ""
    colore = ""
    font_el = content.find("font", attrs={"size": "-1"})
    if font_el:
        for hidden in font_el.find_all("font", attrs={"color": True}):
            if hidden.get("color", "").upper() in ("#FFFFCC", "#FFFFFF"):
                hidden.decompose()
        bold = font_el.find_all("b")
        if len(bold) >= 1:
            celebrazione = bold[0].get_text(strip=True)
        if len(bold) >= 2:
            colore = bold[1].get_text(strip=True).lower()

    # Letture: le sezioni sono fuori da #content, si cercano i link bibbia.php
    # nell'intera pagina (Prima lettura, Salmo, Canto al Vangelo, Vangelo)
    letture = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "bibbia.php" in href and "Citazione=" in href:
            sigla = a.get_text(strip=True)
            if sigla and sigla not in seen:
                seen.add(sigla)
                letture.append({"sigla": sigla, "url": href})

    return {
        "data": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
        "settimana": settimana,
        "celebrazione": celebrazione,
        "colore": colore.lower(),
        "letture": letture,
    }


def parse_args():
    args = sys.argv[1:]
    today = date.today()
    if len(args) == 0:
        return today, today
    if len(args) == 1:
        target = date.fromisoformat(args[0])
        start, end = (today, target) if target >= today else (target, today)
        return start, end
    return date.fromisoformat(args[0]), date.fromisoformat(args[1])


def main():
    start, end = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    current = start
    total = (end - start).days + 1
    done = 0

    while current <= end:
        date_str = current.strftime("%Y%m%d")
        out_path = OUTPUT_DIR / f"{date_str}.json"

        if out_path.exists():
            print(f"[skip]  {date_str}")
        else:
            try:
                print(f"[fetch] {date_str} ...", end=" ", flush=True)
                data = scrape_day(date_str)
                out_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"{data['celebrazione']} — {data['colore']}")
                done += 1
                time.sleep(PAUSE)
            except Exception as exc:
                print(f"ERRORE: {exc}")

        current += timedelta(days=1)

    print(f"\nScaricati {done}/{total} file in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()