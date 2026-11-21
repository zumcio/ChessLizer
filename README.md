# Chess Analysis & Course Authoring Toolkit (`1. d4` & Black Repertoire)

Kompleksowe środowisko analityczne i autorskie do budowy, weryfikacji oraz walidacji repertuaru szachowego (docelowy poziom **1800–2200+ FIDE** / kursy w formacie **Chessable PGN**).

Projekt łączy lokalną ocenę silnika **Stockfish 19**, statystyki praktyczne z baz **Lichess Masters** i **Lichess Online (2000–2500)**, tablice końcówek **Syzygy 7-piece**, bazę kodów **ECO**, wieloagentowe skille (`skills/`) oraz rygorystyczny walidator formatu **Chessable PGN**.

---

## Struktura projektu

```text
├── data/
│   └── eco/                         # Offline baza debiutów ECO (a.tsv – e.tsv) do rozpoznawania nazw i transpozycji
├── repertoire/                      # Gotowe rozdziały repertuaru i szkielety drzewa PGN
│   ├── ch01_qgd/                    # Rozdział 1: Klasyczny Gambit Hetmański (1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5)
│   │   ├── ch01_klasyczny_qgd.pgn
│   │   └── ch01_klasyczny_qgd_chessable.pgn
│   └── ch04_kid/                    # Rozdział 4: Obrona Królewsko-Indyjska – System Gligorića (7. Be3)
│       ├── ch04_kid_gligoric.pgn
│       └── ch04_kid_gligoric_chessable.pgn
├── skills/                          # Skille agentowe sterujące procesem analizy i formatowaniem Chessable
│   ├── chess-analysis-architect/    # Wieloagentowy pipeline (Idea Dossier -> Gate 1 -> Prose -> Gate 2 -> Release)
│   │   └── SKILL.md
│   └── chessable-pgn/               # Specyfikacja i reguły konwersji PGN pod importer Chessable
│       └── SKILL.md
├── tools/
│   ├── analyze.py                   # Zunifikowane CLI analityczne (raporty 360°, Stockfish, Masters, Online, Coverage, SVG)
│   ├── chess_env.py                 # Rdzeń biblioteki (Stockfish UCI, klient Lichess API z cache SQLite, parser ECO)
│   └── validate_chessable.py        # Walidator kompatybilności PGN z Chessable + audyt silnika (HARD/SOFT VETO)
├── prompt.md                        # Kontrakt repertuarowy, mapa całego kursu i specyfikacja dydaktyczna
├── requirements.txt                 # Zależności Pythona
└── .env.example                     # Szablon konfiguracji zmiennych środowiskowych
```

*(Katalogi `bin/` z binarką Stockfisha, `cache/` z bazą SQLite oraz `.venv/` są wykluczone w `.gitignore`).*

---

## Główne możliwości narzędzi (`tools/`) i skilli (`skills/`)

1. **Raport 360° (`report`)** — zestawia w jednym widoku ocenę **Stockfisha 19** (`MultiPV`, `cp`, `WDL`), statystyki **Lichess Masters (2200+ OTB)**, statystyki **Lichess Online** dla wybranego przedziału rankingowego (np. `2000_2500` lub `club`) oraz ocenę z chmury (`Cloud Eval`).
2. **Weryfikacja ruchu kandydata (`engine --check`)** — oblicza dokładną stratę w centypionach (`cp loss`) naszego ruchu względem najlepszego wyboru silnika oraz wskazuje ewentualną refutację.
3. **Audyt pokrycia repertuaru (`coverage`)** — skanuje plik `.pgn` w poszukiwaniu luk i raportuje wszystkie odpowiedzi przeciwnika przekraczające zadany próg popularności (`--min-pct`) w bazie online lub mistrzowskiej.
4. **Walidator Chessable PGN (`validate_chessable.py`)** — weryfikuje:
   - zero błędów parsera PGN oraz 100% legalności ruchów w liniach głównych i podwariantach RAV `( ... )`,
   - poprawność wszystkich strzałek `[%cal]` (czy pole startowe każdej strzałki jest zajęte przez bierkę w danej pozycji),
   - zgodność z restrykcjami edytora Chessable (brak surowych znaków nowej linii wewnątrz komentarzy, brak znaków `()[]{}`, brak niedozwolonych tagów HTML, brak zapisu roszady przez zera `0-0`),
   - opcjonalny test silnika (`--engine-check`) z progami **HARD VETO** (`>70 cp` straty) oraz **SOFT VETO** (`35–70 cp`).
