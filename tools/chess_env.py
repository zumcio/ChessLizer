"""Core chess analysis toolkit: Stockfish, Lichess Masters/Online DB, Cloud Eval, Tablebase, and ECO."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chess
import chess.pgn
import chess.svg
import requests
from dotenv import load_dotenv

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


ROOT_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT_DIR / "bin" / "stockfish"
CACHE_DIR = ROOT_DIR / "cache"
CACHE_DB = CACHE_DIR / "explorer_cache.db"
ECO_DIR = ROOT_DIR / "data" / "eco"

load_dotenv(ROOT_DIR / ".env")


RATING_TIERS: dict[str, str] = {
    "beginner": "1000,1200,1400",
    "club": "1600,1800",
    "advanced": "2000,2200",
    "strong": "2200,2500",
    "2000_2500": "2000,2200,2500",
    "all": "1000,1200,1400,1600,1800,2000,2200,2500",
}

DEFAULT_SPEEDS = "blitz,rapid,classical"


class LichessAuthError(RuntimeError):
    """Raised when Lichess Opening Explorer requires a personal API token."""


class LichessRateLimitError(RuntimeError):
    """Raised when Lichess API returns HTTP 429."""


def parse_position(fen: str | None = None, moves: str | None = None) -> tuple[chess.Board, list[str]]:
    """Build a chess.Board from an optional FEN and/or a SAN/UCI move sequence."""
    board = chess.Board(fen) if fen else chess.Board()
    played_san: list[str] = []

    if moves:
        cleaned = re.sub(r"\{[^}]*\}", " ", moves)
        cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
        cleaned = re.sub(r"\d+\.+", " ", cleaned)
        cleaned = re.sub(r"[!?]+", "", cleaned)
        cleaned = re.sub(r"\$\d+", "", cleaned)
        tokens = [t.strip() for t in cleaned.split() if t.strip() and t.strip() not in {"*", "1-0", "0-1", "1/2-1/2", "..."}]

        for tok in tokens:
            normalized = tok.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
            move: chess.Move | None = None
            try:
                move = board.parse_san(normalized)
            except ValueError:
                try:
                    cand = chess.Move.from_uci(normalized)
                    if cand in board.legal_moves:
                        move = cand
                except ValueError:
                    move = None
            if move is None:
                raise ValueError(f"Illegal or unrecognized move '{tok}' in position {board.fen()}")
            played_san.append(board.san(move))
            board.push(move)

    return board, played_san


def find_stockfish() -> Path:
    """Locate the Stockfish binary from STOCKFISH_PATH or bin/stockfish/."""
    env_path = os.getenv("STOCKFISH_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p

    if BIN_DIR.exists():
        exes = sorted(BIN_DIR.rglob("stockfish*.exe"))
        if exes:
            return exes[0]
        any_exe = sorted(BIN_DIR.rglob("*.exe"))
        if any_exe:
            return any_exe[0]

    raise FileNotFoundError(
        f"Stockfish binary not found in {BIN_DIR}. "
        "Download Stockfish and place the .exe in bin/stockfish/ or set STOCKFISH_PATH."
    )


def _format_white_score(cp_white: int | None, mate_white: int | None) -> str:
    if mate_white is not None:
        sign = "+" if mate_white > 0 else "-"
        return f"#{sign}{abs(mate_white)}"
    assert cp_white is not None
    return f"{cp_white / 100:+.2f}"


@dataclass
class EngineLine:
    rank: int
    move_san: str
    move_uci: str
    score_str: str
    score_cp: int | None
    score_mate: int | None
    wdl: tuple[int, int, int] | None
    pv_san: list[str]
    depth: int
    nodes: int


class StockfishAnalyzer:
    """Zero-asyncio subprocess UCI wrapper for local Stockfish (works cleanly in Windows sandbox)."""

    def __init__(
        self,
        path: Path | None = None,
        threads: int | None = None,
        hash_mb: int | None = None,
    ) -> None:
        self.path = path or find_stockfish()
        self.threads = threads or int(os.getenv("STOCKFISH_THREADS", "6"))
        self.hash_mb = hash_mb or int(os.getenv("STOCKFISH_HASH_MB", "512"))
        self._proc: subprocess.Popen[str] | None = None
        self._engine_name: str = self.path.name
        self._current_multipv: int = 1

    def __enter__(self) -> StockfishAnalyzer:
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _send(self, cmd: str) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.write(cmd + "\n")
        self._proc.stdin.flush()

    def _wait_for(self, token: str) -> list[str]:
        assert self._proc is not None and self._proc.stdout is not None
        lines: list[str] = []
        while True:
            raw = self._proc.stdout.readline()
            if not raw:
                raise RuntimeError(f"Stockfish process terminated unexpectedly while waiting for '{token}'.")
            line = raw.strip()
            lines.append(line)
            if line == token or line.startswith(token + " "):
                return lines

    def open(self) -> None:
        if self._proc is not None:
            return
        self._proc = subprocess.Popen(
            [str(self.path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._send("uci")
        uci_lines = self._wait_for("uciok")
        for line in uci_lines:
            if line.startswith("id name "):
                self._engine_name = line[len("id name ") :].strip()
        self._send(f"setoption name Threads value {max(1, self.threads)}")
        self._send(f"setoption name Hash value {max(16, self.hash_mb)}")
        self._send("setoption name UCI_ShowWDL value true")
        self._send("isready")
        self._wait_for("readyok")

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._send("quit")
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
            finally:
                self._proc = None

    @property
    def engine_name(self) -> str:
        self.open()
        return self._engine_name

    @staticmethod
    def _parse_info_line(line: str, board: chess.Board) -> EngineLine | None:
        if not line.startswith("info ") or " pv " not in line or " score " not in line:
            return None
        if " upperbound " in line or " lowerbound " in line:
            return None

        head, pv_part = line.split(" pv ", 1)
        tokens = head.split()
        depth = 0
        nodes = 0
        multipv = 1
        cp_stm: int | None = None
        mate_stm: int | None = None
        wdl_stm: tuple[int, int, int] | None = None

        i = 1
        while i < len(tokens):
            t = tokens[i]
            if t == "depth" and i + 1 < len(tokens):
                depth = int(tokens[i + 1])
                i += 2
            elif t == "nodes" and i + 1 < len(tokens):
                nodes = int(tokens[i + 1])
                i += 2
            elif t == "multipv" and i + 1 < len(tokens):
                multipv = int(tokens[i + 1])
                i += 2
            elif t == "score" and i + 2 < len(tokens):
                kind = tokens[i + 1]
                val = int(tokens[i + 2])
                if kind == "cp":
                    cp_stm = val
                elif kind == "mate":
                    mate_stm = val
                i += 3
            elif t == "wdl" and i + 3 < len(tokens):
                wdl_stm = (int(tokens[i + 1]), int(tokens[i + 2]), int(tokens[i + 3]))
                i += 4
            else:
                i += 1

        pv_uci = pv_part.split()
        if not pv_uci:
            return None

        try:
            first_move = chess.Move.from_uci(pv_uci[0])
            if first_move not in board.legal_moves:
                return None
        except ValueError:
            return None

        pv_san: list[str] = []
        tmp = board.copy(stack=False)
        for uci in pv_uci[:10]:
            try:
                mv = chess.Move.from_uci(uci)
            except ValueError:
                break
            if mv in tmp.legal_moves:
                pv_san.append(tmp.san(mv))
                tmp.push(mv)
            else:
                break

        # Normalize score & WDL to White's perspective
        if board.turn == chess.WHITE:
            cp_white = cp_stm
            mate_white = mate_stm
            wdl_white = wdl_stm
        else:
            cp_white = -cp_stm if cp_stm is not None else None
            mate_white = -mate_stm if mate_stm is not None else None
            wdl_white = (wdl_stm[2], wdl_stm[1], wdl_stm[0]) if wdl_stm is not None else None

        return EngineLine(
            rank=multipv,
            move_san=board.san(first_move),
            move_uci=first_move.uci(),
            score_str=_format_white_score(cp_white, mate_white),
            score_cp=cp_white,
            score_mate=mate_white,
            wdl=wdl_white,
            pv_san=pv_san,
            depth=depth,
            nodes=nodes,
        )

    def analyze(
        self,
        board: chess.Board,
        depth: int | None = 20,
        time_sec: float | None = None,
        multipv: int = 3,
        root_moves: list[chess.Move] | None = None,
    ) -> list[EngineLine]:
        self.open()
        assert self._proc is not None and self._proc.stdout is not None

        legal_count = board.legal_moves.count()
        if legal_count == 0:
            return []

        eff_multipv = max(1, min(multipv, len(root_moves) if root_moves else legal_count))
        if eff_multipv != self._current_multipv:
            self._send(f"setoption name MultiPV value {eff_multipv}")
            self._current_multipv = eff_multipv
            self._send("isready")
            self._wait_for("readyok")

        self._send(f"position fen {board.fen()}")
        if time_sec is not None:
            go_cmd = f"go movetime {max(10, int(time_sec * 1000))}"
        else:
            go_cmd = f"go depth {max(1, depth or 20)}"
        if root_moves:
            go_cmd += " searchmoves " + " ".join(m.uci() for m in root_moves)
        self._send(go_cmd)

        by_rank: dict[int, EngineLine] = {}
        while True:
            raw = self._proc.stdout.readline()
            if not raw:
                break
            line = raw.strip()
            if line.startswith("info "):
                parsed = self._parse_info_line(line, board)
                if parsed is not None:
                    by_rank[parsed.rank] = parsed
            elif line.startswith("bestmove"):
                break

        return [by_rank[r] for r in sorted(by_rank.keys())]

    def check_move(
        self,
        board: chess.Board,
        candidate_san: str,
        depth: int | None = 20,
        time_sec: float | None = None,
        multipv: int = 3,
    ) -> dict[str, Any]:
        """Evaluate a proposed move against Stockfish's best moves and compute centipawn loss."""
        norm = candidate_san.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
        cand_move = board.parse_san(norm)
        top_lines = self.analyze(board, depth=depth, time_sec=time_sec, multipv=multipv)
        cand_line = next((line for line in top_lines if line.move_uci == cand_move.uci()), None)
        if cand_line is None:
            isolated = self.analyze(board, depth=depth, time_sec=time_sec, multipv=1, root_moves=[cand_move])
            cand_line = isolated[0] if isolated else None

        best = top_lines[0] if top_lines else None
        cp_loss: int | None = None
        if best and cand_line and best.score_cp is not None and cand_line.score_cp is not None:
            sign = 1 if board.turn == chess.WHITE else -1
            cp_loss = max(0, (best.score_cp - cand_line.score_cp) * sign)

        return {
            "candidate": cand_line,
            "best": best,
            "top_lines": top_lines,
            "cp_loss": cp_loss,
            "in_top_multipv": any(line.move_uci == cand_move.uci() for line in top_lines),
        }


