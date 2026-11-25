# Practical Line-Selection Audit: Classical QGD (`ch01_classical_qgd_chessable.pgn`)

- **Audited File:** `repertoire/ch01_qgd/ch01_classical_qgd_chessable.pgn` (17 trainable lines, 1 intro, 5 model games, 154 RAVs; avg depth `10.2` moves, max `14`)
- **Contract Reference:** `prompt.md` (1800–2000 FIDE -> 2200+ FM target; `2000_2500` blitz/rapid/classical + Masters; `8–12h/week` total budget; Karpov-style space-advantage middlegames + sharp tactical training)
- **Tools Used:** Local **Stockfish 19** (depth 18 & depth 24 `MultiPV=1`), `data/lichess_online.db` (`2000_2500` blitz/rapid/classical, 1,000,000 games pre-expansion), and cached Lichess Masters data.
- **Overall Practical Score:** **7.5 / 10** (revised upward to **~8.0 / 10** once Albin `5.g3` and `4...dxc4 5.e3` are validated at depth 24)

---

## 1. User Notes & Stockfish 19 Depth-24 Verification (Albin `5.g3` & Early `4...dxc4 5.e3`)

### Albin Countergambit `5.g3` (`1.d4 d5 2.c4 e5 3.dxe5 d4 4.Nf3 Nc6 5.g3`)
- **User Note:** *"I disagree, `5.g3` is really good — my Stockfish depth 50 says both `5.a3` and `5.g3` are `+0.6`, Lichess SF19 depth 21 shows `+0.8` / `+0.7`, Masters DB has `5.g3` at `51%` (621 games, 60.5% White score), and I like `g3`."*
- **Why the initial depth-18 MultiPV=4 check understated `5.g3` (`+0.44`):**
  - That earlier check ran concurrently with a background `audit-tree` Stockfish process competing for CPU threads, and multi-threaded MultiPV=4 at depth 18 showed search variance (`+0.44` in the concurrent run vs **`+0.75`** in an isolated depth-18 MultiPV=4 run!).
  - **Isolated Depth-24 (`MultiPV=1`) verification:**
    - `5.a3`: **`+0.70`** (WDL `232/767/1`)
    - `5.Nbd2`: **`+0.56`** (WDL `143/855/2`)
    - `5.g3`: **`+0.51`** (WDL `122/876/2`) -> after `5...Nge7 6.Bg2 Ng6 7.O-O Ngxe5 8.Nxe5 Nxe5 9.Na3`: **`+0.34`** (WDL `48/949/3`). Against `5...Bg4` (36.2% online), `6.Bg2` hits **`+1.32`** (WDL `786/214/0`).
- **Revised Verdict on `5.g3`:** **GOOD PICK (Keep).** Objectively sound (`+0.51` at depth 24, `~+0.6` at depth 50), scores **56.7%** online (`217` games vs `51.7%` for `5.a3`) and **60.5%** in Masters (`621` games vs `59.0%` for `5.a3`), and matches the player's comfort in `g3` structures without breaking `SKILL.md` or `prompt.md` intent.
- **Note on `SKILL.md`:** Confirmed no mistake in `SKILL.md` or the local Stockfish 19 binary; the discrepancy was purely MultiPV=4 depth-18 thread/hash variance plus uncached Masters data at `4.Nf3 Nc6`.

### Early `4...dxc4 5.e3` (`Line 5.2`) — Verified Strong at Depth 24
- **Depth-24 (`MultiPV=1`) check:** `5.e3` is **`+0.31`** (WDL `58/937/5`) vs `5.e4` **`+0.04`** (WDL `20/965/15`).
- **Verdict:** **`5.e3` is objectively the right choice** (`+0.31` vs `+0.04`). Practically (`52.9%` online vs `54.5%` for `5.e4`), after `5...c5` (`58.6%` online), `6.Bxc4` (`+0.19` depth 18, `45.0%` in 20 online games) is solid, though `6.dxc5` (`58.3%` in 6 games) or `6.Bxf6` (`+0.14`) are also worth keeping in mind if the `6.Bxc4 cxd4 7.exd4` IQP feels too symmetrical.

---