5. **Renderowanie diagramów SVG (`render-svg`)** — generuje podgląd szachownicy ze strzałkami `[%cal]` i podświetleniami `[%csl]`.
6. **Skille (`skills/`)**:
   - `chess-analysis-architect` — dwubramkowy proces tworzenia rozdziałów repertuarowych z udziałem niezależnych subagentów (Agent 1: Weryfikator silnika i baz, Agent 2: Krytyk strategiczny, Agent 3A: Audytor techniczny/wizualny, Agent 3B: Trener i weryfikator prawdy szachowej w komentarzach).
   - `chessable-pgn` — przetestowane reguły formatowania PGN pod importer Chessable (klikalne podwarianty RAV z przeplataniem tekstu *Inline Interleaving*, nagłówki `━━━`, punktory `•`, kod kolorów strzałek `G/B/R/Y`).

---

## Instalacja i konfiguracja

### 1. Środowisko Python
```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### 2. Silnik Stockfish
Umieść plik wykonywalny Stockfisha w katalogu `bin/stockfish/` (domyślnie skrypt szuka `bin/stockfish/**/stockfish*.exe`) lub wskaż własną ścieżkę w pliku `.env` poprzez `STOCKFISH_PATH`.

### 3. Token Lichess API (dla bazy Online / Amateur)
- **Stockfish**, **Masters DB**, **Cloud Eval**, **Syzygy Tablebase** oraz **Offline ECO** działają bez tokenu.
- **Lichess Online DB** (`/lichess`) wymaga darmowego tokenu Personal Access Token (bez żadnych uprawnień / zero scopes):
  1. Wygeneruj token na: https://lichess.org/account/oauth/token
  2. Skopiuj `.env.example` do `.env` i uzupełnij zmienną:
     ```ini
     LICHESS_API_TOKEN=lip_twoj_token
     ```

---

## Przykłady użycia CLI

```powershell
# Pełny raport 360° (Stockfish + Masters + Online 2000-2500 side-by-side)
.\.venv\Scripts\python.exe tools\analyze.py report --moves "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5" --tier 2000_2500

# Analiza lokalnym Stockfishem 19 + sprawdzenie konkretnego ruchu kandydata
.\.venv\Scripts\python.exe tools\analyze.py engine --moves "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6" --check "Ba4" --depth 22

# Statystyki z bazy Masters (np. tylko partie od 2015 roku)
.\.venv\Scripts\python.exe tools\analyze.py masters --moves "1. d4 Nf6 2. c4 e6 3. Nf3 d5" --since 2015

# Statystyki z bazy Online (przedział 2000-2500 lub club 1600-1800)
.\.venv\Scripts\python.exe tools\analyze.py online --moves "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 7. Be3" --tier 2000_2500

# Lichess Cloud Eval oraz 7-bierkowe tablice Syzygy
.\.venv\Scripts\python.exe tools\analyze.py cloud --moves "1. d4 d5 2. c4 c6"
.\.venv\Scripts\python.exe tools\analyze.py tablebase --fen "8/8/8/8/8/3k4/3P4/3K4 w - - 0 1"

# Pobranie zweryfikowanego zapisu PGN partii modelowej z bazy Masters po ID
.\.venv\Scripts\python.exe tools\analyze.py master-game 87iVR0xv

# Audyt pokrycia repertuaru PGN względem bazy Online
.\.venv\Scripts\python.exe tools\analyze.py coverage repertoire\ch01_qgd\ch01_klasyczny_qgd_chessable.pgn --side white --db online --tier 2000_2500 --min-pct 5

# Walidacja PGN pod Chessable (+ opcjonalny audyt Stockfishem)
.\.venv\Scripts\python.exe tools\validate_chessable.py repertoire\ch01_qgd\ch01_klasyczny_qgd_chessable.pgn
.\.venv\Scripts\python.exe tools\validate_chessable.py repertoire\ch04_kid\ch04_kid_gligoric_chessable.pgn --engine-check --depth 18 --side white
```
