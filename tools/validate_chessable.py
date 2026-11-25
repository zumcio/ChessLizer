"""Chessable PGN validator (+ optional Stockfish soundness check across all games/lines).

Enforces all rules from the chessable-pgn skill:
1. Zero PGN parse errors across all games and all RAV sidelines.
2. Every move in every mainline and sideline is legal from its exact board state.
3. Every arrow ([%cal ...]) originates from an occupied square in that exact position.
4. Zero raw newlines, zero 0-0, zero ()[]{} characters, and zero stripped HTML tags
   (<ul>, <li>, <b>, <i>, <p>, <h3>, <strong>, <em>, <u>, <hr>) inside prose comments.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

import chess
import chess.pgn

from chess_env import CACHE_DB, LichessClient, StockfishAnalyzer, parse_position
from export_fact_sheet import classify_game, enemy_pawn_attackers, find_batteries, find_pins, is_light_sq

CAL_RE = re.compile(r"\[%cal\s+([^\]]+)\]")
CSL_RE = re.compile(r"\[%csl\s+([^\]]+)\]")
CMD_TAG_RE = re.compile(r"\[%[a-zA-Z]+\s+[^\]]*\]")
LICHESS_ID_RE = re.compile(r"lichess\.org/([A-Za-z0-9]{8})")
FORBIDDEN_HTML_RE = re.compile(r"</?(?:ul|ol|li|b|strong|i|em|u|p|h[1-6]|hr|div|span)\b[^>]*>", re.IGNORECASE)
ZERO_CASTLE_RE = re.compile(r"\b0-0(?:-0)?\b")
FORBIDDEN_CHARS_RE = re.compile(r"[()\[\]{}]")
ROBOTIC_LAYER_RE = re.compile(r"(?<!<br>)\bWarstwa\s+[2-4]\b")
MOVE_SEQ_RE = re.compile(
    r"\b\d+\.\s*(?:\.\.\s*)?(?:[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]|O-O(?:-O)?)[+#!?]*\s+"
    r"(?:\d+\.\s*(?:\.\.\s*)?)?(?:[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]|O-O(?:-O)?)"
)
PIN_WORD_RE = re.compile(r"\bpins?\b", re.IGNORECASE)
PIN_EXEMPT_RE = re.compile(
    r"\b(?:no\s+pin|not\s+pin|unpin\w*|breaks?\s+the\s+pin|without\s+pinning|to\s+pin|will\s+pin|once\s+[^.]*\barrives|preparing\s+[^.]*\bpin)\b",
    re.IGNORECASE,
)
BATTERY_WORD_RE = re.compile(r"\bbattery\b", re.IGNORECASE)
BATTERY_LINE_RE = re.compile(r"\b([a-h][1-8])-([a-h][1-8])\s+battery\b", re.IGNORECASE)
BATTERY_EXEMPT_RE = re.compile(
    r"\b(?:aims?\s+a\s+battery|aim\s+a\s+battery|prepares?\s+a\s+battery|builds?\s+a\s+battery|sets?\s+up\s+a\s+battery|future\s+battery)\b",
    re.IGNORECASE,
)
DISAMBIG_MOVE_RE = re.compile(r"(?<!\w)([RNB])([a-h]|[1-8])x?([a-h][1-8])\b")
MOVE_NUM_PRE_RE = re.compile(r"\d+\.(?:\.\.)?\s*$")
BARE_SQ_TO_SQ_RE = re.compile(r"(?<![KQRBN])\b([a-h][1-8])\s+to\s+([a-h][1-8])\b")
LEAVES_WEAKER_RE = re.compile(r"\bleaves?\s+([a-h][1-8])\s+weaker\b", re.IGNORECASE)
ROOK_PRESSURE_RE = re.compile(r"\bR([a-h])([1-8])\b[^.<]*\bpressure\s+([a-h][1-8])\b", re.IGNORECASE)
OUTPOST_SQ_RE = re.compile(
    r"\b(?:([a-h][1-8])\s+(?:[A-Za-z-]+\s+)?(?:outpost|hole)|(?:outpost|holes?)\s+(?:on|at)\s+([a-h][1-8](?:\s*(?:,|and|/)\s*[a-h][1-8])*))\b",
    re.IGNORECASE,
)
JUMP_PLANT_SQ_RE = re.compile(
    r"\b(?:jump|plant|lands?|anchors?|stations?|sinks?)\s+(?:(?:a\s+)?knight\s+(?:on|to|into)\s+|N)([a-h][1-8])\b",
    re.IGNORECASE,
)
PAWN_COMMIT_RE = re.compile(r"\b(?:once|after|commits?)\s+[^.;]*?\.\.\.\s*([a-h][1-8])\b", re.IGNORECASE)
SQ_COLOR_PHRASE_RE = re.compile(
    r"\b(light|dark)[-\s]+squares?\s+(?:on|at)\s+([a-h][1-8](?:\s*(?:,|and|/)\s*[a-h][1-8])*)\b",
    re.IGNORECASE,
)
REJECT_RAV_COMMENT_RE = re.compile(
    r"\b(?:avoid|never|blunder|mistake|loses|loser|inferior|weaker|dubious|bad|poor|walks\s+(?:straight\s+)?into)\b",
    re.IGNORECASE,
)
GM_VS_CITE_RE = re.compile(
    r"\b(?:[Ii]n|[Aa]s\s+in)\s+([A-Z][A-Za-z-]+)(?:\s+[A-Z][A-Za-z-]+)?\s+vs\.?\s+([A-Z][A-Za-z-]+)",
)
PLAIN_MOVE_TOK_RE = re.compile(
    r"(?<![A-Za-z0-9])(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|(?:[a-h]x)?[a-h][2-7])[+#!?]*"
)
COND_PAIR_RE = re.compile(
    r"\b(?:against|meet|after|if)\s+(?:\d+\.\.\.\s*)?([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]|O-O(?:-O)?)[?!]*[^.]{0,30}?"
    r"(?:,\s*(?:play\s+|with\s+|try\s+|answer\s+with\s+)?|\bwith\s+)(?:\d+\.\s*)?(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h][2-7])[!?]*",
    re.IGNORECASE,
)


def strip_command_tags(comment: str) -> str:
    return CMD_TAG_RE.sub("", comment)


def _norm_san(san: str) -> str:
    return re.sub(r"[+#!?]+$", "", san.strip()).replace("0-0-0", "O-O-O").replace("0-0", "O-O")


def _load_cached_gm_games() -> dict[tuple[str, str], dict[str, object]]:
    """Load offline cached Lichess Masters PGNs indexed by lowercase (White surname, Black surname)."""
    out: dict[tuple[str, str], dict[str, object]] = {}
    if not CACHE_DB.is_file():
        return out
    try:
        with sqlite3.connect(CACHE_DB) as conn:
            rows = conn.execute("SELECT payload FROM api_cache WHERE cache_key LIKE 'master_pgn|%'").fetchall()
    except sqlite3.Error:
        return out
    for (payload_s,) in rows:
        try:
            raw_pgn = str(json.loads(payload_s).get("pgn", ""))
            g = chess.pgn.read_game(io.StringIO(raw_pgn))
            if g is None:
                continue
            w_hdr = g.headers.get("White", "")
            b_hdr = g.headers.get("Black", "")
            w_sur = re.split(r"[,\s]+", w_hdr.strip())[0].lower()
            b_sur = re.split(r"[,\s]+", b_hdr.strip())[0].lower()
            if not w_sur or not b_sur:
                continue
            b = g.board()
            sans: set[str] = set()
            mvs = list(g.mainline_moves())
            ucis: list[str] = []
            for mv in mvs:
                sans.add(_norm_san(b.san(mv)))
                ucis.append(mv.uci())
                b.push(mv)
            out[(w_sur, b_sur)] = {"sans": sans, "mvs": mvs, "init": g.board(), "ucis": ucis}
        except Exception:
            continue
    return out


def _collect_rav_san_tokens(
    node: chess.pgn.GameNode, board: chess.Board, board_before: chess.Board | None = None
) -> tuple[set[str], set[str]]:
    """Return (all_san_tokens, first_opp_moves) across all RAV branches attached to `node` or anchored on `node.parent`."""
    all_sans: set[str] = set()
    first_moves: set[str] = set()

    def _walk(n: chess.pgn.GameNode, b: chess.Board) -> None:
        for ch in n.variations:
            s = _norm_san(b.san(ch.move))
            all_sans.add(s)
            b.push(ch.move)
            _walk(ch, b)
            b.pop()

    if node.variations:
        start_idx = 0 if "━━━ SAMPLE CONTINUATIONS ━━━" in (node.comment or "") or "━━━ PRZYKŁADOWE KONTYNUACJE ━━━" in (node.comment or "") else 1
        for ch in node.variations[start_idx:]:
            s = _norm_san(board.san(ch.move))
            first_moves.add(s)
            all_sans.add(s)
            board.push(ch.move)
            _walk(ch, board)
            board.pop()
    elif node.parent is not None and len(node.parent.variations) > 1 and board_before is not None:
        # Anchor-repeated cont_ravs on leaf.parent (e.g. (11. Nge2 a4 12. h4 ...))
        b_anc = board_before.copy(stack=False)
        for ch in node.parent.variations[1:]:
            b_anc.push(ch.move)
            for opp_ch in ch.variations:
                first_moves.add(_norm_san(b_anc.san(opp_ch.move)))
                break
            _walk(ch, b_anc)
            b_anc.pop()
    return all_sans, first_moves


def _extract_action_pawn_moves(text: str) -> set[str]:
    """Return pawn pushes/captures written explicitly as move actions (breaks, captures, !, +, or chained)."""
    acts: set[str] = set()
    for m in re.finditer(
        r"(?:(?:\b(?:push|play|break|strike|thrust|launch|advance|with|meet\s+[^.,;]{1,25}\s+with)\s+|(?:\+|\b\d+\.\s*))"
        r"([a-h][3-6])|([a-h]x[a-h][2-7])|([a-h][3-6])[!+])",
        text,
        re.IGNORECASE,
    ):
        tok = m.group(1) or m.group(2) or m.group(3)
        if tok:
            acts.add(tok.lower())
    return acts


def _extract_clause_moves(text: str) -> list[str]:
    """Extract SAN-like tokens from prose, expanding hyphenated Nc1-a2 -> Nc1, Na2 while ignoring square ranges."""
    expanded: list[str] = []
    # Expand piece route like Nc1-a2 -> Nc1 Na2 before scanning
    norm_txt = re.sub(r"\b([KQRBN])([a-h][1-8])-([a-h][1-8])\b", r"\1\2 \1\3", text)
    for m in PLAIN_MOVE_TOK_RE.finditer(norm_txt):
        tok = _norm_san(m.group(1))
        if tok not in expanded:
            expanded.append(tok)
    return expanded


def _extract_lichess_id(game: chess.pgn.Game) -> str | None:
    lid = game.headers.get("LichessId", "").strip()
    if re.fullmatch(r"[A-Za-z0-9]{8}", lid):
        return lid
    for hdr in ("Site", "Event", "White"):
        m = LICHESS_ID_RE.search(game.headers.get(hdr, ""))
        if m:
            return m.group(1)
    return None


def _rav_uci_path(node: chess.pgn.GameNode) -> tuple[str, ...]:
    seq: list[str] = []
    cur: chess.pgn.GameNode | None = node
    while cur is not None and cur.move is not None:
        seq.append(cur.move.uci())
        cur = cur.variations[0] if cur.variations else None
    return tuple(seq)


def _collect_mainline_and_ravs(game: chess.pgn.Game) -> tuple[tuple[str, ...], dict[int, set[tuple[str, ...]]], chess.pgn.GameNode]:
    main_ucis: list[str] = []
    ravs_by_ply: dict[int, set[tuple[str, ...]]] = {}
    node: chess.pgn.GameNode = game
    ply = 0
    while node.variations:
        for rav in node.variations[1:]:
            ravs_by_ply.setdefault(ply, set()).add(_rav_uci_path(rav))
        main_child = node.variations[0]
        if main_child.move is not None:
            main_ucis.append(main_child.move.uci())
        node = main_child
        ply += 1
    if node.variations:
        for rav in node.variations[1:]:
            ravs_by_ply.setdefault(ply, set()).add(_rav_uci_path(rav))
    return tuple(main_ucis), ravs_by_ply, node


def _rav_subtree_has_prose(node: chess.pgn.GameNode) -> bool:
    if node.comment and strip_command_tags(node.comment).strip():
        return True
    return any(_rav_subtree_has_prose(ch) for ch in node.variations)


def _piece_exists_on_disambig(
    board: chess.Board,
    board_before: chess.Board | None,
    piece_sym: str,
    disambig: str,
    color: chess.Color,
) -> bool:
    pt = {"R": chess.ROOK, "N": chess.KNIGHT, "B": chess.BISHOP}[piece_sym]
    for b in (board, board_before):
        if b is None:
            continue
        for sq in b.pieces(pt, color):
            if disambig.isalpha() and chess.FILE_NAMES[chess.square_file(sq)] == disambig:
                return True
            if disambig.isdigit() and str(chess.square_rank(sq) + 1) == disambig:
                return True
    return False


def _parse_game_selection(spec: str | None) -> set[int] | None:
    """Parse 1-based game selection like '1-10' or '1,3,5-8' into a set of indices."""
    if not spec:
        return None
    selected: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s.strip()), int(hi_s.strip())
            if lo > hi:
                lo, hi = hi, lo
            selected.update(range(lo, hi + 1))
        else:
            selected.add(int(part))
    return selected


def validate_pgn_file(
    pgn_path: Path,
    engine_check: bool = False,
    depth: int = 16,
    blunder_cp: int = 70,
    soft_cp: int = 35,
    our_side: str | None = None,
    skeleton_path: Path | None = None,
    verify_models: bool = False,
    check_plan: bool = False,
    check_claims: bool = False,
    check_intros: bool = False,
    game_range: str | None = None,
    trainable_only: bool = False,
    flags_out: list[str] | None = None,
    use_provenance: bool = False,
) -> tuple[list[str], list[str], int, int]:
    eff_check_claims = (check_claims or check_plan) and not use_provenance
    selected_games = _parse_game_selection(game_range)
    errors: list[str] = []
    warnings: list[str] = []
    sanity_flags: list[str] = flags_out if flags_out is not None else []
    game_count = 0
    selected_idx = 0
    rav_count = 0
    skipped_non_trainable = 0

    trainable_games: list[tuple[int, str, chess.pgn.Game]] = []
    model_games: list[tuple[int, str, chess.pgn.Game]] = []
    gm_cache = _load_cached_gm_games() if (eff_check_claims or verify_models) else {}

    sf: StockfishAnalyzer | None = None
    sf_top_cache: dict[str, list[object]] = {}
    sf_move_cache: dict[tuple[str, str], object | None] = {}
    if engine_check:
        sf = StockfishAnalyzer()
        sf.open()

    def check_move_cached(b: chess.Board, san: str) -> dict[str, object]:
        assert sf is not None
        epd = b.epd()
        if epd not in sf_top_cache:
            sf_top_cache[epd] = sf.analyze(b, depth=depth, multipv=3)
        top_lines = sf_top_cache[epd]
        norm = san.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
        cand_move = b.parse_san(norm)
        uci = cand_move.uci()
        cand_line = next((ln for ln in top_lines if ln.move_uci == uci), None)  # type: ignore[attr-defined]
        if cand_line is None:
            mkey = (epd, uci)
            if mkey not in sf_move_cache:
                iso = sf.analyze(b, depth=depth, multipv=1, root_moves=[cand_move])
                sf_move_cache[mkey] = iso[0] if iso else None
            cand_line = sf_move_cache[mkey]
        best = top_lines[0] if top_lines else None
        cp_loss: int | None = None
        if best and cand_line and best.score_cp is not None and cand_line.score_cp is not None:  # type: ignore[attr-defined]
            sign = 1 if b.turn == chess.WHITE else -1
            cp_loss = max(0, (best.score_cp - cand_line.score_cp) * sign)  # type: ignore[attr-defined]
        return {"candidate": cand_line, "best": best, "cp_loss": cp_loss}

    try:
        with pgn_path.open("r", encoding="utf-8-sig") as fh:
            while True:
                game = chess.pgn.read_game(fh)
                if game is None:
                    break
                kind = classify_game(game)
                if trainable_only and kind != "trainable":
                    continue
                game_count += 1
                selected_idx += 1
                if selected_games is not None and selected_idx not in selected_games:
                    continue
                title = game.headers.get("White", f"Game #{game_count}")
                prefix = f"[Game {game_count}: {title}]"
                is_trainable = kind == "trainable"
                if kind == "trainable":
                    trainable_games.append((game_count, title, game))
                elif kind == "model":
                    model_games.append((game_count, title, game))

                check_sf_this_game = is_trainable or (check_intros and kind == "intro")
                if sf is not None and not check_sf_this_game:
                    skipped_non_trainable += 1

                if game.errors:
                    for err in game.errors:
                        errors.append(f"{prefix} PGN parse error: {err}")

                if game.headers.get("Black", "").strip() not in {"", "?"}:
                    warnings.append(
                        f"{prefix} [Black] header is '{game.headers.get('Black')}' "
                        "(recommended: empty string '' for Chessable variation titles)."
                    )

                def check_comment(
                    raw: str,
                    board: chess.Board,
                    where: str,
                    has_rav_context: bool = True,
                    board_before: chess.Board | None = None,
                    last_move: chess.Move | None = None,
                    rav_boards: list[chess.Board] | None = None,
                    node_for_rav_scan: chess.pgn.GameNode | None = None,
                    is_main: bool = True,
                    path: list[str] | None = None,
                ) -> None:
                    if not raw:
                        return

                    # Check [%cal ...] arrows originate from occupied squares
                    cal_count = 0
                    for m in CAL_RE.finditer(raw):
                        for tok in m.group(1).split(","):
                            tok = tok.strip()
                            if len(tok) != 5 or tok[0] not in "GBRY":
                                errors.append(f"{prefix} {where}: Malformed [%cal] arrow '{tok}'.")
                                continue
                            cal_count += 1
                            try:
                                from_sq = chess.parse_square(tok[1:3])
                                chess.parse_square(tok[3:5])
                            except ValueError:
                                errors.append(f"{prefix} {where}: Invalid square in [%cal] '{tok}'.")
                                continue
                            if board.piece_at(from_sq) is None:
                                errors.append(
                                    f"{prefix} {where}: [%cal] arrow '{tok}' starts on EMPTY square {tok[1:3]}."
                                )
                    if cal_count >= 6:
                        warnings.append(
                            f"{prefix} {where}: {cal_count} arrows on one move — consider running render-svg spot-check to verify readability."
                        )

                    # Check [%csl ...] square highlights syntax
                    for m in CSL_RE.finditer(raw):
                        for tok in m.group(1).split(","):
                            tok = tok.strip()
                            if len(tok) != 3 or tok[0] not in "GBRY":
                                errors.append(f"{prefix} {where}: Malformed [%csl] highlight '{tok}'.")
                                continue
                            try:
                                chess.parse_square(tok[1:3])
                            except ValueError:
                                errors.append(f"{prefix} {where}: Invalid square in [%csl] '{tok}'.")

                    # Check prose rules after stripping [%cal]/[%csl] command tags
                    prose = strip_command_tags(raw).strip()
                    if "\n" in prose or "\r" in prose:
                        errors.append(f"{prefix} {where}: Raw newline found in prose (use <br> / <br><br>).")
                    if ZERO_CASTLE_RE.search(prose):
                        errors.append(f"{prefix} {where}: Castling written as 0-0/0-0-0 (use O-O / O-O-O).")
                    bad_html = FORBIDDEN_HTML_RE.findall(prose)
                    if bad_html:
                        errors.append(f"{prefix} {where}: Stripped HTML tag(s) in prose: {bad_html}.")
                    bad_chars = FORBIDDEN_CHARS_RE.findall(prose)
                    if bad_chars:
                        errors.append(
                            f"{prefix} {where}: Forbidden bracket/brace chars in prose: {sorted(set(bad_chars))}."
                        )

                    # Readability & clickable-link warnings (non-blocking)
                    if ROBOTIC_LAYER_RE.search(prose):
                        warnings.append(
                            f"{prefix} {where}: Robotic inline 'Warstwa N' label without <br><br> break."
                        )
                    for para in prose.split("<br><br>"):
                        if len(para.strip()) > 700:
                            warnings.append(
                                f"{prefix} {where}: Paragraph exceeds 700 chars ({len(para.strip())} chars) — split with <br><br> or bullets."
                            )
                            break
                    if not has_rav_context and MOVE_SEQ_RE.search(prose):
                        warnings.append(
                            f"{prefix} {where}: Multi-move sequence in prose without attached RAV sideline (not clickable in Chessable)."
                        )

                    # Deterministic board-truth claim checks
                    if eff_check_claims and prose and kind != "model":
                        clean_txt = prose.replace("<br>", " ")
                        for sent in re.split(r"(?<!\.\.)(?<!\b\d)(?<!\b\d\d)(?<=[.!?])\s+|\s*•\s*", clean_txt):
                            sent_s = sent.strip()
                            if not sent_s:
                                continue
                            if PIN_WORD_RE.search(sent_s) and not PIN_EXEMPT_RE.search(sent_s):
                                if not find_pins(board):
                                    errors.append(
                                        f"{prefix} {where}: Phantom pin claim (no active pin on board): '{sent_s[:90]}'."
                                    )
                            if BATTERY_WORD_RE.search(sent_s) and not BATTERY_EXEMPT_RE.search(sent_s):
                                batts = find_batteries(board)
                                bm_line = BATTERY_LINE_RE.search(sent_s)
                                if not batts:
                                    errors.append(
                                        f"{prefix} {where}: Phantom battery claim (no aligned Q+B/Q+R/R+R battery on board): '{sent_s[:90]}'."
                                    )
                                elif bm_line:
                                    s1 = chess.parse_square(bm_line.group(1))
                                    s2 = chess.parse_square(bm_line.group(2))
                                    f1, r1 = chess.square_file(s1), chess.square_rank(s1)
                                    f2, r2 = chess.square_file(s2), chess.square_rank(s2)
                                    df, dr = f2 - f1, r2 - r1
                                    line_match = False
                                    for b_tok in batts:
                                        m_sq = re.search(r"\(([a-h][1-8])-([a-h][1-8])\)", b_tok)
                                        if not m_sq:
                                            continue
                                        bs1 = chess.parse_square(m_sq.group(1))
                                        bs2 = chess.parse_square(m_sq.group(2))
                                        bf1, br1 = chess.square_file(bs1), chess.square_rank(bs1)
                                        bf2, br2 = chess.square_file(bs2), chess.square_rank(bs2)
                                        # Both battery pieces must be collinear with s1-s2
                                        if (bf1 - f1) * dr == (br1 - r1) * df and (bf2 - f1) * dr == (br2 - r1) * df:
                                            line_match = True
                                            break
                                    if not line_match:
                                        errors.append(
                                            f"{prefix} {where}: Phantom {bm_line.group(1)}-{bm_line.group(2)} battery claim (found {batts}): '{sent_s[:90]}'."
                                        )
                            for dm in DISAMBIG_MOVE_RE.finditer(sent_s):
                                p_sym, disambig, _ = dm.groups()
                                pre_full = sent_s[: dm.start()]
                                if MOVE_NUM_PRE_RE.search(pre_full):
                                    continue
                                ctx_pre = pre_full[-12:].lower()
                                if "after " in ctx_pre or "future " in ctx_pre or "later " in ctx_pre or "compare with" in sent_s.lower():
                                    continue
                                col = chess.BLACK if re.search(r"\.\.\.\s*$", pre_full) else chess.WHITE
                                tok_mv = dm.group(0)
                                is_castling_rook = (
                                    (
                                        col == chess.WHITE
                                        and "castle" in sent_s.lower()
                                        and (
                                            (tok_mv in {"Rfe1", "Rhf1"} and board.has_kingside_castling_rights(chess.WHITE))
                                            or (tok_mv in {"Rfd1", "Rac1"} and board.has_queenside_castling_rights(chess.WHITE))
                                        )
                                    )
                                    or (
                                        col == chess.BLACK
                                        and "castle" in sent_s.lower()
                                        and (
                                            (tok_mv in {"Rfe8", "Rhf8"} and board.has_kingside_castling_rights(chess.BLACK))
                                            or (tok_mv in {"Rfd8", "Rac8"} and board.has_queenside_castling_rights(chess.BLACK))
                                        )
                                    )
                                )
                                if is_castling_rook:
                                    continue
                                boards_to_check = [board, board_before] + (rav_boards or [])
                                if not any(_piece_exists_on_disambig(rb, None, p_sym, disambig, col) for rb in boards_to_check if rb is not None):
                                    errors.append(
                                        f"{prefix} {where}: Disambiguated move '{dm.group(0)}' references empty/missing {p_sym} on '{disambig}'."
                                    )
                            for bm in BARE_SQ_TO_SQ_RE.finditer(sent_s):
                                warnings.append(
                                    f"{prefix} {where}: Ambiguous '{bm.group(1)} to {bm.group(2)}' without piece letter (e.g. Rc3 to c5)."
                                )
                            for rm in ROOK_PRESSURE_RE.finditer(sent_s):
                                file_ch, rank_ch, target_sq = rm.groups()
                                lower_s = sent_s.lower()
                                if any(w in lower_s for w in ("after ", "once ", "when ", "if ")):
                                    continue
                                f_idx = chess.FILE_NAMES.index(file_ch.lower())
                                r_rank = int(rank_ch) - 1
                                t_rank = int(target_sq[1]) - 1
                                chk_col = chess.BLACK if our_side == "black" else chess.WHITE
                                lo_r, hi_r = min(r_rank, t_rank), max(r_rank, t_rank)
                                for p_sq in board.pieces(chess.PAWN, chk_col):
                                    if chess.square_file(p_sq) == f_idx and lo_r < chess.square_rank(p_sq) < hi_r:
                                        warnings.append(
                                            f"{prefix} {where}: Rook pressure along {file_ch}-file claimed while own pawn on {chess.square_name(p_sq)} blocks it."
                                        )
                                        break
                            # Check outpost/hole and jump/plant pawn-safety claims (0-LLM-token check)
                            claimed_outpost_sqs: list[str] = []
                            for om in OUTPOST_SQ_RE.finditer(sent_s):
                                raw_sqs = om.group(1) or om.group(2) or ""
                                claimed_outpost_sqs.extend(re.findall(r"[a-h][1-8]", raw_sqs.lower()))
                            for jm in JUMP_PLANT_SQ_RE.finditer(sent_s):
                                j_sq = jm.group(1).lower()
                                if j_sq not in claimed_outpost_sqs:
                                    claimed_outpost_sqs.append(j_sq)
                            if claimed_outpost_sqs:
                                is_cond_future = bool(re.search(r"\b(?:after|once|when|if|creating|leaving)\b", lower_s := sent_s.lower()))
                                opp_col = chess.WHITE if our_side == "black" else chess.BLACK
                                our_col = chess.BLACK if our_side == "black" else chess.WHITE
                                commit_sqs = [m.group(1).lower() for m in PAWN_COMMIT_RE.finditer(sent_s)]
                                for sq_s in claimed_outpost_sqs:
                                    sq_i = chess.parse_square(sq_s)
                                    cur_atk, _ = enemy_pawn_attackers(board, sq_i, our_col)
                                    # Exempt only if prose explicitly mentions capturing or vacating the specific pawn attacker
                                    unblocked_atk = [
                                        a for a in cur_atk
                                        if not re.search(rf"(?:x{a}\b|\b{a[0]}x[a-h][1-8]\b)", sent_s)
                                    ]
                                    if unblocked_atk:
                                        errors.append(
                                            f"{prefix} {where}: Claimed outpost/jump square {sq_s} is currently attacked by enemy pawn(s) {','.join(unblocked_atk)}: '{sent_s[:90]}'."
                                        )
                                        continue
                                    # Check if sentence says "once ...g6" where g6 actually attacks the claimed outpost!
                                    if is_cond_future and commit_sqs:
                                        sf_i, sr_i = chess.square_file(sq_i), chess.square_rank(sq_i)
                                        for c_sq_s in commit_sqs:
                                            csq = chess.parse_square(c_sq_s)
                                            cf, cr = chess.square_file(csq), chess.square_rank(csq)
                                            attacks = (cr == sr_i + 1) if opp_col == chess.BLACK else (cr == sr_i - 1)
                                            if abs(cf - sf_i) == 1 and attacks:
                                                errors.append(
                                                    f"{prefix} {where}: Conditional pawn move ...{c_sq_s} defends (not weakens) claimed square {sq_s}: '{sent_s[:90]}'."
                                                )
                            # Check explicit light/dark square color parity claims
                            for cm in SQ_COLOR_PHRASE_RE.finditer(sent_s):
                                want_light = cm.group(1).lower() == "light"
                                for sq_s in re.findall(r"[a-h][1-8]", cm.group(2).lower()):
                                    actual_light = is_light_sq(chess.parse_square(sq_s))
                                    if actual_light != want_light:
                                        actual_lbl = "light" if actual_light else "dark"
                                        errors.append(
                                            f"{prefix} {where}: Square {sq_s} is {actual_lbl}, not {cm.group(1).lower()}: '{sent_s[:90]}'."
                                        )
                        if last_move is not None:
                            for lm in LEAVES_WEAKER_RE.finditer(clean_txt):
                                tsq = chess.parse_square(lm.group(1))
                                if tsq in board.attacks(last_move.to_square):
                                    warnings.append(
                                        f"{prefix} {where}: Comment claims move leaves {lm.group(1)} weaker, yet moved piece directly defends {lm.group(1)}."
                                    )

                        # Leaf plan sanity checks: unbacked multi-move prose recipes, conditional SF test, & GM citations
                        if is_main and kind == "trainable" and (
                            "━━━ PLAN FROM HERE ━━━" in prose
                            or "━━━ PLAN Z TEJ POZYCJI ━━━" in prose
                            or "━━━ GATEWAY TO THE MIDDLEGAME ━━━" in prose
                        ):
                            rav_sans, rav_firsts = _collect_rav_san_tokens(node_for_rav_scan, board, board_before)
                            plan_body = prose.split("━━━ SAMPLE CONTINUATIONS ━━━", 1)[0]
                            for p_sent in re.split(r"(?<!\.\.)(?<!\b\d)(?<!\b\d\d)(?<!\bvs\.)(?<=[.])\s+|\s*•\s*", plan_body.replace("<br>", " ")):
                                ps = p_sent.strip()
                                if not ps or ps.startswith("Verdict:"):
                                    continue
                                clause_mvs = _extract_clause_moves(ps)
                                action_pawns = _extract_action_pawn_moves(ps)
                                def _is_static_piece_ref(mv_tok: str) -> bool:
                                    if len(mv_tok) < 3 or mv_tok[0] not in "KQRBN" or "x" in mv_tok:
                                        return False
                                    try:
                                        dsq = chess.parse_square(mv_tok[-2:])
                                        p = board.piece_at(dsq)
                                        return p is not None and p.symbol().upper() == mv_tok[0]
                                    except ValueError:
                                        return False
                                # Focus strictly on unbacked future piece/castling moves and explicit pawn breaks absent from attached cont_ravs
                                missing_mvs = [
                                    mv for mv in clause_mvs
                                    if mv not in rav_sans
                                    and not _is_static_piece_ref(mv)
                                    and (mv in {"O-O", "O-O-O"} or mv[0] in "KQRBN" or mv in action_pawns)
                                ]
                                if len(clause_mvs) >= 3 and len(missing_mvs) >= 2:
                                    sanity_flags.append(
                                        f"{prefix} {where}: [PROSE-PLAN FLAG] Multi-move prose plan mentions {missing_mvs} not present in attached cont_ravs — verify preconditions/moves on the board."
                                    )
                                # Check direct conditional opponent->our pairs right at the leaf board with SF
                                if sf is not None and check_sf_this_game:
                                    for cm in COND_PAIR_RE.finditer(ps):
                                        opp_s, our_s = _norm_san(cm.group(1)), _norm_san(cm.group(2))
                                        if opp_s in rav_firsts:
                                            continue
                                        try:
                                            opp_mv = board.parse_san(opp_s)
                                        except ValueError:
                                            continue
                                        b_opp = board.copy(stack=False)
                                        b_opp.push(opp_mv)
                                        try:
                                            b_opp.parse_san(our_s)
                                        except ValueError:
                                            continue
                                        res_cond = check_move_cached(b_opp, our_s)
                                        loss_c = res_cond["cp_loss"]
                                        if loss_c is not None and loss_c > blunder_cp:  # type: ignore[operator]
                                            best_c = res_cond["best"]
                                            errors.append(
                                                f"{prefix} {where}: Conditional plan '...{opp_s} -> {our_s}' loses {loss_c} cp (best {best_c.move_san if best_c else '?'}: {best_c.score_str if best_c else '?'})."  # type: ignore[attr-defined]
                                            )
                                        elif loss_c is not None and loss_c >= soft_cp:  # type: ignore[operator]
                                            sanity_flags.append(
                                                f"{prefix} {where}: [CONDITIONAL FLAG] '...{opp_s} -> {our_s}' loses {loss_c} cp vs SF best."
                                            )
                                # Verify GM game citations ("as in Player1 vs. Player2")
                                if gm_cache:
                                    for gm_m in GM_VS_CITE_RE.finditer(ps):
                                        s1, s2 = gm_m.group(1).lower(), gm_m.group(2).lower()
                                        entry = gm_cache.get((s1, s2)) or gm_cache.get((s2, s1))
                                        if not entry:
                                            continue
                                        gm_sans: set[str] = entry["sans"]  # type: ignore[assignment]
                                        clause_pre = re.split(r"(?:,\s+or\s+|;\s*|—)", ps[: gm_m.start()])[-1]
                                        clause_post = re.split(r"(?:,\s+or\s+|;\s*|—|\bas\s+in\b)", ps[gm_m.end() :])[0]
                                        cite_txt = clause_pre + " " + clause_post
                                        cite_mvs = _extract_clause_moves(cite_txt)
                                        cite_pawn_acts = _extract_action_pawn_moves(cite_txt)
                                        missing_gm = [
                                            mv for mv in cite_mvs
                                            if (mv in {"O-O", "O-O-O"} or mv[0] in "KQRBN" or mv in cite_pawn_acts)
                                            and mv not in gm_sans
                                        ]
                                        if missing_gm:
                                            sanity_flags.append(
                                                f"{prefix} {where}: [GM-CITATION FLAG] Clause citing '{gm_m.group(1)} vs {gm_m.group(2)}' attributes {missing_gm} absent from that GM game."
                                            )
                                        # Flag wing-pawn mismatch between leaf and cited GM game (e.g. a6 vs a5)
                                        gm_mvs: list[chess.Move] = entry["mvs"]  # type: ignore[assignment]
                                        gb: chess.Board = entry["init"].copy(stack=False)  # type: ignore[attr-defined]
                                        ply_cmp = min(len(path or []), len(gm_mvs))
                                        for gm_mv in gm_mvs[:ply_cmp]:
                                            gb.push(gm_mv)
                                        opp_c = chess.WHITE if our_side == "black" else chess.BLACK
                                        gm_opp_p = {chess.square_name(s) for s in gb.pieces(chess.PAWN, opp_c)}
                                        lf_opp_p = {chess.square_name(s) for s in board.pieces(chess.PAWN, opp_c)}
                                        if gm_opp_p != lf_opp_p:
                                            sanity_flags.append(
                                                f"{prefix} {where}: [GM-STRUCTURE FLAG] Cited game '{gm_m.group(1)} vs {gm_m.group(2)}' differs in opponent pawns at ply {ply_cmp} ({sorted(gm_opp_p - lf_opp_p)} vs {sorted(lf_opp_p - gm_opp_p)})."
                                            )

                def walk(
                    node: chess.pgn.GameNode,
                    board: chess.Board,
                    path: list[str],
                    is_main: bool,
                    parent_has_rav: bool = False,
                    board_before: chess.Board | None = None,
                    last_move: chess.Move | None = None,
                    rav_boards: list[chess.Board] | None = None,
                    in_dubious_our_rav: bool = False,
                ) -> None:
                    nonlocal rav_count
                    where = "root" if not path else " ".join(path[-6:])
                    if node.comment:
                        has_rav_ctx = (
                            not is_main
                            or not path
                            or parent_has_rav
                            or len(node.variations) > 1
                        )
                        check_comment(
                            node.comment,
                            board,
                            where,
                            has_rav_context=has_rav_ctx,
                            board_before=board_before,
                            last_move=last_move,
                            rav_boards=rav_boards,
                            node_for_rav_scan=node,
                            is_main=is_main,
                            path=path,
                        )

                    if not is_main and len(node.variations) > 1 and _rav_subtree_has_prose(node):
                        errors.append(
                            f"{prefix} {where}: Nested sub-variation inside RAV with prose comments — "
                            "Chessable renders nested variations out of order. Emit flat sibling RAVs instead."
                        )
                    if is_main and len(node.variations) > 5:
                        warnings.append(
                            f"{prefix} {where}: {len(node.variations) - 1} RAV sidelines on one move (>4) — consider splitting to avoid clutter."
                        )

                    node_has_rav = len(node.variations) > 1
                    main_mv = node.variations[0].move if node.variations else None
                    is_leaf_cont_host = is_main and bool(
                        node.comment
                        and (
                            "━━━ SAMPLE CONTINUATIONS ━━━" in node.comment
                            or "━━━ PRZYKŁADOWE KONTYNUACJE ━━━" in node.comment
                        )
                    )
                    for idx, child in enumerate(node.variations):
                        if idx > 0:
                            rav_count += 1
                        child_is_main = is_main and idx == 0
                        is_rav_root = idx > 0 or is_leaf_cont_host
                        if child.move not in board.legal_moves:
                            errors.append(f"{prefix} {where}: Illegal move {child.move}!")
                            continue
                        san = board.san(child.move)

                        is_our_turn = (
                            our_side is None
                            or (our_side == "white" and board.turn == chess.WHITE)
                            or (our_side == "black" and board.turn == chess.BLACK)
                        )
                        child_dubious_our_rav = in_dubious_our_rav
                        is_illustrative_our_branch = (
                            not child_is_main
                            and is_rav_root
                            and is_our_turn
                            and not is_leaf_cont_host
                            and main_mv is not None
                            and child.move != main_mv
                        )
                        if is_illustrative_our_branch:
                            # Skip engine checks on rejected our-turn tries ONLY if explicitly flagged as negative/dubious
                            c_txt = strip_command_tags(child.comment or "")
                            if any(n in child.nags for n in (2, 4, 6)) or REJECT_RAV_COMMENT_RE.search(c_txt):
                                child_dubious_our_rav = True
                            else:
                                is_illustrative_our_branch = False

                        if sf is not None and check_sf_this_game and is_our_turn:
                            should_engine_check = child_is_main or (
                                not child_dubious_our_rav and not is_illustrative_our_branch
                            )
                            if should_engine_check:
                                res = check_move_cached(board, san)
                                loss = res["cp_loss"]
                                scope = "MAIN" if child_is_main else "RAV"
                                if loss is not None and loss > blunder_cp:  # type: ignore[operator]
                                    best = res["best"]
                                    cand = res["candidate"]
                                    errors.append(
                                        f"{prefix} after {' '.join(path[-4:])} [{scope}]: HARD VETO — {san} loses {loss} cp "
                                        f"({cand.score_str if cand else '?'} vs best {best.move_san if best else '?'} {best.score_str if best else '?'})."  # type: ignore[attr-defined]
                                    )
                                elif loss is not None and loss >= soft_cp:  # type: ignore[operator]
                                    best = res["best"]
                                    cand = res["candidate"]
                                    warnings.append(
                                        f"{prefix} after {' '.join(path[-4:])} [{scope}]: SOFT VETO — {san} loses {loss} cp "
                                        f"({cand.score_str if cand else '?'} vs best {best.move_san if best else '?'} {best.score_str if best else '?'})."  # type: ignore[attr-defined]
                                    )

                        prev_b = board.copy(stack=False)
                        board.push(child.move)
                        next_rav_boards = None if child_is_main else ((rav_boards or []) + [prev_b])
                        walk(
                            child,
                            board,
                            path + [san],
                            child_is_main,
                            parent_has_rav=(idx == 0 and node_has_rav),
                            board_before=prev_b,
                            last_move=child.move,
                            rav_boards=next_rav_boards,
                            in_dubious_our_rav=child_dubious_our_rav,
                        )
                        board.pop()

                walk(game, game.board(), [], True)
    finally:
        if sf is not None:
            if skipped_non_trainable:
                print(
                    f"(Skipped Stockfish engine checks on {skipped_non_trainable} non-trainable intro/model game(s); "
                    "structural, move-legality, and arrow checks still ran.)"
                )
            sf.close()

    # Optional Gate-2 checks: --skeleton parity, --verify-models, --check-plan
    if skeleton_path is not None and selected_games is None:
        if not skeleton_path.is_file():
            errors.append(f"Skeleton file not found: {skeleton_path}")
        else:
            skel_trainable: list[tuple[int, str, chess.pgn.Game]] = []
            with skeleton_path.open("r", encoding="utf-8-sig") as sfh:
                s_idx = 0
                while True:
                    sg = chess.pgn.read_game(sfh)
                    if sg is None:
                        break
                    s_idx += 1
                    if classify_game(sg) == "trainable":
                        skel_trainable.append((s_idx, sg.headers.get("White", f"Skeleton #{s_idx}"), sg))

            if len(skel_trainable) != len(trainable_games):
                errors.append(
                    f"Skeleton parity mismatch: skeleton has {len(skel_trainable)} trainable line(s), "
                    f"target PGN has {len(trainable_games)}."
                )

            target_by_uci: dict[tuple[str, ...], tuple[int, str, chess.pgn.Game]] = {}
            for item in trainable_games:
                ucis, _, _ = _collect_mainline_and_ravs(item[2])
                target_by_uci.setdefault(ucis, item)

            for pos_idx, (_, stitle, sgame) in enumerate(skel_trainable):
                s_main, s_ravs, _ = _collect_mainline_and_ravs(sgame)
                matched = target_by_uci.get(s_main)
                if matched is None and pos_idx < len(trainable_games):
                    matched = trainable_games[pos_idx]
                if matched is None:
                    errors.append(f"Skeleton line '{stitle}' has no matching trainable game in PGN.")
                    continue
                t_num, t_title, t_game = matched
                t_main, t_ravs, _ = _collect_mainline_and_ravs(t_game)
                if s_main != t_main:
                    errors.append(
                        f"[Game {t_num}: {t_title}] Mainline mismatch vs skeleton '{stitle}' "
                        f"({len(t_main)} vs {len(s_main)} plies)."
                    )
                    continue
                for ply, req_ravs in s_ravs.items():
                    got_ravs = t_ravs.get(ply, set())
                    for req in req_ravs:
                        if req not in got_ravs:
                            errors.append(
                                f"[Game {t_num}: {t_title}] Missing skeleton RAV at ply {ply}: {' '.join(req)}."
                            )

    if verify_models:
        client = LichessClient()
        for g_num, m_title, m_game in model_games:
            gid = _extract_lichess_id(m_game)
            if not gid:
                errors.append(f"[Game {g_num}: {m_title}] Missing LichessId / lichess.org/<id> for --verify-models.")
                continue
            try:
                ref_pgn, _ = client.master_game_pgn(gid, use_cache=True)
                ref_game = chess.pgn.read_game(io.StringIO(ref_pgn))
                if ref_game is None:
                    errors.append(f"[Game {g_num}: {m_title}] Empty reference PGN returned for {gid}.")
                    continue
                pgn_ucis = [m.uci() for m in m_game.mainline_moves()]
                ref_ucis = [m.uci() for m in ref_game.mainline_moves()]
                if pgn_ucis != ref_ucis or not pgn_ucis:
                    errors.append(
                        f"[Game {g_num}: {m_title}] Model game {gid} differs from /masters verbatim "
                        f"({len(pgn_ucis)} vs {len(ref_ucis)} plies)."
                    )
                stem_moves = m_game.headers.get("StemMoves", "").strip()
                if stem_moves:
                    stem_b, _ = parse_position(moves=stem_moves)
                    stem_epd = stem_b.epd()
                    wb = m_game.board()
                    matched_stem = wb.epd() == stem_epd
                    for mv in m_game.mainline_moves():
                        wb.push(mv)
                        if wb.epd() == stem_epd:
                            matched_stem = True
                            break
                    if not matched_stem:
                        errors.append(
                            f"[Game {g_num}: {m_title}] Model game {gid} does NOT match required [StemMoves \"{stem_moves}\"]."
                        )
            except Exception as exc:
                errors.append(
                    f"[Game {g_num}: {m_title}] Failed to verify model game {gid} ({type(exc).__name__}: {exc})."
                )

    if check_plan:
        for g_num, t_title, t_game in trainable_games:
            _, _, leaf = _collect_mainline_and_ravs(t_game)
            leaf_comment = leaf.comment or ""
            has_plan = (
                "━━━ PLAN FROM HERE ━━━" in leaf_comment
                or "━━━ PLAN Z TEJ POZYCJI ━━━" in leaf_comment
                or "━━━ GATEWAY TO THE MIDDLEGAME ━━━" in leaf_comment
            )
            if not has_plan:
                errors.append(
                    f"[Game {g_num}: {t_title}] Leaf missing '━━━ PLAN FROM HERE ━━━' / Gateway block."
                )
            if not (CAL_RE.search(leaf_comment) or CSL_RE.search(leaf_comment)):
                warnings.append(
                    f"[Game {g_num}: {t_title}] Leaf plan has no [%cal] or [%csl] visual markup."
                )
            if "━━━ SAMPLE CONTINUATIONS ━━━" in leaf_comment or "━━━ PRZYKŁADOWE KONTYNUACJE ━━━" in leaf_comment:
                has_cont_rav = bool(leaf.variations) or (
                    leaf.parent is not None and len(leaf.parent.variations) > 1
                )
                if not has_cont_rav:
                    warnings.append(
                        f"[Game {g_num}: {t_title}] Sample Continuations header present on leaf without attached continuation RAV."
                    )

    return errors, warnings, game_count, rav_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify PGN against Chessable import rules (+ optional Stockfish check)")
    parser.add_argument("pgn", help="Path to PGN file")
    parser.add_argument("--engine-check", action="store_true", help="Also run Stockfish soundness check on mainline moves")
    parser.add_argument("--depth", type=int, default=16, help="Stockfish depth for --engine-check (default 16)")
    parser.add_argument("--blunder-cp", type=int, default=70, help="HARD VETO centipawn loss error threshold (default 70)")
    parser.add_argument("--soft-cp", type=int, default=35, help="SOFT VETO centipawn loss warning threshold (default 35)")
    parser.add_argument("--side", choices=["white", "black"], default=None, help="Only engine-check moves for this side")
    parser.add_argument("--skeleton", default=None, help="Verify 100%% mainline and internal-RAV parity against frozen skeleton PGN")
    parser.add_argument("--verify-models", action="store_true", help="Verify model games verbatim against Lichess Masters cache/API")
    parser.add_argument("--check-plan", action="store_true", help="Verify end-of-line PLAN/Gateway + arrows + sample continuation RAVs")
    parser.add_argument("--check-claims", action="store_true", help="Run deterministic python-chess pin/battery/piece-origin claim linter")
    parser.add_argument("--check-intros", action="store_true", help="Also run --engine-check on Informational intro games")
    parser.add_argument("--games", default=None, help="Optional 1-based game slice, e.g. '1-10' or '1,3,5-8'")
    parser.add_argument("--trainable-only", action="store_true", help="Count/check only trainable games (matches slice-pgn --trainable-only)")
    parser.add_argument("--provenance", action="store_true", help="Run v4 Game-or-Stockfish provenance + claim_lexicon + arrow checks")
    parser.add_argument("--tier", default="2000_2500", help="Online DB tier for provenance checks")
    parser.add_argument("--claims", default=None, help="Optional backing claims JSON/YAML sidecar")
    parser.add_argument("--ledger", default=None, help="Optional flag dismissal ledger JSON")
    parser.add_argument("--emit-residual", default=None, help="Write unverified residual clauses to Markdown")
    parser.add_argument("--summary", action="store_true", help="Print compact <=25-line ranked summary")
    args = parser.parse_args()

    pgn_path = Path(args.pgn)
    if not pgn_path.is_file():
        print(f"ERROR: File not found: {pgn_path}", file=sys.stderr)
        return 2

    sanity_flags: list[str] = []
    errors, warnings, count, rav_count = validate_pgn_file(
        pgn_path,
        engine_check=args.engine_check,
        depth=args.depth,
        blunder_cp=args.blunder_cp,
        soft_cp=args.soft_cp,
        our_side=args.side,
        skeleton_path=Path(args.skeleton) if args.skeleton else None,
        verify_models=args.verify_models,
        check_plan=args.check_plan,
        check_claims=args.check_claims,
        check_intros=args.check_intros,
        game_range=args.games,
        trainable_only=args.trainable_only,
        flags_out=sanity_flags,
        use_provenance=args.provenance,
    )

    if args.provenance:
        if not args.side:
            print("ERROR: --provenance requires --side white|black", file=sys.stderr)
            return 2
        from flag_ledger import format_summary
        from provenance import load_config, run as run_provenance

        cfg = load_config()
        cfg["depth"] = args.depth
        cfg["blunder_cp"] = args.blunder_cp
        cfg["soft_cp"] = args.soft_cp
        prov_fnds, _ = run_provenance(
            pgn_path,
            args.side,
            tier=args.tier,
            games_sel=_parse_game_selection(args.games),
            trainable_only=args.trainable_only,
            cfg=cfg,
            use_engine=args.engine_check or True,
            claims_path=Path(args.claims) if args.claims else None,
            ledger_path=Path(args.ledger) if args.ledger else None,
            emit_residual=Path(args.emit_residual) if args.emit_residual else None,
            check_arrows=True,
        )
        for pf in prov_fnds:
            if pf.severity == "ERROR":
                errors.append(pf.line())
            else:
                sanity_flags.append(pf.line())

    if args.summary:
        print(
            f"Verified {pgn_path.name}: {count} game(s), {rav_count} RAV sideline(s), "
            f"{len(errors)} error(s), {len(warnings)} warning(s), {len(sanity_flags)} flag(s)."
        )
        for e in errors[:15]:
            print(f"  [X] {e}")
        if len(errors) > 15:
            print(f"  ... +{len(errors) - 15} more error(s)")
        for w in warnings[:5]:
            print(f"  [!] {w}")
        for f in sanity_flags[:8]:
            print(f"  [?] {f}")
        if len(sanity_flags) > 8:
            print(f"  ... +{len(sanity_flags) - 8} more flag(s)")
        return 1 if errors else 0

    print(
        f"Verified {pgn_path.name}: {count} game(s), {rav_count} RAV sideline(s), "
        f"{len(errors)} error(s), {len(warnings)} warning(s), {len(sanity_flags)} sanity flag(s)."
    )
    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  [X] {e}")
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  [!] {w}")
    if sanity_flags:
        print("\nSANITY FLAGS (advisory — parent to verify on board):")
        for f in sanity_flags:
            print(f"  [?] {f}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
