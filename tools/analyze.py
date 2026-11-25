"""Unified CLI for Stockfish, Lichess Masters/Online DB, Cloud Eval, Tablebase, Coverage, and SVG rendering."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import chess
import chess.pgn
import chess.svg
import requests

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
        except (LichessAuthError, LichessRateLimitError, requests.exceptions.RequestException) as exc:
            print(f"\n[Masters DB unavailable]: {type(exc).__name__}")

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
        except (LichessAuthError, LichessRateLimitError, requests.exceptions.RequestException, FileNotFoundError) as exc:
            print(f"\n[Online DB unavailable]: {type(exc).__name__}")

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


_LICHESS_ID_RE = re.compile(r"lichess\.org/([A-Za-z0-9]{8})")


def _classify_pgn_game(game: chess.pgn.Game) -> str:
    """Classify a PGN game as 'model', 'intro', or 'trainable'."""
    res = game.headers.get("Result", "*").strip()
    title = game.headers.get("White", "").strip().lower()
    event = game.headers.get("Event", "").strip().lower()
    if res in {"1-0", "0-1", "1/2-1/2"} or "LichessId" in game.headers or "model game" in title or "model game" in event:
        return "model"
    if "intro" in title or "why " in title or "dlaczego " in title or "wstęp" in title or "wstep" in title:
        return "intro"
    return "trainable"


def _extract_lichess_id(game: chess.pgn.Game) -> str | None:
    lid = game.headers.get("LichessId", "").strip()
    if re.fullmatch(r"[A-Za-z0-9]{8}", lid):
        return lid
    for hdr in ("Site", "Event", "White"):
        m = _LICHESS_ID_RE.search(game.headers.get(hdr, ""))
        if m:
            return m.group(1)
    return None


def _compute_cp_loss(best: Any, cand: Any, turn: chess.Color) -> int | None:
    """Compute non-negative centipawn loss for candidate move vs best line."""
    if not best or not cand:
        return None
    sign = 1 if turn == chess.WHITE else -1
    if best.score_cp is not None and cand.score_cp is not None:
        return max(0, (best.score_cp - cand.score_cp) * sign)
    if best.score_mate is not None and cand.score_mate is not None:
        best_for_us = best.score_mate * sign > 0
        cand_for_us = cand.score_mate * sign > 0
        if best_for_us and not cand_for_us:
            return 9999
        return 0
    if best.score_mate is not None:
        return 9999 if (best.score_mate * sign > 0) else 0
    if cand.score_mate is not None:
        return 9999 if (cand.score_mate * sign < 0) else 0
    return None


def cmd_audit_tree(args: argparse.Namespace) -> int:
    """Deterministic Gate-1 tree audit: deduplicated SF19 soundness, reach coverage, leaves, ECO & model games."""
    pgn_path = Path(args.pgn)
    if not pgn_path.is_file():
        print(f"ERROR: PGN file not found: {pgn_path}", file=sys.stderr)
        return 2

    our_color = chess.WHITE if args.side.lower() == "white" else chess.BLACK
    client = LichessClient()
    eco_lookup = EcoLookup()
    db_notes: list[str] = []
    seen_notes: set[str] = set()

    def add_note(msg: str) -> None:
        if msg not in seen_notes:
            seen_notes.add(msg)
            db_notes.append(msg)

    def fetch_db(board: chess.Board) -> tuple[ExplorerResult | None, ExplorerResult | None]:
        mst_res: ExplorerResult | None = None
        onl_res: ExplorerResult | None = None
        if args.db in {"auto", "masters"}:
            try:
                mst_res = client.masters(board, moves=10, top_games=0, use_cache=not args.no_cache)
            except (LichessAuthError, LichessRateLimitError, requests.exceptions.RequestException, ValueError) as exc:
                add_note(f"Masters DB skipped on uncached positions ({type(exc).__name__}).")
        if args.db in {"auto", "online"}:
            try:
                onl_res = client.online(
                    board,
                    tier=args.tier,
                    ratings=args.ratings,
                    speeds=args.speeds,
                    moves=10,
                    top_games=0,
                    use_cache=not args.no_cache,
                )
            except LichessAuthError:
                add_note("Online `/lichess` skipped on uncached positions (missing `LICHESS_API_TOKEN` / 401).")
            except (LichessRateLimitError, requests.exceptions.RequestException, ValueError) as exc:
                add_note(f"Online DB skipped on uncached positions ({type(exc).__name__}).")
        return mst_res, onl_res

    trainable_games: list[chess.pgn.Game] = []
    model_games: list[chess.pgn.Game] = []
    intro_count = 0

    with pgn_path.open("r", encoding="utf-8-sig") as fh:
        while True:
            game = chess.pgn.read_game(fh)
            if game is None:
                break
            kind = _classify_pgn_game(game)
            if kind == "model":
                model_games.append(game)
            elif kind == "intro":
                intro_count += 1
            else:
                trainable_games.append(game)

    if not trainable_games:
        print("ERROR: No trainable games found in PGN.", file=sys.stderr)
        return 2

    # Compute chapter root ply count (from --root-moves or longest common mainline prefix)
    if args.root_moves:
        _, root_sans = parse_position(moves=args.root_moves)
        root_ply = len(root_sans)
    else:
        main_ucis: list[list[str]] = []
        for g in trainable_games:
            seq = [mv.uci() for mv in g.mainline_moves()]
            if seq:
                main_ucis.append(seq)
        root_ply = 0
        if len(main_ucis) > 1:
            min_len = min(len(s) for s in main_ucis)
            while root_ply < min_len and all(s[root_ply] == main_ucis[0][root_ply] for s in main_ucis):
                root_ply += 1

    # Walk all trainable games: collect covered moves, opponent nodes (with max reach), our moves, and leaves
    covered_from_epd: dict[str, set[str]] = {}
    opp_nodes: dict[str, dict[str, Any]] = {}
    our_moves_by_epd: dict[str, dict[str, dict[str, Any]]] = {}
    leaf_nodes: dict[str, dict[str, Any]] = {}
    parse_or_illegal_errors: list[str] = []
    mainline_depths: list[int] = []
    rav_total = 0

    # First pass without DB so we know parent->child edges for BFS/recursive reach propagation
    opp_edges: dict[str, list[tuple[str, str]]] = {}  # parent_epd -> [(child_epd, san)]
    our_edges: dict[str, list[str]] = {}

    for g_idx, game in enumerate(trainable_games, 1):
        title = game.headers.get("White", f"Line #{g_idx}")
        if game.errors:
            for err in game.errors:
                parse_or_illegal_errors.append(f"{title}: parse error `{err}`")
        mainline_depths.append(len(list(game.mainline_moves())))

        def walk_collect(
            node: chess.pgn.GameNode,
            board: chess.Board,
            path: list[str],
            is_main: bool,
            in_rec_tree: bool = True,
        ) -> None:
            nonlocal rav_total
            epd = board.epd()

            if is_main and not node.variations and path:
                leaf_nodes.setdefault(
                    epd,
                    {
                        "board": board.copy(stack=False),
                        "path": " ".join(path),
                        "title": title,
                        "ply": len(path),
                    },
                )

            if not node.variations:
                return

            if in_rec_tree and len(path) < args.max_ply:
                covered_from_epd.setdefault(epd, set()).update(board.san(v.move) for v in node.variations)
                if board.turn != our_color:
                    if epd not in opp_nodes:
                        opp_nodes[epd] = {
                            "board": board.copy(stack=False),
                            "path": " ".join(path),
                            "ply": len(path),
                            "reach": 0.0,
                        }

            for idx, child in enumerate(node.variations):
                if idx > 0:
                    rav_total += 1
                if child.move not in board.legal_moves:
                    parse_or_illegal_errors.append(f"{title} after {' '.join(path)}: illegal move {child.move}")
                    continue
                san = board.san(child.move)
                uci = child.move.uci()
                child_is_main = is_main and idx == 0
                # Alternative moves for OUR side (idx > 0 on our turn) are illustrative/rejected tries,
                # so keep SF soundness checking on them while keeping coverage strictly inside our recommended tree.
                child_rec_tree = in_rec_tree and (board.turn != our_color or idx == 0)

                if board.turn == our_color:
                    slot = our_moves_by_epd.setdefault(epd, {})
                    if uci not in slot:
                        slot[uci] = {
                            "board": board.copy(stack=False),
                            "san": san,
                            "uci": uci,
                            "path": " ".join(path),
                            "title": title,
                            "is_main": child_is_main,
                        }
                    elif child_is_main:
                        slot[uci]["is_main"] = True

                board.push(child.move)
                child_epd = board.epd()
                if child_rec_tree and len(path) < args.max_ply:
                    if board.turn == our_color:  # parent was opponent turn
                        opp_edges.setdefault(epd, []).append((child_epd, san))
                    else:  # parent was our turn
                        our_edges.setdefault(epd, []).append(child_epd)

                walk_collect(child, board, path + [san], child_is_main, child_rec_tree)
                board.pop()

        walk_collect(game, game.board(), [], True)

    # Propagate repertoire reach from initial board along tree (reach=100% through root_ply, then * play_pct at opponent turns)
    db_cache_by_epd: dict[str, tuple[ExplorerResult | None, ExplorerResult | None]] = {}

    def get_db(epd: str, board: chess.Board) -> tuple[ExplorerResult | None, ExplorerResult | None]:
        if epd not in db_cache_by_epd:
            db_cache_by_epd[epd] = fetch_db(board)
        return db_cache_by_epd[epd]

    def pick_primary_db(mst: ExplorerResult | None, onl: ExplorerResult | None) -> ExplorerResult | None:
        if args.db == "online":
            return onl
        if args.db == "masters":
            return mst
        if onl is not None and onl.total_games >= args.min_games:
            return onl
        return mst or onl

    # BFS reach propagation up to max_ply
    start_epd = chess.Board().epd()
    best_reach: dict[str, float] = {start_epd: 100.0}
    frontier: list[tuple[str, int, float]] = [(start_epd, 0, 100.0)]
    while frontier:
        cur_epd, cur_ply, cur_reach = frontier.pop(0)
        if cur_epd in opp_nodes and cur_reach > opp_nodes[cur_epd]["reach"]:
            opp_nodes[cur_epd]["reach"] = cur_reach

        if cur_ply >= args.max_ply:
            continue

        # Advance through our-turn edges at zero reach decay
        for nxt_epd in our_edges.get(cur_epd, []):
            if cur_reach > best_reach.get(nxt_epd, -1.0):
                best_reach[nxt_epd] = cur_reach
                frontier.append((nxt_epd, cur_ply + 1, cur_reach))

        # Advance through opponent-turn edges
        edges = opp_edges.get(cur_epd, [])
        if edges and cur_epd in opp_nodes:
            node_info = opp_nodes[cur_epd]
            if cur_ply < root_ply:
                for nxt_epd, _ in edges:
                    if cur_reach > best_reach.get(nxt_epd, -1.0):
                        best_reach[nxt_epd] = cur_reach
                        frontier.append((nxt_epd, cur_ply + 1, cur_reach))
            else:
                mst, onl = get_db(cur_epd, node_info["board"])
                prim = pick_primary_db(mst, onl)
                pct_map = {mv.san: mv.play_pct for mv in prim.moves} if prim else {}
                for nxt_epd, san in edges:
                    child_reach = cur_reach * (pct_map.get(san, 0.0) / 100.0)
                    if child_reach > best_reach.get(nxt_epd, -1.0):
                        best_reach[nxt_epd] = child_reach
                        frontier.append((nxt_epd, cur_ply + 1, child_reach))

    # Coverage audit across opponent nodes
    line_gaps: list[dict[str, Any]] = []
    rav_candidates: list[dict[str, Any]] = []
    forced_nodes: list[dict[str, Any]] = []

    for epd, info in opp_nodes.items():
        if info["ply"] < root_ply:
            continue
        mst, onl = get_db(epd, info["board"])
        prim = pick_primary_db(mst, onl)
        if prim is None or prim.total_games < args.min_games:
            continue
        covered = covered_from_epd.get(epd, set())
        node_reach = info["reach"]

        if prim.moves and prim.moves[0].play_pct >= args.forced_pct:
            forced_nodes.append(
                {
                    "path": info["path"],
                    "top": prim.moves[0].san,
                    "pct": prim.moves[0].play_pct,
                    "games": prim.total_games,
                    "covered": prim.moves[0].san in covered,
                }
            )

        for mv in prim.moves:
            if mv.san in covered or mv.total < 10:
                continue
            cum_reach = node_reach * (mv.play_pct / 100.0)
            entry = {
                "path": info["path"],
                "move": mv.san,
                "play_pct": mv.play_pct,
                "cum_reach": cum_reach,
                "games": mv.total,
                "score_pct": mv.side_score_pct,
                "source": prim.source,
            }
            if cum_reach >= args.min_reach:
                line_gaps.append(entry)
            elif cum_reach >= args.rav_reach and mv.play_pct >= 10.0:
                rav_candidates.append(entry)

    # Deduplicated Stockfish audit on our moves + leaf practicality / tactical shots
    hard_vetoes: list[dict[str, Any]] = []
    soft_vetoes: list[dict[str, Any]] = []
    leaf_reports: list[dict[str, Any]] = []
    engine_name = "skipped"
    fen_top_cache: dict[str, list[Any]] = {}

    if not args.skip_engine:
        with StockfishAnalyzer(threads=args.threads, hash_mb=args.hash) as sf:
            engine_name = sf.engine_name
            for epd, move_map in our_moves_by_epd.items():
                sample_info = next(iter(move_map.values()))
                board = sample_info["board"]
                if epd not in fen_top_cache:
                    fen_top_cache[epd] = sf.analyze(board, depth=args.depth, multipv=3)
                top_lines = fen_top_cache[epd]
                best = top_lines[0] if top_lines else None
                for uci, info in move_map.items():
                    cand = next((ln for ln in top_lines if ln.move_uci == uci), None)
                    if cand is None:
                        iso = sf.analyze(
                            board,
                            depth=args.depth,
                            multipv=1,
                            root_moves=[chess.Move.from_uci(uci)],
                        )
                        cand = iso[0] if iso else None
                    loss = _compute_cp_loss(best, cand, board.turn)
                    row = {
                        "title": info["title"],
                        "path": info["path"],
                        "move": info["san"],
                        "kind": "MAIN" if info["is_main"] else "RAV",
                        "cand_eval": cand.score_str if cand else "?",
                        "wdl": _fmt_wdl(cand.wdl) if cand else "-",
                        "best": f"{best.move_san} ({best.score_str})" if best else "?",
                        "cp_loss": loss,
                    }
                    if loss is not None and loss > args.blunder_cp:
                        hard_vetoes.append(row)
                    elif loss is not None and loss >= args.soft_cp:
                        soft_vetoes.append(row)

            # Leaf scan
            for epd, linfo in leaf_nodes.items():
                board = linfo["board"]
                mst, onl = get_db(epd, board)
                prim = pick_primary_db(mst, onl)
                top_db_str = "-"
                forced_leaf = False
                if prim and prim.total_games > 0 and prim.moves:
                    top_db_str = ", ".join(
                        f"{m.san} {m.play_pct:.0f}% (scr {m.side_score_pct:.0f}%)" for m in prim.moves[:3]
                    )
                    if prim.moves[0].play_pct >= args.forced_pct:
                        forced_leaf = True

                lines = fen_top_cache.get(epd)
                if lines is None:
                    lines = sf.analyze(board, depth=args.depth, multipv=2)
                    fen_top_cache[epd] = lines
                top1 = lines[0] if lines else None
                top2 = lines[1] if len(lines) > 1 else None
                tactical_shot = False
                if top1 and top2:
                    if top1.score_mate is not None and top2.score_mate is None:
                        tactical_shot = True
                    elif top1.score_cp is not None and top2.score_cp is not None:
                        if abs(top1.score_cp - top2.score_cp) >= 100:
                            tactical_shot = True

                leaf_reports.append(
                    {
                        "title": linfo["title"],
                        "moves": linfo["ply"] // 2 + (linfo["ply"] % 2),
                        "sf_eval": f"{top1.move_san} {top1.score_str}" if top1 else "-",
                        "wdl": _fmt_wdl(top1.wdl) if top1 else "-",
                        "db_replies": top_db_str,
                        "flags": ", ".join(
                            f for f, cond in [("TACTICAL SHOT", tactical_shot), ("FORCED LEAF", forced_leaf)] if cond
                        )
                        or "-",
                    }
                )
    else:
        for epd, linfo in leaf_nodes.items():
            mst, onl = get_db(epd, linfo["board"])
            prim = pick_primary_db(mst, onl)
            top_db_str = "-"
            forced_leaf = False
            if prim and prim.total_games > 0 and prim.moves:
                top_db_str = ", ".join(
                    f"{m.san} {m.play_pct:.0f}% (scr {m.side_score_pct:.0f}%)" for m in prim.moves[:3]
                )
                if prim.moves[0].play_pct >= args.forced_pct:
                    forced_leaf = True
            leaf_reports.append(
                {
                    "title": linfo["title"],
                    "moves": linfo["ply"] // 2 + (linfo["ply"] % 2),
                    "sf_eval": "(skipped)",
                    "wdl": "-",
                    "db_replies": top_db_str,
                    "flags": "FORCED LEAF" if forced_leaf else "-",
                }
            )

    # Model game verbatim verification
    model_checks: list[dict[str, str]] = []
    model_errors = 0
    for idx, mg in enumerate(model_games, 1):
        title = mg.headers.get("White", f"Model #{idx}")
        gid = _extract_lichess_id(mg)
        if not gid:
            model_errors += 1
            model_checks.append({"title": title, "id": "-", "status": "MISSING_ID"})
            continue
        try:
            ref_pgn, from_cache = client.master_game_pgn(gid, use_cache=not args.no_cache)
            import io

            ref_game = chess.pgn.read_game(io.StringIO(ref_pgn))
            if ref_game is None:
                model_errors += 1
                model_checks.append({"title": title, "id": gid, "status": "EMPTY_REF_PGN"})
                continue
            pgn_ucis = [m.uci() for m in mg.mainline_moves()]
            ref_ucis = [m.uci() for m in ref_game.mainline_moves()]
            if pgn_ucis == ref_ucis and pgn_ucis:
                src = "cache" if from_cache else "live"
                model_checks.append({"title": title, "id": gid, "status": f"VERIFIED ({len(pgn_ucis)} plies, {src})"})
            else:
                model_errors += 1
                model_checks.append(
                    {
                        "title": title,
                        "id": gid,
                        "status": f"MISMATCH (pgn {len(pgn_ucis)} vs ref {len(ref_ucis)} plies)",
                    }
                )
        except Exception as exc:
            model_errors += 1
            model_checks.append({"title": title, "id": gid, "status": f"UNVERIFIED ({type(exc).__name__})"})

    # Verdict
    has_hard = bool(parse_or_illegal_errors or hard_vetoes or model_errors > 0 or line_gaps)
    has_soft = bool(soft_vetoes)
    verdict = "HARD_VETO" if has_hard else ("SOFT_VETO" if has_soft else "PASS")

    # Root ECO
    root_eco = None
    if root_ply > 0:
        sample_sans: list[str] = []
        b = chess.Board()
        for mv in list(trainable_games[0].mainline_moves())[:root_ply]:
            sample_sans.append(b.san(mv))
            b.push(mv)
        root_eco = eco_lookup.lookup_path(sample_sans)

    max_moves = max((p // 2 + p % 2) for p in mainline_depths) if mainline_depths else 0
    avg_moves = (sum(mainline_depths) / len(mainline_depths) / 2.0) if mainline_depths else 0.0
    total_checked_moves = sum(len(v) for v in our_moves_by_epd.values())

    md: list[str] = [
        f"# Gate 1 Deterministic Audit: `{pgn_path.name}`",
        "",
        f"**VERDICT: {verdict}**",
        "",
        f"- **Side:** `{args.side}` | **Engine:** `{engine_name}` (depth {args.depth}) | **Root ECO:** `{f'{root_eco[0]} {root_eco[1]}' if root_eco else 'N/A'}`",
        f"- **Games:** {len(trainable_games)} trainable (+ {intro_count} intro, {len(model_games)} model), {rav_total} RAVs",
        f"- **Depth profile:** avg `{avg_moves:.1f}` moves, max `{max_moves}` moves (unique our-side moves audited: `{total_checked_moves}`)",
        f"- **Findings:** `{len(parse_or_illegal_errors)}` parse/illegal | `{len(hard_vetoes)}` HARD_VETO (`>{args.blunder_cp}cp`) | `{len(soft_vetoes)}` SOFT_VETO (`{args.soft_cp}-{args.blunder_cp}cp`) | `{len(line_gaps)}` LINE GAP (`>={args.min_reach}%` reach) | `{len(rav_candidates)}` RAV candidates | `{model_errors}` model-game errors",
    ]
    for n in db_notes:
        md.append(f"- **DB Note:** {n}")

    if parse_or_illegal_errors:
        md.extend(["", "## Parse & Legality Errors", ""])
        for err in parse_or_illegal_errors:
            md.append(f"- {err}")

    if hard_vetoes or soft_vetoes:
        md.extend(["", "## Engine Soundness Vetoes", "", "| Severity | Line | Context | Move | Eval | WDL | Best | Loss |", "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |"])
        for r in hard_vetoes:
            md.append(
                f"| HARD_VETO | {r['title']} | `{r['path']}` | `{r['move']}` ({r['kind']}) | {r['cand_eval']} | {r['wdl']} | {r['best']} | {r['cp_loss']} cp |"
            )
        for r in soft_vetoes:
            md.append(
                f"| SOFT_VETO | {r['title']} | `{r['path']}` | `{r['move']}` ({r['kind']}) | {r['cand_eval']} | {r['wdl']} | {r['best']} | {r['cp_loss']} cp |"
            )

    if line_gaps:
        line_gaps.sort(key=lambda x: -x["cum_reach"])
        md.extend(["", f"## Missing High-Reach Branches (>= {args.min_reach:.1f}% Reach)", "", "| After | Missing | Play% | Cum Reach% | Games | Opp Score% | DB |", "| :--- | :--- | :---: | :---: | :---: | :---: | :--- |"])
        for g in line_gaps[:25]:
            md.append(
                f"| `{g['path']}` | `{g['move']}` | {g['play_pct']:.1f}% | {g['cum_reach']:.2f}% | {g['games']:,} | {g['score_pct']:.1f}% | {g['source']} |"
            )

    if rav_candidates:
        rav_candidates.sort(key=lambda x: -x["cum_reach"])
        md.extend(["", f"## Suggested Inline RAV Candidates ({args.rav_reach:.1f}% - {args.min_reach:.1f}% Reach, >=10% Conditional)", "", "| After | Candidate | Play% | Cum Reach% | Games | Opp Score% |", "| :--- | :--- | :---: | :---: | :---: | :---: |"])
        for g in rav_candidates[:20]:
            md.append(
                f"| `{g['path']}` | `{g['move']}` | {g['play_pct']:.1f}% | {g['cum_reach']:.2f}% | {g['games']:,} | {g['score_pct']:.1f}% |"
            )

    if forced_nodes:
        md.extend(["", f"## High-Forced Nodes (>= {args.forced_pct:.0f}% Single Reply)", ""])
        for fn in forced_nodes[:20]:
            cov_tag = "covered" if fn["covered"] else "missing"
            md.append(f"- `{fn['path']}` -> `{fn['top']}` played **{fn['pct']:.1f}%** ({fn['games']:,} games, {cov_tag})")

    md.extend(["", "## Leaf Practicality & Tactical-Shot Scan", "", "| Line | Moves | SF Top | WDL | Top DB Replies | Flags |", "| :--- | :---: | :--- | :--- | :--- | :--- |"])
    for lr in leaf_reports:
        md.append(f"| {lr['title']} | {lr['moves']} | {lr['sf_eval']} | {lr['wdl']} | {lr['db_replies']} | {lr['flags']} |")

    if model_checks:
        md.extend(["", "## Model Games Verification", "", "| Title | Lichess ID | Status |", "| :--- | :--- | :--- |"])
        for mc in model_checks:
            md.append(f"| {mc['title']} | `{mc['id']}` | {mc['status']} |")

    report_text = "\n".join(md) + "\n"
    print(report_text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report_text, encoding="utf-8")
        print(f"Saved audit report to: {out.resolve()}")

    return 1 if verdict == "HARD_VETO" else 0


def cmd_warm_cache(args: argparse.Namespace) -> int:
    """Batch-warm Lichess Masters (+ since) and Online DB cache for a chapter tree."""
    client = LichessClient()
    boards_by_epd: dict[str, chess.Board] = {}
    root_boards: list[chess.Board] = []

    if args.pgn:
        pgn_path = Path(args.pgn)
        if not pgn_path.is_file():
            raise FileNotFoundError(f"PGN not found: {pgn_path}")
        with pgn_path.open("r", encoding="utf-8-sig") as fh:
            while (game := chess.pgn.read_game(fh)) is not None:
                if game.headers.get("Result", "*") != "*":
                    continue

                def _walk_pgn(node: chess.pgn.GameNode, board: chess.Board, ply: int) -> None:
                    if ply > args.max_ply:
                        return
                    boards_by_epd.setdefault(board.epd(), board.copy(stack=False))
                    for ch in node.variations:
                        if ch.move in board.legal_moves:
                            board.push(ch.move)
                            _walk_pgn(ch, board, ply + 1)
                            board.pop()

                _walk_pgn(game, game.board(), 0)
                if game.variations and not root_boards:
                    root_boards.append(game.board())

    if args.moves:
        root_b, root_sans = parse_position(moves=args.moves)
        root_boards.append(root_b)
        b_walk = chess.Board()
        for san in root_sans:
            boards_by_epd.setdefault(b_walk.epd(), b_walk.copy(stack=False))
            b_walk.push_san(san)
        boards_by_epd.setdefault(b_walk.epd(), b_walk.copy(stack=False))

        # BFS down to min_reach / max_ply using local Online DB (if built) and Masters
        eff_ratings = args.ratings or RATING_TIERS.get(args.tier, args.tier)
        has_local_online = client.online_source != "api" and client.local_online.is_available(eff_ratings)
        bfs_seen: set[str] = {b_walk.epd()}
        frontier: list[tuple[chess.Board, int, float]] = [(b_walk.copy(stack=False), len(root_sans), 100.0)]
        while frontier:
            cur_b, cur_ply, cur_reach = frontier.pop(0)
            if cur_ply >= args.max_ply or cur_reach < args.min_reach:
                continue
            src_res: ExplorerResult | None = None
            if has_local_online:
                try:
                    onl = client.online(
                        cur_b,
                        tier=args.tier,
                        ratings=args.ratings,
                        speeds=args.speeds,
                        use_cache=True,
                    )
                    if onl.total_games >= 20 and onl.moves:
                        src_res = onl
                except Exception:
                    pass
            if src_res is None:
                try:
                    mst = client.masters(cur_b, use_cache=not args.no_cache)
                    if mst.total_games >= 20 and mst.moves:
                        src_res = mst
                except (requests.RequestException, LichessRateLimitError):
                    pass
            if src_res is None:
                continue
            for mv_stat in src_res.moves[:6]:
                nxt_reach = cur_reach * (mv_stat.play_pct / 100.0)
                if nxt_reach < args.min_reach:
                    continue
                nb = cur_b.copy(stack=False)
                nb.push_san(mv_stat.san)
                nepd = nb.epd()
                boards_by_epd.setdefault(nepd, nb)
                if nepd not in bfs_seen:
                    bfs_seen.add(nepd)
                    frontier.append((nb, cur_ply + 1, nxt_reach))

    if not boards_by_epd:
        raise ValueError("Provide --pgn and/or --moves to warm cache.")

    mst_hits = mst_fetch = since_hits = since_fetch = onl_hits = onl_fetch = 0
    eff_ratings = args.ratings or RATING_TIERS.get(args.tier, args.tier)
    using_local_online = client.online_source != "api" and client.local_online.is_available(eff_ratings)
    onl_auth_ok = not using_local_online
    since_yr = args.since if args.since and args.since > 0 else None

    for epd, b in boards_by_epd.items():
        try:
            r_mst = client.masters(b, use_cache=not args.no_cache)
            if r_mst.from_cache:
                mst_hits += 1
            else:
                mst_fetch += 1
        except requests.RequestException as exc:
            print(f"  [warn] Masters skipped at {epd[:24]}: {type(exc).__name__}")

        if since_yr:
            try:
                r_s = client.masters(b, since=since_yr, use_cache=not args.no_cache)
                if r_s.from_cache:
                    since_hits += 1
                else:
                    since_fetch += 1
            except requests.RequestException:
                pass

        if onl_auth_ok:
            try:
                r_onl = client.online(
                    b,
                    tier=args.tier,
                    ratings=args.ratings,
                    speeds=args.speeds,
                    use_cache=not args.no_cache,
                )
                if r_onl.from_cache:
                    onl_hits += 1
                else:
                    onl_fetch += 1
            except LichessAuthError as exc:
                onl_auth_ok = False
                print(f"Notice: Online DB skipped ({exc.args[0].splitlines()[0]})")
            except requests.RequestException as exc:
                print(f"  [warn] Online skipped at {epd[:24]}: {type(exc).__name__}")

    models_fetched = 0
    if args.fetch_models > 0:
        seen_ids: set[str] = set()
        seed_boards = root_boards if root_boards else list(boards_by_epd.values())[:5]
        for sb in seed_boards:
            try:
                r_mst = client.masters(sb, use_cache=True)
            except requests.RequestException:
                continue
            for tg in r_mst.top_games:
                gid = tg.get("id")
                if not gid or gid in seen_ids:
                    continue
                seen_ids.add(gid)
                try:
                    _, cached = client.master_game_pgn(gid, use_cache=not args.no_cache)
                    if not cached:
                        models_fetched += 1
                except requests.RequestException:
                    pass
                if len(seen_ids) >= args.fetch_models:
                    break
            if len(seen_ids) >= args.fetch_models:
                break

    online_status = (
        f"  Online ({args.ratings or args.tier}): served offline via {client.local_online.db_path}\n"
        if using_local_online
        else (f"  Online ({args.ratings or args.tier}): {onl_hits} cached, {onl_fetch} fetched\n" if onl_auth_ok else "")
    )
    print(
        f"Warmed cache across {len(boards_by_epd)} unique positions:\n"
        f"  Masters (all-time): {mst_hits} cached, {mst_fetch} fetched\n"
        + (f"  Masters (since {since_yr}): {since_hits} cached, {since_fetch} fetched\n" if since_yr else "")
        + online_status
        + f"  Model PGNs newly fetched: {models_fetched}"
    )
    return 0


def _classify_endgame(board: chess.Board) -> str:
    def _mat(c: chess.Color) -> str:
        parts = []
        for pt, sym in [(chess.QUEEN, "Q"), (chess.ROOK, "R"), (chess.BISHOP, "B"), (chess.KNIGHT, "N")]:
            cnt = len(board.pieces(pt, c))
            parts.extend([sym] * cnt)
        return "".join(parts) or "K"

    return f"{_mat(chess.WHITE)} vs {_mat(chess.BLACK)}"


def _wing_pawns(board: chess.Board) -> str:
    wp = board.pieces(chess.PAWN, chess.WHITE)
    bp = board.pieces(chess.PAWN, chess.BLACK)

    def _cnt(pset: chess.SquareSet, files: set[int]) -> int:
        return sum(1 for s in pset if chess.square_file(s) in files)

    return (
        f"Q:{_cnt(wp, {0,1,2})}v{_cnt(bp, {0,1,2})} "
        f"C:{_cnt(wp, {3,4})}v{_cnt(bp, {3,4})} "
        f"K:{_cnt(wp, {5,6,7})}v{_cnt(bp, {5,6,7})}"
    )


def _pawn_diff_note(
    gm_moves: list[chess.Move],
    gm_init: chess.Board,
    our_color: chess.Color,
    skeleton_lines: list[tuple[str, list[chess.Move], chess.Board]],
) -> str | None:
    if not skeleton_lines:
        return None
    opp_color = not our_color
    best_title = ""
    best_shared = -1
    best_line_mvs: list[chess.Move] = []
    best_leaf: chess.Board | None = None
    for title, line_mvs, leaf_b in skeleton_lines:
        shared = 0
        for gm_m, ln_m in zip(gm_moves, line_mvs):
            if gm_m == ln_m:
                shared += 1
            else:
                break
        if shared > best_shared:
            best_shared = shared
            best_title = title
            best_line_mvs = line_mvs
            best_leaf = leaf_b
    if best_leaf is None or best_shared < 4:
        return None
    # Walk GM up to best_leaf length / divergence
    gb = gm_init.copy(stack=False)
    reached_leaf = False
    for idx, mv in enumerate(gm_moves):
        gb.push(mv)
        if gb.epd() == best_leaf.epd():
            reached_leaf = True
            break
        if idx > len(best_line_mvs) + 8:
            break
    if reached_leaf:
        return f"EXACT leaf match ({best_title})"

    # Describe first divergence vs closest skeleton line + wing pawn difference
    div_b = gm_init.copy(stack=False)
    for mv in best_line_mvs[:best_shared]:
        div_b.push(mv)
    div_num = div_b.fullmove_number
    dots = "..." if div_b.turn == chess.BLACK else "."
    gm_san = div_b.san(gm_moves[best_shared]) if best_shared < len(gm_moves) else "end"
    ln_san = div_b.san(best_line_mvs[best_shared]) if best_shared < len(best_line_mvs) else "end"
    gb_post = gm_init.copy(stack=False)
    for mv in gm_moves[: min(len(gm_moves), len(best_line_mvs))]:
        gb_post.push(mv)
    opp_gm = {chess.square_name(s) for s in gb_post.pieces(chess.PAWN, opp_color)}
    opp_ln = {chess.square_name(s) for s in best_leaf.pieces(chess.PAWN, opp_color)}
    our_gm = {chess.square_name(s) for s in gb_post.pieces(chess.PAWN, our_color)}
    our_ln = {chess.square_name(s) for s in best_leaf.pieces(chess.PAWN, our_color)}
    diffs: list[str] = []
    if opp_gm != opp_ln:
        diffs.append(f"opp {sorted(opp_gm - opp_ln)} vs {sorted(opp_ln - opp_gm)}")
    if our_gm != our_ln:
        diffs.append(f"our {sorted(our_gm - our_ln)} vs {sorted(our_ln - our_gm)}")
    diff_s = ("; pawns " + ", ".join(diffs)) if diffs else ""
    return f"DIVERGES at {div_num}{dots}{gm_san} vs '{best_title}' ({ln_san}){diff_s}"


def _digest_master_game(
    raw_pgn: str,
    gid: str,
    tabiya_epd: str,
    our_color: chess.Color,
    skeleton_lines: list[tuple[str, list[chess.Move], chess.Board]] | None = None,
) -> dict[str, Any] | None:
    import io

    game = chess.pgn.read_game(io.StringIO(raw_pgn))
    if game is None:
        return None
    b = game.board()
    moves = list(game.mainline_moves())
    start_idx: int | None = None
    for idx, mv in enumerate(moves):
        if b.epd() == tabiya_epd:
            start_idx = idx
            break
        b.push(mv)
    if start_idx is None and b.epd() == tabiya_epd:
        start_idx = len(moves)
    if start_idx is None:
        start_idx = 0
        b = game.board()

    next_sans: list[str] = []
    our_breaks: list[str] = []
    opp_breaks: list[str] = []
    our_routes: list[str] = []
    trades: list[str] = []
    q_trade_move: int | None = None
    endgame_mat = ""
    endgame_pawns = ""

    for offset, mv in enumerate(moves[start_idx:]):
        san = b.san(mv)
        mover = b.turn
        piece = b.piece_at(mv.from_square)
        is_capture = b.is_capture(mv)
        captured = b.piece_at(mv.to_square)
        if offset < 16:
            prefix = f"{b.fullmove_number}." if mover == chess.WHITE else (f"{b.fullmove_number}..." if offset == 0 else "")
            next_sans.append(f"{prefix}{san}".strip())

        if offset < 60 and piece is not None:
            to_rank = chess.square_rank(mv.to_square)
            to_file = chess.square_file(mv.to_square)
            mv_tag = f"{b.fullmove_number}.{san}" if mover == chess.WHITE else f"{b.fullmove_number}...{san}"
            if piece.piece_type == chess.PAWN:
                if is_capture or (mover == chess.WHITE and to_rank >= 3) or (mover == chess.BLACK and to_rank <= 4):
                    if mover == our_color and len(our_breaks) < 6:
                        our_breaks.append(mv_tag)
                    elif mover != our_color and len(opp_breaks) < 5:
                        opp_breaks.append(mv_tag)
            else:
                if is_capture and captured is not None and captured.piece_type != chess.PAWN and len(trades) < 6:
                    trades.append(mv_tag)
                if mover == our_color and len(our_routes) < 7:
                    is_castle = b.is_castling(mv)
                    active_rank = (to_rank >= 2) if mover == chess.WHITE else (to_rank <= 5)
                    central_rook = piece.piece_type == chess.ROOK and to_file in {2, 3, 4, 5}
                    if is_castle or (
                        piece.piece_type in {chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN}
                        and (active_rank or central_rook)
                        and not is_capture
                    ):
                        our_routes.append(mv_tag)

        b.push(mv)
        if q_trade_move is None and not b.pieces(chess.QUEEN, chess.WHITE) and not b.pieces(chess.QUEEN, chess.BLACK):
            q_trade_move = b.fullmove_number
            endgame_mat = _classify_endgame(b)
            endgame_pawns = _wing_pawns(b)

    struct_note = _pawn_diff_note(moves, game.board(), our_color, skeleton_lines or [])
    return {
        "id": gid,
        "white": game.headers.get("White", "?"),
        "black": game.headers.get("Black", "?"),
        "date": (game.headers.get("Date", "????") or "????")[:4],
        "result": game.headers.get("Result", "*"),
        "next_moves": " ".join(next_sans),
        "our_breaks": ", ".join(our_breaks) or "-",
        "opp_breaks": ", ".join(opp_breaks) or "-",
        "our_routes": ", ".join(our_routes) or "-",
        "trades": ", ".join(trades) or "-",
        "endgame": f"m.{q_trade_move} ({endgame_mat} | {endgame_pawns})" if q_trade_move else "queens stay on",
        "struct_note": struct_note,
    }


def cmd_mine_ideas(args: argparse.Namespace) -> int:
    """Mine 3-5 (or N) high-rated Masters games per tabiya into a compact strategic digest."""
    client = LichessClient()
    our_color = chess.WHITE if args.side == "white" else chess.BLACK
    tabiyas: list[tuple[str, chess.Board]] = []
    skeleton_lines: list[tuple[str, list[chess.Move], chess.Board]] = []

    for spec in args.tabiya or []:
        if "=" in spec:
            label, mv_str = spec.split("=", 1)
        else:
            label, mv_str = spec, spec
        b, _ = parse_position(moves=mv_str.strip())
        tabiyas.append((label.strip(), b))

    if args.pgn:
        pgn_path = Path(args.pgn)
        if not pgn_path.is_file():
            raise FileNotFoundError(f"PGN not found: {pgn_path}")
        from validate_chessable import classify_game  # noqa: E402

        seen_epds: set[str] = set()
        with pgn_path.open("r", encoding="utf-8-sig") as fh:
            while (g := chess.pgn.read_game(fh)) is not None:
                if classify_game(g) != "trainable":
                    continue
                b = g.board()
                mvs = list(g.mainline_moves())
                for mv in mvs:
                    b.push(mv)
                title = g.headers.get("White", f"Line {len(skeleton_lines)+1}")
                skeleton_lines.append((title, mvs, b.copy(stack=False)))
                if not args.tabiya and len(tabiyas) < args.max_tabiyas and b.epd() not in seen_epds:
                    seen_epds.add(b.epd())
                    tabiyas.append((title, b))

    if not tabiyas:
        raise ValueError("Provide at least one --tabiya 'Label=1. d4 ...' or --pgn.")

    md: list[str] = [
        f"# Compact GM Idea Digest (side={args.side}, target={args.games_per_tabiya} games/tabiya)",
        "",
    ]

    for label, tb in tabiyas:
        md.append(f"## {label}")
        candidates: list[dict[str, Any]] = []
        seen_gids: set[str] = set()

        def _collect_from_board(qb: chess.Board) -> None:
            try:
                res = client.masters(qb, top_games=5, since=args.since, use_cache=not args.no_cache)
            except requests.RequestException:
                return
            for tg in res.top_games:
                gid = tg.get("id")
                if gid and gid not in seen_gids:
                    seen_gids.add(gid)
                    candidates.append(tg)

        _collect_from_board(tb)
        if len(candidates) < args.games_per_tabiya:
            try:
                root_res = client.masters(tb, top_games=5, since=args.since, use_cache=not args.no_cache)
                for mv_s in root_res.moves[:3]:
                    nb = tb.copy(stack=False)
                    nb.push_san(mv_s.san)
                    _collect_from_board(nb)
                    if len(candidates) >= args.games_per_tabiya * 2:
                        break
            except requests.RequestException:
                pass

        # Prioritize ~75% our wins + ~25% opponent counterplay wins
        our_win = "white" if our_color == chess.WHITE else "black"
        opp_win = "black" if our_color == chess.WHITE else "white"
        wins = [g for g in candidates if g.get("winner") == our_win]
        losses = [g for g in candidates if g.get("winner") == opp_win]
        draws = [g for g in candidates if g.get("winner") not in {our_win, opp_win}]

        want_opp = 1 if args.games_per_tabiya >= 4 else 0
        picked: list[dict[str, Any]] = wins[: max(1, args.games_per_tabiya - want_opp)]
        picked.extend(losses[:want_opp])
        for pool in (wins, losses, draws):
            for g in pool:
                if len(picked) >= args.games_per_tabiya:
                    break
                if g not in picked:
                    picked.append(g)

        epd = tb.epd()
        digested = 0
        for tg in picked[: args.games_per_tabiya]:
            gid = tg.get("id", "")
            try:
                raw_pgn, _ = client.master_game_pgn(gid, use_cache=not args.no_cache)
            except requests.RequestException:
                continue
            d = _digest_master_game(raw_pgn, gid, epd, our_color, skeleton_lines=skeleton_lines)
            if d is None:
                continue
            digested += 1
            struct_line = f"\n  - Structure vs Skeleton: `{d['struct_note']}`" if d.get("struct_note") else ""
            md.append(
                f"- **`{d['id']}`** {d['white']} vs {d['black']} ({d['date']}, `{d['result']}`)"
                f" | Next: `{d['next_moves']}`{struct_line}\n"
                f"  - Routes: `{d['our_routes']}` | Our breaks: `{d['our_breaks']}`"
                f" | Opp breaks: `{d['opp_breaks']}` | Trades: `{d['trades']}` | EG: `{d['endgame']}`"
            )
        if digested == 0:
            md.append("- *(No cached/reachable `/masters` games found at this tabiya.)*")
        md.append("")

    out_text = "\n".join(md)
    print(out_text)
    if args.out:
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(out_text, encoding="utf-8")
        print(f"Saved GM digest to: {out_p.resolve()}")
    return 0


def cmd_slice_pgn(args: argparse.Namespace) -> int:
    """Write a 1-based game slice from a multi-game PGN so verifier subagents inspect small batches."""
    pgn_path = Path(args.pgn)
    if not pgn_path.is_file():
        raise FileNotFoundError(f"PGN not found: {pgn_path}")

    selected: set[int] = set()
    for part in args.games.split(","):
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

    from validate_chessable import classify_game  # noqa: E402

    kept: list[str] = []
    idx = 0
    with pgn_path.open("r", encoding="utf-8-sig") as fh:
        while (game := chess.pgn.read_game(fh)) is not None:
            if args.trainable_only and classify_game(game) != "trainable":
                continue
            idx += 1
            if idx in selected:
                exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
                kept.append(game.accept(exporter))

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text("\n\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    print(f"Wrote {len(kept)} game(s) from {pgn_path.name} ({args.games}) to {out_p}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Verify local toolkit health: Stockfish, caches, Online DB, and global skill sync."""
    import hashlib
    import sqlite3
    from chess_env import CACHE_DB, ENGINE_CACHE_DB, LOCAL_ONLINE_DB, ROOT_DIR, find_stockfish

    bad = 0
    try:
        sf_path = find_stockfish()
        print(f"[OK] Stockfish: {sf_path}")
    except FileNotFoundError as exc:
        print(f"[FAIL] Stockfish: {exc}")
        bad = 1

    if ENGINE_CACHE_DB.is_file():
        with sqlite3.connect(ENGINE_CACHE_DB) as conn:
            n_sf = conn.execute("SELECT COUNT(*) FROM sf_cache").fetchone()[0]
        print(f"[OK] Engine cache: {n_sf} positions in {ENGINE_CACHE_DB.name}")
    else:
        print(f"[WARN] Engine cache not yet created: {ENGINE_CACHE_DB}")

    if LOCAL_ONLINE_DB.is_file():
        with sqlite3.connect(LOCAL_ONLINE_DB) as conn:
            bands = [r[0] for r in conn.execute("SELECT DISTINCT band FROM pos_stats ORDER BY band").fetchall()]
        print(f"[OK] Local Online DB: bands={bands} ({LOCAL_ONLINE_DB.name})")
    else:
        print(f"[WARN] Local Online DB missing: {LOCAL_ONLINE_DB}")

    if CACHE_DB.is_file():
        with sqlite3.connect(CACHE_DB) as conn:
            n_mst = conn.execute("SELECT COUNT(*) FROM api_cache WHERE cache_key LIKE 'masters%'").fetchone()[0]
            n_pgn = conn.execute("SELECT COUNT(*) FROM api_cache WHERE cache_key LIKE 'master_pgn|%'").fetchone()[0]
        print(f"[OK] Explorer cache: {n_mst} masters queries, {n_pgn} GM PGNs")

    global_root = Path.home() / ".gemini" / "config" / "skills"
    ws_root = ROOT_DIR / "skills"
    for name in ("chess-analysis-architect", "chessable-pgn"):
        ws_dir = ws_root / name
        gl_dir = global_root / name
        if not ws_dir.exists():
            continue
        if not gl_dir.exists():
            print(f"[DRIFT] Missing global skill: {gl_dir}")
            bad = 1
            continue
        drift = []
        ws_files = {p.relative_to(ws_dir): hashlib.sha256(p.read_bytes()).hexdigest() for p in ws_dir.rglob("*") if p.is_file()}
        gl_files = {p.relative_to(gl_dir): hashlib.sha256(p.read_bytes()).hexdigest() for p in gl_dir.rglob("*") if p.is_file()}
        for rel, h in ws_files.items():
            if gl_files.get(rel) != h:
                drift.append(str(rel))
        if drift:
            print(f"[SKILL DRIFT] {name}: differing files {drift} (sync global -> workspace!)")
            bad = 1
        else:
            kind = "junction" if gl_dir.is_symlink() or str(gl_dir.resolve()) == str(ws_dir.resolve()) else "copied-sync"
            print(f"[OK] Skill '{name}' synced ({kind}, {len(ws_files)} files)")
    return bad


