# Task: Generatore Foglietto Settimanale

## Obiettivo

Aggiungere al sito `parrschiara.github.io` una pagina web (`foglietto.html`) che permetta a un catechista non tecnico di generare il foglietto settimanale della Parrocchia Santa Chiara direttamente dal browser, senza installazioni, senza account aggiuntivi e senza modifiche manuali al layout.

**Successo =** il catechista apre il sito, sceglie la domenica, compila 4-5 campi, clicca stampa. Zero formattazione manuale.

---

## Contesto

### Struttura attuale del foglietto (2 pagine A4)

**Pagina 1 — Letture liturgiche**
- Intestazione fissa: nome parrocchia, indirizzo, chiese filiali
- Data + nome domenica (es. "V DOMENICA DI PASQUA ANNO A")
- Colonna sinistra: Prima Lettura, Salmo Responsoriale, Seconda Lettura
- Colonna destra: Canto dal Vangelo, Vangelo, Preghiera dei Fedeli
- Le letture vengono da `lachiesa.it` tramite scraping

**Pagina 2 — Calendario settimanale**
- Tabella: giorno + data (sinistra) | appuntamenti (destra)
- Copre dalla domenica corrente alla domenica successiva (8 giorni)
- Appuntamenti fissi pre-compilati da `appuntamenti_fissi.json`
- Appuntamenti variabili inseriti manualmente (intenzioni messe, eventi speciali)
- Footer: orari confessioni, avvisi speciali

### Infrastruttura esistente (da riutilizzare)
- `scraper.py` — scarica i dati liturgici da `lachiesa.it` e li salva in `assets/liturgia/YYYYMMDD.json`
- GitHub Action (`.github/workflows/update_liturgia.yml`) — esegue lo scraper ogni lunedì alle 05:00 UTC automaticamente
- `assets/liturgia/YYYYMMDD.json` — oggi contiene: `data`, `settimana`, `celebrazione`, `colore`, `letture[]` (solo sigla + URL, non il testo)

### File di configurazione da usare
- `/Users/AndreaValenziano/Documents/parr/foglietto_settimanale/appuntamenti_fissi.json` — appuntamenti ricorrenti per ogni giorno della settimana. Va copiato in `assets/foglietto/appuntamenti_fissi.json` nel repo.

### Reference visivo
- PDF esempio: `/Users/AndreaValenziano/Documents/parr/foglietto_settimanale/IV DOMENICA DI PASQUA 2026 ANNO A.pdf`

---

## Cose da fare

### 1. Modifica `scraper.py`
- [x] Aggiungere il fetch del testo integrale di ogni lettura dall'URL `bibbia.php` già presente nel JSON
- [x] Salvare il testo nel campo `testo` di ogni lettura in `assets/liturgia/YYYYMMDD.json`
- [x] Gestire la struttura: Prima Lettura, Salmo (con ritornello), Seconda Lettura, Canto dal Vangelo, Vangelo
- [x] Flag `--force` per rigenerare file già esistenti
- [x] Flag `--no-text` e `--fix-version`
- [x] **Estrazione inline** per tutte le letture (non solo salmo): `_extract_reading_inline(section_div)` legge `div.section-content-testo` dalla pagina del calendario, più affidabile di bibbia.php (evita troncature da `<p>` annidati HTML malformato). Fallback su bibbia.php se il div è assente.
- [x] **Bug fix**: seconda lettura 2026-04-26 troncata — causa: bibbia.php ha `<p>` annidati che il filtro `if el.find(["p","table","div"]): continue` eliminava il contenitore con i vv. 20-21. Risolto con estrazione inline.
- [x] **Bug fix**: canto dal vangelo mancante — la sezione usa `div.section-content` (non `section-content-testo`): il verso è in un `<p>` insieme a "Alleluia, alleluia." e "Alleluia.". `_extract_reading_inline` ora gestisce questo caso estraendo il testo e filtrando le acclamazioni.

### 2. Aggiornare il GitHub Action
- [x] Workflow `update_liturgia.yml` compatibile con lo scraper aggiornato (nessuna nuova dipendenza aggiunta)

