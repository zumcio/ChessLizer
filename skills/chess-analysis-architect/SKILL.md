---
name: chess-analysis-architect
description: Multi-agent chess opening repertoire and position analysis pipeline using local Stockfish 19, Lichess Masters and Online databases, 360-degree reports, coverage audits, Syzygy tablebases, and Chessable PGN validation. Use whenever the user asks to analyze an opening, build a repertoire chapter, prepare lines with ideas and model games, deeply analyze a chess position or endgame, or produce a verified Chessable-ready PGN file.
---

# Chess Analysis Architect

A two-gate, multi-agent workflow for producing engine-verified, database-grounded, idea-heavy chess analysis and Chessable-ready PGN chapters without tactical hallucinations, missing repertoire coverage, or wasted prose rewrites.

## When to Use

- The user asks to prepare an opening repertoire chapter (lines, strategic ideas, middlegame plans, and reference model games), preferably as a `.pgn` file.
- The user asks for deep analysis of a specific chess position, game, opening novelty, or endgame.
- The user asks to audit, expand, or verify an existing repertoire or PGN chapter against engine and database statistics.

## Output Language Rule

Write all explanations, PGN comments, titles, and reports in the language of the user's prompt. Keep chess move notation in standard English SAN (`Nf3`, `Bxc4`, `O-O`).

## Phase 0: Environment Discovery and Input Contract

Before proposing any moves, establish the workspace and task contract.

1. Discover the exact CLI invocation for the local chess toolkit in the workspace (do not guess wrapper paths). Expected capabilities:
   - Local Stockfish 19 (`stockfish-windows-x86-64-universal.exe` - MultiPV, `UCI_ShowWDL`, centipawn loss, refutation checks)
   - Lichess Masters DB (`/masters`, supports `--since` and GM model games)
   - Lichess Online DB (`/lichess`, presets: `beginner`, `club`, `advanced`, `strong`, `2000_2500`, `all`, or exact `--ratings` / `--speeds`)
   - 360-degree report (`report` - tags: `COMMON-AMATEUR`, `MAIN-THEORY`, `AMATEUR-SPECIAL`, `SF#1`)
   - Coverage audit (`coverage`)
   - Lichess Cloud Eval (`cloud`)
   - Syzygy 7-piece Tablebase (`tablebase`)
   - Local ECO database (`data/eco/a.tsv` through `e.tsv`, `cache/eco_index.json`)
   - SQLite Explorer Cache (`cache/explorer_cache.db`)
   - Chessable PGN validator (`validate_chessable.py`, supports `--engine-check`)
   - SVG diagram renderer (`render-svg`)

2. Check `/lichess` availability. If `LICHESS_API_TOKEN` is missing in `.env` and `/lichess` returns `401 Unauthorized`, continue using `/masters`, `cloud`, and local Stockfish 19, and explicitly record in the final report that amateur database coverage was skipped due to missing token.

3. Lock the Input Contract (infer from context or ask briefly only if critical fields are missing):
   - Mode: **Mode A (Repertoire Chapter -> PGN)** or **Mode B (Position / Game / Endgame Deep Analysis -> PGN or Markdown)**
   - Color: White or Black
   - Target opponent rating & time-control bracket(s): capture the user's exact declared online bracket and speeds (e.g., `2000-2200` blitz, `2200-2500` rapid, or `2000-2500` overall via `--ratings` / `--speeds` on `/lichess`, defaulting to `2000_2500` + `masters`). Online DB stats at this declared level are a **primary driver** for choosing which opponent lines and practical sidelines to prepare, while `/masters` and Stockfish 19 confirm objective soundness.
   - Existing repertoire context (to prevent move-order collisions and maximize structural transfer)
   - Scope budget: target line count and move depth (default for repertoire chapters: 8 to 12 moves, up to 14 in forced tactical lines)
   - Output target: Chessable-ready `.pgn` following `chessable-pgn` conventions (default), or standard PGN if requested

## Phase 1A: Human GM Idea Mining (Idea Dossier)

Before proposing a skeleton tree or writing any prose, extract real human strategic and tactical patterns from top-level practice.

