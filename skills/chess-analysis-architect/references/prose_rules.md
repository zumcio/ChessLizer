# Prose Grounding, Chess Logic & Chessable Hygiene

## Move Provenance & Conceptual Precision
Enforced deterministically by `validate_chessable.py --provenance` (`tools/provenance.py` + `tools/claim_lexicon.py`):
- **Game-or-Stockfish Rule:** Every SAN move in any comment (trainable, intro, model) must resolve to a chapter/GM/DB game line or SF top-3 PV. Every resolved move is SF-checked (`>70 cp` ERROR, `>35 cp` FLAG), opponent moves must be plausible (`SF` or `DB`) unless framed as a mistake/trap, and unnamed gap moves must be expected (`SF #1` or `>=30% DB`).
- **Disambiguating Optional Recipes:** If a complex future plan isn't auto-matched, add a line to `cache/<chapter>_claims.json` (`[{"node": "G4:13w", "line": "Qd2 a4 Rc8 b4"}]`) or attach a `cont_rav`.
- **Board & Lexicon Truth:** Never state an eval label (`winning` / `clear edge` / `equal`), pawn status (`isolated`, `doubled`, `passed`, `open file`), `outpost` (`e6->f5`), `pin`, `battery`, `bishop pair`, or `light/dark square` parity without verifying against `facts.md`.
- **Causal Chess Logic:** Include piece letters (`Rc3 to c5`), respect move-order blocking (state pawn pushes before pieces behind them), match trade polarity, and separate active facts from conditional future plans.
- **GM Citations (`"as in X vs Y"`):** Verified against cached `/masters` PGNs; match flank-pawn structures (`Structure vs Skeleton` in `gm_digest.md`) before porting plans across branches.

## Mandatory Leaf Template (Every Trainable Leaf)
```text
━━━ PLAN FROM HERE ━━━<br><br>Verdict: <Honest eval & edge> — <Structure name><br><br>• Our Plan — <Green/Blue arrows: primary breaks, piece routes, key targets>.<br><br>• Watch Out — <Red arrows: opponent counterplay, tactical shots, prophylaxis>.<br><br>• Key Trades & Endgame — <Which pieces to trade or keep, target endgame>.<br><br><br>━━━ SAMPLE CONTINUATIONS ━━━<br><br><1-sentence lead-in to natural continuations and tactical traps below>
```
Attach **1–3 clickable, SF-verified `cont_ravs`** (anchor-repeated on the leaf move).

## Chessable PGN Rules (`chessable-pgn`)
- **Flat Sibling RAV Rule:** Emit sibling RAVs as independent flat branches (`force_new_first=True`), never nested sub-variations with prose. Cap direct RAVs at `<= 4` per move.
- **Headers & Markup:** `[White "<title>"]`, `[Black ""]`, `$1`–`$6` NAGs, `<br>`/`<br><br>`/`<br><br><br>━━━ HEADER ━━━<br><br>`, `• Label — text.<br><br>`, separate `{ [%csl ...] [%cal ...] }` blocks (`< 6` arrows/node; `G`/`B` arrows must follow legal moves, routes, or attack rays). Zero raw `\n`, `( ) [ ] { }`, `0-0`, `<ul>/<li>/<b>/<i>/<p>`, or paragraphs `> 650` chars.
- **Model Games:** `3–5` verbatim `/masters` PGNs (`[Result]`, `[LichessId]`, `[StemMoves]`, `[Black ""]`) with only a 1-line root note matching the actual result and game moves.
