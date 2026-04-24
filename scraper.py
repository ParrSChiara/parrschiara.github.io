#!/usr/bin/env python3
"""
Scarica le informazioni liturgiche da lachiesa.it e le salva come JSON puliti
in assets/liturgia/YYYYMMDD.json.

Utilizzo:
  python scraper.py                          # solo oggi
  python scraper.py 2026-01-01               # da oggi a quella data
  python scraper.py 2026-01-01 2026-12-31    # intervallo specifico

Opzioni:
  --force        Rigenera i file anche se già esistenti
  --no-text      Non scaricare il testo delle letture (solo sigla + url + tipo)
  --fix-version  Post-processa i JSON esistenti estraendo solo CEI2008 (nessun fetch HTTP)
"""

import copy
import json
import requests
import sys
import time
from bs4 import BeautifulSoup, NavigableString, Tag
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

VERSION_PRIORITY = ("CEI2008", "CEI74", "TILC")

_VERSION_MARKERS = {
    "(testo cei74)":  "CEI74",
    "(testo tilc)":   "TILC",
    "(testo cei2008)": "CEI2008",
}


def _detect_tipo(text: str):
    t = text.upper()
    for kw, tipo in TIPO_KEYWORDS:
        if kw in t:
            return tipo
    return None


def _extract_version(testo: str, version: str) -> str:
    """Estrae il testo di una specifica versione da un campo testo multi-versione."""
    marker = f"(Testo {version})"
    if marker not in testo:
        return ""
    start = testo.index(marker) + len(marker)
    end = len(testo)
    for other in ("CEI74", "TILC", "CEI2008"):
        if other == version:
            continue
        pos = testo.find(f"(Testo {other})", start)
        if 0 <= pos < end:
            end = pos
    return testo[start:end].strip()


def _extract_reading_inline(section_div) -> dict:
    """
    Estrae il testo di una lettura non-salmo direttamente dalla pagina del calendario
    (div.section), senza seguire il link bibbia.php.

    La pagina lachiesa.it usa questo markup per le letture:
      <div class="section-content-testo">
        <p>Fonte testuale (es. "Dalla prima lettera di san Pietro apostolo")<br>
        <br/>
        Testo della lettura riga 1<br/>
        riga 2<br/>
        ...
        </p>
        <p>Parola di Dio</p>
      </div>

    Il primo <br> non ha tag di chiusura: BeautifulSoup (html.parser) lo interpreta come
    contenitore di tutto il testo che segue fino alla chiusura del <p> padre. Di conseguenza,
    br.get_text() restituisce l'intero testo della lettura senza numeri di versetto.

    Restituisce dict con 'testo', oppure {} se la struttura non è trovata o il div è vuoto.
    """
    testo_el = section_div.find("div", class_="section-content-testo")

    # Fallback per sezioni senza section-content-testo (es. canto_vangelo):
    # il testo del versetto è in un <p> dentro section-content, insieme a "Alleluia, alleluia."
    if not testo_el:
        content_el = section_div.find("div", class_="section-content")
        if not content_el:
            return {}
        _alleluia = {"alleluia, alleluia.", "alleluia.", "alleluia, alleluia", "alleluia"}
        for p in content_el.find_all("p"):
            linee = [l.strip() for l in p.get_text(separator="\n").replace("\r", "\n").split("\n")]
            linee = [l for l in linee if l and l.lower() not in _alleluia]
            testo = " ".join(linee)
            if len(testo) > 10:
                return {"testo": testo}
        return {}

    p0 = testo_el.find("p")
    if not p0:
        return {}

    # Il primo <br> contiene come figli (secondo il parser) tutto il testo della lettura.
    # Per sezioni brevi (es. canto_vangelo) può non esserci il <br>: si usa p0 direttamente.
    br = p0.find("br")
    raw = br.get_text(separator="\n") if br else p0.get_text(separator="\n")
    # Normalizza a capo, rimuove righe vuote iniziali, esegue strip per riga
    linee = []
    for riga in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        pulita = riga.strip()
        if pulita:
            linee.append(pulita)

    testo = "\n".join(linee)
    if not testo:
        return {}
    return {"testo": testo}