1. Query `/masters` (and `/masters --since` for modern trends) from the chapter's main tabiya(s) to collect **5–10 highest-rated games** — mandating **decisive wins for our side** (`1-0` when building for White, `0-1` when building for Black) plus **1–2 top-rated games** illustrating the opponent's best practical counterplay.
2. Review those high-level games like a coach (checking sharp tactical moments with local Stockfish 19 on the side so rapid/blitz human inaccuracies or one-trick blunders are filtered out rather than copied blindly).
3. Save a compact persistent working dossier at `cache/<chapter>_idea_dossier.md` recording:
   - Recurring pawn breaks and pawn-tension decisions (when to close, open, or lock a flank)
   - Typical structural transitions (e.g., IQP, Carlsbad, Benoni/KID breaks, `c4-c5` vs `h4-h5`)
   - Signature piece routes, regroupings, and preferred minor/major-piece exchanges
   - The opponent's standard human counterplay motifs and practical jumps/sacrifices (including leaf continuations)
   - Proven endgame conversion blueprints and top-rated Model Game candidates (exact Lichess Masters IDs)

## Phase 1B: Skeleton Tree Proposal (Main Model - No Prose Yet)

Never write long prose comments or arrows before the move tree is frozen. Doing so wastes work if critics change a branch.

1. Use `report` (360-degree, passing the user's exact `--ratings` / `--speeds` or `--tier`), `cloud`, the local ECO index (`cache/eco_index.json`), and your `cache/<chapter>_idea_dossier.md` to scout the starting position, key transpositions, and practical frequencies. Treat `/lichess` frequencies and practical winrates at the user's declared online rating and time control as a **primary driver** for prioritizing which branches and sidelines belong in the course (paired with `/masters` and Stockfish 19 for soundness). If `/lichess` is unavailable (`401` due to missing `LICHESS_API_TOKEN`), flag it clearly as a degraded fallback.
2. **Equal-Option DB Tie-Breaker:** Whenever 2+ candidate moves for our side evaluate roughly equal objectively in Stockfish 19 (within `~0.15–0.25 cp`) and fit the broader repertoire, choose the move with the **highest practical score/winrate** in `/lichess` at the user's declared Elo/speed bracket and in `/masters`.
3. Build a **bare skeleton PGN** containing only:
   - Candidate mainlines and key tactical sidelines informed by both `report` and the GM Idea Dossier
   - One-line rationale per branch (tagged `MAIN-THEORY`, `COMMON-AMATEUR`, `AMATEUR-SPECIAL`, or `NOVELTY`)
   - Candidate reference/model games pulled **exclusively** from `/masters` (never recall long master games from memory)
4. Proceed immediately to Gate 1.

## Gate 1: Tree Verification and Strategic Critique

Spawn **Agent 1** and **Agent 2** in clean, independent contexts (parallel execution preferred). Pass them ONLY the Input Contract, the skeleton PGN, and tool access. Do not pass persuasive arguments from the Main Model.

### Agent 1: Verifier (Engine and Database Auditor)

Audit the skeleton in two directions: **Soundness** and **Coverage**.

1. **Soundness check:**
   - Run `cloud` first for fast deep evals.
   - Run local Stockfish 19 (`MultiPV`, `UCI_ShowWDL`) whenever `cloud` is unavailable, on every novelty or rare move not in `/masters`, and on every proposed refutation or sharp tactical branch.
   - Run `tablebase` whenever any branch or endgame analysis reaches 7 or fewer pieces.
   - Apply strict thresholds to every recommended move for our side:
      - **HARD VETO:** Illegal move, tactical blunder, missed refutation, or CP loss `> 0.70` vs best move without explicit gambit mandate.
      - **SOFT VETO:** CP loss `0.35` to `0.70` (acceptable only if `UCI_ShowWDL` and target preset winrate justify practical pressure and the trade-off is disclosed in prose).

2. **Coverage & Leaf Practicality check:**
   - Run `coverage` on the skeleton PGN against the target `/lichess` preset (if token active) and `/masters` through the **full target move depth of the chapter** (e.g., `--max-ply 24` to `26` for 12–13 move lines — never stop early at `--max-ply 18`!). Rely on `--min-games` / `--min-move-games` rather than truncating ply depth so deep mainlines do not blind-spot late high-frequency replies.
   - Flag every opponent reply played in `> 5%` of games within full target depth that is missing from the skeleton, as well as dangerous `AMATEUR-SPECIAL` traps.
   - **Leaf Practicality Check:** On every leaf position (especially after major pawn tension changes such as closing/opening the center), query `/masters` and `/lichess` (when token active) alongside Stockfish 19 `MultiPV`. Do NOT rely solely on SF19's top 1–2 engine lines at the leaf — capture the most popular practical human replies (e.g., attacking knight jumps or pawn breaks like `13... Nh5` after `13. c5`) so Phase 2 covers them explicitly in clickable `cont_ravs` and Gateway warnings.

3. **Transposition and Model Game check:**
   - Verify ECO transpositions via `cache/eco_index.json` so lines do not accidentally walk into unwanted enemy systems.
   - Confirm every candidate model game exists verbatim in `/masters` (exact players, year, event, and move list).

4. **Required output format:**
   - `VERDICT: PASS | SOFT_VETO | HARD_VETO`
   - Per-line table: eval, `WDL`, best PV, CP loss, DB frequency (`online` / `masters`), flags
   - Missing coverage list (`> 5%` replies)
   - Verified model game IDs / PGNs

### Agent 2: Critic (Strategic and Repertoire Architect)

Perform an adversarial review of the move choices themselves. Never rubber-stamp by default.

1. Use `report` (360-degree) and `/masters --since` (modern trends) to challenge the Main Model's selection:
   - **System fit:** Is there a better system or move order for the user's style, rating target, and practical score?
   - **Repertoire coherence:** Does each line harmonize with the user's broader repertoire (shared pawn structures, mirrored transfer, zero move-order collisions)?
   - **Structural-versatility guardrails (e.g., deliberate `g3` dosing):** Respect user-defined structural quotas when they limit fianchetto/`g3` mainlines to specific chapters in order to build classical central versatility (`e3`/`Bd3`/`Bg5`) instead of playing a Catalan setup against everything. Do **not**, however, treat a versatility cap as an absolute blanket ban on every `g3` move — surgical, objectively best `g3` replies in concrete sidelines remain explicitly acceptable when backed by engine and database performance.
   - **SRS budget discipline:** Cut low-frequency (`< 2%`) side branches that bloat spaced-repetition workload without strategic value.
   - **Human playability:** Challenge sterile engine lines where Stockfish says `+0.25` but human play requires unnatural computer-only precision, or where an opponent gets easy practical counterplay.

2. **Required output format:**
   - `VERDICT: PASS | SOFT_VETO | HARD_VETO` (use `HARD_VETO` only for direct repertoire collisions or unplayable structural errors; use `SOFT_VETO` for strategic/stylistic trade-offs)
   - Concrete counter-proposals backed by `report` statistics and winrates

### Gate 1 Resolution and Deadlock Breaker

- Any `HARD_VETO` from Agent 1 or Agent 2 requires the Main Model to revise the skeleton and re-run Gate 1.
- Enforce a maximum of **2 revision rounds** at Gate 1.
- If a `SOFT_VETO` deadlock remains after Round 2 (for example, Agent 2 pushes a practical `AMATEUR-SPECIAL` gambit scoring 61% while Agent 1 flags `-0.45` CP in Stockfish 19), stop looping and present a concise **Decision Card** to the user with both agents' metrics (`report`, `WDL`, PV) so the user decides.
- Once Gate 1 passes (or the user resolves a Soft Veto), **FREEZE THE TREE**. No mainline or sideline moves may be altered in Phase 2 without re-running Agent 1.

## Phase 2: Idea-Heavy Prose, Visuals, and Model Games (Main Model)

Write full instructional content strictly on top of the frozen tree as a **warm, friendly opening guide** walking the student through lines, ideas, motifs, and plans.

1. **Tone, Readability & Level-Calibrated Proportionality:**
   - **Never glue multi-point breakdowns into a single wall of text** and **never emit robotic labels** like `"Warstwa 1 — ... Warstwa 2 — ..."`.
   - **Calibrate to the student's target Elo (with practical moderation):** Skip empty 1000-Elo filler on truly routine moves (don't over-explain self-evident basics or annotate trivial moves with arrows just for volume). **However**, if a seemingly basic move (such as castling `O-O` at a specific moment instead of delaying it, or tucking the king) carries concrete timing, move-order, or prophylactic value in that exact position, **do** explain why it matters now. When in doubt between slight over-explaining and skipping a subtle nuance, prefer including the concise insight rather than leaving a gap — just keep moderation.
   - Use the four instructional angles as an **internal checklist**, rendered naturally in short paragraphs (`<br><br>`) or separate bullet points (`• ...<br><br>`):
     - Why NOT the natural human autopilot error?
     - What exact concession did the opponent make (tempo, square, bishop pair, king safety, file)?
     - Where do our pawns and pieces want to go over the next 3 to 5 moves?
     - What is the opponent's main counterplay and our prophylactic response?
   - **Proportionality:** When an alternative move is obviously bad, keep it concise — a crisp 1–2 sentence explanation plus a short clickable sideline is enough. Save multi-paragraph deep dives for genuine strategic turning points.
   - **Consistency-Break Rule ("Why deviate from our usual move?"):** Whenever our line departs from the chapter's default reflex (e.g., retreating `Bc1` instead of the usual `Bh4`, or `O-O` instead of closing with `d5`), explicitly explain **what specific detail on the board makes the usual repertoire move inferior or unworkable here**.

