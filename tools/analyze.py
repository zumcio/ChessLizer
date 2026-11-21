"""Unified CLI for Stockfish, Lichess Masters/Online DB, Cloud Eval, Tablebase, Coverage, and SVG rendering."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import chess
import chess.pgn
import chess.svg

from chess_env import (
    DEFAULT_SPEEDS,
    RATING_TIERS,
    EcoLookup,
    ExplorerResult,
    LichessAuthError,
    LichessClient,
    LichessRateLimitError,
    StockfishAnalyzer,
    parse_position,
)


def _fmt_wdl(wdl: tuple[int, int, int] | None) -> str:
    if not wdl:
        return "-"
    w, d, l = wdl
    return f"W{w/10:.1f}%/D{d/10:.1f}%/L{l/10:.1f}%"


def _print_explorer(res: ExplorerResult, limit: int = 10, show_games: bool = True) -> None:
    cache_tag = " [cache]" if res.from_cache else " [live]"
    opening_str = f" | {res.opening_eco} {res.opening_name}" if res.opening_name else ""
    print(f"\n=== {res.source.upper()} ({res.total_games:,} games{opening_str}){cache_tag} ===")
    if res.total_games == 0:
        print("  (Brak partii w bazie dla tej pozycji)")
        return

    print(
        f"  {'Move':<8} {'Games':>10} {'Play%':>7} {'Cum%':>7} "
        f"{'Score%':>7} {'W%':>6} {'D%':>6} {'B%':>6} {'AvgElo':>7}"
    )
    print("  " + "-" * 72)
    for mv in res.moves[:limit]:
        elo_s = str(mv.average_rating) if mv.average_rating else "-"
        print(
            f"  {mv.san:<8} {mv.total:>10,} {mv.play_pct:>6.1f}% {mv.cum_pct:>6.1f}% "
            f"{mv.side_score_pct:>6.1f}% {mv.white_pct:>5.1f}% {mv.draw_pct:>5.1f}% {mv.black_pct:>5.1f}% {elo_s:>7}"
        )

    if show_games and res.top_games:
        print("\n  Top model games:")
        for g in res.top_games[:5]:
            w = g.get("white", {})
            b = g.get("black", {})
            yr = g.get("year", "")
            winner = g.get("winner")
            res_str = "1-0" if winner == "white" else ("0-1" if winner == "black" else "1/2-1/2")
            gid = g.get("id", "")
            print(
                f"    - {w.get('name', '?')} ({w.get('rating', '?')}) vs "
                f"{b.get('name', '?')} ({b.get('rating', '?')}) [{res_str}, {yr}] https://lichess.org/{gid}"
            )


def cmd_engine(args: argparse.Namespace) -> int:
    board, san_list = parse_position(args.fen, args.moves)
    eco = EcoLookup().lookup_path(san_list) if san_list else EcoLookup().lookup(board)
    print(f"FEN: {board.fen()}")
    print(f"Turn: {'White' if board.turn == chess.WHITE else 'Black'}")
    if eco:
        print(f"ECO: {eco[0]} — {eco[1]}")

    with StockfishAnalyzer(threads=args.threads, hash_mb=args.hash) as sf:
        print(f"Engine: {sf.engine_name} (depth={args.depth}, time={args.time}, multipv={args.multipv})")
        if args.check:
            res = sf.check_move(board, args.check, depth=args.depth, time_sec=args.time, multipv=args.multipv)
            cand = res["candidate"]
            best = res["best"]
            print(f"\nCandidate move check: {args.check}")
            if cand:
                print(
                    f"  {cand.move_san}: {cand.score_str} (d{cand.depth}, WDL {_fmt_wdl(cand.wdl)}) "
                    f"PV: {' '.join(cand.pv_san)}"
                )
            if best:
                print(
                    f"  Best ({best.move_san}): {best.score_str} (d{best.depth}, WDL {_fmt_wdl(best.wdl)}) "
                    f"PV: {' '.join(best.pv_san)}"
                )
            if res["cp_loss"] is not None:
                loss = res["cp_loss"]
                verdict = "SOUND" if loss <= 25 else ("PLAYABLE / INACCURACY" if loss <= 70 else "DUBIOUS / BLUNDER")
                print(f"  Centipawn loss: {loss} cp -> {verdict}")
            lines = res["top_lines"]
        else:
            lines = sf.analyze(board, depth=args.depth, time_sec=args.time, multipv=args.multipv)

    print("\nTop Engine Lines:")
    for ln in lines:
        print(
            f"  #{ln.rank} {ln.move_san:<7} {ln.score_str:>7} (d{ln.depth:<2}, {_fmt_wdl(ln.wdl)}) "
            f"| {' '.join(ln.pv_san)}"
        )
    return 0


def cmd_masters(args: argparse.Namespace) -> int:
    board, _ = parse_position(args.fen, args.moves)
    client = LichessClient()
    res = client.masters(
        board,
        moves=args.limit,
        top_games=args.top_games,
        since=args.since,
        until=args.until,
        use_cache=not args.no_cache,
    )
    print(f"FEN: {board.fen()}")
    _print_explorer(res, limit=args.limit, show_games=args.top_games > 0)
    return 0


def cmd_online(args: argparse.Namespace) -> int:
    board, _ = parse_position(args.fen, args.moves)
    client = LichessClient()
    res = client.online(
        board,
        tier=args.tier,
        ratings=args.ratings,
        speeds=args.speeds,
        moves=args.limit,
        top_games=args.top_games,
        use_cache=not args.no_cache,
    )
    print(f"FEN: {board.fen()}")
    _print_explorer(res, limit=args.limit, show_games=args.top_games > 0)
    return 0


def cmd_cloud(args: argparse.Namespace) -> int:
    board, _ = parse_position(args.fen, args.moves)
    client = LichessClient()
    data = client.cloud_eval(board, multipv=args.multipv, use_cache=not args.no_cache)
    print(f"FEN: {board.fen()}")
    if not data:
        print("Brak pozycji w Lichess Cloud Eval (404) — użyj lokalnego Stockfisha (`engine`).")
        return 0
    cache_tag = " [cache]" if data.get("_from_cache") else " [live]"
    print(f"=== LICHESS CLOUD EVAL (depth={data.get('depth')}, knodes={data.get('knodes')}){cache_tag} ===")
    for idx, pv in enumerate(data.get("pvs", []), start=1):
        score_s = f"#{pv['mate']:+d}" if "mate" in pv else f"{pv.get('cp', 0)/100:+.2f}"
        tmp = board.copy(stack=False)
        san_pv = []
        for uci in pv.get("moves", "").split()[:10]:
            mv = chess.Move.from_uci(uci)
            if mv in tmp.legal_moves:
                san_pv.append(tmp.san(mv))
                tmp.push(mv)
            else:
                break
        first = san_pv[0] if san_pv else "?"
        print(f"  #{idx} {first:<7} {score_s:>7} | {' '.join(san_pv)}")
    return 0


def cmd_tablebase(args: argparse.Namespace) -> int:
    board, _ = parse_position(args.fen, args.moves)
    print(f"FEN: {board.fen()} (pieces={len(board.piece_map())})")
    if len(board.piece_map()) > 7:
        print("Tablebase obsługuje maksymalnie 7 bierek na szachownicy.")
        return 1
    client = LichessClient()
    data = client.tablebase(board, use_cache=not args.no_cache)
    if not data:
        print("Brak wyniku w Syzygy Tablebase.")
        return 0
    print(f"Category: {data.get('category')} | DTZ: {data.get('dtz')} | DTM: {data.get('dtm')}")
    for mv in data.get("moves", [])[:8]:
        print(f"  {mv['san']:<7} -> {mv.get('category'):<12} (DTZ={mv.get('dtz')}, DTM={mv.get('dtm')})")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Full 360-degree course-author report: Stockfish + Masters + Online side-by-side."""
    board, san_list = parse_position(args.fen, args.moves)
    eco = EcoLookup().lookup_path(san_list) if san_list else EcoLookup().lookup(board)
    print(f"Position: {' '.join(san_list) if san_list else '(FEN)'}")
    print(f"FEN:      {board.fen()}")
    print(f"To move:  {'White' if board.turn == chess.WHITE else 'Black'}")
    if eco:
        print(f"ECO:      {eco[0]} — {eco[1]}")

    client = LichessClient()
    masters_res: ExplorerResult | None = None
    online_res: ExplorerResult | None = None

    if not args.skip_db:
        try:
            masters_res = client.masters(board, moves=args.limit, top_games=3, use_cache=not args.no_cache)
        except (LichessAuthError, LichessRateLimitError) as exc:
            print(f"\n[Masters DB niedostępna]: {exc}")

        try:
            online_res = client.online(
                board,
                tier=args.tier,
                ratings=args.ratings,
                speeds=args.speeds,
                moves=args.limit,
                top_games=0,
                use_cache=not args.no_cache,
            )
        except (LichessAuthError, LichessRateLimitError) as exc:
            print(f"\n[Online DB niedostępna]: {exc}")

    # Collect candidate moves from DBs + Stockfish
    sf_lines = []
    if not args.skip_engine:
        with StockfishAnalyzer(threads=args.threads, hash_mb=args.hash) as sf:
            sf_lines = sf.analyze(board, depth=args.depth, time_sec=args.time, multipv=args.multipv)
            sf_name = sf.engine_name
        print(f"\n=== STOCKFISH ({sf_name}, d{args.depth}) ===")
        for ln in sf_lines:
            print(
                f"  #{ln.rank} {ln.move_san:<7} {ln.score_str:>7} (d{ln.depth:<2}, {_fmt_wdl(ln.wdl)}) "
                f"| {' '.join(ln.pv_san)}"
            )

    if masters_res:
        _print_explorer(masters_res, limit=args.limit, show_games=True)
    if online_res:
        _print_explorer(online_res, limit=args.limit, show_games=False)

    # Combined comparison table for course authoring
    if masters_res or online_res or sf_lines:
        m_map = {m.san: m for m in (masters_res.moves if masters_res else [])}
        o_map = {m.san: m for m in (online_res.moves if online_res else [])}
        sf_map = {ln.move_san: ln for ln in sf_lines}

        all_moves: list[str] = []
        for source_list in (
            [m.san for m in (online_res.moves[:8] if online_res else [])],
            [m.san for m in (masters_res.moves[:8] if masters_res else [])],
            [ln.move_san for ln in sf_lines],
        ):
            for san in source_list:
                if san not in all_moves:
                    all_moves.append(san)

        online_label = args.ratings if args.ratings else args.tier
        print(f"\n=== COURSE AUTHOR MATRIX (Online[{online_label}] vs Masters vs Stockfish) ===")
        print(
            f"  {'Move':<7} | {'Onl Play%':>9} {'Onl Scr%':>8} | "
            f"{'Mst Play%':>9} {'Mst Scr%':>8} | {'SF Eval':>8} | Course Tag"
        )
        print("  " + "-" * 84)
        for san in all_moves:
            om = o_map.get(san)
            mm = m_map.get(san)
            sf_ln = sf_map.get(san)

            o_play = f"{om.play_pct:5.1f}%" if om else "    -"
            o_scr = f"{om.side_score_pct:5.1f}%" if om else "    -"
            m_play = f"{mm.play_pct:5.1f}%" if mm else "    -"
            m_scr = f"{mm.side_score_pct:5.1f}%" if mm else "    -"
            sf_eval = sf_ln.score_str if sf_ln else "-"

            tags: list[str] = []
            if om and om.play_pct >= 15.0:
                tags.append("COMMON-AMATEUR")
            if mm and mm.play_pct >= 15.0:
                tags.append("MAIN-THEORY")
            if om and om.play_pct >= 8.0 and (not mm or mm.play_pct < 2.0):
                tags.append("AMATEUR-SPECIAL")
            if sf_ln and sf_ln.rank == 1:
                tags.append("SF#1")
            tag_str = ", ".join(tags) if tags else ""
            print(
                f"  {san:<7} | {o_play:>9} {o_scr:>8} | {m_play:>9} {m_scr:>8} | {sf_eval:>8} | {tag_str}"
            )
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    """Walk a PGN repertoire and flag popular opponent replies missing from the PGN."""
    pgn_path = Path(args.pgn)
    if not pgn_path.is_file():
        print(f"Nie znaleziono pliku PGN: {pgn_path}")
        return 1

    our_color = chess.WHITE if args.side.lower() == "white" else chess.BLACK
    client = LichessClient()

    # Build unified move tree across all games in the PGN
    covered_from_fen: dict[str, set[str]] = {}
    opponent_nodes: dict[str, tuple[chess.Board, list[str]]] = {}

    def walk(node: chess.pgn.GameNode, board: chess.Board, path: list[str]) -> None:
        if len(path) >= args.max_ply:
            return
        fen_key = board.epd()
        child_sans = {board.san(v.move) for v in node.variations}
        covered_from_fen.setdefault(fen_key, set()).update(child_sans)

        if board.turn != our_color and node.variations:
            if fen_key not in opponent_nodes:
                opponent_nodes[fen_key] = (board.copy(stack=False), list(path))

        for var in node.variations:
            san = board.san(var.move)
            board.push(var.move)
            walk(var, board, path + [san])
            board.pop()

    with pgn_path.open("r", encoding="utf-8-sig") as fh:
        game_count = 0
        while True:
            game = chess.pgn.read_game(fh)
            if game is None:
                break
            game_count += 1
            walk(game, game.board(), [])

    print(
        f"Sprawdzanie pokrycia: {pgn_path.name} ({game_count} gier, {len(opponent_nodes)} pozycji ruchu przeciwnika)"
    )
    cov_label = args.ratings if args.ratings else args.tier
    print(f"Baza: {args.db} (ratings={cov_label}, speeds={args.speeds}, min_pct={args.min_pct}%, min_games={args.min_games})\n")

    gaps: list[dict[str, Any]] = []
    for fen_key, (board, path) in opponent_nodes.items():
        covered = covered_from_fen.get(fen_key, set())
        if args.db == "masters":
            res = client.masters(board, moves=10, top_games=0, use_cache=not args.no_cache)
        else:
            res = client.online(
                board,
                tier=args.tier,
                ratings=args.ratings,
                speeds=args.speeds,
                moves=10,
                top_games=0,
                use_cache=not args.no_cache,
            )

        if res.total_games < args.min_games:
            continue

        missing = [
            mv
            for mv in res.moves
            if mv.san not in covered and mv.play_pct >= args.min_pct and mv.total >= args.min_move_games
        ]
        if missing:
            gaps.append(
                {
                    "path": " ".join(path),
                    "total_games": res.total_games,
                    "covered": sorted(covered),
                    "missing": missing,
                }
            )

    if not gaps:
        print("Świetnie! Nie znaleziono brakujących popularnych odpowiedzi powyżej progu.")
        return 0

    for g in gaps:
        print(f"Po: {g['path']}  ({g['total_games']:,} partii w bazie)")
        print(f"  Pokryte w PGN: {', '.join(g['covered'])}")
        for mv in g["missing"]:
            print(
                f"  [BRAK] {mv.san:<7} — {mv.play_pct:5.1f}% ({mv.total:,} partii), "
                f"wynik przeciwnika: {mv.side_score_pct:5.1f}%"
            )
        print()
    return 0


