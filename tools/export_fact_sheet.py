"""Deterministic Per-Node Board Fact Sheet generator (0 LLM tokens).

Exports exact piece squares, active pins, active batteries, open/semi-open files,
wing pawn counts, bishop color complexes, cached DB replies, and Stockfish 19 top lines
for every decision node (nodes with RAVs), RAV leaf, and mainline leaf in a skeleton PGN.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from chess_env import LichessClient, StockfishAnalyzer, RATING_TIERS, DEFAULT_SPEEDS  # noqa: E402

PIECE_VAL = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}

DIAG_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
ORTHO_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def classify_game(game: chess.pgn.Game) -> str:
    """Classify a PGN game as 'model', 'intro', or 'trainable'."""
    res = game.headers.get("Result", "*").strip()
    title = game.headers.get("White", "").strip().lower()
    event = game.headers.get("Event", "").strip().lower()
    if res in {"1-0", "0-1", "1/2-1/2"} or "LichessId" in game.headers or "model game" in title or "model game" in event:
        return "model"
    if "intro" in title or "why " in title or "dlaczego " in title or "wstęp" in title or "wstep" in title:
        return "intro"
    return "trainable"


def is_light_sq(sq: int) -> bool:
    return (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1


def enemy_pawn_attackers(board: chess.Board, sq: int, for_color: chess.Color) -> tuple[list[str], list[str]]:
    """Return (current_attackers, future_kickers) among enemy pawns for a square `sq`."""
    enemy = not for_color
    f = chess.square_file(sq)
    r = chess.square_rank(sq)
    current: list[str] = []
    future: list[str] = []
    for p_sq in board.pieces(chess.PAWN, enemy):
        pf = chess.square_file(p_sq)
        pr = chess.square_rank(p_sq)
        if abs(pf - f) != 1:
            continue
        if enemy == chess.BLACK:
            if pr == r + 1:
                current.append(chess.square_name(p_sq))
            elif pr > r + 1:
                future.append(chess.square_name(p_sq))
        else:
            if pr == r - 1:
                current.append(chess.square_name(p_sq))
            elif pr < r - 1:
                future.append(chess.square_name(p_sq))
    return sorted(current), sorted(future)


def find_outposts(board: chess.Board, for_color: chess.Color, ranks: tuple[int, ...] | None = None) -> list[str]:
    """Find strict permanent outpost squares (b-g, rank 5-6 for White / 3-4 for Black) unattackable by enemy pawns."""
    if ranks is not None:
        target_ranks = ranks
    else:
        target_ranks = (4, 5) if for_color == chess.WHITE else (2, 3)
    own_pawns = board.pieces(chess.PAWN, for_color)
    outposts: list[str] = []
    for r in target_ranks:
        for f in range(1, 7):
            sq = chess.square(f, r)
            if sq in own_pawns:
                continue
            cur, fut = enemy_pawn_attackers(board, sq, for_color)
            if cur or fut:
                continue
            # Require either own-pawn support or occupation by own minor/heavy piece
            supp_rank = r - 1 if for_color == chess.WHITE else r + 1
            supported = any(
                0 <= f + df < 8 and chess.square(f + df, supp_rank) in own_pawns for df in (-1, 1)
            )
            occ = board.piece_at(sq)
            occupied_by_own = occ is not None and occ.color == for_color and occ.piece_type != chess.PAWN
            if supported or occupied_by_own:
                outposts.append(chess.square_name(sq))
    return outposts


def find_pins(board: chess.Board) -> list[str]:
    """Find all strict collinear slider -> target -> higher-value/king pins on board."""
    pins: list[str] = []
    for color in (chess.WHITE, chess.BLACK):
        enemy = not color
        for sq in range(64):
            attacker = board.piece_at(sq)
            if attacker is None or attacker.color != color:
                continue
            if attacker.piece_type == chess.BISHOP:
                dirs = DIAG_DIRS
            elif attacker.piece_type == chess.ROOK:
                dirs = ORTHO_DIRS
            elif attacker.piece_type == chess.QUEEN:
                dirs = DIAG_DIRS + ORTHO_DIRS
            else:
                continue
            f0, r0 = chess.square_file(sq), chess.square_rank(sq)
            for df, dr in dirs:
                f, r = f0 + df, r0 + dr
                first: tuple[int, chess.Piece] | None = None
                while 0 <= f < 8 and 0 <= r < 8:
                    csq = chess.square(f, r)
                    cp = board.piece_at(csq)
                    if cp is not None:
                        if first is None:
                            if cp.color == color:
                                break
                            first = (csq, cp)
                        else:
                            if cp.color == enemy and PIECE_VAL[cp.piece_type] > PIECE_VAL[first[1].piece_type]:
                                atk_sym = attacker.symbol().upper()
                                t_sym = first[1].symbol().upper()
                                b_sym = cp.symbol().upper()
                                pins.append(
                                    f"{'W' if color == chess.WHITE else 'B'}:{atk_sym}{chess.square_name(sq)}->{t_sym}{chess.square_name(first[0])}->{b_sym}{chess.square_name(csq)}"
                                )
                            break
                    f += df
                    r += dr
    return pins


def find_batteries(board: chess.Board) -> list[str]:
    """Find aligned friendly Q+B (diagonal) and Q+R/R+R (rank/file) batteries with no blockers between."""
    batts: list[str] = []
    for color in (chess.WHITE, chess.BLACK):
        tag = "W" if color == chess.WHITE else "B"
        q_sqs = list(board.pieces(chess.QUEEN, color))
        b_sqs = list(board.pieces(chess.BISHOP, color))
        r_sqs = list(board.pieces(chess.ROOK, color))
        pairs: list[tuple[str, int, int, bool]] = []
        for q in q_sqs:
            for b in b_sqs:
                pairs.append(("Q+B", q, b, True))
            for r in r_sqs:
                pairs.append(("Q+R", q, r, False))
        r_list = list(r_sqs)
        for i in range(len(r_list)):
            for j in range(i + 1, len(r_list)):
                pairs.append(("R+R", r_list[i], r_list[j], False))

        for label, s1, s2, want_diag in pairs:
            f1, r1 = chess.square_file(s1), chess.square_rank(s1)
            f2, r2 = chess.square_file(s2), chess.square_rank(s2)
            df, dr = f2 - f1, r2 - r1
            if want_diag:
                if abs(df) != abs(dr) or df == 0:
                    continue
            else:
                if df != 0 and dr != 0:
                    continue
            step_f = 0 if df == 0 else (1 if df > 0 else -1)
            step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
            cf, cr = f1 + step_f, r1 + step_r
            blocked = False
            while (cf, cr) != (f2, r2):
                if board.piece_at(chess.square(cf, cr)) is not None:
                    blocked = True
                    break
                cf += step_f
                cr += step_r
            if not blocked:
                batts.append(f"{tag}:{label}({chess.square_name(s1)}-{chess.square_name(s2)})")
    return batts


def fmt_pieces(board: chess.Board) -> str:
    parts: list[str] = []
    for color, tag in ((chess.WHITE, "W"), (chess.BLACK, "B")):
        items = []
        for pt, sym in [
            (chess.KING, "K"),
            (chess.QUEEN, "Q"),
            (chess.ROOK, "R"),
            (chess.BISHOP, "B"),
            (chess.KNIGHT, "N"),
        ]:
            sqs = sorted(chess.square_name(s) for s in board.pieces(pt, color))
            if sqs:
                items.append(f"{sym} {','.join(sqs)}")
        parts.append(f"{tag}: {' '.join(items)}")
    return " | ".join(parts)


def fmt_files_and_pawns(board: chess.Board) -> str:
    open_f: list[str] = []
    w_semi: list[str] = []
    b_semi: list[str] = []
    wp = board.pieces(chess.PAWN, chess.WHITE)
    bp = board.pieces(chess.PAWN, chess.BLACK)
    for fi in range(8):
        fn = chess.FILE_NAMES[fi]
        wc = sum(1 for s in wp if chess.square_file(s) == fi)
        bc = sum(1 for s in bp if chess.square_file(s) == fi)
        if wc == 0 and bc == 0:
            open_f.append(fn)
        elif wc == 0 and bc > 0:
            w_semi.append(fn)
        elif bc == 0 and wc > 0:
            b_semi.append(fn)

    def _cnt(pset: chess.SquareSet, files: set[int]) -> int:
        return sum(1 for s in pset if chess.square_file(s) in files)

    q_w, q_b = _cnt(wp, {0, 1, 2}), _cnt(bp, {0, 1, 2})
    c_w, c_b = _cnt(wp, {3, 4}), _cnt(bp, {3, 4})
    k_w, k_b = _cnt(wp, {5, 6, 7}), _cnt(bp, {5, 6, 7})

    def _b_colors(col: chess.Color) -> str:
        bs = board.pieces(chess.BISHOP, col)
        tags = ["L" if is_light_sq(s) else "D" for s in bs]
        return "+".join(sorted(tags)) or "none"

    def _p_list(col: chess.Color) -> str:
        return ",".join(chess.square_name(s) for s in sorted(board.pieces(chess.PAWN, col))) or "-"

    w_out = ",".join(find_outposts(board, chess.WHITE)) or "none"
    b_out = ",".join(find_outposts(board, chess.BLACK)) or "none"
    w_r4 = find_outposts(board, chess.WHITE, ranks=(3,))
    b_r5 = find_outposts(board, chess.BLACK, ranks=(4,))
    r4_tag = f" | Anchors W:[{','.join(w_r4) or '-'}] B:[{','.join(b_r5) or '-'}]" if (w_r4 or b_r5) else ""

    return (
        f"Open:[{','.join(open_f) or '-'}] W-semi:[{','.join(w_semi) or '-'}] B-semi:[{','.join(b_semi) or '-'}]"
        f" | Pawns Q:{q_w}v{q_b} C:{c_w}v{c_b} K:{k_w}v{k_b}"
        f" | Bishops W:{_b_colors(chess.WHITE)} B:{_b_colors(chess.BLACK)}"
        f"\n- **Pawn Map:** W:[{_p_list(chess.WHITE)}] B:[{_p_list(chess.BLACK)}] | Outposts W:[{w_out}] B:[{b_out}]{r4_tag}"
    )


def cached_db_summary(client: LichessClient, board: chess.Board, tier: str) -> str:
    chunks: list[str] = []
    try:
        mst = client.masters(board, use_cache=True)
        if mst.from_cache and mst.total_games > 0:
            top = ", ".join(f"{m.san} {m.play_pct:.0f}%({m.side_score_pct:.0f}%)" for m in mst.moves[:3])
            chunks.append(f"Mst({mst.total_games}): {top}")
    except Exception:
        pass
    try:
        onl = client.online(board, tier=tier, use_cache=True)
        if onl.from_cache and onl.total_games > 0:
            top = ", ".join(f"{m.san} {m.play_pct:.0f}%({m.side_score_pct:.0f}%)" for m in onl.moves[:3])
            chunks.append(f"Onl({onl.total_games}): {top}")
    except Exception:
        pass
    return " | ".join(chunks) or "(uncached)"


def _parse_game_selection(spec: str | None) -> set[int] | None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate per-node deterministic Board Fact Sheet for prose authoring")
    parser.add_argument("pgn", help="Frozen skeleton or chapter PGN")
    parser.add_argument("--side", choices=["white", "black"], required=True)
    parser.add_argument("--depth", type=int, default=18)
    parser.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="2000_2500")
    parser.add_argument("--all-nodes", action="store_true", help="Emit every mainline/RAV node from --min-ply onward (recommended for full grounding)")
    parser.add_argument("--min-ply", type=int, default=4, help="Minimum ply when --all-nodes is enabled (default: 4)")
    parser.add_argument("--games", default=None, help="Optional 1-based trainable game slice, e.g. '1-7' or '8-14'")
    parser.add_argument("--trainable-only", action="store_true", help="Skip Intro and Model games when numbering/emitting (matches slice-pgn --trainable-only)")
    parser.add_argument("--delta", action="store_true", help="Emit full board at first node of each game, then only changed fields")
    parser.add_argument("--nodes", choices=["all", "commented", "leaves"], default="all", help="Which nodes to emit (default: all)")
    parser.add_argument("--skip-engine", action="store_true")
    parser.add_argument("--out", help="Optional Markdown output file")
    args = parser.parse_args()

    selected_games = _parse_game_selection(args.games)
    pgn_path = Path(args.pgn)
    if not pgn_path.is_file():
        print(f"ERROR: File not found: {pgn_path}", file=sys.stderr)
        return 2

    client = LichessClient()
    sf: StockfishAnalyzer | None = None
    if not args.skip_engine:
        sf = StockfishAnalyzer()
        sf.open()

    sf_cache: dict[str, str] = {}
    md: list[str] = [
        f"# Board Fact Sheet: `{pgn_path.name}` (side={args.side}, depth={args.depth})",
        "",
    ]

    def get_sf_str(board: chess.Board) -> str:
        if sf is None:
            return "(engine skipped)"
        epd = board.epd()
        if epd not in sf_cache:
            lines = sf.analyze(board, depth=args.depth, multipv=2)
            sf_cache[epd] = " ; ".join(
                f"{ln.move_san} {ln.score_str} [{' '.join(ln.pv_san[:5])}]" for ln in lines
            )
        return sf_cache[epd]

    try:
        with pgn_path.open("r", encoding="utf-8-sig") as fh:
            g_idx = 0
            emitted_games = 0
            while (game := chess.pgn.read_game(fh)) is not None:
                if args.trainable_only:
                    if classify_game(game) != "trainable":
                        continue
                elif game.headers.get("Result", "*") != "*":
                    continue
                g_idx += 1
                if selected_games is not None and g_idx not in selected_games:
                    continue
                emitted_games += 1
                title = game.headers.get("White", f"Line {g_idx}")
                md.append(f"## {g_idx}. {title}")

                nodes_to_emit: list[tuple[str, chess.Board]] = []

                def walk(node: chess.pgn.GameNode, board: chess.Board, path: list[str], is_main: bool) -> None:
                    has_ravs = len(node.variations) > 1
                    is_leaf = not node.variations
                    has_comment = bool(node.comment and node.comment.strip())
                    want_node = bool(path) and (
                        (args.nodes == "commented" and has_comment)
                        or (args.nodes == "leaves" and is_leaf)
                        or (
                            args.nodes == "all"
                            and (has_ravs or is_leaf or has_comment or (args.all_nodes and len(path) >= args.min_ply))
                        )
                    )
                    if want_node:
                        if is_main and is_leaf:
                            tag = "LEAF"
                        elif is_leaf:
                            tag = "RAV-LEAF"
                        elif has_ravs:
                            tag = "CROSSROAD"
                        else:
                            tag = "NODE"
                        nodes_to_emit.append((f"{tag} ply {len(path)} (`{' '.join(path[-4:])}`)", board.copy(stack=False)))
                    for idx, ch in enumerate(node.variations):
                        san = board.san(ch.move)
                        board.push(ch.move)
                        walk(ch, board, path + [san], is_main and idx == 0)
                        board.pop()

                walk(game, game.board(), [], True)
                prev_state: dict[str, str] | None = None
                for label, nb in nodes_to_emit:
                    pins = find_pins(nb)
                    batts = find_batteries(nb)
                    pieces_s = fmt_pieces(nb)
                    pins_s = ", ".join(pins) if pins else "none"
                    batts_s = ", ".join(batts) if batts else "none"
                    struct_s = fmt_files_and_pawns(nb)
                    db_s = cached_db_summary(client, nb, args.tier)
                    sf_s = get_sf_str(nb)
                    md.append(f"### {label}")
                    if not args.delta or prev_state is None:
                        md.append(f"- **Pieces:** {pieces_s}")
                        md.append(f"- **Pins:** {pins_s} | **Batteries:** {batts_s}")
                        md.append(f"- **Structure:** {struct_s}")
                    else:
                        if pieces_s != prev_state["pieces"]:
                            md.append(f"- **Pieces (Δ):** {pieces_s}")
                        if pins_s != prev_state["pins"] or batts_s != prev_state["batts"]:
                            md.append(f"- **Pins/Batts (Δ):** Pins: {pins_s} | Batteries: {batts_s}")
                        if struct_s != prev_state["struct"]:
                            md.append(f"- **Structure (Δ):** {struct_s}")
                    md.append(f"- **DB:** {db_s} | **SF19:** {sf_s}")
                    prev_state = {"pieces": pieces_s, "pins": pins_s, "batts": batts_s, "struct": struct_s}
                md.append("")
    finally:
        if sf is not None:
            sf.close()

    out_text = "\n".join(md)
    if args.out:
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(out_text, encoding="utf-8")
        print(f"Wrote Board Fact Sheet ({emitted_games} lines) to {out_p}")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