2. **Exchanges & Structural Transitions (Mandatory Commentary):**
   - **On every exchange:** Explain briefly whether the trade favors us and why, why we capture (or allow it) now rather than keeping tension, and why we recapture with this specific piece or pawn.
   - **Whenever the position opens, closes, or changes pawn structure** (e.g., entering an IQP, Carlsbad, hanging pawns, or locked center): State our concise plan adapted to the new nature of the position.

3. **Plausible Opponent Defenses & Verified Claims (Zero Strawmen / Zero False Dismissals):**
   - Never justify a plan or attack by assuming a nonsensical opponent blunder (e.g., hanging a queen for free instead of playing a natural retreat). Verify every illustrative prose or RAV sequence with Stockfish 19 so opponent replies represent natural or best defenses (or mark real tactical traps explicitly with `??`).
   - **Never claim in prose that an opponent move is "unplayable", "forced", or "cannot be played"** without checking it first with Stockfish 19! If a dismissed move is objectively playable or even `#1` (e.g., an alternative recapture like `...dxe5`), explain the actual balanced trade-off or add a brief verified RAV rather than oversimplifying a sound move into a false rule.

4. **Gateway to the Middlegame (mandatory on the final move of every leaf line in Mode A):**
   - Position diagnosis (structure and gained assets)
   - Pawn map (green arrows `G`: planned breaks and pushes to avoid)
   - Piece map (blue arrows `B`: exact target squares and routes)
   - Opponent counterplay (red arrows `R`: threats and prophylaxis)
   - Endgames and conversion (what to trade, what to keep, target endgame)
   - Include high-frequency practical human leaf replies surfaced by Gate 1's Leaf Practicality Check alongside SF19 `MultiPV` in clickable `cont_ravs` / Gateway bullets so popular club/GM moves at move 12–14 are never ignored merely because SF19 prefers quieter engine alternatives.

