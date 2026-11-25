# Kontrakt Repertuarowy i Profil Gracza (Białe 1. d4 + Czarne)

> **Przeznaczenie pliku:** Jedno źródło prawdy (*single source of truth*) dla pipeline’u budującego i audytującego kurs oraz analizy pozycji (`analyze.py audit-tree`, `chess-critic`, `validate_chessable.py`, `chess-coach-verifier`). Wszystkie decyzje muszą być oceniane przez pryzmat poniższego profilu, celów i twardych ograniczeń.

---

## 0. Kontekst, profil gracza i wymagania jakościowe

### A. Kim jestem, jaki mam poziom i w co celuję
- **Poziom bieżący:** ok. **2100–2200 Elo Rapid** online (Chess.com), szacowana realna siła turniejowa OTB ok. **1800–2000 FIDE**.
- **Docelowy przedział bazy Online (Lichess Explorer):** **`2000–2200` blitz**, **`2200–2500` rapid**, lub ogólnie **`2000–2500`** (`--ratings 2000,2200,2500 --speeds blitz,rapid,classical` / `--tier 2000_2500`), używany obok `/masters` jako główne kryterium doboru linii i bocznych odchyłek, z którymi faktycznie spotykam się w partiach.
- **Cel sportowy:** stabilny rozwój w partiach klasycznych OTB i dojście do poziomu **2200+ FIDE (tytuł FM)**.
- **Praktyka:** regularne partie szybkie (15+10) oraz klasyczne OTB (m.in. sekcja szachowa i turnieje). Repertuar musi wygrywać z ludźmi w przedziale **1800–2200 FIDE**, a jednocześnie pozostawać obiektywnie zdrowy na poziomie 2200–2300+ (bez tanich pułapek, które sypią się po jednym ruchu silnego rywala).
- **Budżet czasu:** ok. **8–12 godzin tygodniowo** na całe szachy (przy intensywnych studiach i projektach technicznych). Debiuty **nie mogą** przekroczyć **20–25% tygodniowego budżetu**, bo ok. 90% błędów pada w grze środkowej i końcówkach.

### B. Mocne strony i wąskie gardła (kluczowe dla Agenta 2 — Krytyka)
- **Mocna strona:** bardzo dobra wiedza debiutowa i rozumienie struktur, analityczne podejście od pierwszych zasad (*first principles*).
- **Dwa główne wąskie gardła, które repertuar ma świadomie trenować:**
  1. **Formułowanie planów w złożonych grach środkowych z przewagą przestrzeni bez oczywistych, natychmiastowych celów ataku** — dlatego wybieram pryncypialne, klasyczne struktury z przewagą przestrzeni (`1. d4`, Klasyczny QG, Rubinstein, Petrosjan, Grünfeld `8. Bb5+`), a **nie** pasywne czy wyłącznie kontratakujące systemy (np. nie chcę Obrony Francuskiej). Chcę grać pozycje, w których obecnie jestem słabszy, żeby właśnie w nich rosnąć.
  2. **Szybkość i ostrość kalkulacji na prostszych motywach taktycznych** — dlatego repertuar musi mieć wyraźną przeciwwagę dynamiczną i taktyczną (Półsłowiańska Meran + Cambridge Springs, Klasyczna Sycylijska, `7. Bf4` w Benoni, `3. e4` w QGA, agresywny London `h3-g4` / `h4-h5` na Holenderską), a nie usypiać gry systemami „na autopilota”.

