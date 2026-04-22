# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static website for **Parrocchia Santa Chiara** (a Catholic parish), hosted on GitHub Pages. No build system, no framework, no backend — pure HTML/CSS/vanilla JavaScript committed directly to the repo and served as-is.

## Deployment

Pushes to `main` are automatically served via GitHub Pages. There is no build step.

Un workflow GitHub Actions (`.github/workflows/update_liturgia.yml`) gira ogni lunedì alle 05:00 UTC: scarica i prossimi 90 giorni di dati liturgici da lachiesa.it tramite `scraper.py`, committa i nuovi JSON in `assets/liturgia/` e pusha. Si può attivare manualmente dalla UI di GitHub con "Run workflow".

## Architecture

Three main pages:

- **`index.html`** — Main portal. Dynamically loads the current day's liturgical data from `assets/html/YYYYMMDD.html` using the Fetch API. Contains character-encoding fix logic (UTF-8 → Italian accented characters) and Italian locale date formatting.
- **`pdf_viewer.html`** — Custom PDF viewer using PDF.js (v2.10.377, CDN). Accepts a `?file=` query parameter to select which PDF to display.
- **`upload.html`** — Admin tool that uses the GitHub REST API to upload PDFs directly from the browser, without needing git CLI access. Uses a Personal Access Token stored in `localStorage`.

## Content Files

- **`assets/liturgia/YYYYMMDD.json`** — Un file per giorno, generato da `scraper.py`. Contiene: `settimana`, `celebrazione`, `colore`, `letture[]`. Aggiornato automaticamente dal workflow CI.
- **`assets/pdf/`** — Liturgical PDFs (weekly bulletin, adoration, compline, seasonal services).
- **`foglio_settimanale.pdf`** (repo root) — Current weekly parish bulletin; also mirrored at `assets/pdf/foglio_settimanale.pdf`.

## Generazione manuale dei JSON liturgici

```bash
pip install -r requirements.txt
python scraper.py 2026-01-01 2026-12-31
```

I file già presenti vengono saltati automaticamente. Per forzare il riscaricare, eliminare prima il file JSON corrispondente.

## Language

All content, UI strings, and commit messages are in **Italian**.