5. **Model Games (4-stop annotation):**
   - Annotate only verified `/masters` games at four stops: end of course theory, key pawn break or exchange, human turning point, and endgame conversion (checked with `tablebase` if reaching `<= 7` pieces).

6. **Chessable PGN formatting (when targeting Chessable):**
   - Follow the `chessable-pgn` skill rules strictly:
     - One PGN game per trainable leaf line; `[White "<title>"]` and `[Black ""]`
     - **Clickable Variation Completeness & Inline Placement:** Every concrete 2+ move tactical or strategic variation discussed on a move (including opponent replies like `9... Qxa2??` on `9. Rc1!` or `11... Bd6?!` on `11. a3!`) must be emitted as a real legal PGN RAV sideline `( ... )` attached directly to that move (using anchor-move repetition when continuing after the move) rather than left as plain text. When multiple variations are discussed on the same move, place bridge prose inside the preceding sideline's trailing `{ ... }` comment so clickable blue links appear right where they are explained instead of all dumped at the bottom.
     - Use `<br><br>` for paragraph breaks, `<br><br><br>━━━ SECTION ━━━<br><br>` for headers, and `• Label — text.<br><br>` for bullet lists
     - Never use raw newlines, `( ) [ ] { }`, `0-0`, `<ul>`, `<li>`, `<b>`, `<i>`, `<p>`, Markdown, or BBCode inside prose comments
     - Put `[%csl ...]` and `[%cal ...]` in their own `{ }` block right after the prose comment, using the color code: `G` (pawns), `B` (pieces), `R` (threats/weaknesses), `Y` (turning points)
     - Use standard `$1` through `$6` NAGs

