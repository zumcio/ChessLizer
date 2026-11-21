---
name: chessable-pgn
description: Turn a normal PGN (Lichess study chapter, ChessBase export, hand-written repertoire, or newly authored course lines with long prose comments) into PGN files that import cleanly into Chessable, with one trainable variation per line, clickable move links inside comments, clean section headers, real line breaks, and non-collapsing bullet lists. Use whenever the user mentions Chessable, a Chessable course or import, "import from PGN", clickable variations/moves in comments, or wants a Lichess study/PGN prepared for a chess course - even if they only say "format this PGN for Chessable" or complain that moves in comments are not clickable or that line breaks/lists break after import.
---

# Chessable PGN Preparation

Chessable's PGN importer is quirky and strips most HTML/Markdown tags. Everything below was verified by real imports—follow it strictly instead of guessing.

## What the Importer Actually Does (Tested Facts)

| Goal | What Works | What Does NOT Work |
|---|---|---|
| Clickable move links inside comments | Real PGN sidelines `( ... )` attached to the comment's own move, imported with **"Import all sub-variations as their own item" UNTICKED**. Moves render as inline blue links. | Typing `(6. Bc4 Qb6)` or `[text]` inside `{}` prose: the importer turns `(` into `@@StartBracket@@` and shows plain text, not a link. |
| Prose *after* a link, on the same line | Put the prose in the **sideline's own comment** after its last move (e.g., `( 13. Bb3 e4 14. Nd2 { — opis. } )`). Renders inline in black while every move stays clickable. | Prose placed after `)` in the main comment: consecutive comments merge, pushing all text **before** all links. |
| One trainable line per idea | One PGN game per leaf line (full path from move 1). | Ticking "Import all sub-variations as their own item" turns every tiny link sideline into a separate trainable variation. |
| Line breaks & spacing | `<br>` (line break), `<br><br>` (paragraph gap), `<br><br><br>` (wide section break). | Raw `\n`, blank lines, `<p>...</p>`, `&#10;`, `&NewLine;`, U+2028, `\r` — all flattened or stripped. |
| Section headers | ALL CAPS framed with box-drawing bars and generous breaks: `<br><br><br>━━━ SECTION TITLE ━━━<br><br>` | `<h3>`, `<b>`, `<strong>`, `<hr>`, `**bold**`, `[b]bold[/b]` — HTML tags are stripped (often gluing headings to text); Markdown/BBCode render as raw characters. |
| Bullet lists (ALL lists) | Plain Unicode bullets separated by double breaks: `• Label — text.<br><br>• Label 2 — text.` | `<ul><li>...</li></ul>` (stripped by importer, gluing the first item to the heading!), `- item`, `1)` raw lines. |
| Inline emphasis (bold / italic) | None via PGN markup—Chessable only auto-bolds recognized chess moves/squares (`d4`, `Nf6`, `a2-g8`, `dxe5`). Build visual hierarchy with short paragraphs, `━━━ HEADERS ━━━`, and `• ` bullets. | `<b>`, `<strong>`, `<i>`, `<em>`, `<u>`, `**...**`, `*...*`, `[b]`, `[i]`. |
| Arrows / square highlights | `[%csl ...]` and `[%cal ...]` placed in their **own `{ }` block** immediately after the prose comment. | Mixing arrows into prose without separation or originating arrows from empty squares. |
| Move annotations | Standard PGN NAGs: `!` = `$1`, `?` = `$2`, `!!` = `$3`, `??` = `$4`, `!?` = `$5`, `?!` = `$6`. | Raw symbols without NAGs when strict PGN compliance is needed. |
| Variation titles | `[White "<title>"]` and `[Black ""]`. | Leaving `[White]` generic (Chessable displays `White vs. Black`; if `"Untitled"` appears for Black, adjust the *"Format of variations/games title"* dropdown on the import page). |

### Additional Importer Rules
- **Anchor move repetition:** A sideline link always branches from the move it belongs to, so when continuing *after* that move, it repeats the move itself (e.g., `13. Bb3 e4 14. Nd2 ...` attached to `13. Bb3`). This is expected Chessable behavior.
- **No brackets or braces in prose:** Never use `(`, `)`, `[`, `]`, `{`, or `}` inside prose comments—replace parenthetical remarks with em-dashes (`—`).
- **One growing line = one sideline:** A single continuous explanation with several moves should be one RAV sideline with inline `{ ... }` comments between moves, rather than multiple separate sidelines repeating the same start.
- **Inline Interleaving Pattern (links right where explained):** Because Chessable merges consecutive main `{ }` comment blocks *before* all sidelines, NEVER put two separate prose explanations in the main comment and dump two sidelines at the bottom. Instead, place intro prose in the move's main `{ }`, then interleave each sideline with bridge prose inside its own trailing `{ ... }` comment: e.g., `9. Rc1! { Wstęp... } ( 9... Qxa2 10. Nxa2 Bxd2+ 11. Kxd2 { — traci figurę.<br><br>Co z 9. a3?: } ) ( 9. a3 Nxc3 10. axb4 Qxa1+ { — traci wieżę.<br><br>Podsumowanie... } )`. Chessable renders each sideline's trailing `{}` comment inline in black right after that sideline's blue links!
- **No plain-text move sequences on a move:** Any concrete 2+ move tactical/strategic variation discussed on a move (including opponent traps or refutations like `9... Qxa2?? 10. Nxa2` on `9. Rc1!`) must be emitted as an anchor-repeated (or direct) RAV sideline on that exact move, not written solely as plain text inside `{}`.
- **Color-coded arrows convention (for repertoire courses):**
  - `G` (Green) — pawns, pawn pushes, and pawn breaks (`Gf2f3`, `Gc4d5`).
  - `B` (Blue) — piece maneuvers, target squares, active files/diagonals (`Bf3e5`, `Ba3c5`).
  - `R` (Red) — opponent threats, counterplay, and target weaknesses (`Rc5`, `Rf6e4`).
  - `Y` (Yellow) — turning points, move-order traps, and tactical nuances (`Ya2`, `Yd4d5`).