## 2. Line-by-Line Assessment

### Good Picks (Keep)
1. **6.1 Triangle Slav (`3...c6 4.e4!`)** — SF19 `#1` (`+0.46`), **57.3%** online (`616` games vs `53.0%` for `4.Nf3`), bypasses Noteboom theory, directly trains sharp calculation. *(Caveat: only covers `2...e6 3.Nc3 c6`, not `2...c6 3.Nf3 e6` from Ch3.)*
2. **4.1 Cambridge Springs (`7.cxd5 Nxd5 8.Qd2 Bb4 9.Rc1 h6 10.Bh4 c5 11.a3!`)** — `7.cxd5` is SF19 `#1` (`+0.27`), scores **62.5%** online (`60` games) and **60.8%** in Masters (`1,286` games), outscoring `7.Nd2` (`+0.15`, `55.4%` online, `56.4%` Masters). `8.Qd2` (`+0.24`) and `11.a3` (`+0.23`) are also SF19 `#1`.
3. **4.2 Anti-Botvinnik / Delayed Ragozin (`4...c6 5.e3! Nbd7 6.Nf3 Bb4 7.cxd5 exd5 8.Bd3 Qa5 9.Qc2 O-O 10.O-O`)** — Enforces `prompt.md` Rule 1 and reaches **`+0.83`** in SF19.
4. **8.1 Chigorin (`3.Nf3 Bg4 4.cxd5 Bxf3 5.gxf3 Qxd5 6.e3 e5 7.Nc3 Bb4 8.Bd2 Bxc3 9.bxc3 Qd6 10.Qb3!`)** — `10.Qb3` is SF19 `#1` (`+0.83`, WDL `305/695/0`) and scores **63.2%** in Masters (`53` games) vs `50.0%` for `10.Rb1` (`147` games). *(Needs RAV coverage for `3...Nf6` and `3...dxc4`.)*
5. **7.1 Tarrasch (`6.g3 ... 9.Bg5 cxd4 10.Nxd4 h6 11.Be3`)** — Mandated by `prompt.md` Rule 6; `9.Bg5` (`+0.29`) and `11.Be3` (`+0.42`) are SF19 `#1` Karpov mainlines.
6. **6.2 Alatortsev (`3...Be7 4.cxd5 exd5 5.Bf4 c6 6.e3 Bf5 7.g4!`)** — Cleanly handles `3...Be7` (`4.Bg5?? Bxg5` loses a piece) and `7.g4!` (`+0.32` SF19 `#1`, `58.3%` in 12 online games) avoids trading off Black's bad bishop.
7. **1.1–1.4 Orthodox (`7.Rc1`, `13.Bb3`, `14.Nd2`, `12.a4`, `7...a6 8.cxd5`)** — Sound OTB backbone for `2200+ FIDE` (`13.Bb3` `+0.30`, `14.Re1` `+0.47`, `12.a4` critical), though `12...e5` has `0` games in the 1M online DB (so ROI is OTB rather than online blitz/rapid).
8. **9.1 Albin (`5.g3!`)** — Validated above (`+0.51` depth 24, `56.7%` online, `60.5%` Masters).

---

### Weak / Suboptimal Practical Picks (Recommended Changes)

#### 1. **3.1 Lasker (`9.cxd5 Nxc3 10.bxc3 exd5 11.Qb3 Rd8 12.c4`) — REPLACE**
- **Why it's bad practically:** Voluntarily liquidates into a sterile symmetrical `0.00` endgame where Black equalizes comfortably.
  - **Online (`2000_2500`, 72 games at `8...Qxe7`):** `9.cxd5` scores **28.1%** (`16` games: `25%` W, `6.2%` D, `68.8%` B).
  - **Depth-24 SF19:** `9.Rc1` **`+0.14`** (WDL `23/970/7`) vs `9.cxd5` **`+0.08`** (`18/973/9`). After `9.cxd5 Nxc3 10.bxc3 exd5`, `11.Qb3` is only `+0.05` (depth 18, 4th choice).