### 3. Creare `assets/foglietto/appuntamenti_fissi.json`
- [x] File creato con struttura: `{ giorni: [{ giorno, appuntamenti: [{ orario, descrizione, chiesa, intenzione, fisso, sospeso }] }], note_permanenti: { confessioni, whatsapp_community } }`
- [x] Campo `sospeso: true` per sospendere appuntamenti fissi
- [x] Campo `intenzione: null` per messe con intenzione da inserire manualmente

### 4. Creare `assets/foglietto/foglietto.css`
- [x] Layout pagina 1: intestazione 3 colonne (parrocchia | logo | chiese filiali), etichetta data verticale, due colonne letture
- [x] Layout pagina 2: tabella calendario (giorno+data | appuntamenti), footer confessioni/avvisi/whatsapp
- [x] Font: Times New Roman per letture, stesso per calendario (A4 compatto)
- [x] `@media print`: nasconde UI, pagine A4 esatte, `page-break-after: always`
- [x] Indicatore visivo fine pagina (`::after` dashed) visibile solo a schermo

### 5. Creare `foglietto.html`
- [x] **Sezione A**: date picker domenica → fetch `assets/liturgia/YYYYMMDD.json`, chip colore liturgico
- [x] **Sezione B**: form letture (solo info, editing in anteprima), textarea Preghiera dei Fedeli, form calendario con appuntamenti fissi/variabili, checkbox sospeso, campo intenzione inline
- [x] **Sezione C**: anteprima pagina 1 (letture) + pagina 2 (calendario), `contenteditable`, pulsante stampa
- [x] Algoritmo overflow pagina 1: riduzione font 7.8→6.6pt, spostamento sezioni sx→dx, pagina extra `.foglietto-page-overflow`
- [x] **Fix rendering salmo**: `readingText()` per salmo usa `\n\n` per strofe (ogni strofa = `<p>`), `\n` → `<br>` dentro la strofa
- [x] **Fix spacing letture**: paragrafi con `margin-bottom:0` per ridurre spazio verticale

### 6. Accesso al foglietto
- [x] Nessun link pubblico in `index.html` — accesso solo conoscendo l'URL diretto `foglietto.html` (sicurezza per oscurità, sufficiente per uso interno parrocchiale)
- [x] Rimosso il pulsante "Genera Foglietto" da `index.html`

### 7. Scaling font automatico pagina 1
- [x] `adjustPage1Layout()` parte da 12pt e scende fino a 6.6pt: trova il massimo che entra invece di partire sempre da 7.8pt
- [x] `SIZES = [12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8, 7.8, 7.5, 7.2, 6.9, 6.6]`
- [x] `#ce-preghiera { min-height: 35mm }` in foglietto.css — riserva spazio per la Preghiera dei Fedeli anche quando vuota, evitando che il font cresca eccessivamente e poi collassi quando si aggiunge il testo

---

## Regole da rispettare durante lo sviluppo

1. Le citazioni bibliche devono essere esatte come da fonte `lachiesa.it` — nessuna parafrasi
2. Gli appuntamenti fissi vengono solo da `appuntamenti_fissi.json` — mai hardcoded nel codice
3. La Preghiera dei Fedeli non viene mai generata automaticamente — sempre placeholder
4. Il testo del foglietto è in italiano, registro formale parrocchiale
5. Il layout deve essere fedele al reference PDF — non semplificare per comodità
6. Zero dipendenze esterne a runtime (niente CDN a pagamento, niente API key) — tutto statico

---

## Utente finale

Catechista non tecnico, accede solo dal browser (PC o telefono). Non ha accesso a GitHub. Non sa usare terminali o editor di codice. Lo strumento deve essere autonomo e auto-esplicativo.

---

## Note tecniche

- Il sito è statico (HTML/CSS/JS puro, no backend) — tutto deve funzionare lato client
- I file JSON liturgici sono già pubblici su GitHub Pages, raggiungibili via fetch()
- Il CORS non è un problema: i JSON sono sulla stessa origine del sito
- Per il testo delle letture da `lachiesa.it`: lo scraper li recupera server-side (GitHub Action) e li salva nel JSON — nessuna chiamata cross-origin dal browser
- Nessun framework JS richiesto — vanilla JS è sufficiente