### C. Styl pisania, preferencje dydaktyczne i oczekiwania (kluczowe dla Modela Głównego i `chess-coach-verifier`)
- **Zasada „obfitość idei zamiast pustego tekstu”:** preferuję styl gęsty merytorycznie w duchu kursów **Kacpra Plichty** oraz mojego własnego studium Klasycznej Sycylijskiej — naturalny, konwersacyjny głos sparingpartnera, bez sztywnej akademickiej gadki. Tniemy bezlitośnie *szerokość drzewa SRS* (nie wrzucamy śmieciowych gałęzi), ale **maksymalizujemy gęstość idei na kluczowych rozwidleniach ORAZ na końcu linii**, budując wielokrotnego użytku „zestaw schematów” (*box of setups*) i stałe motywy taktyczne. W uzasadnionych miejscach dodajemy krótką 1-zdaniową wzmiankę o grywalnych opcjach praktycznych pod blitz/klub.
- **Krótki Wstęp do rozdziału (1 gra Informational):** każdy rozdział otwieramy 1 krótkim wpisem wstępnym (*„Dlaczego ten debiut?”*, ~5–8 ruchów): dlaczego wybieramy tę broń, 2–3 główne struktury docelowe oraz najważniejsze reguły kolejności posunięć (na Chessable oznaczamy jako **Informational**).
- **Partie wzorcowe (Model Games — 3–5 na rozdział, bez komentarzy):** moją główną inspiracją i kręgosłupem są partie **Anatolija Karpowa** (profilaktyka, duszenie kontrgry, wiszące piony, struktury QGD, Wymienny Grünfeld, KID/Benoni), uzupełnione nowoczesnymi wzorcami 2650+ z `/masters`. Włączamy **3–5 zweryfikowanych partii z `/masters` w stanie surowym (bez komentarza ruch po ruchu, wyłącznie 1-liniowy tytuł motywu)** — na Chessable oznaczane jako **Informational**, do samodzielnej analizy.
- **Styl przyjaznego przewodnika po debiucie:** pisz przystępnym tonem dobrego przewodnika pokazującego idee, motywy i plany — nigdy nie sklejaj tekstu w jedną ścianę z robotycznymi etykietami typu *„Warstwa 1 ... Warstwa 2 ...”*. Każdy punkt i akapit rozdzielaj osobnym akapitem (`<br><br>`) lub punktorem (`• ...<br><br>`).
- **Proporcjonalność wyjaśnień:** jeśli odrzucona opcja jest w oczywisty sposób zła, wystarczy krótkie 1–2 zdaniowe wyjaśnienie i krótki klikalny wariant RAV. Długie analizy rezerwujemy na prawdziwe rozwidlenia strategiczne. Nie powielamy też pustych komentarzy do rutynowych ruchów znanych z wcześniejszych gałęzi.
- **Obowiązkowe komentarze przy wymianach i zmianie natury pozycji:** przy każdej wymianie bierek lub pionów wyjaśnij krótko, czy jest dla nas korzystna, dlaczego idziemy w nią teraz i dlaczego bijemy akurat tą bierką; zawsze gdy pozycja się otwiera, zamyka lub zmienia strukturę pionową, podaj zwięzły plan dostosowany do nowej natury gry.
- **Logiczna całość od góry do dołu:** każde wyjaśnienie musi budować ścisły ciąg przyczynowo-skutkowy bez przeskoków myślowych i pustych sloganów typu *„białe stoją nieco lepiej”*. Na kluczowych rozwidleniach (jako wewnętrzna checklista autora, rozłożona czytelnie w osobnych akapitach lub punktorach, bez etykiet „Warstwa 1–4”) uwzględniamy:
  1. **Refutację odruchu ludzkiego** — dlaczego NIE gramy najbardziej oczywistego ruchu z autopilota?
  2. **Diagnozę ustępstwa rywala** — co dokładnie oddał przeciwnik (pole, tempo, strukturę, parę gońców)?
  3. **Mapę adresów pionów i figur** — konkretne trasy na kolejne 3–5 ruchów.
  4. **Profilaktykę i dynamikę ludzką** — czego chce rywal i czym to gasimy w zarodku.