- **Proposed Replacement:** **`9.Rc1!`**
  - Scores **61.1%** online (`18` games; `9.Bd3` `64.3%`, `9.Qc2` `62.5%`).
  - Keeps tension and pieces on the board: meet `9...Nxc3` (`73%` online) with **`10.Rxc3!`** (`+0.18`, semi-open c-file + rook lift), and `9...c6` with **`10.Bd3`** / **`10.Be2`** (`+0.17`).

#### 2. **2.1 Tartakower (`8.cxd5 Nxd5 9.Bxe7 Qxe7 10.Nxd5 exd5 11.Rc1 Be6 12.Qa4 c5 13.Qa3 Rc8 14.Be2`) — REPLACE**
- **Why it's bad practically:** White spends a 14-move flagship line forcing two minor-piece swaps into Tartakower's easiest `0.00` equality (`14.Be2` is **`-0.02`** in SF19, WDL `7/984/9`).
  - **Masters (`6,487` games at `7...b6`):** `8.cxd5` scores **50.3%** — the **lowest** of all main 8th moves (`8.Be2` **55.5%**, `8.Bd3` **55.0%**, `8.Rc1` **54.5%**, `8.Qb3` **58.6%**). Online (`349` games): `8.cxd5` scores `50.3%`.
  - **Depth-24 SF19 (`7...b6`):** `8.Qb3` **`+0.13`**, `8.Be2` **`+0.12`**, `8.Rc1` **`+0.10`**, `8.Qc2` **`+0.06`**, vs **`8.cxd5` `+0.04`**.
- **Proposed Replacement:** **`8.Rc1`** (`+0.10`, `54.5%` Masters, `52.2%` online after `8...Bb7`) or **`8.Be2`** (`+0.12`, `55.5%` Masters) or **`8.Qb3`** (`+0.13`, `58.6%` Masters, `75.0%` in 12 online games; meet `8...Bb7` with `9.Bxf6 Bxf6 10.cxd5 exd5`).

#### 3. **5.3 Early `3...Bb4` (`4.cxd5 exd5 5.Bf4`) — BORDERLINE (Trade-Off)**
- **Pros:** Scores **59.4%** online (`101` games vs `49.2%` for `4.e3`) and unifies with Line `5.1` (`Nge2` Carlsbad).
- **Cons:** Depth-24 SF19 prefers **`4.a3`** (`+0.36`, WDL `72/923/5`) and **`4.e3`** (`+0.23`, transposing directly into Chapter 2 Nimzo Rubinstein, saving study load) over `4.cxd5` (`+0.20`). Keeping `4.cxd5` for practical online winrate is reasonable, just a conscious choice.

---

## 3. High-Frequency Practical Coverage Gaps (`2000–2500` Online DB)

| Position | Missing Move | Freq / Games | Practical Fix |
| :--- | :--- | :---: | :--- |
| `1.d4 d5 2.c4 e6 3.Nc3` | **`3...dxc4`** | `2.1%` (`319` g) | Add RAV **`4.e4!`** (`+0.49`, `54.5%` online) |
| `...4.Bg5 Be7 5.e3 O-O 6.Nf3` | **`6...a6`** | `8.0%` (`166` g) | Add RAV **`7.cxd5 exd5 8.Bd3`** (`+0.32`, `62.0%` online) — far more common than `7.Rc1 a6` (`31` g) |
| `...4.Bg5 Be7 5.e3 O-O 6.Nf3` | **`6...c5`** | `5.9%` (`122` g) | Add RAV **`7.dxc5`** (`+0.32`, `66.7%` online) or `7.cxd5` |
| `...4.Bg5 Be7 5.e3` | **`5...Nbd7`** | `7.5%` (`127` g) | Note transposition / `6.Nf3 c6` |
| `1.d4 d5 2.c4 Nc6 3.Nf3` | **`3...Nf6` & `3...dxc4`** | `15.6%` (`155` g) & `11.0%` (`109` g) | Add RAVs after `3.Nf3` (or switch to `3.cxd5 Qxd5 4.e3` `57.4%`) |
| `1.d4 d5 2.c4 e5 3.dxe5 d4 4.Nf3` | **`4...c5`** | `12.5%` (`105` g) | Add RAV **`5.e3 Nc6 6.exd4`** / `5.g3` |
