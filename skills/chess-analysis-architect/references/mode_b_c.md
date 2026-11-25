# Mode B (Deep Analysis) & Mode C (Low-Token Course Audit)

## Mode B: Position / Game / Endgame Deep Analysis
1. **Engine & DB Grounding:**
   - Run `analyze.py report --moves "<pos>" --tier <tier> --depth 22 --multipv 4` (plus `cloud`, and `tablebase` whenever `<= 7` pieces are on the board).
   - Spot-check critical tries via `analyze.py engine --check "<move>" --depth 22+`.
2. **Board Facts (if outputting an annotated `.pgn`):**
   - Generate `export_fact_sheet.py <out.pgn> --side <white|black> --delta --all-nodes` before writing prose.
   - Validate via `validate_chessable.py <out.pgn> --engine-check --depth 20 --side <white|black> --provenance --emit-residual cache\topic_residual.md --summary`.
3. **Verification & Output:**
   - Run 1 `chess-coach-verifier` pass on `cache\topic_residual.md` (or the Markdown draft) + `prompt.md`.
   - Deliver objective eval + `WDL`, DB trends, concrete refutations, key breaks, and endgame assessment.

## Mode C: Existing Course / PGN Audit (Low-Token)
Skips `mine-ideas`, Crossroads Card, skeleton authoring, and prose authoring:

1. **Deterministic Audit (Step 1):**
   - If `/masters` or model PGNs are not cached yet, run one unsandboxed `analyze.py warm-cache --pgn <existing.pgn> --tier <tier> --since 2015`.
   - Run both deterministic gates:
     ```powershell
     .\.venv\Scripts\python.exe tools\analyze.py gate1 <existing.pgn> --side <white|black> --tier <tier>
     .\.venv\Scripts\python.exe tools\analyze.py gate2 <existing.pgn> --side <white|black> --tier <tier>
     ```
     *(Pass `--skeleton <skel.pgn>` to `gate2` if a reference skeleton exists; run `analyze.py render-svg` on any `>= 6` arrows warning.)*
2. **Targeted Verifiers (Step 2 — Skip if User Asked for Deterministic-Only):**
   - **`chess-critic`:** pass ONLY `prompt.md` and `cache\<stem>_audit.md`.
   - **`chess-coach-verifier`:** pass ONLY `prompt.md` and `cache\<stem>_residual.md` (`EnableWriteTools: true`, no file edits).
3. **Audit Report & Optional Patching (Step 3):**
   - Group findings by **HARD VETO** (`UNBACKED`, `UNSOUND`, `UNSTATED-ASSUMPTION`, `GM-CITATION`, `MODEL-RESULT`, `LEX-*`, `>= 2%` reach gaps, nested prose RAVs), **SOFT VETO** (`DUBIOUS`, `IMPLAUSIBLE-OPP`, `EVAL-MISMATCH`, `prompt.md` style/guardrail issues), and **POLISH** (`> 700`-char paragraphs, bare `"sq to sq"`, non-clickable sequences).
   - Edit `<existing.pgn>` only when asked, then re-run `gate2` (and `gate1` if moves changed).