- **Czysty Plan Końcowy + Przykładowe Kontynuacje (`━━━ PLAN FROM HERE ━━━` + `━━━ SAMPLE CONTINUATIONS ━━━`):** na ostatnim ruchu każdej linii treningowej dajemy zwięzły, przejrzysty blok (zamiast ciężkiego wieloakapitowego eseju):
  - `Verdict:` szczera ocena i nazwa struktury
  - `• Our Plan —` strzałki `[G]`/`[B]`: główne przełomy i trasy figur
  - `• Watch Out —` strzałki `[R]`: kontrgra rywala, pułapki taktyczne i profilaktyka
  - `• Key Trades & Endgame —` co wymieniamy, co zostawiamy i do jakiej końcówki dążymy
  - Pod spodem obowiązkowa sekcja **`━━━ SAMPLE CONTINUATIONS ━━━`** z 1–3 klikalnymi wariantami RAV pokazującymi, jak partia naturalnie toczy się dalej (w tym najczęstsze odpowiedzi ludzkie oraz ewentualne uderzenia taktyczne).
- **Bezkompromisowa szczerość audytorska:** zero lukrowania i bezkrytycznego przytakiwania. Jeśli wariant ma w Stockfishu `0.00` albo `-0.30` w zamian za praktyczną presję, ma to być nazwane wprost (z podaniem oceny, `WDL` i wyników z bazy). Nigdy nie sprzedawać równej pozycji jako „łatwej wygranej”.

### D. Budżet linii SRS, progi pokrycia i standard techniczny PGN (Chessable)
- **Budżet linii treningowych:** ok. **100 linii treningowych na kolor (~200 łącznie: ~95–105 Białymi + ~95–105 Czarnymi)**.
  - **Głębokość docelowa:** ok. **11 posunięć**, twardy limit **15 posunięć** (przekraczamy tylko w niezakończonych wymuszonych taktykach).
  - **Próg zasięgu i cięcie gałęzi:** osobną linię treningową zakładamy przy **`>= 2.0%` skumulowanego zasięgu** od punktu startowego rozdziału. Jeśli dalsza odpowiedź ma **`~85–90%+` grywalności** (jest praktycznie wymuszona) i **nie kryje uderzeń taktycznych**, kończymy linię czysto wcześniej zamiast doklejać puste ruchy. Jeśli jednak nawet przy niższym zasięgu albo na końcu linii pojawia się **uderzenie taktyczne / typowa pułapka klubowa**, wydłużamy linię (do 15. ruchu) albo dopinamy oznaczony klikalny RAV w tym punkcie.
- **Język:** domyślnie zgodny z poleceniem użytkownika (dla nowych kursów możliwy angielski lub polski); notacja szachowa zawsze w standardowym angielskim SAN (`Nf3`, `Bxc4`, `O-O`, nigdy `0-0`).
- **Format PGN pod Chessable (zgodny ze skillem `chessable-pgn`):**
  - Jedna gra PGN na jedną linię treningową; tytuł w `[White "<tytuł>"]`, puste `[Black ""]`.
  - Wszystkie konkretne warianty poboczne, refutacje i przykładowe kontynuacje jako prawdziwe podwarianty RAV `( ... )` z opisem w `{ ... }` (import z **ODZNACZONYM** *"Import all sub-variations as their own item"*).
  - Odstępy wyłącznie przez `<br>`, `<br><br>` (akapity) i `<br><br><br>━━━ NAGŁÓWEK ━━━<br><br>` (sekcje).
  - Listy wyłącznie jako `• Etykieta — opis.<br><br>`.
  - Zakaz surowych enterów `\n`, znaków `( ) [ ] { }` w prozie oraz tagów wycinanych przez Chessable (`<b>`, `<i>`, `<ul>`, `<li>`, `<p>`, Markdown, BBCode).
  - Strzałki i podświetlenia w osobnym bloku `{ [%csl ...] [%cal ...] }` tuż po komentarzu prozą, według stałego kodu kolorów:
    - `G` (zielone) — piony, przełomy pionowe, punkty struktury
    - `B` (niebieskie) — figury, trasy manewrowe, aktywne linie i przekątne
    - `R` (czerwone) — groźby przeciwnika, profilaktyka, cele ataku
    - `Y` (żółte) — punkty zwrotne, pułapki kolejności posunięć, niuanse taktyczne

