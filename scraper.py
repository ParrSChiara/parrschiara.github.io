#!/usr/bin/env python3
"""
Scarica le informazioni liturgiche da lachiesa.it e le salva come JSON puliti
in assets/liturgia/YYYYMMDD.json.

Utilizzo:
  python scraper.py                          # solo oggi
  python scraper.py 2026-01-01               # da oggi a quella data
  python scraper.py 2026-01-01 2026-12-31    # intervallo specifico

Opzioni:
  --force     Rigenera i file anche se già esistenti
  --no-text   Non scaricare il testo delle letture (solo sigla + url + tipo)
"""

import json
import requests
import sys
import time
from bs4 import BeautifulSoup
from datetime import date, timedelta
from pathlib import Path

BASE_URL   = "https://www.lachiesa.it/calendario/Detailed/{}.shtml"
OUTPUT_DIR = Path("assets/liturgia")
PAUSE         = 1.5  # secondi tra un giorno e l'altro
PAUSE_READING = 0.8  # secondi tra una lettura e l'altra

# Ordine conta: "SECONDA LETTURA" va prima di "LETTURA" per evitare match parziali
TIPO_KEYWORDS = [
    ("PRIMA LETTURA",       "prima_lettura"),
    ("SECONDA LETTURA",     "seconda_lettura"),
    ("SALMO RESPONSORIALE", "salmo"),
    ("SALMO",               "salmo"),
    ("CANTO AL VANGELO",    "canto_vangelo"),
    ("CANTO DAL VANGELO",   "canto_vangelo"),
    ("VANGELO",             "vangelo"),
]


def _detect_tipo(text: str):
    t = text.upper()
    for kw, tipo in TIPO_KEYWORDS:
        if kw in t:
            return tipo
    return None


def fetch_reading_text(url: str) -> dict:
    """Scarica il testo di una lettura da bibbia.php; restituisce dict con 'testo' e opzionale 'ritornello'."""
    try:
        resp = requests.get(url, timeout=20, headers={"Accept-Charset": "utf-8"})
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # Rimuovi elementi di navigazione
        for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # Cerca il contenitore principale del testo biblico
        container = (
            soup.find(id="risultati")
            or soup.find(id="bibbia")
            or soup.find(class_="bibbia-testo")
            or soup.find("div", class_="testo-biblico")
            or soup.find(id="content")
            or soup.body
        )
        if not container:
            return {}

        paragraphs = []
        ritornello = None
        seen: set[str] = set()

        for el in container.find_all("p"):
            if el.find(["p", "table", "div"]):
                continue
            text = " ".join(el.get_text(separator=" ").split())
            if not text or len(text) < 8 or text in seen:
                continue
            lower = text.lower()
            if any(s in lower for s in ["versione", "cerca", "login", "copyright",
                                         "lachiesa", "bibbia.php", "scegli", "seleziona"]):
                continue
            seen.add(text)
            if text.startswith("R.") or text.startswith("Rit."):
                if ritornello is None:
                    ritornello = text
            paragraphs.append(text)

        # Fallback: span/td con classe verso
        if not paragraphs:
            for el in container.find_all(["span", "td"],
                                          class_=lambda c: c and "vers" in c.lower()):
                text = " ".join(el.get_text(separator=" ").split())
                if text and len(text) >= 8 and text not in seen:
                    seen.add(text)
                    paragraphs.append(text)

        result: dict = {}
        if paragraphs:
            result["testo"] = "\n".join(paragraphs)
        if ritornello:
            result["ritornello"] = ritornello
        return result

    except Exception as exc:
        print(f"    [warn] testo non scaricabile: {exc}", flush=True)
        return {}


def scrape_day(date_str: str, fetch_texts: bool = True) -> dict:
    url = BASE_URL.format(date_str)
    resp = requests.get(url, timeout=15, headers={"Accept-Charset": "utf-8"})
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.find(id="content")
    if not content:
        raise ValueError(f"Struttura HTML non trovata per {date_str}")

    # Titolo liturgico
    title_el = content.find(class_="section-title")
    settimana = title_el.get_text(strip=True) if title_el else ""

    # Grado e colore
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

    # Letture: scansione lineare per rilevare tipo dai tag <b>/<strong>
    letture = []
    seen_siglas: set[str] = set()
    current_tipo = None

    for el in soup.find_all(["b", "strong", "a"]):
        if el.name in ("b", "strong"):
            tipo = _detect_tipo(el.get_text(strip=True))
            if tipo:
                current_tipo = tipo
        elif el.name == "a":
            href = el.get("href", "")
            if "bibbia.php" in href and "Citazione=" in href:
                sigla = el.get_text(strip=True)
                if sigla and sigla not in seen_siglas:
                    seen_siglas.add(sigla)
                    entry: dict = {
                        "sigla": sigla,
                        "url": href,
                        "tipo": current_tipo or "lettura",
                    }
                    if fetch_texts:
                        label = (current_tipo or "?").ljust(18)
                        print(f"    [{label}] {sigla} ...", end=" ", flush=True)
                        text_data = fetch_reading_text(href)
                        entry.update(text_data)
                        print("✓" if text_data.get("testo") else "–", flush=True)
                        time.sleep(PAUSE_READING)
                    letture.append(entry)

    return {
        "data": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
        "settimana": settimana,
        "celebrazione": celebrazione,
        "colore": colore,
        "letture": letture,
    }


def parse_args():
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    force   = "--force"   in sys.argv
    no_text = "--no-text" in sys.argv

    today = date.today()
    if len(positional) == 0:
        return today, today, force, not no_text
    if len(positional) == 1:
        target = date.fromisoformat(positional[0])
        start, end = (today, target) if target >= today else (target, today)
        return start, end, force, not no_text
    return date.fromisoformat(positional[0]), date.fromisoformat(positional[1]), force, not no_text


def main():
    start, end, force, fetch_texts = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    current = start
    total   = (end - start).days + 1
    done    = 0

    while current <= end:
        date_str = current.strftime("%Y%m%d")
        out_path = OUTPUT_DIR / f"{date_str}.json"

        if out_path.exists() and not force:
            print(f"[skip]  {date_str}")
        else:
            try:
                mode = "force" if (force and out_path.exists()) else "fetch"
                print(f"[{mode}]  {date_str}", flush=True)
                data = scrape_day(date_str, fetch_texts=fetch_texts)
                out_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"  ✓ {data['celebrazione']} — {data['colore']}")
                done += 1
                time.sleep(PAUSE)
            except Exception as exc:
                print(f"  ERRORE: {exc}")

        current += timedelta(days=1)

    print(f"\nScaricati {done}/{total} file in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
