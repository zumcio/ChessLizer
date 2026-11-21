# Kontrakt Repertuarowy i Profil Gracza (Białe 1. d4 + Czarne)

> **Przeznaczenie pliku:** Jedno źródło prawdy (*single source of truth*) dla agentów budujących i audytujących kurs oraz analizy pozycji. Wszystkie decyzje Agenta 1 (Weryfikatora), Agenta 2 (Krytyka) i Agenta 3 (Audytora Narracji) muszą być oceniane przez pryzmat poniższego profilu, celów i twardych ograniczeń.

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
  1. **Formułowanie planów w złożonych grach środkowych z przewagą przestrzeni bez oczywistych, natychmiastowych celów ataku** — dlatego wybieram pryncypialne, klasyczne struktury z przewagą przestrzeni (`1. d4`, Klasyczny QG, Rubinstein, Gligorić, Grünfeld `8. h3`), a **nie** pasywne czy wyłącznie kontratakujące systemy (np. nie chcę Obrony Francuskiej). Chcę grać pozycje, w których obecnie jestem słabszy, żeby właśnie w nich rosnąć.
  2. **Szybkość i ostrość kalkulacji na prostszych motywach taktycznych** — dlatego repertuar musi mieć wyraźną przeciwwagę dynamiczną i taktyczną (Półsłowiańska Meran + Cambridge Springs, Klasyczna Sycylijska, `7. Bf4` w Benoni, `3. e4` w QGA, agresywny London `h3-g4` / `h4-h5` na Holenderską), a nie usypiać gry systemami „na autopilota”.

### C. Styl pisania, preferencje dydaktyczne i oczekiwania (kluczowe dla Modela Głównego i Agenta 3)
- **Zasada „za dużo idei zamiast za mało”:** preferuję styl gęsty merytorycznie w duchu kursów **Kacpra Plichty** na Chessable. Tniemy bezlitośnie *szerokość drzewa SRS* (nie wrzucamy śmieciowych gałęzi), ale **maksymalizujemy gęstość wyjaśnień strategicznych w prozie**.
- **Partie wzorcowe (Model Games):** moją główną inspiracją i kręgosłupem partii referencyjnych są partie **Anatolija Karpowa** (profilaktyka, duszenie kontrgry, wiszące piony, struktury QGD, Wymienny Grünfeld, KID/Benoni). Wszędzie tam, gdzie Karpow ma klasyk pod daną strukturę, wybieramy go w pierwszej kolejności; w nowoczesnych niuansach uzupełniamy współczesnymi wzorcami z `/masters`.
- **Styl przyjaznego przewodnika po debiucie:** pisz przystępnym tonem dobrego przewodnika pokazującego idee, motywy i plany — nigdy nie sklejaj tekstu w jedną ścianę z robotycznymi etykietami typu *„Warstwa 1 ... Warstwa 2 ...”*. Każdy punkt i akapit rozdzielaj osobnym akapitem (`<br><br>`) lub punktorem (`• ...<br><br>`).
- **Proporcjonalność wyjaśnień:** jeśli odrzucona opcja jest w oczywisty sposób zła, wystarczy krótkie 1–2 zdaniowe wyjaśnienie i krótki klikalny wariant RAV. Długie analizy rezerwujemy na prawdziwe rozwidlenia strategiczne.
- **Obowiązkowe komentarze przy wymianach i zmianie natury pozycji:** przy każdej wymianie bierek lub pionów wyjaśnij krótko, czy jest dla nas korzystna, dlaczego idziemy w nią teraz i dlaczego bijemy akurat tą bierką; zawsze gdy pozycja się otwiera, zamyka lub zmienia strukturę pionową, podaj zwięzły plan dostosowany do nowej natury gry.
- **Logiczna całość od góry do dołu:** każde wyjaśnienie musi budować ścisły ciąg przyczynowo-skutkowy bez przeskoków myślowych i pustych sloganów typu *„białe stoją nieco lepiej”*. Na kluczowych ruchach (jako wewnętrzna checklista autora, rozłożona czytelnie w osobnych akapitach lub punktorach, bez etykiet „Warstwa 1–4”) uwzględniamy:
  1. **Refutację odruchu ludzkiego** — dlaczego NIE gramy najbardziej oczywistego ruchu z autopilota?
  2. **Diagnozę ustępstwa rywala** — co dokładnie oddał przeciwnik (pole, tempo, strukturę, parę gońców)?
  3. **Mapę adresów pionów i figur** — konkretne trasy na kolejne 3–5 ruchów.
  4. **Profilaktykę i dynamikę ludzką** — czego chce rywal i czym to gasimy w zarodku.
