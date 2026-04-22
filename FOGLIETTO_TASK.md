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
- [ ] Aggiungere il fetch del testo integrale di ogni lettura dall'URL `bibbia.php` già presente nel JSON
- [ ] Salvare il testo nel campo `testo` di ogni lettura in `assets/liturgia/YYYYMMDD.json`
- [ ] Gestire la struttura: Prima Lettura, Salmo (con ritornello), Seconda Lettura, Canto dal Vangelo, Vangelo
- [ ] I file JSON già esistenti non vanno rigenerati (lo scraper già li salta se presenti) — aggiungere un flag `--force` opzionale per rigenerare

### 2. Aggiornare il GitHub Action
- [ ] Verificare che il workflow `update_liturgia.yml` continui a funzionare con il nuovo scraper
- [ ] Aggiornare `requirements.txt` se servono nuove dipendenze

### 3. Creare `assets/foglietto/appuntamenti_fissi.json`
- [ ] Copiare e adattare il file da `/Users/AndreaValenziano/Documents/parr/foglietto_settimanale/appuntamenti_fissi.json`
- [ ] Struttura per giorno: `orario`, `descrizione`, `chiesa`, `intenzione` (null = da inserire), `fisso`, `sospeso`
- [ ] Campo `sospeso: true` per sospendere temporaneamente appuntamenti fissi (es. durante la Novena)

### 4. Creare `assets/foglietto/foglietto.css`
- [ ] Layout pagina 1: intestazione full-width + due colonne per le letture + testo data verticale sul lato sinistro
- [ ] Layout pagina 2: tabella calendario a due colonne (giorno+data | appuntamenti)
- [ ] Font: serif per le letture, sans-serif per il calendario
- [ ] Stile citazioni bibliche: corsivo, riferimento tra parentesi
- [ ] Orari in grassetto nel calendario
- [ ] Media print: nascondere UI, mostrare solo le due pagine A4

### 5. Creare `foglietto.html`
Pagina web con tre sezioni:

**Sezione A — Selezione domenica**
- Date picker (solo domeniche selezionabili)
- Al cambio data: fetch automatico di `assets/liturgia/YYYYMMDD.json`
- Mostra titolo domenica e colore liturgico

**Sezione B — Compilazione**
- Letture pre-compilate (testo già estratto dallo scraper) — modificabili
- Textarea per la Preghiera dei Fedeli
- Tabella calendario con:
  - Righe pre-compilate dagli appuntamenti fissi (da `appuntamenti_fissi.json`)
  - Per ogni riga con `intenzione: null`: campo testo inline per inserire "per Mario", "per i defunti..."
  - Per ogni giorno: pulsante "+ Aggiungi appuntamento" per eventi variabili
  - Checkbox per sospendere un appuntamento fisso (override temporaneo del campo `sospeso`)
- Campo avvisi speciali (textarea, opzionale)

**Sezione C — Anteprima e stampa**
- Preview del foglietto formattato (fedele al layout PDF originale)
- Testo nell'anteprima modificabile inline (`contenteditable`)
- Pulsante "Stampa / Salva come PDF" → `window.print()`

### 6. Aggiungere link nella navigazione del sito
- [ ] Aggiungere voce "Foglietto" (o icona) in `index.html` che punta a `foglietto.html`
- [ ] Accesso protetto opzionale (es. password semplice in localStorage) se si vuole evitare accessi non autorizzati

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