## Gate 2: Parallel Technical & Coaching Audit

Spawn **Agent 3A** and **Agent 3B** in parallel inside clean, independent contexts (neither shares Main Model persuasive drafts). Pass both the drafted `.pgn`, the frozen skeleton, Agent 1's report (evals, WDL, PVs, leaf DB statistics), `cache/<chapter>_idea_dossier.md`, and tool access (`python-chess`, Stockfish 19, `/masters`, `render-svg`).

### Agent 3A: Technical, Visual & Authenticity Auditor

1. **Skeleton & Model Game Parity:** Verify 100% move-for-move parity with the frozen skeleton (mainlines + Gate-1 RAVs) and confirm every Model Game ID, header, player, year, event, and move sequence matches `/masters` verbatim (`HARD_VETO` on any fabricated game or move).
2. **Eval, WDL & Arrow Mechanics:** Verify numerical consistency with Agent 1's SF19 evals/WDLs, check every `[%cal]` arrow originates from an occupied square, check `[%csl]` syntax, and run `render-svg` spot-checks on the 1–2 most arrow-heavy critical positions to catch colliding, backwards, or unreadable arrows.
3. **Chessable Format & Completeness Compliance:** Verify `[White "<title>"]` + `[Black ""]`, `{ prose } { [%csl ...] [%cal ...] }` order, clickable RAV sideline presence for every concrete 2+ move prose variation (inline interleaving + leaf anchor repetition), complete 5-point Gateway at every leaf, and zero forbidden characters (`()[]{}`, raw `\n`, `0-0`, HTML, robotic `"Warstwa N"` labels, `>700`-char paragraphs, or punctuation artifacts).

### Agent 3B: Chess Coach & Comment Verifier (Dedicated Content Truth Auditor)

Dedicated specialist receiving the drafted `.pgn`, `cache/<chapter>_idea_dossier.md`, `python-chess`, and **local Stockfish 19**. Its **sole responsibility** is auditing the chess truth, instructional completeness, and clarity of every comment (intro, move notes, RAVs, Gateways, `cont_ravs`, Model Game stops) against the exact board FEN and engine reality:

1. **Fact-check every chess claim against the exact board state:** Catch any false or hallucinated statement in prose: non-existent threats, false pins/forks, claiming a file is open when blocked, mislabeling connected pawns as isolated islands, citing pieces/pawns that already moved or were traded (e.g., claiming a phantom rook or bishop pair), wrong king/piece squares, wrong **bishop/square color complex** (`Bd6`/`Bf4` dark-squared vs `Be2`/`Bf1` light-squared), or `[%cal]` arrows contradicting the written plan.
2. **Engine-backed verification of dismissed moves & illustrative prose (anti-oversimplification / anti-overselling):**
   - Run local Stockfish 19 on **every prose claim that says `"Black/White cannot play X"`, `"forced"`, or dismisses an unshown reply as bad** — issue a **`HARD_VETO`** if Stockfish 19 shows that the dismissed move is actually playable, equal, or best (`#1`)!
   - Run local Stockfish 19 on any unverified illustrative claim or opponent reply; issue `HARD_VETO` whenever prose oversells an equal (`~0.00–0.20`) line as winning or invents strawman opponent blunders instead of natural defenses.
