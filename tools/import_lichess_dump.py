"""Build a compact offline Lichess Online Opening Explorer SQLite DB from Hugging Face Parquet.

Streams rating- and speed-filtered games from `Lichess/standard-chess-games` using DuckDB
(column projection + predicate pushdown + max-games cap) so you never download a 100M-game
monthly dump, parses only the first `--max-ply` half-moves with a transposition-aware EPD
move cache, and exports aggregated move statistics to `data/lichess_online.db`.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import chess
import duckdb
import requests
import truststore

truststore.inject_into_ssl()

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "tools"))

from chess_env import DEFAULT_SPEEDS, LOCAL_ONLINE_DB, RATING_TIERS  # noqa: E402

HF_API_TREE = "https://huggingface.co/api/datasets/Lichess/standard-chess-games/tree/main/data"
HF_RESOLVE_BASE = "https://huggingface.co/datasets/Lichess/standard-chess-games/resolve/main"

BAND_BOUNDS: dict[int, tuple[int, int]] = {
    1000: (1000, 1200),
    1200: (1200, 1400),
    1400: (1400, 1600),
    1600: (1600, 1800),
    1800: (1800, 2000),
    2000: (2000, 2200),
    2200: (2200, 2500),
    2500: (2500, 4000),
}

RE_COMMENT = re.compile(r"\{[^}]*\}")
RE_MOVE_NUM = re.compile(r"\b\d+\.+")
RE_ANNOT = re.compile(r"[!?]+|\$\d+")
RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}


def elo_to_band(avg_elo: float) -> int | None:
    for band, (lo, hi) in BAND_BOUNDS.items():
        if lo <= avg_elo < hi:
            return band
    return None


def parse_bands(tier: str, ratings: str | None) -> list[int]:
    raw = ratings or RATING_TIERS.get(tier, tier)
    bands: list[int] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        val = int(tok)
        if val not in BAND_BOUNDS:
            raise ValueError(f"Unsupported Lichess rating bucket '{val}'. Valid: {sorted(BAND_BOUNDS)}")
        if val not in bands:
            bands.append(val)
    if not bands:
        raise ValueError("At least one rating bucket is required.")
    return sorted(bands)


def parse_speeds(speeds_csv: str) -> list[str]:
    valid = {"blitz", "rapid", "classical"}
    out: list[str] = []
    for tok in speeds_csv.split(","):
        s = tok.strip().lower()
        if not s:
            continue
        if s not in valid:
            raise ValueError(f"Unsupported speed '{s}'. Valid: {sorted(valid)}")
        if s not in out:
            out.append(s)
    if not out:
        raise ValueError("At least one speed is required.")
    return out


def list_hf_shards(year: str | None, months: list[str] | None) -> list[str]:
    """Discover Parquet shard URLs from Hugging Face for the requested or latest year/month."""
    session = requests.Session()
    resp = session.get(HF_API_TREE, timeout=20)
    resp.raise_for_status()
    years = sorted(
        item["path"].split("year=")[1]
        for item in resp.json()
        if item.get("type") == "directory" and "year=" in item.get("path", "")
    )
    if not years:
        raise RuntimeError("No year partitions found on Hugging Face Lichess/standard-chess-games.")

    target_year = year or years[-1]
    m_resp = session.get(f"{HF_API_TREE}/year={target_year}", timeout=20)
    m_resp.raise_for_status()
    avail_months = sorted(
        item["path"].split("month=")[1]
        for item in m_resp.json()
        if item.get("type") == "directory" and "month=" in item.get("path", "")
    )
    if not avail_months:
        raise RuntimeError(f"No month partitions found for year={target_year}.")

    if months:
        target_months = [m.zfill(2) for m in months]
    else:
        target_months = [avail_months[-1]]

    urls: list[str] = []
    # Reverse month order if multiple months provided so newest month is ingested first
    for m in reversed(target_months):
        f_resp = session.get(f"{HF_API_TREE}/year={target_year}/month={m}", timeout=20)
        f_resp.raise_for_status()
        shards = sorted(
            item["path"]
            for item in f_resp.json()
            if item.get("type") == "file" and item.get("path", "").endswith(".parquet")
        )
        urls.extend(f"{HF_RESOLVE_BASE}/{p}" for p in shards)
    return urls


def extract_san_tokens(movetext: str, max_ply: int) -> list[str]:
    """Strip clock/eval annotations and extract up to `max_ply` SAN tokens cleanly."""
    if not movetext:
        return []
    # Truncate long movetext strings before regex to avoid scanning moves 16-100
    chunk = movetext[: max_ply * 95]
    cleaned = RE_COMMENT.sub(" ", chunk)
    cleaned = RE_MOVE_NUM.sub(" ", cleaned)
    cleaned = RE_ANNOT.sub("", cleaned)
    tokens: list[str] = []
    for raw_tok in cleaned.split():
        if raw_tok in RESULT_TOKENS or raw_tok == "...":
            continue
        tokens.append(raw_tok.replace("0-0-0", "O-O-O").replace("0-0", "O-O"))
        if len(tokens) >= max_ply:
            break
    return tokens


def build_where_sql(bands: list[int], speeds: list[str]) -> str:
    band_clauses = [f"(((WhiteElo + BlackElo) / 2.0) >= {BAND_BOUNDS[b][0]} AND ((WhiteElo + BlackElo) / 2.0) < {BAND_BOUNDS[b][1]})" for b in bands]
    speed_clauses = [f"Event LIKE 'Rated {s.capitalize()}%'" for s in speeds]
    return (
        "Result IN ('1-0', '0-1', '1/2-1/2') "
        f"AND ({' OR '.join(band_clauses)}) "
        f"AND ({' OR '.join(speed_clauses)})"
    )


def event_to_speed(event: str) -> str | None:
    if event.startswith("Rated Blitz"):
        return "blitz"
    if event.startswith("Rated Rapid"):
        return "rapid"
    if event.startswith("Rated Classical"):
        return "classical"
    return None


def process_rows(
    rows: list[tuple[str, str, int, int, str]],
    max_ply: int,
    trans_cache: dict[tuple[str, str], tuple[str, str, str]],
    trans_cache_limit: int = 400_000,
) -> tuple[list[tuple[str, int, str, str, str, int, int, int, int, int]], int]:
    """Walk up to `max_ply` moves per game and aggregate position-move stats for one batch."""
    # key: (epd, band, speed, uci) -> [san, min_ply, white, draws, black, elo_sum]
    agg: dict[tuple[str, int, str, str], list[Any]] = {}
    start_epd = chess.Board().epd()
    parsed_games = 0

    for event, result, w_elo, b_elo, movetext in rows:
        speed = event_to_speed(event)
        if speed is None:
            continue
        avg_elo = int(round((w_elo + b_elo) / 2.0))
        band = elo_to_band(avg_elo)
        if band is None:
            continue

        tokens = extract_san_tokens(movetext, max_ply)
        if not tokens:
            continue

        w_inc = 1 if result == "1-0" else 0
        d_inc = 1 if result == "1/2-1/2" else 0
        b_inc = 1 if result == "0-1" else 0

        cur_epd = start_epd
        board: chess.Board | None = None
        parsed_games += 1

        for ply, tok in enumerate(tokens):
            ckey = (cur_epd, tok)
            hit = trans_cache.get(ckey)
            if hit is None:
                if board is None:
                    board = chess.Board()
                    if cur_epd != start_epd:
                        board.set_epd(cur_epd)
                try:
                    mv = board.parse_san(tok)
                except ValueError:
                    break
                clean_san = board.san(mv)
                uci = mv.uci()
                board.push(mv)
                next_epd = board.epd()
                hit = (next_epd, uci, clean_san)
                if len(trans_cache) < trans_cache_limit:
                    trans_cache[ckey] = hit
            else:
                next_epd, uci, clean_san = hit
                if board is not None:
                    board.push_uci(uci)

            akey = (cur_epd, band, speed, uci)
            slot = agg.get(akey)
            if slot is None:
                agg[akey] = [clean_san, ply, w_inc, d_inc, b_inc, avg_elo]
            else:
                if ply < slot[1]:
                    slot[1] = ply
                slot[2] += w_inc
                slot[3] += d_inc
                slot[4] += b_inc
                slot[5] += avg_elo

            cur_epd = next_epd

    batch_records = [
        (epd, band, speed, uci, vals[0], vals[1], vals[2], vals[3], vals[4], vals[5])
        for (epd, band, speed, uci), vals in agg.items()
    ]
    return batch_records, parsed_games


def init_target_sqlite(db_path: Path, reset: bool) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if reset and db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingested_shards (
            shard_url TEXT PRIMARY KEY,
            games_matched INTEGER NOT NULL,
            ingested_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pos_stats (
            epd TEXT NOT NULL,
            band INTEGER NOT NULL,
            speed TEXT NOT NULL,
            uci TEXT NOT NULL,
            san TEXT NOT NULL,
            min_ply INTEGER NOT NULL,
            white INTEGER NOT NULL,
            draws INTEGER NOT NULL,
            black INTEGER NOT NULL,
            elo_sum INTEGER NOT NULL,
            PRIMARY KEY (epd, band, speed, uci)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_stats_epd ON pos_stats(epd)")
    conn.commit()
    return conn


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build local SQLite Online DB from Lichess/standard-chess-games Parquet via DuckDB"
    )
    parser.add_argument("--tier", choices=list(RATING_TIERS.keys()), default="2000_2500")
    parser.add_argument("--ratings", help="Custom rating buckets CSV, e.g. '2000,2200,2500'")
    parser.add_argument("--speeds", default=DEFAULT_SPEEDS, help="Speeds CSV (default: blitz,rapid,classical)")
    parser.add_argument("--year", help="Partition year, e.g. 2025 (defaults to latest on Hugging Face)")
    parser.add_argument("--months", help="Comma-separated months, e.g. '09' or '09,08' (defaults to latest)")
    parser.add_argument("--local-parquet", nargs="*", help="Optional local .parquet path(s)/glob instead of Hugging Face")
    parser.add_argument("--max-games", type=int, default=5_000_000, help="Stop after N matching games (default: 5,000,000)")
    parser.add_argument("--max-shards", type=int, default=None, help="Optional cap on Parquet shards to scan")
    parser.add_argument("--max-ply", type=int, default=30, help="Max half-moves per game to index (default: 30 = 15 moves)")
    parser.add_argument(
        "--min-node-games",
        type=int,
        default=3,
        help="Prune positions past ply 10 with fewer than N total games (default: 3)",
    )
    parser.add_argument("--append", action="store_true", help="Merge into existing DB instead of overwriting")
    parser.add_argument("--out", default=str(LOCAL_ONLINE_DB), help=f"Output SQLite path (default: {LOCAL_ONLINE_DB})")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    bands = parse_bands(args.tier, args.ratings)
    speeds = parse_speeds(args.speeds)
    out_path = Path(args.out)

    if args.local_parquet:
        shard_urls = args.local_parquet
    else:
        months = [m.strip() for m in args.months.split(",") if m.strip()] if args.months else None
        shard_urls = list_hf_shards(args.year, months)

    if args.max_shards is not None:
        shard_urls = shard_urls[: args.max_shards]

    if not shard_urls:
        print("ERROR: No Parquet shards found to import.", file=sys.stderr)
        return 2

    sqlite_conn = init_target_sqlite(out_path, reset=not args.append)
    already_ingested = {
        r[0] for r in sqlite_conn.execute("SELECT shard_url FROM ingested_shards").fetchall()
    }

    where_sql = build_where_sql(bands, speeds)
    print(
        f"Importing up to {args.max_games:,} games | bands={bands} | speeds={speeds} | "
        f"max_ply={args.max_ply} | shards={len(shard_urls)}"
    )

    t_start = time.time()
    trans_cache: dict[tuple[str, str], tuple[str, str, str]] = {}
    total_imported = 0
    shards_done: list[tuple[str, int, float]] = []

    with tempfile.TemporaryDirectory(prefix="lichess_stage_") as tmp_dir:
        stage_db = Path(tmp_dir) / "staging.duckdb"
        duck = duckdb.connect(str(stage_db))
        if not args.local_parquet:
            duck.execute("INSTALL httpfs; LOAD httpfs;")
        duck.execute(
            """
            CREATE TABLE stage_stats (
                epd VARCHAR,
                band INTEGER,
                speed VARCHAR,
                uci VARCHAR,
                san VARCHAR,
                min_ply INTEGER,
                white BIGINT,
                draws BIGINT,
                black BIGINT,
                elo_sum BIGINT
            )
            """
        )

        # Seed staging with existing SQLite rows when --append is used so final group-by merges cleanly
        if args.append and out_path.exists():
            seed_tsv = Path(tmp_dir) / "seed.tsv"
            cur = sqlite_conn.execute(
                "SELECT epd, band, speed, uci, san, min_ply, white, draws, black, elo_sum FROM pos_stats"
            )
            seed_cnt = 0
            with seed_tsv.open("w", encoding="utf-8", newline="\n") as fh:
                while True:
                    chunk = cur.fetchmany(50_000)
                    if not chunk:
                        break
                    fh.writelines(
                        f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\t{r[5]}\t{r[6]}\t{r[7]}\t{r[8]}\t{r[9]}\n"
                        for r in chunk
                    )
                    seed_cnt += len(chunk)
            if seed_cnt:
                duck.execute(
                    f"INSERT INTO stage_stats SELECT * FROM read_csv('{seed_tsv.as_posix()}', "
                    "delim='\t', header=false, quote='', escape='', "
                    "columns={'epd':'VARCHAR','band':'INTEGER','speed':'VARCHAR','uci':'VARCHAR',"
                    "'san':'VARCHAR','min_ply':'INTEGER','white':'BIGINT','draws':'BIGINT',"
                    "'black':'BIGINT','elo_sum':'BIGINT'})"
                )
                print(f"Loaded {seed_cnt:,} existing position-move rows for merge.")

        movetext_slice = max(1200, args.max_ply * 85)
        for idx, url in enumerate(shard_urls, 1):
            if url in already_ingested:
                print(f"[{idx}/{len(shard_urls)}] Skipping already-ingested shard: {Path(url).name}")
                continue
            remaining = args.max_games - total_imported
            if remaining <= 0:
                break

            t_shard = time.time()
            safe_url = url.replace("'", "''")
            query = (
                f"SELECT Event, Result, WhiteElo, BlackElo, left(movetext, {movetext_slice}) "
                f"FROM read_parquet('{safe_url}') "
                f"WHERE {where_sql} "
                f"LIMIT {remaining}"
            )
            rows = duck.execute(query).fetchall()
            records, game_cnt = process_rows(rows, max_ply=args.max_ply, trans_cache=trans_cache)
            if records:
                batch_tsv = Path(tmp_dir) / f"shard_{idx}.tsv"
                with batch_tsv.open("w", encoding="utf-8", newline="\n") as fh:
                    fh.writelines(
                        f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\t{r[5]}\t{r[6]}\t{r[7]}\t{r[8]}\t{r[9]}\n"
                        for r in records
                    )
                duck.execute(
                    f"INSERT INTO stage_stats SELECT * FROM read_csv('{batch_tsv.as_posix()}', "
                    "delim='\t', header=false, quote='', escape='', "
                    "columns={'epd':'VARCHAR','band':'INTEGER','speed':'VARCHAR','uci':'VARCHAR',"
                    "'san':'VARCHAR','min_ply':'INTEGER','white':'BIGINT','draws':'BIGINT',"
                    "'black':'BIGINT','elo_sum':'BIGINT'})"
                )
                batch_tsv.unlink(missing_ok=True)
            total_imported += game_cnt
            shards_done.append((url, game_cnt, time.time()))
            print(
                f"[{idx}/{len(shard_urls)}] {Path(url).name}: +{game_cnt:,} games "
                f"({len(records):,} move rows, {time.time() - t_shard:.1f}s) | total={total_imported:,}/{args.max_games:,}"
            )
            if total_imported >= args.max_games:
                break

        if total_imported == 0 and not args.append:
            print("No matching games were imported.", file=sys.stderr)
            duck.close()
            sqlite_conn.close()
            return 1

        print("Aggregating and exporting clean index to SQLite...")
        t_export = time.time()
        sqlite_conn.execute("DELETE FROM pos_stats")
        agg_cur = duck.execute(
            f"""
            SELECT
                epd,
                band,
                speed,
                uci,
                ANY_VALUE(san) AS san,
                MIN(min_ply) AS min_ply,
                SUM(white) AS w,
                SUM(draws) AS d,
                SUM(black) AS b,
                SUM(elo_sum) AS esum
            FROM stage_stats
            GROUP BY epd, band, speed, uci
            HAVING MIN(min_ply) <= 10 OR SUM(white + draws + black) >= {max(1, args.min_node_games)}
            """
        )

        exported_rows = 0
        while True:
            chunk = agg_cur.fetchmany(50_000)
            if not chunk:
                break
            sqlite_conn.executemany(
                "INSERT INTO pos_stats (epd, band, speed, uci, san, min_ply, white, draws, black, elo_sum) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                chunk,
            )
            exported_rows += len(chunk)

        if shards_done:
            sqlite_conn.executemany(
                "INSERT OR REPLACE INTO ingested_shards (shard_url, games_matched, ingested_at) VALUES (?, ?, ?)",
                shards_done,
            )

        prev_total = 0
        row_meta = sqlite_conn.execute("SELECT value FROM meta WHERE key = 'total_games'").fetchone()
        if args.append and row_meta:
            prev_total = int(row_meta[0])
        meta_items = [
            ("schema_version", "1"),
            ("source", "huggingface:Lichess/standard-chess-games"),
            ("max_ply", str(args.max_ply)),
            ("min_node_games", str(args.min_node_games)),
            ("total_games", str(prev_total + total_imported)),
            ("updated_at", str(int(time.time()))),
        ]
        sqlite_conn.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", meta_items)
        sqlite_conn.commit()
        duck.close()

    sqlite_conn.execute("PRAGMA optimize")
    sqlite_conn.close()
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(
        f"Done in {time.time() - t_start:.1f}s (export {time.time() - t_export:.1f}s): "
        f"{exported_rows:,} position-move rows written to {out_path} ({size_mb:.1f} MB)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