- **Rozbudowana „Brama do gry środkowej”:** na ostatnim ruchu każdej linii treningowej obowiązkowy 5-punktowy przewodnik: (1) Diagnoza pozycji, (2) Mapa pionów `[G]`, (3) Mapa figur `[B]`, (4) Kontrgra czarnych `[R]`, (5) Wymiany i końcówka.
- **Bezkompromisowa szczerość audytorska:** zero lukrowania i bezkrytycznego przytakiwania. Jeśli wariant ma w Stockfishu `0.00` albo `-0.30` w zamian za praktyczną presję, ma to być nazwane wprost (z podaniem oceny, `WDL` i wyników z bazy). Nigdy nie sprzedawać równej pozycji jako „łatwej wygranej”.

### D. Budżet linii SRS i standard techniczny PGN (Chessable)
- **Budżet linii treningowych:** łącznie **~350–450 linii SRS** na cały repertuar (~215–230 białymi + ~140–220 czarnymi). Głębokość bazowa: **8–12 posunięć** (do 14 wyłącznie w wymuszonych wariantach taktycznych). Rozbudowa reaktywna dopiero po własnych partiach.
- **Język:** cały tekst, komentarze i tytuły **po polsku**, notacja szachowa w standardowym angielskim SAN (`Nf3`, `Bxc4`, `O-O`, nigdy `0-0`).
- **Format PGN pod Chessable (zgodny ze skillem `chessable-pgn`):**
  - Jedna gra PGN na jedną linię treningową; tytuł w `[White "<tytuł>"]`, puste `[Black ""]`.
  - Wszystkie konkretne warianty poboczne i refutacje jako prawdziwe podwarianty RAV `( ... )` z opisem w `{ ... }` po ostatnim ruchu podwariantu (import z **ODZNACZONYM** *"Import all sub-variations as their own item"*).
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
REPERTUAR KOMPLETNY
│
├── BIAŁE (1. d4 + 2. c4) — ok. 215–230 linii SRS
│   ├── Ch0: Fundamenty (0A Wstęp, 0B Mapa 9 Struktur, 0C Partie Wzorcowe — Informational)
│   ├── Ch1: QGD (2... e6 / 3. Nc3 d5)     ──► Klasyczny QG (4. Bg5, 5. e3, 6. Nf3)        [~40 linii]
│   ├── Ch2: Nimzowitsch (3. Nc3 Bb4)      ──► Rubinstein (4. e3, 5. Bd3, 6. Nf3)          [~38 linii]
│   ├── Ch3: Słowiańska (2... c6)          ──► 3. Nf3 Nf6 4. Qc2 + g3 (jedyne główne g3)   [~28 linii]
│   ├── Ch4: KID (2... g6 3. Nc3 Bg7)      ──► Gligorić (7. Be3)                           [~30 linii]
│   ├── Ch5: Grünfeld (2... g6 3. Nc3 d5)  ──► Wymienny z 8. h3                            [~22 linie]
│   ├── Ch6: Benoni & Benkö (2... c5)      ──► Benoni 7. Bf4 (Qa4+-Qb3 / a4) | Benkö 5. e3 [~24 linie]
│   ├── Ch7: QGA (2... dxc4)               ──► Centralne 3. e4                             [~16 linii]
│   ├── Ch8: Holenderska (1... f5) & inne  ──► Agresywny London (2. Bf4, e3, h3-g4 / h4-h5)[~22 linie]
│   └── Ch9: Quizy przeplatane (Interleaving — podchwytliwe rozwidlenia kolejności)        [~15 pozycji]
│
└── CZARNE — ok. 140–220 linii SRS
    ├── vs 1. e4          ──► Klasyczna Sycylijska (rdzeń Scheveningen ...e6)
    │                         └── Anty: Alapin 2... Nf6 (preferencja: linie z ...g6) | Moskwa 3... Bd7 | Zamk./GP ...g6 + ...Nge7 + ...d5
    ├── vs 1. d4          ──► Półsłowiańska bramą słowiańską (2... c6, unifikacja 5... Nbd7)
    │                         ├── vs 5. e3  ──► Meran (6... dxc4 7. Bxc4 b5 8. Bd3 Bb7) | Anty-Meran 6. Qc2 Bd6
    │                         ├── vs 5. Bg5 ──► Cambridge Springs (6... Qa5!) | 6. cxd5 exd5 (Karlsbad)
    │                         └── vs London ──► Aktywne ...c5, ...cxd4, ...Nc6
    ├── vs 1. Nf3 / 1. c4 ──► Kompleks Słowiański (1. Nf3 d5 | 1. c4 c6)
    │                         └── vs Panow (2. e4 d5) ──► Prosty schemat 5... e6 6. Nf3 Be7
    └── vs 1. b3/g3/f4    ──► 1. b3 / 1. g3: szkielet Réti | 1. f4 (Bird): ...d5, ...Nf6, ...c5, ...Nc6, ...e6