def cmd_master_game(args: argparse.Namespace) -> int:
    client = LichessClient()
    pgn_text, from_cache = client.master_game_pgn(args.game_id, use_cache=not args.no_cache)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(pgn_text + "\n", encoding="utf-8")
        print(f"Zapisano zweryfikowaną partię Masters ({args.game_id}) do: {out.resolve()}")
    else:
        cache_tag = "[cache]" if from_cache else "[live]"
        print(f"# Lichess Masters PGN: {args.game_id} {cache_tag}\n")
        print(pgn_text)
    return 0


def cmd_render_svg(args: argparse.Namespace) -> int:
    board, _ = parse_position(args.fen, args.moves)
    arrows: list[chess.svg.Arrow] = []
    fill: dict[chess.Square, str] = {}
    color_map = {"G": "#15781B", "R": "#882020", "B": "#003088", "Y": "#e68f00"}

    if args.cal:
        for item in args.cal.split(","):
            item = item.strip()
            if len(item) == 5 and item[0] in color_map:
                col = color_map[item[0]]
                tail = chess.parse_square(item[1:3])
                head = chess.parse_square(item[3:5])
                arrows.append(chess.svg.Arrow(tail, head, color=col))

    if args.csl:
        for item in args.csl.split(","):
            item = item.strip()
            if len(item) == 3 and item[0] in color_map:
                fill[chess.parse_square(item[1:3])] = color_map[item[0]] + "cc"

    orientation = chess.BLACK if args.flip else chess.WHITE
    svg = chess.svg.board(
        board=board,
        orientation=orientation,
        arrows=arrows,
        fill=fill,
        size=args.size,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"Zapisano diagram SVG: {out.resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Chess Analysis Toolkit (Stockfish + Lichess Masters/Online + Cloud + TB)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_pos_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--fen", help="Position FEN (default: startpos)")
        sp.add_argument("--moves", help="SAN/UCI moves from startpos or --fen, e.g. '1. d4 d5 2. c4 e6'")

    # engine
    sp_e = sub.add_parser("engine", help="Analyze position or check a candidate move with local Stockfish")
    add_pos_args(sp_e)
    sp_e.add_argument("--depth", type=int, default=20)
    sp_e.add_argument("--time", type=float, default=None, help="Time in seconds (overrides --depth)")
    sp_e.add_argument("--multipv", type=int, default=3)
    sp_e.add_argument("--check", help="Candidate SAN move to verify against Stockfish top lines")
    sp_e.add_argument("--threads", type=int, default=None)
    sp_e.add_argument("--hash", type=int, default=None)
    sp_e.set_defaults(func=cmd_engine)

    # masters
    sp_m = sub.add_parser("masters", help="Query Lichess Masters OTB database")
    add_pos_args(sp_m)
    sp_m.add_argument("--limit", type=int, default=12)
    sp_m.add_argument("--top-games", type=int, default=5)
    sp_m.add_argument("--since", type=int, default=None, help="Filter games since year (e.g. 2015)")
    sp_m.add_argument("--until", type=int, default=None)
    sp_m.add_argument("--no-cache", action="store_true")
    sp_m.set_defaults(func=cmd_masters)

    # online
    sp_o = sub.add_parser("online", help="Query Lichess Online/Amateur database by rating tier")
    add_pos_args(sp_o)
    sp_o.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="club")
    sp_o.add_argument("--ratings", help="Custom Lichess ratings CSV, e.g. '1600,1800,2000'")
    sp_o.add_argument("--speeds", default=DEFAULT_SPEEDS)
    sp_o.add_argument("--limit", type=int, default=12)
    sp_o.add_argument("--top-games", type=int, default=3)
    sp_o.add_argument("--no-cache", action="store_true")
    sp_o.set_defaults(func=cmd_online)

    # cloud
    sp_c = sub.add_parser("cloud", help="Query Lichess Cloud Eval (deep precomputed Stockfish)")
    add_pos_args(sp_c)
    sp_c.add_argument("--multipv", type=int, default=3)
    sp_c.add_argument("--no-cache", action="store_true")
    sp_c.set_defaults(func=cmd_cloud)

    # tablebase
    sp_tb = sub.add_parser("tablebase", help="Query Lichess Syzygy 7-piece tablebase")
    add_pos_args(sp_tb)
    sp_tb.add_argument("--no-cache", action="store_true")
    sp_tb.set_defaults(func=cmd_tablebase)

    # report (combined 360)
    sp_r = sub.add_parser("report", help="Full report: Stockfish + Masters DB + Online DB side-by-side")
    add_pos_args(sp_r)
    sp_r.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="2000_2500")
    sp_r.add_argument("--ratings", help="Custom Lichess ratings CSV, e.g. '2000,2200' or '2000,2200,2500'")
    sp_r.add_argument("--speeds", default=DEFAULT_SPEEDS)
    sp_r.add_argument("--depth", type=int, default=20)
    sp_r.add_argument("--time", type=float, default=None)
    sp_r.add_argument("--multipv", type=int, default=4)
    sp_r.add_argument("--limit", type=int, default=10)
    sp_r.add_argument("--threads", type=int, default=None)
    sp_r.add_argument("--hash", type=int, default=None)
    sp_r.add_argument("--skip-engine", action="store_true")
    sp_r.add_argument("--skip-db", action="store_true")
    sp_r.add_argument("--no-cache", action="store_true")
    sp_r.set_defaults(func=cmd_report)

    # coverage
    sp_cov = sub.add_parser("coverage", help="Audit PGN repertoire against Online/Masters DB for missing popular replies")
    sp_cov.add_argument("pgn", help="Path to PGN file")
    sp_cov.add_argument("--side", choices=["white", "black"], required=True)
    sp_cov.add_argument("--db", choices=["online", "masters"], default="online")
    sp_cov.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="2000_2500")
    sp_cov.add_argument("--ratings", help="Custom Lichess ratings CSV, e.g. '2000,2200' or '2000,2200,2500'")
    sp_cov.add_argument("--speeds", default=DEFAULT_SPEEDS)
    sp_cov.add_argument("--min-pct", type=float, default=5.0, help="Minimum opponent play%% to flag (default 5%%)")
    sp_cov.add_argument("--min-games", type=int, default=50, help="Min total games in position to audit")
    sp_cov.add_argument("--min-move-games", type=int, default=15, help="Min games for a single missing move")
    sp_cov.add_argument("--max-ply", type=int, default=24)
    sp_cov.add_argument("--no-cache", action="store_true")
    sp_cov.set_defaults(func=cmd_coverage)

    # master-game
    sp_mg = sub.add_parser("master-game", help="Fetch verbatim verified PGN of a Lichess Masters game by ID")
    sp_mg.add_argument("game_id", help="Lichess Masters game ID (from `masters` topGames, e.g. 87iVR0xv)")
    sp_mg.add_argument("--out", help="Optional path to save the PGN file")
    sp_mg.add_argument("--no-cache", action="store_true")
    sp_mg.set_defaults(func=cmd_master_game)

    # render-svg
    sp_svg = sub.add_parser("render-svg", help="Render board position with optional [%cal]/[%csl] arrows to SVG")
    add_pos_args(sp_svg)
    sp_svg.add_argument("--cal", help="Chessable/Lichess arrows, e.g. 'Gf2f3,Bf3e5,Rc5'")
    sp_svg.add_argument("--csl", help="Square highlights, e.g. 'Yd5,Rc5'")
    sp_svg.add_argument("--flip", action="store_true", help="View from Black's perspective")
    sp_svg.add_argument("--size", type=int, default=480)
    sp_svg.add_argument("--out", required=True, help="Output SVG path")
    sp_svg.set_defaults(func=cmd_render_svg)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, LichessAuthError, LichessRateLimitError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