3. **Consistency-break & Idea Dossier coverage check:**
   - Verify every **repertoire consistency break** (deviating from the chapter's default reflex, e.g., `Bc1` instead of `Bh4`) explicitly explains *why* the default repertoire move fails or loses punch on this specific board.
   - Cross-check comments and Gateways against **`cache/<chapter>_idea_dossier.md`** so real GM middlegame ideas/plans are never omitted, while verifying every capture/exchange justification and open/closed structural plan holds logically on the board.
4. **Level-calibrated pacing & language polish:** Flag empty 1000-Elo filler that adds zero position-specific value (while preserving concise notes on basic-looking moves like `O-O` whenever timing or safety actually matters in that line), confirm warm friendly opening-guide tone with proportional brevity on forced blunders, and verify clean grammar, diacritics, chess terminology, and case agreement in the user's language (e.g., Polish).

### Gate 2 Resolution

- Each agent outputs `VERDICT: PASS | SOFT_VETO | HARD_VETO` with an exact line/ply diff list.
- Both `Agent 3A` and `Agent 3B` must return `PASS` (max **2 revision rounds**). Any move change discovered during Gate 2 must pass Agent 1 again before Phase 3.

## Phase 3: Deterministic Technical Gate and Delivery (Main Model)

Never validate PGN syntax or legality by eye. Before delivering the file, run:

1. `validate_chessable.py <output.pgn> --engine-check --side <white|black>` (must exit with status `0` — zero parse errors, 100% legal mainlines and RAVs, valid arrow origins, zero forbidden prose characters or HTML tags, and zero tactical blunders on repertoire lines; verbatim historical Model Games skip engine blunder checks while keeping full structural, move-legality, and arrow checks).
2. `coverage <output.pgn> --max-ply <full_target_depth>` (final confirmation across the **entire repertoire move depth**, e.g. `--max-ply 24`–`26`, that no `> 5%` opponent reply was dropped during PGN assembly).

### Strict Release Gate

Deliver the final `.pgn` ONLY when ALL FIVE conditions hold:

- Agent 1 (Verifier) = `PASS` (or user-approved Soft Veto)
- Agent 2 (Critic) = `PASS` (or user-approved Soft Veto)
- Agent 3A (Technical, Visual & Authenticity Auditor) = `PASS`
- Agent 3B (Chess Coach & Comment Verifier) = `PASS`
- `validate_chessable.py --engine-check` = `PASSED` (exit code `0`)

### Handover Summary

Provide a compact release report alongside the `.pgn`:

- Verification summary: Stockfish 19 depth/settings used, DB presets checked (noting if `/lichess` was skipped due to missing token), coverage status, line count, RAV count, and `validate_chessable.py` pass confirmation.
- Any accepted `SOFT_VETO` trade-offs and verified model games included.
- Short Chessable import reminder: import into a test chapter with **"Import all sub-variations as their own item" UNTICKED**, and manually mark any intro/model-game entries as **Informational**.

## Gotchas

- **Writing prose before Gate 1:** Always freeze the bare move tree first; never spend tokens annotating branches that Agent 1 or Agent 2 may reject.
- **Confusing RAV links with separate lines:** Keep sidelines inline in PGN and remind the user to leave sub-variation splitting unticked on Chessable import.
- **Rubber-stamping between agents:** Keep Agent 1, Agent 2, Agent 3A, and Agent 3B in clean, isolated contexts so they critique the actual PGN and tool output rather than agreeing with the Main Model's reasoning.
- **Early `coverage` `--max-ply` cutoffs & leaf DB blind spots:** Never cap `coverage` below the chapter's actual line length (e.g., `--max-ply 18` misses 24–25-ply deviations and leaves). Always pair full-depth `coverage` with explicit `/masters` + `/lichess` checks on leaf positions so popular human continuations (such as aggressive knight jumps like `...Nh5`) are covered even when SF19 `MultiPV` prefers quieter moves.
- **Unverified master games:** Never quote a master game from memory; every move must come from `/masters` or user-supplied PGN.
- **Burning CPU on known theory:** Always check `cloud` and the SQLite cache before running deep local Stockfish 19 searches.