def _extract_psalm_inline(section_div) -> dict:
    """
    Estrae il testo liturgico del Salmo Responsoriale direttamente dalla pagina del
    calendario (div.section), senza seguire il link bibbia.php.

    Il markup della pagina ha questa struttura:
      <div class="section">
        <div class="section-title">Salmo responsoriale</div>
        <div class="section-content">
          <div class="section-content-mini"><a href="bibbia.php?...">Sal XX</a></div>
          <div class="section-content-testo">
            <p><b>testo del ritornello</b>
            <p>verso1<br/>verso2<br/>...<br/>
            <br/>        ← separatore di strofa (riga vuota)
            verso3<br/>...
          </div>
        </div>
      </div>

    Ritorna dict con 'ritornello' e 'testo'. Se la struttura non viene trovata
    restituisce {}.
    """
    testo_el = section_div.find("div", class_="section-content-testo")
    if not testo_el:
        return {}

    # Ritornello: testo del primo tag <b> dentro section-content-testo
    b_tag = testo_el.find("b")
    ritornello_testo = b_tag.get_text(strip=True) if b_tag else ""

    # Versi: il parser HTML (HTML malformato con <p> annidato) produce due paragrafi:
    #   paragraphs[0] = ritornello + versi (tutto)
    #   paragraphs[1] = solo i versi (quello che vogliamo)
    paragraphs = testo_el.find_all("p")
    if len(paragraphs) >= 2:
        body_p = paragraphs[1]
    elif paragraphs:
        body_p = copy.copy(paragraphs[0])
        b = body_p.find("b")
        if b:
            b.decompose()
    else:
        return {"ritornello": f"R. {ritornello_testo}"} if ritornello_testo else {}

    # Costruisce le strofe iterando i nodi figli del paragrafo.
    # Struttura: TEXT<br/>TEXT<br/>...<br/>\n<br/>TEXT<br/>...
    # Un nodo TEXT whitespace-only tra due <br/> segnala il confine di strofa.
    strofe: list[str] = []
    strofa_corrente: list[str] = []
    children = list(body_p.children)
    i = 0
    while i < len(children):
        child = children[i]
        if isinstance(child, NavigableString):
            line = str(child).replace("\r\n", "\n").replace("\r", "\n").strip()
            if line:
                strofa_corrente.append(line)
        elif isinstance(child, Tag) and child.name == "br":
            # Se il nodo successivo è whitespace-only → separatore di strofa
            next_idx = i + 1
            if next_idx < len(children):
                nxt = children[next_idx]
                if isinstance(nxt, NavigableString) and not str(nxt).strip():
                    if strofa_corrente:
                        strofe.append("\n".join(strofa_corrente))
                        strofa_corrente = []
                    i += 1  # consuma il nodo whitespace
        i += 1

    if strofa_corrente:
        strofe.append("\n".join(strofa_corrente))

    testo_versi = "\n\n".join(strofe)
    testo_completo = (f"R. {ritornello_testo}\n\n{testo_versi}"
                      if ritornello_testo else testo_versi)

    result: dict = {}
    if testo_completo:
        result["testo"] = testo_completo
    if ritornello_testo:
        result["ritornello"] = f"R. {ritornello_testo}"
    return result


def fetch_reading_text(url: str) -> dict:
    """Scarica il testo di una lettura da bibbia.php; restituisce solo la versione CEI2008 (con fallback)."""
    try:
        resp = requests.get(url, timeout=20, headers={"Accept-Charset": "utf-8"})
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

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

        by_version: dict[str, list[str]] = {v: [] for v in ("CEI74", "TILC", "CEI2008", "none")}
        seen: set[str] = set()
        current_version = "none"

        for el in container.find_all("p"):
            if el.find(["p", "table", "div"]):
                continue
            text = " ".join(el.get_text(separator=" ").split())
            if not text:
                continue
            # Rileva marker di versione
            marker_version = _VERSION_MARKERS.get(text.lower())
            if marker_version:
                current_version = marker_version
                continue
            if len(text) < 8 or text in seen:
                continue
            lower = text.lower()
            if any(s in lower for s in ["versione", "cerca", "login", "copyright",
                                         "lachiesa", "bibbia.php", "scegli", "seleziona"]):
                continue
            seen.add(text)
            by_version[current_version].append(text)

        # Preferisce CEI2008, fallback su CEI74, TILC, non-versionato
        paragraphs: list[str] = []
        for v in (*VERSION_PRIORITY, "none"):
            if by_version[v]:
                paragraphs = by_version[v]
                break

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
        # Ritornello dal testo della versione selezionata
        for p in paragraphs:
            if p.startswith("R.") or p.startswith("Rit."):
                result["ritornello"] = p
                break
        return result

    except Exception as exc:
        print(f"    [warn] testo non scaricabile: {exc}", flush=True)
        return {}


