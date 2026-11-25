---
name: chess-analysis-architect
description: Lean multi-agent chess opening repertoire, audit, and position analysis pipeline combining deterministic CLI audits (Stockfish 19 with persistent disk cache, offline Lichess Online DB, Lichess Masters DB, Syzygy, Game-or-Stockfish move provenance, concept lexicon, Chessable validation, delta board fact sheets) with interactive crossroads, GM idea mining, and residual-only verifier passes. Use whenever the user asks to analyze an opening, build a repertoire chapter, prepare lines with ideas and model games, deeply analyze a position or endgame, audit or verify an existing PGN/course, or produce a verified Chessable-ready PGN file.
---

# Chess Analysis Architect (v4.0)

Deterministic tools enforce move provenance (every prose move must resolve to a **game line OR Stockfish PV** and pass soundness, plausibility, and stated-assumption checks across trainable, intro, and model games), conceptual predicates, arrow provenance, and Chessable syntax—leaving `chess-coach-verifier` to read only unverified residual sentences (`residual.md`).

## Modes & Output Language

- **Mode A — Repertoire Chapter (`-> .pgn`):** Build/expand a chapter with lines, plans, and verified model games -> read [references/mode_a.md](references/mode_a.md) and [references/prose_rules.md](references/prose_rules.md).
- **Mode B — Deep Analysis (`-> Markdown` or `.pgn`):** Deeply analyze a position, game, novelty, or endgame -> read [references/mode_b_c.md](references/mode_b_c.md).
- **Mode C — Course / PGN Audit (`-> Audit Report` + optional fixes):** Audit an existing `.pgn` without rebuilding -> read [references/mode_b_c.md](references/mode_b_c.md).
- **Language:** Write all outputs, comments, titles, and headers (`━━━ PLAN FROM HERE ━━━`, `━━━ SAMPLE CONTINUATIONS ━━━`) in **English** with English SAN (`Nf3`, `O-O`); read `prompt.md` in any language.

## Phase 0: Environment & Contract

1. **Verify toolkit & skill sync first:**
   ```powershell
   .\.venv\Scripts\python.exe tools\analyze.py doctor
   ```
   - `tools/chess_env.py` (`EngineCache` in `cache/engine_cache.db`, `LocalOnlineDB` in `data/lichess_online.db`)
   - `tools/analyze.py` (`doctor`, `warm-cache`, `mine-ideas`, `gate1`, `gate2`, `audit-tree`, `slice-pgn`, `report`, `engine`, `masters`, `online`, `cloud`, `tablebase`, `render-svg`)
   - `tools/export_fact_sheet.py` (`--delta --all-nodes` or `--nodes commented|leaves`)
   - `tools/validate_chessable.py` + `tools/provenance.py` + `tools/claim_lexicon.py` + `tools/flag_ledger.py`
2. **DB Readiness (Offline-First):**
   - If `data/lichess_online.db` lacks the target rating bucket for Mode A, run **one unsandboxed** `tools/import_lichess_dump.py --tier <tier> --speeds <speeds> --max-games 5000000` (or note `/masters`-only fallback).
   - Run **one unsandboxed** `analyze.py warm-cache` per Mode A chapter (`--moves "<root>"` / `--pgn <skeleton>` `--tier <tier> --since 2015 --fetch-models 10`) so all downstream checks run 100% offline in the sandbox.
3. **Input Contract (`prompt.md`):**
   Treat workspace `prompt.md` as authoritative for repertoire scope, move-order guardrails, rating/speed tier (`2000_2500`, `blitz,rapid,classical`), line/depth budget (`~11` moves target, `15` cap, `>= 2.0%` reach split, `85–90%+` forced stop), `3–5` unannotated Model Games (`[LichessId]`, `[StemMoves]`), and tone.

## Deterministic Gates & Release Criteria (Mode A)

| Gate | Command | Pass Condition | Verifier |
| :--- | :--- | :--- | :--- |
| **Gate 1** | `analyze.py gate1 <skel.pgn> --side <w\|b> --tier <tier>` | Exit `0`, `0` unresolved `>=2%` gaps | `chess-critic` (`prompt.md` + `audit.md` only; max 1 round) |
| **Authoring** | `export_fact_sheet.py <skel.pgn> --side <w\|b> --delta --all-nodes` | Generated before prose authoring | Follow [references/prose_rules.md](references/prose_rules.md) |
| **Gate 2** | `analyze.py gate2 <out.pgn> --side <w\|b> --tier <tier> --skeleton <skel.pgn>` | Exit `0` (`0` errors); ranked flags reviewed | `chess-coach-verifier` reads **ONLY** `residual.md` + `prompt.md` |

See [references/verifier_prompts.md](references/verifier_prompts.md) for subagent definitions and output schemas. Release only when all 5 criteria hold: Crossroads approved, Gate 1 + `chess-critic` `PASS`, `facts.md` generated, Gate 2 exit `0`, and `chess-coach-verifier` `PASS`.