- **Manual-only Chessable features:** Key moves, diagrams, links between variations, *Informational* flags, and course settings cannot be set via PGN—remind the user to set them in Chessable after import.

## Workflow

### 1. Clarify Input & Granularity
Identify whether the source is an existing PGN/Lichess study to convert or newly authored repertoire lines. Default to **one PGN game per trainable leaf line** unless the user asks to keep everything in one game.

### 2. Clean & Structure the Prose
- Preserve the author's voice, tone, and wording when converting existing text; fix typos/punctuation only when requested or clearly broken.
- Normalize chess notation in prose: one space after move numbers (`14. Nd2`), `11...` never `11....`, castling as `O-O` / `O-O-O` (never `0-0`).
- Remove all `(`, `)`, `[`, `]`, `{`, `}`, raw newlines (`\n`), and stripped HTML tags (`<ul>`, `<li>`, `<b>`, `<i>`, `<p>`, etc.) from prose comments.
- Structure long comments cleanly (never glue multi-point explanations like `Warstwa 1`, `Warstwa 2`, ... into one continuous wall of text — separate every distinct point with `<br><br>` or `• ...<br><br>`):
  - Short paragraphs (2–3 sentences) separated by `<br><br>`.
  - Section headers formatted as `<br><br><br>━━━ SECTION TITLE ━━━<br><br>`.
  - Lists formatted as `• Label — explanation.<br><br>• Label 2 — explanation.`.

### 3. Convert Move Mentions to Clickable Sidelines & Add Visuals
- Turn every concrete 2+ move variation/refutation (including opponent traps and alternatives) into a legal PGN RAV sideline `( ... )` attached directly to the move being commented on, using the **Inline Interleaving Pattern** (trailing explanation + bridge text to the next idea inside each sideline's `{ ... }` comment) so clickable blue links sit right next to their explanations instead of piled at the bottom.
- Mentions without a move sequence (single square/piece references like `e5` or `Nf6`) stay in prose (Chessable auto-bolds them automatically).
- Place `[%csl ...]` / `[%cal ...]` tags in a dedicated `{ }` block right after the prose comment, before any `( ... )` sidelines.
- Use descriptive titles in `[White "..."]` with `[Black ""]`, e.g., `1.1 Ortodoksyjna: 7. Rc1 c6 13. Bb3 – Cichy nacisk Karpowa`.

### 4. Verify with `python-chess` (Mandatory When Sandbox Is Available)
Before handing over the PGN, run a Python verification pass using `python-chess` (`chess.pgn.read_game`) to confirm:
1. Zero PGN parse errors across all games and all RAV sidelines.
2. Every move in every mainline and sideline is legal from its exact board state.
3. Every arrow (`[%cal]`) originates from a square occupied by a piece in that exact position (highlights `[%csl]` may target empty squares).
4. Zero raw newlines, zero `0-0`, zero `( ) [ ]` characters, and zero stripped HTML tags (`<ul>`, `<li>`, `<b>`, `<i>`, `<p>`) inside prose comments.

Never claim a PGN is verified without actually running this check.

### 5. Hand Over with Import Checklist
Briefly remind the user to:
1. Import into a **test chapter** first with **"Import all sub-variations as their own item" UNTICKED**.
2. Check the first commented move with links: verify inline blue links, black trailing text, clean `━━━` headers, `• ` bullets, and arrows.
3. Manually set any *Informational* entries, key moves, diagrams, and title-format dropdown (`White vs. Untitled`) in Chessable.

## Troubleshooting Common Import Issues
- **Links show as `@@StartBracket@@` or plain text:** Moves or parentheses were left inside `{}` prose instead of real `( ... )` RAV sidelines.
- **Heading glued to first bullet:** `<ul><li>` tags were used and stripped by Chessable—replace with `<br><br><br>━━━ HEADER ━━━<br><br>• item`.
- **Entire comment collapsed into one wall of text:** Raw `\n` newlines were used instead of `<br><br>`.
- **Every sideline became its own trainable variation:** "Import all sub-variations as their own item" was left ticked during import.
- **Links appear at the bottom of the *next* move's comment:** Sidelines were attached as alternatives to the next move instead of the comment's own move.