---

## 1. Mapa całościowa repertuaru

```text
REPERTUAR KOMPLETNY (~200 linii SRS: ~100 na kolor + Wstępy i Model Games jako Informational)
│
├── BIAŁE (1. d4 + 2. c4) — ok. 95–105 linii SRS
│   ├── Ch0: Fundamenty (Informational: Mapa Struktur, Partie Wzorcowe)
│   ├── Ch1: QGD (2... e6 / 3. Nc3 d5)     ──► Klasyczny QG (4. Bg5, 5. e3, 6. Nf3)        [~18–20 linii]
│   ├── Ch2: Nimzowitsch (3. Nc3 Bb4)      ──► Rubinstein (4. e3, 5. Bd3, 6. Nf3)          [~16–18 linii]
│   ├── Ch3: Słowiańska (2... c6)          ──► 3. Nf3 Nf6 4. Qc2 + g3 (jedyne główne g3)   [~12–14 linii]
│   ├── Ch4: KID (2... g6 3. Nc3 Bg7)      ──► Petrosjan (7. d5)                           [~12–14 linii]
│   ├── Ch5: Grünfeld (2... g6 3. Nc3 d5)  ──► Wymienny z 8. Bb5+                          [~10–12 linii]
│   ├── Ch6: Benoni & Benkö (2... c5)      ──► Benoni (7. Bf4) | Benkö (5. e3)                [~10–12 linii]
│   ├── Ch7: QGA (2... dxc4)               ──► Centralne 3. e4                             [~7–8 linii]
│   └── Ch8: Holenderska (1... f5) & inne  ──► Agresywny London (2. Bf4 + 3. e3)           [~8–10 linii]
│
└── CZARNE — ok. 95–105 linii SRS
    ├── vs 1. e4          ──► Klasyczna Sycylijska (rdzeń Scheveningen ...e6) + Anty-Syc.  [~38–42 linii]
    ├── vs 1. d4          ──► Półsłowiańska bramą słowiańską (2... c6, unifikacja 5... Nbd7)[~38–42 linii]
    └── vs 1. Nf3 / 1. c4 / flankowe ──► Kompleks Słowiański (1. Nf3 d5 | 1. c4 c6)        [~16–20 linii]
```

---

## 2. Repertuar białymi (`1. d4`)

> **Zasada generowania:** Poniżej zdefiniowane są wyłącznie rozdziały i bazowe systemy startowe. Konkretne linie główne, odgałęzienia (`>= 2.0%` zasięgu), warianty poboczne RAV oraz wybory między równorzędnymi opcjami GM dobiera pipeline na podstawie analizy Stockfisha 19, bazy Online (`2000–2500`), `/masters` i karty Crossroads (Faza 1A.5).

- **Ch0:** Fundamenty (Informational: Mapa Struktur, Partie Wzorcowe)
- **Ch1:** Klasyczny Gambit Hetmański — QGD (`1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5`, w tym wczesne odchyłki przeciw `1. d4 d5 2. c4 e6` / `2... Nc6` / `2... e5`)
- **Ch2:** Obrona Nimzowitscha — System Rubinsteina (`1. d4 Nf6 2. c4 e6 3. Nc3 Bb4 4. e3`)
- **Ch3:** Obrona Słowiańska i Półsłowiańska (`1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Qc2` + `g3`)
- **Ch4:** Obrona Królewsko-Indyjska — System Petrosjana (`1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 7. d5`)
- **Ch5:** Obrona Grünfelda — Wymienny z `8. Bb5+` (`1. d4 Nf6 2. c4 g6 3. Nc3 d5 4. cxd5 Nxd5 5. e4 Nxc3 6. bxc3 Bg7 7. Nf3 c5 8. Bb5+`)
- **Ch6:** Nowoczesne Benoni (`7. Bf4`) i Gambit Benkö (`5. e3`)
- **Ch7:** Przyjęty Gambit Hetmański — QGA (`1. d4 d5 2. c4 dxc4 3. e4`)
- **Ch8:** Obrona Holenderska (`1. d4 f5 2. Bf4` + `3. e3!`) oraz rzadkie otwarcia turniejowe przeciw `1. d4` (Budapeszt, Stara Indyjska, Tango, Englund, Owen)