class ExplorerCache:
    """SQLite cache for Lichess Explorer, Cloud Eval, and Tablebase responses."""

    def __init__(self, db_path: Path = CACHE_DB) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def get(self, key: str, max_age_sec: float = 30 * 86400) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM api_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        payload, fetched_at = row
        if time.time() - fetched_at > max_age_sec:
            return None
        return json.loads(payload)

    def set(self, key: str, data: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO api_cache (cache_key, payload, fetched_at) VALUES (?, ?, ?)",
                (key, json.dumps(data), time.time()),
            )
            conn.commit()


@dataclass
class MoveStat:
    san: str
    uci: str
    white: int
    draws: int
    black: int
    total: int
    play_pct: float
    cum_pct: float
    white_pct: float
    draw_pct: float
    black_pct: float
    side_score_pct: float
    average_rating: int | None = None


@dataclass
class ExplorerResult:
    source: str
    fen: str
    turn: str
    total_games: int
    white: int
    draws: int
    black: int
    opening_eco: str | None
    opening_name: str | None
    moves: list[MoveStat] = field(default_factory=list)
    top_games: list[dict[str, Any]] = field(default_factory=list)
    from_cache: bool = False


class LichessClient:
    """Client for Lichess Masters DB, Online DB, Cloud Eval, and Syzygy Tablebase."""

    EXPLORER_BASE = "https://explorer.lichess.org"
    CLOUD_EVAL_URL = "https://lichess.org/api/cloud-eval"
    TABLEBASE_URL = "https://tablebase.lichess.ovh/standard"

    def __init__(
        self,
        token: str | None = None,
        cache: ExplorerCache | None = None,
        min_delay_sec: float = 0.35,
    ) -> None:
        self.token = (token if token is not None else os.getenv("LICHESS_API_TOKEN", "")).strip()
        self.cache = cache or ExplorerCache()
        self.min_delay_sec = min_delay_sec
        self._last_net_call = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "ChessAnalysisToolkit/1.0"})

    def _headers(self, require_auth: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif require_auth:
            raise LichessAuthError(
                "Brak tokenu LICHESS_API_TOKEN! Lichess Opening Explorer wymaga darmowego tokenu "
                "(bez żadnych uprawnień / zero scopes).\n"
                "Wygeneruj go na: https://lichess.org/account/oauth/token\n"
                "i zapisz w pliku .env jako: LICHESS_API_TOKEN=lip_..."
            )
        return headers

    def _get_json(
        self,
        url: str,
        params: dict[str, Any],
        cache_prefix: str,
        use_cache: bool = True,
        require_auth: bool = False,
        allow_404: bool = False,
    ) -> tuple[dict[str, Any] | None, bool]:
        sorted_items = sorted((k, str(v)) for k, v in params.items() if v is not None)
        cache_key = f"{cache_prefix}|{json.dumps(sorted_items, separators=(',', ':'))}"

        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached, True

        headers = self._headers(require_auth=require_auth)

        elapsed = time.time() - self._last_net_call
        if elapsed < self.min_delay_sec:
            time.sleep(self.min_delay_sec - elapsed)

        resp = self._session.get(url, params=dict(sorted_items), headers=headers, timeout=20)
        self._last_net_call = time.time()

        if resp.status_code == 401:
            raise LichessAuthError(
                "Lichess API zwrócił 401 Unauthorized. Sprawdź poprawność LICHESS_API_TOKEN w pliku .env "
                "(wygeneruj darmowy token na https://lichess.org/account/oauth/token)."
            )
        if resp.status_code == 429:
            raise LichessRateLimitError(
                "Lichess API zwrócił 429 Too Many Requests. Odczekaj 60 sekund przed kolejnymi zapytaniami."
            )
        if resp.status_code == 404 and allow_404:
            return None, False

        resp.raise_for_status()
        data = resp.json()
        if use_cache:
            self.cache.set(cache_key, data)
        return data, False

    def _parse_explorer(
        self, data: dict[str, Any], board: chess.Board, source: str, from_cache: bool
    ) -> ExplorerResult:
        w = int(data.get("white", 0))
        d = int(data.get("draws", 0))
        b = int(data.get("black", 0))
        total = w + d + b

        opening = data.get("opening") or {}
        eco = opening.get("eco")
        name = opening.get("name")

        moves_out: list[MoveStat] = []
        cum = 0.0
        for mv in data.get("moves", []):
            mw = int(mv.get("white", 0))
            md = int(mv.get("draws", 0))
            mb = int(mv.get("black", 0))
            mtot = mw + md + mb
            if mtot == 0:
                continue
            play_pct = (mtot / total * 100.0) if total > 0 else 0.0
            cum += play_pct
            w_pct = mw / mtot * 100.0
            d_pct = md / mtot * 100.0
            b_pct = mb / mtot * 100.0
            if board.turn == chess.WHITE:
                side_score = (mw + 0.5 * md) / mtot * 100.0
            else:
                side_score = (mb + 0.5 * md) / mtot * 100.0

            moves_out.append(
                MoveStat(
                    san=mv["san"],
                    uci=mv["uci"],
                    white=mw,
                    draws=md,
                    black=mb,
                    total=mtot,
                    play_pct=play_pct,
                    cum_pct=cum,
                    white_pct=w_pct,
                    draw_pct=d_pct,
                    black_pct=b_pct,
                    side_score_pct=side_score,
                    average_rating=mv.get("averageRating"),
                )
            )

        return ExplorerResult(
            source=source,
            fen=board.fen(),
            turn="White" if board.turn == chess.WHITE else "Black",
            total_games=total,
            white=w,
            draws=d,
            black=b,
            opening_eco=eco,
            opening_name=name,
            moves=moves_out,
            top_games=data.get("topGames", []),
            from_cache=from_cache,
        )

    def masters(
        self,
        board: chess.Board,
        moves: int = 12,
        top_games: int = 5,
        since: int | None = None,
        until: int | None = None,
        use_cache: bool = True,
    ) -> ExplorerResult:
        params: dict[str, Any] = {
            "fen": board.fen(),
            "moves": moves,
            "topGames": top_games,
        }
        if since is not None:
            params["since"] = since
        if until is not None:
            params["until"] = until

        data, from_cache = self._get_json(
            f"{self.EXPLORER_BASE}/masters",
            params=params,
            cache_prefix="masters",
            use_cache=use_cache,
            require_auth=False,
        )
        assert data is not None
        return self._parse_explorer(data, board, source="masters", from_cache=from_cache)

    def online(
        self,
        board: chess.Board,
        tier: str = "club",
        ratings: str | None = None,
        speeds: str = DEFAULT_SPEEDS,
        moves: int = 12,
        top_games: int = 4,
        recent_games: int = 0,
        use_cache: bool = True,
    ) -> ExplorerResult:
        eff_ratings = ratings or RATING_TIERS.get(tier, tier)
        params: dict[str, Any] = {
            "variant": "standard",
            "fen": board.fen(),
            "speeds": speeds,
            "ratings": eff_ratings,
            "moves": moves,
            "topGames": top_games,
            "recentGames": recent_games,
        }
        data, from_cache = self._get_json(
            f"{self.EXPLORER_BASE}/lichess",
            params=params,
            cache_prefix="lichess",
            use_cache=use_cache,
            require_auth=False,
        )
        assert data is not None
        label = f"online:{tier}({eff_ratings})" if ratings is None else f"online({eff_ratings})"
        return self._parse_explorer(data, board, source=label, from_cache=from_cache)

    def cloud_eval(
        self,
        board: chess.Board,
        multipv: int = 3,
        use_cache: bool = True,
    ) -> dict[str, Any] | None:
        params = {"fen": board.fen(), "multiPv": multipv}
        data, from_cache = self._get_json(
            self.CLOUD_EVAL_URL,
            params=params,
            cache_prefix="cloud_eval",
            use_cache=use_cache,
            require_auth=False,
            allow_404=True,
        )
        if data is None:
            return None
        data["_from_cache"] = from_cache
        return data

    def tablebase(
        self,
        board: chess.Board,
        use_cache: bool = True,
    ) -> dict[str, Any] | None:
        if len(board.piece_map()) > 7:
            return None
        params = {"fen": board.fen()}
        data, from_cache = self._get_json(
            self.TABLEBASE_URL,
            params=params,
            cache_prefix="tablebase",
            use_cache=use_cache,
            require_auth=False,
            allow_404=True,
        )
        if data is None:
            return None
        data["_from_cache"] = from_cache
        return data

    def master_game_pgn(self, game_id: str, use_cache: bool = True) -> tuple[str, bool]:
        """Fetch verbatim PGN of a master game by Lichess Masters ID (cached)."""
        cache_key = f"master_pgn|{game_id.strip()}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None and "pgn" in cached:
                return str(cached["pgn"]), True

        elapsed = time.time() - self._last_net_call
        if elapsed < self.min_delay_sec:
            time.sleep(self.min_delay_sec - elapsed)

        url = f"{self.EXPLORER_BASE}/masters/pgn/{game_id.strip()}"
        resp = self._session.get(url, headers=self._headers(require_auth=False), timeout=20)
        self._last_net_call = time.time()
        if resp.status_code == 429:
            raise LichessRateLimitError(
                "Lichess API zwrócił 429 Too Many Requests. Odczekaj 60 sekund przed kolejnymi zapytaniami."
            )
        resp.raise_for_status()
        pgn_text = resp.text.strip()
        if use_cache:
            self.cache.set(cache_key, {"pgn": pgn_text})
        return pgn_text, False


class EcoLookup:
    """Offline ECO opening name lookup from data/eco/*.tsv (cached as cache/eco_index.json)."""

    def __init__(self, eco_dir: Path = ECO_DIR, index_path: Path = CACHE_DIR / "eco_index.json") -> None:
        self.eco_dir = eco_dir
        self.index_path = index_path
        self._by_epd: dict[str, tuple[str, str]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self.index_path.is_file():
            try:
                raw = json.loads(self.index_path.read_text(encoding="utf-8"))
                self._by_epd = {k: (v[0], v[1]) for k, v in raw.items()}
                return
            except Exception:
                pass
        if not self.eco_dir.exists():
            return
        for tsv in sorted(self.eco_dir.glob("*.tsv")):
            with tsv.open("r", encoding="utf-8") as fh:
                header = fh.readline()
                if not header:
                    continue
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        continue
                    eco, name, pgn_str = parts[0], parts[1], parts[2]
                    try:
                        board, _ = parse_position(moves=pgn_str)
                        self._by_epd[board.epd()] = (eco, name)
                    except ValueError:
                        continue
        if self._by_epd:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            self.index_path.write_text(json.dumps(self._by_epd), encoding="utf-8")

    def lookup(self, board: chess.Board) -> tuple[str, str] | None:
        self._load()
        return self._by_epd.get(board.epd())

    def lookup_path(self, moves_san: list[str]) -> tuple[str, str] | None:
        """Walk move list from start and return the deepest known ECO opening."""
        self._load()
        board = chess.Board()
        found: tuple[str, str] | None = None
        for san in moves_san:
            board.push_san(san)
            hit = self._by_epd.get(board.epd())
            if hit:
                found = hit
        return found
