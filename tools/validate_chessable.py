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
import re
import sys
from pathlib import Path

import chess
import chess.pgn

from chess_env import StockfishAnalyzer

CAL_RE = re.compile(r"\[%cal\s+([^\]]+)\]")
CSL_RE = re.compile(r"\[%csl\s+([^\]]+)\]")
CMD_TAG_RE = re.compile(r"\[%[a-zA-Z]+\s+[^\]]*\]")
FORBIDDEN_HTML_RE = re.compile(r"</?(?:ul|ol|li|b|strong|i|em|u|p|h[1-6]|hr|div|span)\b[^>]*>", re.IGNORECASE)
ZERO_CASTLE_RE = re.compile(r"\b0-0(?:-0)?\b")
FORBIDDEN_CHARS_RE = re.compile(r"[()\[\]{}]")
ROBOTIC_LAYER_RE = re.compile(r"(?<!<br>)\bWarstwa\s+[2-4]\b")
MOVE_SEQ_RE = re.compile(
    r"\b\d+\.\s*(?:\.\.\s*)?(?:[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]|O-O(?:-O)?)[+#!?]*\s+"
    r"(?:\d+\.\s*(?:\.\.\s*)?)?(?:[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]|O-O(?:-O)?)"
)


def strip_command_tags(comment: str) -> str:
    return CMD_TAG_RE.sub("", comment)


def validate_pgn_file(
    pgn_path: Path,
    engine_check: bool = False,
    depth: int = 16,
    blunder_cp: int = 70,
    soft_cp: int = 35,
    our_side: str | None = None,
) -> tuple[list[str], list[str], int, int]:
    errors: list[str] = []
    warnings: list[str] = []
    game_count = 0
    rav_count = 0
    skipped_model_games = 0

    sf: StockfishAnalyzer | None = None
    if engine_check:
        sf = StockfishAnalyzer()
        sf.open()

    try:
        with pgn_path.open("r", encoding="utf-8-sig") as fh:
            while True:
                game = chess.pgn.read_game(fh)
                if game is None:
                    break
                game_count += 1
                title = game.headers.get("White", f"Game #{game_count}")
                prefix = f"[Game {game_count}: {title}]"
                is_model_game = (
                    game.headers.get("Result", "*").strip() in {"1-0", "0-1", "1/2-1/2"}
                    or "LichessId" in game.headers
                )
                if sf is not None and is_model_game:
                    skipped_model_games += 1

                if game.errors:
                    for err in game.errors:
                        errors.append(f"{prefix} PGN parse error: {err}")

                if game.headers.get("Black", "").strip() not in {"", "?"}:
                    warnings.append(
                        f"{prefix} [Black] header is '{game.headers.get('Black')}' "
                        "(recommended: empty string '' for Chessable variation titles)."
                    )

                def check_comment(raw: str, board: chess.Board, where: str, has_rav_context: bool = True) -> None:
                    if not raw:
                        return

                    # Check [%cal ...] arrows originate from occupied squares
                    for m in CAL_RE.finditer(raw):
                        for tok in m.group(1).split(","):
                            tok = tok.strip()
                            if len(tok) != 5 or tok[0] not in "GBRY":
                                errors.append(f"{prefix} {where}: Malformed [%cal] arrow '{tok}'.")
                                continue
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

                def walk(
                    node: chess.pgn.GameNode,
                    board: chess.Board,
                    path: list[str],
                    is_main: bool,
                    parent_has_rav: bool = False,
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
                        check_comment(node.comment, board, where, has_rav_context=has_rav_ctx)

                    node_has_rav = len(node.variations) > 1
                    for idx, child in enumerate(node.variations):
                        if idx > 0:
                            rav_count += 1
                        child_is_main = is_main and idx == 0
                        if child.move not in board.legal_moves:
                            errors.append(f"{prefix} {where}: Illegal move {child.move}!")
                            continue
                        san = board.san(child.move)

                        if sf is not None and child_is_main and not is_model_game:
                            should_check = (
                                our_side is None
                                or (our_side == "white" and board.turn == chess.WHITE)
                                or (our_side == "black" and board.turn == chess.BLACK)
                            )
                            if should_check:
                                res = sf.check_move(board, san, depth=depth, multipv=2)
                                loss = res["cp_loss"]
                                if loss is not None and loss > blunder_cp:
                                    best = res["best"]
                                    cand = res["candidate"]
                                    errors.append(
                                        f"{prefix} after {' '.join(path[-4:])}: HARD VETO — {san} loses {loss} cp "
                                        f"({cand.score_str if cand else '?'} vs best {best.move_san} {best.score_str if best else '?'})."
                                    )
                                elif loss is not None and loss >= soft_cp:
                                    best = res["best"]
                                    cand = res["candidate"]
                                    warnings.append(
                                        f"{prefix} after {' '.join(path[-4:])}: SOFT VETO — {san} loses {loss} cp "
                                        f"({cand.score_str if cand else '?'} vs best {best.move_san} {best.score_str if best else '?'})."
                                    )

                        board.push(child.move)
                        walk(child, board, path + [san], child_is_main, parent_has_rav=(idx == 0 and node_has_rav))
                        board.pop()

                walk(game, game.board(), [], True)
    finally:
        if sf is not None:
            if skipped_model_games:
                print(
                    f"(Skipped Stockfish engine checks on {skipped_model_games} historical/model game(s); "
                    "structural, move-legality, and arrow checks still ran.)"
                )
            sf.close()

    return errors, warnings, game_count, rav_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify PGN against Chessable import rules (+ optional Stockfish check)")
    parser.add_argument("pgn", help="Path to PGN file")
    parser.add_argument("--engine-check", action="store_true", help="Also run Stockfish soundness check on mainline moves")
    parser.add_argument("--depth", type=int, default=16, help="Stockfish depth for --engine-check (default 16)")
    parser.add_argument("--blunder-cp", type=int, default=70, help="HARD VETO centipawn loss error threshold (default 70)")
    parser.add_argument("--soft-cp", type=int, default=35, help="SOFT VETO centipawn loss warning threshold (default 35)")
    parser.add_argument("--side", choices=["white", "black"], default=None, help="Only engine-check moves for this side")
    args = parser.parse_args()

    pgn_path = Path(args.pgn)
    if not pgn_path.is_file():
        print(f"ERROR: File not found: {pgn_path}", file=sys.stderr)
        return 2

    errors, warnings, count, rav_count = validate_pgn_file(
        pgn_path,
        engine_check=args.engine_check,
        depth=args.depth,
        blunder_cp=args.blunder_cp,
        soft_cp=args.soft_cp,
        our_side=args.side,
    )

    print(
        f"Verified {pgn_path.name}: {count} game(s), {rav_count} RAV sideline(s), "
        f"{len(errors)} error(s), {len(warnings)} warning(s)."
    )
    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  [X] {e}")
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  [!] {w}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