```

---

## 2. Repertuar białymi (`1. d4`)

### Ch1: Klasyczny Gambit Hetmański (`1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5`)
Zawsze zachowujemy kolejność `3. Nc3` -> `4. Bg5` -> `5. e3` przed `Nf3`.

- **Ortodoksyjna (`4... Be7 5. e3 O-O 6. Nf3 Nbd7 7. Rc1`):**
  - Główna z `7... c6 8. Bd3 dxc4 9. Bxc4 Nd5 10. Bxe7 Qxe7 11. O-O Nxc3 12. Rxc3 e5 13. Bb3!` (plan Karpowa: nacisk w centrum, `Re1`, `Ne5` po `...exd4` lub `Nd2` + `f3` po `...e4`).
  - Ekspansja z `8... h6 9. Bh4 dxc4 10. Bxc4 b5 11. Bd3 a6 12. O-O c5 13. Ne4!` (nacisk na `c5` i `f6`, na `...c4` odejście `Bb1` + bateria `Qc2`).
  - Wczesne `7... b6` bez `...h6`: `8. cxd5! exd5 9. Bd3 Bb7 10. O-O c5 11. Qe2!` (pułapka `8... Nxd5?? 9. Nxd5 exd5 10. Bxe7 Qxe7 11. Rxc7`; potem `Ba6` przeciw gońcowi `b7`).
- **Tartakower (`4... Be7 5. e3 O-O 6. Nf3 h6 7. Bh4 b6`):**
  - Główny klasyk Karpowa: `8. cxd5 Nxd5 9. Bxe7 Qxe7 10. Nxd5 exd5 11. Rc1 Be6 12. Qa4! c5 13. Qa3! Rc8 14. Bb5!` (oblężenie wiszących pionów `c5/d5`).
  - Odbicie `8... exd5`: `9. Bd3 Bb7 10. O-O Nbd7 11. Qe2 c5 12. Ba6!` (wymiana aktywnego gońca `b7`).
- **Lasker (`4... Be7 5. e3 O-O 6. Nf3 h6 7. Bh4 Ne4`):**
  - Główna: `8. Bxe7 Qxe7 9. cxd5! Nxc3 10. bxc3 exd5 11. Qb3! Qd6 12. c4!` (taran w centrum, likwidacja zdwojonego piona).
  - Pasywne `11... c6`: `12. c4 Be6 13. c5!` (klin na skrzydle hetmańskim, presja po linii `b` i `c` na `c6/b7`).
- **Cambridge Springs (`4... Nbd7 5. e3 c6 6. Nf3 Qa5`):**
  - `7. cxd5! Nxd5 8. Qd2! Bb4 9. Rc1! h6 10. Bh4 O-O 11. Bd3!` (pułapka `9... Qxa2?? 10. Nxa2 Bxd2+ 11. Kxd2`).
- **Opóźniony Ragozin (`4... Nbd7 5. e3 c6 6. Nf3 Bb4`):**
  - `7. cxd5 exd5 8. Bd3 Qa5 9. Qc2! O-O 10. O-O!` (plan: `a3` -> `Bxc3 bxc3` + `c4` z parą gońców).
- **Bezpiecznik kolejnościowy vs Półsłowiańska (`4... c6`):**
  - **`5. e3!`** (nigdy `5. Nf3?` wpuszczające Botwinnika) -> transpozycja do Ortodoksyjnej (`5... Nbd7 6. Nf3 Be7 7. Rc1 O-O 8. Bd3`) lub Cambridge Springs.
- **Wczesne `4... Bb4` (Pseudo-Ragozin):**
  - `5. cxd5! exd5 6. e3 h6 7. Bh4 O-O 8. Bd3 c6 9. Nge2!` (kontrolowany Karlsbad z centralnym taranem `f3` + `e4`).
- **Obrona Tarrascha (`3... c5`):**
  - `4. cxd5 exd5 5. Nf3 Nc6 6. g3!` (chirurgiczne fianchetto przeciw IQP `d5`: `Bg2`, `O-O`, `Bg5`, `Be3`, `Rc1`, `Na4-c5`).
- **Obrona Czigorina (`2... Nc6`):**
  - `3. Nf3 Bg4 4. cxd5 Bxf3 5. gxf3 Qxd5 6. e3 e5 7. Nc3 Bb4 8. Bd2 Bxc3 9. bxc3 Nf6 10. Rb1!` (para gońców i taran `c4-d5`).
- **Kontrgambit Albina (`2... e5`):**
  - `3. dxe5 d4 4. Nf3 Nc6 5. a3!` (unikanie pułapki Laskera `4. e3?`; dalej `b4`, `Bb2`, `e3` rozbrajające klina `d4`).

### Ch2: Obrona Nimzowitscha — System Rubinsteina (`1. d4 Nf6 2. c4 e6 3. Nc3 Bb4 4. e3`)
Wspólny szkielet rozwoju: `4. e3`, `5. Bd3`, `6. Nf3`.

- **Główna z `4... O-O 5. Bd3 d5 6. Nf3 c5`:** struktury IQP (placówka `e5`, `Bg5`, `Re1`, `a3`, przełom `d4-d5`) oraz walka w centrum przy `...c5`.
- **Wariant Hübnera (`4... c5 5. Bd3 Nc6 6. Nf3 Bxc3+ 7. bxc3 d6 8. e4 e5 9. d5 Ne7`):**
  - **`10. Nh4!`** (przed roszadą! Odsłonięcie piona `f` pod szybkie `f4` i kontrola pola `f5` przeciw blokadzie `...h6/...g5`).
- **Wariant Fianchetto (`4... b6 5. Bd3 Bb7 6. Nf3 Ne4`):**
  - **`7. O-O!`** (dynamiczna walka o centrum z `Qc2` i `e4`).
- **Wczesne odchyłki:** `4... d5`, `4... Bxc3+`, `4... Nc6`, `4... Qe7`.

### Ch3: Obrona Słowiańska i Półsłowiańska (`1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Qc2`)
Jedyny główny kompleks z fianchettem `g3` w białym repertuarze.

- **Przyjęcie piona (`4... dxc4 5. Qxc4 Bf5`):** `6. g3` (długofalowa presja po przekątnej `h1-a8`, profilaktyka przed `...e5`).
- **Fianchetto czarnych (`4... g6`):** walka o centrum i test osłabionego punktu `b7`.
- **Półsłowiańska (`4... e6`):** `5. g3` (czyste struktury katalońskie bez wpuszczania Notebooma).
- **Wczesne odchyłki:** `3... Bf5`, `3... dxc4`, `3... e6`, `4... Bg4`.

### Ch4: Obrona Królewsko-Indyjska — System Gligoricia (`1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 7. Be3`)
- **`7... Ng4 8. Bg5`:** walka o kontrolę pola `d5` i parę gońców.
- **`7... Nc6 8. d5 Ne7 9. Nd2`:** zamknięty klin centralny — wyścig `b4` + `c4-c5` z profilaktyką `f3`/`Bf2` albo `g4` w stylu Karpowa przed roszadą.
- **`7... exd4 8. Nxd4`:** otwarty KID i stały nacisk na słabego piona `d6`.
- **Odchyłki:** `7... Na6`, `7... c6`, wczesne `6... c5`, `6... Bg4`, Obrona Pirca.

### Ch5: Obrona Grünfelda — Wymienny z `8. h3` (`1. d4 Nf6 2. c4 g6 3. Nc3 d5 4. cxd5 Nxd5 5. e4 Nxc3 6. bxc3 Bg7 7. Nf3 c5 8. h3`)
- **Główna (`8... O-O 9. Be2 Nc6 10. Be3 cxd4 11. cxd4 Qa5+`):** odejście `12. Bd2`, konsolidacja wieżą (`Rb1`/`Rc1`) zanim uruchomimy wolnego piona `d4-d5` i `O-O`.
- **Boczne po `8... O-O 9. Be2`:** `9... b6`, `9... Bg4`, `9... e6`.
- **Wczesne odchyłki:** `7... O-O`, `4... Qxd5`, `5... Nb6`, `3... c5`.

### Ch6: Nowoczesne Benoni (`7. Bf4`) i Gambit Benkö (`5. e3`)
- **Nowoczesne Benoni (`1. d4 Nf6 2. c4 c5 3. d5 e6 4. Nc3 exd5 5. cxd5 d6 6. Nf3 g6 7. Bf4`):**
  - `7... Bg7`: **`8. Qa4+! Bd7 9. Qb3`** (natychmiastowy nacisk na `b7` i `d6`).
  - `7... a6`: **`8. a4!`** (twarda profilaktyka przed `...b5`, potem `e4`, `O-O`, `Nd2-c4`).
  - `7... Be7` oraz Czeskie Benoni (`3... e5`).
- **Gambit Benkö (`1. d4 Nf6 2. c4 c5 3. d5 b5 4. cxb5 a6 5. e3`):**
  - `5... g6` (z ideą `Ra3` neutralizującą przekątną `g7` i linie `a/b`), `5... axb5`, `5... d6`.

### Ch7: Przyjęty Gambit Hetmański — QGA (`1. d4 d5 2. c4 dxc4 3. e4`)
- **`3... Nf6 4. e5 Nd5 5. Bxc4`** (przewaga przestrzeni, placówka `e5`, atak na skrzydle królewskim).
- **`3... e5 4. Nf3 exd4 5. Bxc4`** (dynamiczne prowadzenie IQP / inicjatywa rozwojowa).
- **Boczne:** `3... c5`, `3... Nc6`, `3... b5`.

### Ch8: Obrona Holenderska (`2. Bf4`) i „Śmietnik Turniejowy”
- **Obrona Holenderska (`1. d4 f5 2. Bf4 Nf6 3. e3!`):**
  - Klucz kolejnościowy: **`e3` przed `Nf3`**, żeby zostawić otwartą przekątną `d1-h5` i pole `f3` dla hetmana.
  - **Mechanizm A (vs Leningradzka `...g6`):** `h4-h5` + `Qf3-g3` (otwarcie linii `h` i przeładowanie `g6`).
  - **Mechanizm B (vs Klasyczna i Stonewall `...e6`):** `h3`, `Bd3`, `Nf3` i **`g4!`** (rozbicie podstawy `f5` i otwarcie linii `g`).
- **Śmietnik turniejowy:** Gambit Budapeszteński (`1. d4 Nf6 2. c4 e5`), Stara Indyjska (`2... d6`), Tango (`1. d4 Nf6 2. c4 Nc6`), Gambit Englunda (`1. d4 e5`), Obrona Owena (`1. d4 b6`).

---

## 3. Repertuar czarnymi

### vs `1. e4`: Klasyczna Sycylijska (`1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 Nc6`)
- **Sycylijska Otwarta:** rdzeń **Scheveningen (`...e6`)** — elastyczna struktura centralna i dynamiczna gra figurowa przeciw atakom białych.
- **Anty-Sycylijskie:**
  - **Alapin (`2. c3`):** `2... Nf6` (natychmiastowy nacisk na `e4`; preferencja gracza: lubię linie z `g3`/`...g6` przeciw Alapinowi — do uwzględnienia i doprecyzowania przy budowie rozdziału czarnymi).
  - **Moskwa (`2. Nf3 d6 3. Bb5+`):** `3... Bd7` (solidne wygaszenie presji i przejście w zdrową grę środkową).
  - **Sycylijska Zamknięta i Grand Prix:** schemat z `...g6`, `...Nge7` i szybkim przełomem `...d5`.

### vs `1. d4`: Półsłowiańska bramą słowiańską (`1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Nc3 e6`)
Unifikacja ruchem **`5... Nbd7`** na oba główne wybory białych (`5. e3` i `5. Bg5`) — maksymalna dynamika bez 20-ruchowych drzew Botwinnika i Anty-Moskwy.

- **Przeciw `5. e3 Nbd7` — Meran i Anty-Meran:**
  - Główny **Meran (`6. Bd3`):** **`6... dxc4 7. Bxc4 b5 8. Bd3 Bb7`** (ekspansja na skrzydle hetmańskim, aktywacja gońca `b7`, szybkie uderzenia `...c5` lub `...b4` — po `9. O-O a6 10. e4 c5` lub `9. e4 b4 10. Na4 c5 11. e5 Nd5`).
  - **Anty-Meran (`6. Qc2`):** **`6... Bd6`** (przygotowanie `...e5` lub spóźnionego `...dxc4` + `...b5`; na agresywne `7. g4` konkretne `7... h6` lub `7... dxc4`).
- **Przeciw `5. Bg5 Nbd7` — Cambridge Springs i Karlsbad:**
  - **Cambridge Springs (`6. e3`):** **`6... Qa5!`**
    - na `7. Nd2`: `7... Bb4 8. Qc2 O-O` (z planem `...e5`/`...c5`) lub konkretne `7... dxc4! 8. Bxf6 Nxf6 9. Nxc4 Qc7`.
    - na `7. cxd5 Nxd5 8. Qd2 Bb4 9. Rc1`: **`9... h6 10. Bh4 O-O`** (pamiętać o pułapce `9... Qxa2?? 10. Nxa2`!).
    - na `7. Bxf6 Nxf6`: para gońców i elastyczna struktura.
  - **Wymiana w 6. ruchu (`6. cxd5`):** `6... exd5 7. e3 Be7 8. Bd3 O-O` (asymetryczny Karlsbad, lustro białego QGD).
- **Boczne zjazdy białych w bramie słowiańskiej (`1. d4 d5 2. c4 c6`):**
  - **Wymienna Słowiańska (`3. cxd5 cxd5`):** aktywny rozwój `...Nc6`, `...Nf6`, `...Bf5`, `...e6`, `...Rc8`, szukanie asymetrii (`...Na5`, `...Qb6`, `...Ne4`).
  - **Wolna Słowiańska (`3. Nf3 Nf6 4. e3`):** `4... Bf5` (na `5. Nc3 e6 6. Nh4 Be4!`/`Bg6`) albo spójne `4... e6` (`...Nbd7, ...Bd6, ...O-O`).
  - **`3. Nf3 Nf6 4. Qc2`:** `4... g6` z szybkim `...Bf5` albo `4... dxc4 5. Qxc4 Bf5`.
- **Przeciw Systemowi Londyńskiemu (`2. Bf4` / `2. Nf3 Nf6 3. Bf4`):** aktywne **`...c5`**, **`...cxd4`**, **`...Nc6`**.

### vs `1. Nf3` (Réti) i `1. c4` (Angielska): Kompleks Słowiański (`1. Nf3 d5` | `1. c4 c6`)
Każda transpozycja białych ruchem `d4` wpada bezpośrednio w naszą Słowiańską / Półsłowiańską (zero kolizji z KID).

- **Przeciw Réti (`1. Nf3 d5`):**
  - `2. d4 Nf6`: transpozycja do Półsłowiańskiej (`3. c4 c6`) lub anty-Londona (`3. Bf4 c5`).
  - `2. c4 c6 3. g3 Nf6 4. Bg2`: główny schemat **`4... Bf5`** (`...e6, ...h6, ...Nbd7, ...Be7/Bd6`; na `5. cxd5 cxd5 6. Qb3` -> **`6... Qc8!`**); ostrzejsza opcja `4... dxc4 5. O-O Nbd7 6. Na3 Nb6`.
  - `2. c4 c6 3. b3 Nf6 4. Bb2`: `4... Bf5` lub aktywne `4... Bg4` (`...e6, ...Nbd7, ...Bd6, ...e5`).
  - `2. c4 c6 3. e3 Nf6 4. Nc3 e6`: struktury Półsłowiańskiej (`5. b3 Nbd7 6. Bb2 Bd6`).
  - Atak Królewsko-Indyjski (`2. g3 Nf6 3. Bg2 c6 4. O-O`): `4... Bf5` lub `4... Bg4`.
- **Przeciw Partii Angielskiej (`1. c4 c6`):**
  - Transpozycje (`2. d4 d5`, `2. Nf3 d5`, `2. Nc3 d5 3. d4/3. e3`): powrót do linii wyżej.
  - Wczesne `2. Nc3 d5 3. e4`: dynamiczne **`3... d4 4. Nce2 e5`**.
  - **Atak Panowa (`2. e4 d5 3. exd5 cxd5 4. d4 Nf6 5. Nc3`):** prosty, solidny system **`5... e6 6. Nf3 Be7`** (wycina ostre warianty z `5... Nc6` i sprowadza grę do podręcznikowej blokady IQP):
    - na `7. cxd5 Nxd5 8. Bd3 Nc6 9. O-O O-O`: blokada `d5` (`...b6`, `...Bb7`, `...Bf6`/`...Nf6`, wieże `c8` i `d8`).
    - na `7. Bd3`: czekamy na gońca i dopiero bijemy **`7... dxc4 8. Bxc4 O-O 9. O-O`** (zysk tempa na gońcu, potem `...b6`/`...Nc6`, `...Bb7`, `...Nbd7-b6`).
    - na `7. c5` (lub `6. c5`): natychmiastowe rozbicie łańcucha przez **`...b6`** i **`...a5!`** (`7. c5 O-O 8. Bd3 b6 9. b4 a5!`).
  - Kolejność bez `d4` (`2. e4 d5 3. cxd5 cxd5 4. exd5 Nf6` / `3. exd5 cxd5 4. cxd5 Nf6`): na `5. Nc3 Nxd5 6. Nf3 e6` powrót do schematu; na szachy `5. Qa4+ Nbd7` / `5. Bb5+ Nbd7` spokojne `...g6, ...Bg7, ...O-O, ...Nb6` i odzyskanie piona `d5`.

### vs rzadkie otwarcia flankowe (`1. b3`, `1. g3`, `1. f4`)
- **`1. b3` i `1. g3`:** ten sam szkielet co na Réti (`...d5, ...Nf6, ...c6, ...Bf5/Bg4, ...e6`).
- **`1. f4` (Bird):** zdrowe centrum `1... d5, ...Nf6, ...c5, ...Nc6, ...e6` (albo `...g6, ...Bg7`).

---

## 4. Zakazane transpozycje i twarde reguły (dla Agenta 1 i Agenta 2)

1. **Białe QGD:** nigdy `4. Nf3` przed `4. Bg5` (nie wpuszczamy Wiedeńskiego, klasycznego Ragozina ani Botwinnika); na `4... c6` obowiązkowy bezpiecznik `5. e3!`.
2. **Białe Holenderska:** nigdy `Nf3` przed `e3` (zachowujemy otwartą przekątną `d1-h5` i pole `f3` pod manewr `Qf3-g3`).
3. **Białe Benoni:** na `7. Bf4 a6` obowiązkowe `8. a4` (nie oddajemy darmowego `...b5`), na `7. Bf4 Bg7` konkretne `8. Qa4+ Bd7 9. Qb3`.
4. **Czarne vs `1. c4` / `1. Nf3`:** zakaz kolejności z KID (`1... Nf6`, `2... g6`, `3... Bg7`), która pozwala białym transponować w głównego KID i rozbija jednolitość Półsłowiańskiej.
5. **Czarne Półsłowiańska:** nie rozbudowywać w stronę Botwinnika (`5. Bg5 dxc4 6. e4 b5`) ani Anty-Moskwy (`5. Bg5 h6 6. Bh4 dxc4`) — utrzymujemy unifikację `5... Nbd7`.
6. **Świadome dawkowanie `g3` (cel: wszechstronność, nie niechęć):** Lubię struktury z `g3` i dobrze się w nich czuję, ale celowo ograniczam główne gałęzie z fianchettem do Słowiańskiej (`4. Qc2 + g3`) oraz Tarrascha (`6. g3`), żeby rozwijać uniwersalność w klasycznych strukturach centralnych (`e3`/`Bd3`/`Bg5`). Nie zamieniać całego repertuaru w Katalońską na wszystko, natomiast punktowe, obiektywnie najlepsze warianty z `g3` w konkretnych odchyłkach są jak najbardziej akceptowalne.