---

## 3. Repertuar czarnymi

> **Zasada generowania:** Rozdziały określają wyłącznie wybrane kompleksy otwarciowe. Szczegółowe warianty i odpowiedzi na poszczególne odchylenia białych wyprowadza pipeline z analizy silnika i baz.

- **vs `1. e4` (główna):** Klasyczna Sycylijska — rdzeń Scheveningen (`1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 Nc6`, ...`e6`)
- **vs `1. e4` (Anty-Sycylijskie):** Alapin (`2. c3 Nf6`, preferencja: linie z `...g6`), Moskwa (`3. Bb5+`), Zamknięta / Grand Prix oraz wczesne boczne (`2. Nc3`, `2. f4`, Morra, `2. b3`, `2. d4`)
- **vs `1. d4`:** Półsłowiańska bramą słowiańską (`1. d4 d5 2. c4 c6`, unifikacja `5... Nbd7`), Słowiańska Wymienna/Wolna oraz System Londyński
- **vs `1. Nf3` / `1. c4` / flankowe:** Kompleks Słowiański (`1. Nf3 d5` | `1. c4 c6`, w tym Atak Panowa oraz `1. b3`, `1. g3`, `1. f4`)

---

## 4. Zakazane transpozycje i twarde reguły (dla `audit-tree` i `chess-critic`)

1. **Białe QGD:** nigdy `4. Nf3` przed `4. Bg5` (nie wpuszczamy Wiedeńskiego, klasycznego Ragozina ani Botwinnika); na `4... c6` obowiązkowy bezpiecznik `5. e3!`.
2. **Białe Holenderska:** nigdy `Nf3` przed `e3` (zachowujemy otwartą przekątną `d1-h5` i pole `f3` pod manewr `Qf3-g3`).
3. **Białe Benoni:** na `7. Bf4 a6` obowiązkowe `8. a4` (nie oddajemy darmowego `...b5`), na `7. Bf4 Bg7` konkretne `8. Qa4+ Bd7 9. Qb3`.
4. **Czarne vs `1. c4` / `1. Nf3`:** zakaz kolejności z KID (`1... Nf6`, `2... g6`, `3... Bg7`), która pozwala białym transponować w głównego KID i rozbija jednolitość Półsłowiańskiej.
5. **Czarne Półsłowiańska:** nie rozbudowywać w stronę Botwinnika (`5. Bg5 dxc4 6. e4 b5`) ani Anty-Moskwy (`5. Bg5 h6 6. Bh4 dxc4`) — utrzymujemy unifikację `5... Nbd7`.
6. **Świadome dawkowanie `g3` (cel: wszechstronność, nie niechęć):** Lubię struktury z `g3` i dobrze się w nich czuję, ale celowo ograniczam główne gałęzie z fianchettem do Słowiańskiej (`4. Qc2 + g3`) oraz Tarrascha (`6. g3`), żeby rozwijać uniwersalność w klasycznych strukturach centralnych (`e3`/`Bd3`/`Bg5`). Nie zamieniać całego repertuaru w Katalońską na wszystko, natomiast punktowe, obiektywnie najlepsze warianty z `g3` w konkretnych odchyłkach są jak najbardziej akceptowalne.