def fix_json_versions(path: Path) -> bool:
    """Post-processa un JSON già salvato: estrae solo la versione CEI2008 (con fallback su CEI74/TILC)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for lettura in data.get("letture", []):
        testo = lettura.get("testo", "")
        if "(Testo " not in testo:
            continue  # Già singola versione, salta
        for version in VERSION_PRIORITY:
            extracted = _extract_version(testo, version)
            if extracted:
                lettura["testo"] = extracted
                # Aggiorna ritornello dalla versione selezionata
                ritornello = None
                for line in extracted.split("\n"):
                    if line.startswith("R.") or line.startswith("Rit."):
                        ritornello = line
                        break
                if ritornello:
                    lettura["ritornello"] = ritornello
                elif "ritornello" in lettura:
                    del lettura["ritornello"]
                changed = True
                break
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


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

    # Letture: scansione per div.section per rilevare tipo e sigla insieme.
    # Ogni div.section ha un div.section-title (es. "Prima lettura", "Salmo responsoriale")
    # e un div.section-content-mini che contiene il link bibbia.php con la sigla.
    # Questo approccio è più robusto della scansione lineare per tag <b>/<strong> perché
    # il titolo della sezione NON è racchiuso in <b>/<strong> nella pagina corrente.
    letture = []
    seen_siglas: set[str] = set()

    for section_div in soup.find_all("div", class_="section"):
        title_el = section_div.find("div", class_="section-title")
        if not title_el:
            continue
        tipo = _detect_tipo(title_el.get_text(strip=True))
        if not tipo:
            continue

        # Cerca il link bibbia.php nel div.section-content-mini (o in tutta la sezione)
        mini_el = section_div.find("div", class_="section-content-mini")
        search_root = mini_el if mini_el else section_div
        for a in search_root.find_all("a"):
            href = a.get("href", "")
            if "bibbia.php" not in href or "Citazione=" not in href:
                continue
            sigla = a.get_text(strip=True)
            if not sigla or sigla in seen_siglas:
                continue
            seen_siglas.add(sigla)
            entry: dict = {
                "sigla": sigla,
                "url": href,
                "tipo": tipo,
            }
            if fetch_texts:
                label = tipo.ljust(18)
                if tipo == "salmo":
                    # Il salmo usa il testo liturgico inline della pagina
                    # calendario, non il testo integrale di bibbia.php.
                    print(f"    [{label}] {sigla} ... (inline)", flush=True)
                    entry.update(_extract_psalm_inline(section_div))
                else:
                    # Prima tenta l'estrazione inline dalla pagina del calendario:
                    # è più affidabile di bibbia.php (niente troncature da HTML malformato).
                    text_data = _extract_reading_inline(section_div)
                    if text_data.get("testo"):
                        print(f"    [{label}] {sigla} ... (inline) ✓", flush=True)
                    else:
                        # Fallback: scarica da bibbia.php
                        print(f"    [{label}] {sigla} ...", end=" ", flush=True)
                        text_data = fetch_reading_text(href)
                        print("✓" if text_data.get("testo") else "–", flush=True)
                        time.sleep(PAUSE_READING)
                    entry.update(text_data)
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
    force        = "--force"        in sys.argv
    no_text      = "--no-text"      in sys.argv
    fix_version  = "--fix-version"  in sys.argv

    today = date.today()
    if len(positional) == 0:
        return today, today, force, not no_text, fix_version
    if len(positional) == 1:
        target = date.fromisoformat(positional[0])
        start, end = (today, target) if target >= today else (target, today)
        return start, end, force, not no_text, fix_version
    return date.fromisoformat(positional[0]), date.fromisoformat(positional[1]), force, not no_text, fix_version


def main():
    start, end, force, fetch_texts, fix_version = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if fix_version:
        files = sorted(OUTPUT_DIR.glob("*.json"))
        fixed = 0
        for path in files:
            if fix_json_versions(path):
                print(f"[fix]   {path.name}")
                fixed += 1
            else:
                print(f"[skip]  {path.name}")
        print(f"\nAggiornati {fixed}/{len(files)} file in {OUTPUT_DIR}/")
        return

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
