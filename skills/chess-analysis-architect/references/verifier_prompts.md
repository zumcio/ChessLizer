# Verifier Subagent Contracts (Low-Token)

## Subagent 1: `chess-critic` (Gate 1 — Isolated, Read-Only)
- **Invoke via:** `define_subagent(Name="chess-critic", EnableWriteTools=false)`.
- **Pass ONLY:** `prompt.md` (if present), `<skeleton.pgn>` (Mode A) or skip `<skeleton.pgn>` in Mode C, and `cache/<chapter>_audit.md`.
- **Scope:** `prompt.md` move-order/style guardrails, line & depth budgets, human playability, quiet-stop pruning (`>=85–90%` single-reply dominance), `<=4` RAVs/node, plus a **Board-First Sanity Check (`FLAG`)** for any suspicious or mismatched plan.
- **Required Output:**
  - `VERDICT: PASS | REVISE`
  - `VETO / REVISE` table (`Line/Node | Rule from prompt.md | Exact fix`)
  - `SANITY FLAGS (Parent to verify)` table (`Line/Node | Flagged idea | Board-based concern`)

## Subagent 2: `chess-coach-verifier` (Gate 2 — Residual-Only, No Edits)
- **Invoke via:** `define_subagent(Name="chess-coach-verifier", EnableWriteTools=true)` with explicit instruction **forbidding any file edits** (only `analyze.py engine --check` allowed for spot-checks).
- **Pass ONLY:** `cache/<stem>_residual.md` and `prompt.md` (NO full PGN, NO `--all-nodes` fact sheet, NO `idea_dossier.md` unless a deep strategic dispute arises).
- **Scope:** Verify ONLY the unverified conceptual claims listed in `residual.md` (and any disputed `SANITY FLAGS` forwarded by the parent):
  1. Pure conceptual strategic assertions (`"Black has no counterplay"`, `"passive endgame"`, etc.) against the 1-line board facts and `analyze.py engine` spot-checks.
  2. Pedagogical clarity, trade-explanation quality, and `prompt.md` coaching-voice fidelity.
  3. Any residual board-first sanity concerns (`FLAG`).
- **Required Output:**
  - `VERDICT: PASS | HARD_VETO`
  - `HARD_VETO` table (`Where | Claimed text | SF19 eval+PV or Fact contradiction`)
  - `SANITY FLAGS (Parent to verify)` table (`Where | Flagged idea | Board-based reason`)
- Parent resolves or documents any dismissed flags in `cache/<ch>_flag_ledger.json`, then re-runs `analyze.py gate2` if prose changed.