def cmd_gate1(args: argparse.Namespace) -> int:
    """Gate 1 macro: run audit-tree and print <=40-line compact summary."""
    import io
    from contextlib import redirect_stdout

    pgn_p = Path(args.pgn)
    out_p = Path(args.out) if args.out else (Path("cache") / f"{pgn_p.stem}_audit.md")
    ns = argparse.Namespace(
        pgn=str(pgn_p),
        side=args.side,
        root_moves=None,
        db="auto",
        tier=args.tier,
        ratings=None,
        speeds=DEFAULT_SPEEDS,
        min_reach=args.min_reach,
        rav_reach=0.5,
        forced_pct=85.0,
        min_games=30,
        max_ply=30,
        depth=args.depth,
        blunder_cp=70,
        soft_cp=35,
        threads=None,
        hash=None,
        skip_engine=False,
        no_cache=False,
        out=str(out_p),
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_audit_tree(ns)
    report = out_p.read_text(encoding="utf-8") if out_p.is_file() else buf.getvalue()
    lines = report.splitlines()
    keep = [ln for ln in lines if ln.startswith(("# ", "## ", "- **", "| `", "Verdict", "HARD", "SOFT"))]
    print(f"GATE 1 ({pgn_p.name}) -> exit={rc} | full report: {out_p}")
    for ln in keep[:36]:
        print(ln)
    if len(keep) > 36:
        print(f"... +{len(keep) - 36} lines in {out_p}")
    return rc


def cmd_gate2(args: argparse.Namespace) -> int:
    """Gate 2 macro: run validate_chessable --engine-check --verify-models --check-plan --check-intros --provenance --summary."""
    import subprocess

    pgn_p = Path(args.pgn)
    res_p = Path(args.emit_residual) if args.emit_residual else (Path("cache") / f"{pgn_p.stem}_residual.md")
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / "validate_chessable.py"),
        str(pgn_p),
        "--engine-check",
        "--depth",
        str(args.depth),
        "--side",
        args.side,
        "--tier",
        args.tier,
        "--verify-models",
        "--check-plan",
        "--check-intros",
        "--provenance",
        "--emit-residual",
        str(res_p),
        "--summary",
    ]
    if args.skeleton:
        cmd.extend(["--skeleton", args.skeleton])
    if args.claims:
        cmd.extend(["--claims", args.claims])
    if args.ledger:
        cmd.extend(["--ledger", args.ledger])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "").strip()
    if out:
        for ln in out.splitlines()[:40]:
            print(ln)
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    print(f"Residual claims written to: {res_p}")
    return proc.returncode


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
    sp_svg = sub.add_parser("render-svg", help="Render board position with optional [%%cal]/[%%csl] arrows to SVG")
    add_pos_args(sp_svg)
    sp_svg.add_argument("--cal", help="Chessable/Lichess arrows, e.g. 'Gf2f3,Bf3e5,Rc5'")
    sp_svg.add_argument("--csl", help="Square highlights, e.g. 'Yd5,Rc5'")
    sp_svg.add_argument("--flip", action="store_true", help="View from Black's perspective")
    sp_svg.add_argument("--size", type=int, default=480)
    sp_svg.add_argument("--out", required=True, help="Output SVG path")
    sp_svg.set_defaults(func=cmd_render_svg)

    # warm-cache
    sp_wc = sub.add_parser("warm-cache", help="Batch-warm Masters + Online DB cache for a chapter tree")
    sp_wc.add_argument("--pgn", help="Optional skeleton or chapter PGN to walk")
    sp_wc.add_argument("--moves", help="Optional root SAN moves for reach-bounded BFS warming")
    sp_wc.add_argument("--side", choices=["white", "black"], default="white")
    sp_wc.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="2000_2500")
    sp_wc.add_argument("--ratings", help="Custom Lichess ratings CSV, e.g. '2000,2200,2500'")
    sp_wc.add_argument("--speeds", default=DEFAULT_SPEEDS)
    sp_wc.add_argument("--max-ply", type=int, default=18)
    sp_wc.add_argument("--min-reach", type=float, default=1.5)
    sp_wc.add_argument("--since", type=int, default=2015, help="Also cache Masters since year (0 to disable)")
    sp_wc.add_argument("--fetch-models", type=int, default=0, help="Fetch up to N Masters topGames PGNs")
    sp_wc.add_argument("--no-cache", action="store_true")
    sp_wc.set_defaults(func=cmd_warm_cache)

    # mine-ideas
    sp_mi = sub.add_parser("mine-ideas", help="Digest 3-5 top GM games per tabiya into compact strategic bullets")
    sp_mi.add_argument("--tabiya", action="append", help="Tabiya spec 'Label=1. d4 d5 ...' (repeatable)")
    sp_mi.add_argument("--pgn", help="Skeleton/chapter PGN (extracts tabiyas if omitted, and annotates structural divergence vs each line)")
    sp_mi.add_argument("--side", choices=["white", "black"], required=True)
    sp_mi.add_argument("--games-per-tabiya", type=int, default=5)
    sp_mi.add_argument("--max-tabiyas", type=int, default=8)
    sp_mi.add_argument("--since", type=int, default=None)
    sp_mi.add_argument("--no-cache", action="store_true")
    sp_mi.add_argument("--out", help="Optional Markdown digest output path")
    sp_mi.set_defaults(func=cmd_mine_ideas)

    # audit-tree
    sp_at = sub.add_parser(
        "audit-tree",
        help="Deterministic Gate 1 tree audit (deduplicated SF19, cumulative reach coverage, leaves & model games)",
    )
    sp_at.add_argument("pgn", help="Path to skeleton or chapter PGN")
    sp_at.add_argument("--side", choices=["white", "black"], required=True)
    sp_at.add_argument("--root-moves", help="Optional SAN moves defining chapter root (defaults to common prefix)")
    sp_at.add_argument("--db", choices=["auto", "masters", "online"], default="auto")
    sp_at.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="2000_2500")
    sp_at.add_argument("--ratings", help="Custom Lichess ratings CSV, e.g. '2000,2200,2500'")
    sp_at.add_argument("--speeds", default=DEFAULT_SPEEDS)
    sp_at.add_argument("--min-reach", type=float, default=2.0, help="Cumulative %% reach threshold for missing lines (default 2.0)")
    sp_at.add_argument("--rav-reach", type=float, default=0.5, help="Cumulative %% reach threshold for inline RAV suggestions (default 0.5)")
    sp_at.add_argument("--forced-pct", type=float, default=85.0, help="Flag nodes/leaves where #1 reply >= %% (default 85.0)")
    sp_at.add_argument("--min-games", type=int, default=30, help="Min DB games in node to evaluate gaps (default 30)")
    sp_at.add_argument("--max-ply", type=int, default=30, help="Max ply depth for coverage check (default 30)")
    sp_at.add_argument("--depth", type=int, default=18, help="Stockfish depth for soundness & leaf scan (default 18)")
    sp_at.add_argument("--blunder-cp", type=int, default=70, help="HARD_VETO cp loss threshold (default 70)")
    sp_at.add_argument("--soft-cp", type=int, default=35, help="SOFT_VETO cp loss threshold (default 35)")
    sp_at.add_argument("--threads", type=int, default=None)
    sp_at.add_argument("--hash", type=int, default=None)
    sp_at.add_argument("--skip-engine", action="store_true")
    sp_at.add_argument("--no-cache", action="store_true")
    sp_at.add_argument("--out", help="Optional Markdown report path")
    sp_at.set_defaults(func=cmd_audit_tree)

    # slice-pgn
    sp_sp = sub.add_parser("slice-pgn", help="Extract a 1-based game slice from a PGN for batched verification")
    sp_sp.add_argument("pgn", help="Source PGN path")
    sp_sp.add_argument("--games", required=True, help="1-based game range, e.g. '1-10' or '11-20'")
    sp_sp.add_argument("--trainable-only", action="store_true", help="Count only trainable games (Result '*')")
    sp_sp.add_argument("--out", required=True, help="Output PGN path")
    sp_sp.set_defaults(func=cmd_slice_pgn)

    # doctor
    sp_doc = sub.add_parser("doctor", help="Check Stockfish, caches, Online DB, and global skill sync")
    sp_doc.set_defaults(func=cmd_doctor)

    # gate1
    sp_g1 = sub.add_parser("gate1", help="Run Gate 1 tree audit and print compact <=40-line summary")
    sp_g1.add_argument("pgn")
    sp_g1.add_argument("--side", choices=["white", "black"], required=True)
    sp_g1.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="2000_2500")
    sp_g1.add_argument("--min-reach", type=float, default=2.0)
    sp_g1.add_argument("--depth", type=int, default=18)
    sp_g1.add_argument("--out", default=None)
    sp_g1.set_defaults(func=cmd_gate1)

    # gate2
    sp_g2 = sub.add_parser("gate2", help="Run Gate 2 deterministic + provenance validation (<=40 lines + residual.md)")
    sp_g2.add_argument("pgn")
    sp_g2.add_argument("--side", choices=["white", "black"], required=True)
    sp_g2.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="2000_2500")
    sp_g2.add_argument("--depth", type=int, default=18)
    sp_g2.add_argument("--skeleton", default=None)
    sp_g2.add_argument("--claims", default=None)
    sp_g2.add_argument("--ledger", default=None)
    sp_g2.add_argument("--emit-residual", default=None)
    sp_g2.set_defaults(func=cmd_gate2)

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
