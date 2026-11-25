# Mode A: Repertoire Chapter Pipeline

## Phase 1A: Low-Token GM Idea Mining & Dossier
1. Run `analyze.py mine-ideas` across major tabiyas (`--games-per-tabiya 3` to `5`; pass `--pgn <skeleton.pgn>` once built so GM games carry `Structure vs Skeleton` divergence tags) -> `cache/<chapter>_gm_digest.md`.
2. Combine GM breaks, routes, trades, and targeted SF19 checks (`analyze.py report` / `engine`) into `cache/<chapter>_idea_dossier.md` (`<= 80` bullets):
   - Reusable "box of setups" and tactical motifs
   - Recurring pawn breaks and tension decisions
   - Signature piece routes and preferred exchanges
   - Opponent practical counterplay & leaf continuations
   - Exact verified Lichess Masters IDs (`game_id`, players, year, exact stem moves, theme)

## Phase 1A.5: Interactive Line-Selection Crossroads Card
Never guess stylistic preferences when 2+ sound GM weapons exist:
1. Present a concise **Crossroads Card** with the chapter's 3–6 real strategic choices: **SF19 eval**, **Online (`2000–2500` / target tier) score & play%**, **Masters score**, and a 1-sentence structural summary per option, plus the **3–5 candidate Model Games** with exact stem moves.
2. Wait for user approval (`"1B, 2A, models ok"`) unless every branch was locked upfront.

## Phase 1B: Bare Skeleton Tree (No Prose Yet)
1. Use `analyze.py report`, `cloud`, `idea_dossier.md`, and Crossroads choices to map `>= 2.0%` reach branches and tactical-shot deviations up to target depth (`~11` moves, cap `15`).
2. **Equal-Option Tie-Breaker:** within `~15–25 cp` in SF19 and obeying `prompt.md`, pick the highest practical DB score.
3. **RAV Density:** `<= 4` direct RAVs per move.
4. Build `<skeleton.pgn>` with candidate mainlines, Gate-1 RAVs, 1-line branch rationale, and 3–5 unannotated Model Games (`[LichessId]`, `[StemMoves]`).

## Gate 1: Deterministic Tree Audit + `chess-critic`
1. Run `.\.venv\Scripts\python.exe tools\analyze.py gate1 <skeleton.pgn> --side <white|black> --tier <tier>`. Fix any `HARD_VETO` (`>70 cp`, illegal move, unverified model, `>=2%` reach gap) before invoking `chess-critic`.
2. Run 1 isolated `chess-critic` pass (see `references/verifier_prompts.md`). Max 1 revision round, then **FREEZE THE TREE**.

## Phase 2: Grounded Batched Prose Authoring
1. Generate the deterministic fact sheet BEFORE writing prose:
   ```powershell
   .\.venv\Scripts\python.exe tools\export_fact_sheet.py <skeleton.pgn> --side <white|black> --tier <tier> --delta --all-nodes --depth 18 --out cache\<chapter>_facts.md
   ```
   *(For `>10` lines, batch in 5–7 line slices via `--games 1-7`, `--games 8-14`, etc.)*
2. Follow `references/prose_rules.md` strictly: author every claim from `<chapter>_facts.md` and `<chapter>_gm_digest.md`, include `PLAN FROM HERE` + `1–3` engine-verified `cont_ravs` on every trainable leaf, keep Intro blueprints (`5–8` moves) sound, and keep Model Games verbatim/unannotated.

## Gate 2: Deterministic Validation + Residual-Only `chess-coach-verifier`
1. Run:
   ```powershell
   .\.venv\Scripts\python.exe tools\analyze.py gate2 <output.pgn> --side <white|black> --tier <tier> --skeleton <skeleton.pgn>
   ```
   This runs SF19 mainline+RAV checks, skeleton parity, model verification, Chessable syntax, Game-or-Stockfish move provenance, claim lexicon, and arrow provenance, printing `<= 40` lines and writing `cache\<stem>_residual.md`.
2. Fix every `ERROR`. For any intentional `FLAG`, either fix the prose or dismiss it with a reason in `cache\<ch>_flag_ledger.json` (auto-reopens if the sentence changes).
3. Pass **ONLY** `cache\<stem>_residual.md` and `prompt.md` to `chess-coach-verifier` (see `references/verifier_prompts.md`). Re-run `gate2` after any final edit.

## Phase 3: Handover Summary
Deliver only after `gate1`, `gate2` (`0` errors), and `chess-coach-verifier` (`PASS`) are clean. Report: SF depth, DB sources (`data/lichess_online.db` or `/masters`-only), trainable line & RAV counts, verified Model Game IDs + `[StemMoves]`, and Chessable import checklist (*"Import all sub-variations as their own item"* **UNTICKED**; mark Intros & Model Games **Informational**).
