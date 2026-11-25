"""Move-provenance resolver for PGN prose (Game-OR-Stockfish backing).

Every move mentioned in any comment of any game (trainable, intro, model) must resolve to a real line:
each step is either played in a game (chapter tree, cached Masters/model games, DB continuations) or
suggested by Stockfish. Independently of the source, the resolved line must pass the same checks:

  1. Our mentioned moves are sound (SF cp-loss vs best), unless the prose frames them as bad.
  2. Opponent mentioned moves are plausible (SF top-N within margin, DB frequency, or game-played),
     unless the prose frames them as a mistake/trap.
  3. Moves the prose does NOT name (gap moves) are only the opponent's *expected* moves and sound
     moves of ours; otherwise the plan silently depends on an unstated assumption.
  4. Moves the prose dismisses (?!, ?, ??, "autopilot", "mistake", ...) really are inferior.
  5. Moves the prose says are prevented ("stops ...f5") are really illegal or bad.
  6. Numeric eval claims (+0.82) attached to a resolved clause roughly match Stockfish.
  7. Named game citations ("as in X vs Y") match that game's moves in order.

All rules are generic properties of the line (provenance, soundness, plausibility, stated assumptions);
none refer to specific openings, moves, squares or players. Clauses that contain no checkable move are
returned as residual so they are reviewed rather than passed silently.
"""

from __future__ import annotations

import argparse
import io
import itertools
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import chess
import chess.pgn

from chess_env import (
    CACHE_DB,
    RATING_TIERS,
    DEFAULT_SPEEDS,
    EngineLine,
    ExplorerCache,
    LocalOnlineDB,
    ROOT_DIR,
    StockfishAnalyzer,
)

CONFIG_PATH = ROOT_DIR / "tools" / "provenance_config.json"
DEFAULT_CONFIG: dict[str, float | int] = {
    "depth": 16,                # SF depth for provenance checks
    "multipv": 3,               # SF lines considered "suggested"
    "soft_cp": 35,              # our mentioned move: FLAG above this loss
    "blunder_cp": 70,           # our mentioned move: ERROR above this loss
    "gap_our_cp": 70,           # unnamed our-move inside a backing line must lose <= this
    "opp_plausible_cp": 60,     # opponent mention plausible if within this of SF best (top-N)
    "opp_expected_cp": 20,      # unnamed opponent move "expected" if within this of SF best
    "db_min_games": 20,         # DB move needs >= games to count
    "db_plausible_pct": 5.0,    # DB move share to count as plausible
    "db_expected_pct": 30.0,    # DB move share to count as expected
    "max_gap_plies": 8,         # max unnamed plies for DB/SF search
    "max_tree_gap_plies": 16,   # max unnamed plies for zero-cost chapter/GM lines
    "max_perm_mentions": 3,     # try reorderings only when chronological order fails
    "dismiss_cp": 25,           # a move framed as bad must lose >= this
    "prevent_cp": 35,           # a move framed as prevented must be illegal or lose >= this
    "eval_tol_abs": 0.45,       # eval claim tolerance (pawns), absolute
    "eval_tol_rel": 0.40,       # ... or relative to |claimed|
}


def load_config(path: Path = CONFIG_PATH) -> dict[str, float | int]:
    cfg = dict(DEFAULT_CONFIG)
    if path.is_file():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    return cfg


# ----------------------------------------------------------------------------------------------
# Text -> clauses -> move mentions
# ----------------------------------------------------------------------------------------------

CMD_TAG_RE = re.compile(r"\[%[a-zA-Z]+\s+[^\]]*\]")
HEADER_RE = re.compile(r"━━━[^━]*━━━")
TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9/])"
    r"(?P<num>\d{1,3}\.(?:\s*\.\.)?\s*)?"
    r"(?P<dots>\.\.\.\s?)?"
    r"(?P<san>O-O-O|O-O|0-0-0|0-0|[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)"
    r"(?P<route>(?:-[a-h][1-8])+)?"
    r"(?P<ann>[+#]?(?:!!|\?\?|!\?|\?!|!|\?)?)"
    r"(?![A-Za-z0-9])"
)
PIECE_WORD_AFTER_RE = re.compile(r"^-(?:knight|bishop|rook|queen|king|pawn|square|file|diagonal)s?\b", re.I)
STATIC_DET_RE = re.compile(r"\b(?:the|our|his|her|their|its|Black's|White's|a|an)\s+$", re.I)
PAWN_VERB_RE = re.compile(
    r"\b(?:push(?:es|ing)?|play(?:s|ing|ed)?|break(?:s|ing)?|strike|strikes|thrust|launch(?:es)?|advanc(?:e|es|ing)|"
    r"answer(?:s|ing)?(?:\s+with)?|followed\s+by|recaptur(?:e|es|ing)\s+with|then)\s+$",
    re.I,
)
NEG_RE = re.compile(
    r"\b(?:omit\w*|skip(?:s|ping|ped)?|without|instead\s+of|rather\s+than|no\s+longer|unless)\b[^.;]{0,40}$", re.I
)
AVOID_RE = re.compile(r"\b(?:never\s+play|avoid\w*|do\s+not\s+play|don't\s+play|reject\w*)\b[^.;]{0,30}$", re.I)
PREVENT_RE = re.compile(
    r"\b(?:prevent\w*|stops?|stopping|rules?\s+out|deter\w*|kills?|cannot|can't|unable\s+to|denies|denying|forbids?)\b[^.;]{0,40}$",
    re.I,
)
BAD_PRE_RE = re.compile(
    r"\b(?:autopilot|routine|dubious|inferior|inaccura\w*|careless|naive|greedy|premature|passive)\s+(?:\w+\s+){0,2}$",
    re.I,
)
BAD_POST_RE = re.compile(
    r"^\s*(?:,?\s*(?:is|are|was|were)\s+(?:a\s+|an\s+)?(?:mistake|blunder|error|inferior|dubious|bad|poor|inaccura\w*)|"
    r"\s*(?:blunders?|loses|backfires?|walks?\s+into|falls?\s+into|fails?\s+to|gets?\s+punished|hands?\b))",
    re.I,
)
EVAL_RE = re.compile(r"(?<![\w.])([+\-−–])(\d{1,2}\.\d{1,2})(?!\d)")
GM_VS_CITE_RE = re.compile(r"\b([A-Z][A-Za-z\-]+)(?:'s)?\s+vs\.?\s+([A-Z][A-Za-z\-]+)")
CLAUSE_SPLIT_RE = re.compile(
    r"(?:<br>|•|;|\s[—–]\s|(?<!\b\d)(?<!\b\d\d)(?<!\b\d\d\d)(?<!\.\.)(?<!\bvs)(?<!\be\.g)(?<!\bi\.e)(?<=[a-z0-9\)!?])[.!?]\s+(?=[A-Z0-9])|,\s+(?:while|whereas|but|or)\s+|\s+either\s+)"
)
MOVE_VERB_RE = re.compile(
    r"\b(?:play(?:s|ing|ed)?|push(?:es|ing)?|move(?:s|ing)?|step(?:s|ping)?|jump(?:s|ing)?|drop(?:s|ping)?|tuck(?:s|ing)?|"
    r"put(?:s|ting)?|bring(?:s|ing)?|rout(?:e|es|ing)|rerout(?:e|es|ing)|send(?:s|ing)?|plac(?:e|es|ing)|retreat(?:s|ing)?|"
    r"develop(?:s|ing)?|meet(?:s|ing)?|answer(?:s|ing)?|try|tries|trying|choose|prefer|continue|follow(?:s|ing|ed)?|"
    r"castle(?:s|ing)?|via|with)\s+(?:\w+\s+){0,2}$",
    re.I,
)
AFTER_KW_RE = re.compile(r"\b(?:after|once|when|if)\s+(?:\w+\s+){0,2}$", re.I)
BEFORE_KW_RE = re.compile(r"\bbefore\s+(?:\w+\s+){0,2}$", re.I)
GOAL_CLAUSE_RE = re.compile(
    r"\b(?:prepar(?:e|es|ing)|sets?\s+up|clears?\s+\S+\s+for|threatening|threatens|aims?\s+(?:for|at)|"
    r"looking\s+for|eyeing|ideas?\s+of|\bideas\b|\bplans?\b|paving\s+the\s+way\s+for|creates?\s+a\s+threat\s+of)\b",
    re.I,
)


@dataclass
class Mention:
    san: str                   # normalized SAN destination token, e.g. "Ng3", "h5", "O-O-O"
    raw: str
    side: chess.Color | None   # explicit side if notation says so (num / dots), else None
    number: int | None         # explicit move number
    ann: str
    optional: bool = False     # route origin square: satisfied if the piece already stands there
    has_verb: bool = False     # preceded by explicit action verb
    after_kw: bool = False     # preceded by after/once/when
    before_kw: bool = False    # preceded by before
    framed_bad: bool = False
    negated: bool = False
    prevented: bool = False
    is_goal: bool = False
    pos: int = 0
    end: int = 0


def _norm(san: str) -> str:
    return san.replace("0-0-0", "O-O-O").replace("0-0", "O-O")


def split_clauses(text: str) -> list[str]:
    txt = CMD_TAG_RE.sub(" ", text)
    txt = HEADER_RE.sub(" • ", txt)
    parts = [p.strip(" ,.:") for p in CLAUSE_SPLIT_RE.split(txt)]
    return [p for p in parts if p and p.strip()]


def _route_valid(san: str, route: list[str]) -> bool:
    """A route a-b-c is a move route if consecutive squares are reachable by the piece type."""
    sqs = [san[-2:]] + route
    pt = san[0] if san[0] in "KQRBN" else "P"
    for a, b in zip(sqs, sqs[1:]):
        fa, ra = ord(a[0]) - 97, int(a[1])
        fb, rb = ord(b[0]) - 97, int(b[1])
        df, dr = abs(fa - fb), abs(ra - rb)
        if pt == "P":
            if df != 0 or dr == 0 or dr > 2:
                return False
        elif pt == "N":
            if sorted((df, dr)) != [1, 2]:
                return False
        elif pt == "B":
            if df != dr or df == 0:
                return False
        elif pt == "R":
            if df and dr:
                return False
        elif pt == "K":
            if max(df, dr) != 1:
                return False
        elif pt == "Q":
            if not (df == dr or df == 0 or dr == 0):
                return False
    return True


def extract_mentions(clause: str) -> list[Mention]:
    # Normalize "Bd3 to b1" -> "Bd3-b1" so piece-origin + target square parses as a route (origin optional)
    clause = re.sub(r"\b([KQRBN][a-h][1-8])\s+to\s+([a-h][1-8])\b", r"\1-\2", clause)
    raw_toks = list(TOKEN_RE.finditer(clause))
    out: list[Mention] = []
    spans: list[tuple[int, int, int]] = []  # (start, end, index in out)
    pending_bare: list[tuple[re.Match[str], Mention]] = []
    for m in raw_toks:
        san = _norm(m.group("san"))
        if PIECE_WORD_AFTER_RE.match(clause[m.end():]):
            continue
        num_s, dots, ann = m.group("num"), m.group("dots"), m.group("ann") or ""
        route = [r for r in (m.group("route") or "").split("-") if r]
        if route and not _route_valid(san, route):
            continue  # square range such as c1-h6 diagonal
        number = int(re.match(r"\d+", num_s).group(0)) if num_s else None  # type: ignore[union-attr]
        side: chess.Color | None = None
        if num_s:
            side = chess.BLACK if ".." in num_s.replace(" ", "")[len(str(number)) :] else chess.WHITE
        if dots:
            side = chess.BLACK
        before = clause[: m.start()]
        is_piece = san[0] in "KQRBN" or san.startswith("O-O")
        is_pawn_capture = "x" in san and san[0] in "abcdefgh"
        has_promo = "=" in san
        explicit = bool(num_s or dots or ann.strip("+#") or "+" in ann or "#" in ann)
        if is_piece and not san.startswith("O-O") and not explicit and STATIC_DET_RE.search(before):
            continue
        movelike = is_piece or is_pawn_capture or has_promo or explicit or bool(route) or bool(PAWN_VERB_RE.search(before))
        has_avoid = bool(AVOID_RE.search(before))
        has_neg = bool(NEG_RE.search(before))
        # "Never play X because Y" needs X kept (framed_bad) so Y resolves; only standalone "never play X" with no continuation is dropped if needed
        base = dict(
            raw=m.group(0).strip(),
            side=side,
            number=number,
            ann=ann,
            has_verb=bool(MOVE_VERB_RE.search(before)),
            after_kw=bool(AFTER_KW_RE.search(before)),
            before_kw=bool(BEFORE_KW_RE.search(before)),
            framed_bad=("?" in ann) or has_avoid,
            negated=has_neg and not has_avoid,
            prevented=bool(PREVENT_RE.search(before)),
            pos=m.start(),
            end=m.end(),
        )
        squares = [san] + [(san[0] if is_piece and not san.startswith("O-O") else "") + r for r in route]
        if route:
            # every square of a route is a destination; the first is optional (piece may already stand there)
            for i, s in enumerate(squares):
                mt = Mention(san=s, optional=(i == 0), **base)  # type: ignore[arg-type]
                if i > 0:
                    mt.side = side
                out.append(mt)
                spans.append((m.start(), m.end(), len(out) - 1))
            continue
        mt = Mention(san=san, **base)  # type: ignore[arg-type]
        if movelike:
            out.append(mt)
            spans.append((m.start(), m.end(), len(out) - 1))
        else:
            pending_bare.append((m, mt))
    # Bare pawn squares adjacent (only whitespace / move numbers between) to a mention are moves too (e.g. "...cxd5 cxd5")
    if pending_bare and spans:
        for m, mt in pending_bare:
            for s, e, _ in spans:
                gap = clause[e : m.start()] if e <= m.start() else clause[m.end() : s] if m.end() <= s else None
                if gap is not None and re.fullmatch(r"\s*(?:\d{1,3}\.(?:\s*\.\.)?\s*)?", gap):
                    out.append(mt)
                    spans.append((m.start(), m.end(), len(out) - 1))
                    break
    # restore textual order
    order = sorted(range(len(out)), key=lambda i: (out[i].pos, i))
    out = [out[i] for i in order]
    # framing words closely attached to a mention (dismissals)
    for mt in out:
        pre = clause[max(0, mt.pos - 30) : mt.pos]
        post = clause[mt.end : mt.end + 40]
        if BAD_PRE_RE.search(pre) or BAD_POST_RE.search(post):
            mt.framed_bad = True
    return out


# ----------------------------------------------------------------------------------------------
# Sources: chapter tree, GM games, DB, Stockfish
# ----------------------------------------------------------------------------------------------


def _line_cp(line: EngineLine | None) -> int | None:
    if line is None:
        return None
    if line.score_cp is not None:
        return line.score_cp
    if line.score_mate is not None:
        return (10000 - 10 * abs(line.score_mate)) * (1 if line.score_mate > 0 else -1)
    return None


@dataclass
class GapStep:
    move: chess.Move
    source: str  # main | chapter | gm | db | sf | sf-alt


class Sources:
    def __init__(
        self,
        games: list[chess.pgn.Game],
        cfg: dict[str, float | int],
        tier: str = "2000_2500",
        use_engine: bool = True,
        claims_path: Path | None = None,
    ) -> None:
        self.cfg = cfg
        self.sf: StockfishAnalyzer | None = StockfishAnalyzer() if use_engine else None
        self._top: dict[str, list[EngineLine]] = {}
        self._iso: dict[tuple[str, str], EngineLine | None] = {}
        self.chapter: dict[str, set[str]] = {}          # epd -> child ucis (all games, all variations)
        self.main_by_game: list[set[tuple[str, str]]] = []
        self.claims_lines: dict[str, list[list[GapStep]]] = {}
        self.gm_games: list[dict[str, object]] = []
        self.gm_index: dict[str, list[tuple[int, int]]] = {}
        self._db_cache: dict[str, dict[str, tuple[int, float]]] = {}
        self._opp_plaus_cache: dict[tuple[str, str], tuple[bool, str]] = {}
        self._opp_exp_cache: dict[tuple[str, str], bool] = {}
        self._tree_paths_cache: dict[tuple[str, int], list[list[GapStep]]] = {}
        self.explorer = ExplorerCache() if CACHE_DB.is_file() else None
        self.online = LocalOnlineDB()
        self.ratings = RATING_TIERS.get(tier, tier)
        self.online_ok = self.online.is_available(self.ratings)
        for g in games:
            self._index_chapter_game(g)
        self._load_gm_games(games)
        if claims_path and claims_path.is_file():
            self._load_claims(claims_path, games)

    def _load_claims(self, claims_path: Path, games: list[chess.pgn.Game]) -> None:
        """Load optional backing lines from JSON or simple YAML (`- node: ... / line: ...`)."""
        txt = claims_path.read_text(encoding="utf-8")
        items: list[dict[str, str]] = []
        try:
            raw = json.loads(txt)
            if isinstance(raw, list):
                items = [dict(x) for x in raw if isinstance(x, dict)]
        except ValueError:
            cur: dict[str, str] = {}
            for line in txt.splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("- "):
                    if cur:
                        items.append(cur)
                        cur = {}
                    s = s[2:].strip()
                if ":" in s:
                    k, v = s.split(":", 1)
                    cur[k.strip()] = v.strip().strip("\"'")
            if cur:
                items.append(cur)
        for item in items:
            line_s = item.get("line", "").strip()
            if not line_s:
                continue
            node_spec = item.get("node", "").strip()
            fen_s = item.get("fen", "").strip()
            b = None
            if fen_s:
                b = chess.Board(fen_s)
            elif node_spec.startswith("G"):
                m = re.match(r"G(\d+):(\d+)([wb])", node_spec, re.I)
                if m:
                    gi, mnum, sc = int(m.group(1)), int(m.group(2)), m.group(3).lower()
                    if 1 <= gi <= len(games):
                        gb = games[gi - 1].board()
                        want_turn = chess.WHITE if sc == "w" else chess.BLACK
                        for mv in games[gi - 1].mainline_moves():
                            gb.push(mv)
                            if gb.fullmove_number == mnum and gb.turn == want_turn:
                                b = gb.copy(stack=False)
                                break
                        if b is None and gb.fullmove_number >= mnum:
                            b = gb.copy(stack=False)
            if b is None:
                continue
            bb = b.copy(stack=False)
            steps: list[GapStep] = []
            for tok in line_s.split():
                if re.fullmatch(r"\d+\.+", tok):
                    continue
                try:
                    mv = bb.parse_san(_norm(tok))
                except ValueError:
                    break
                steps.append(GapStep(mv, "claim"))
                bb.push(mv)
            if steps:
                self.claims_lines.setdefault(b.epd(), []).append(steps)

    # ---- chapter tree ----
    def _index_chapter_game(self, game: chess.pgn.Game) -> None:
        main: set[tuple[str, str]] = set()
        b = game.board()
        node: chess.pgn.GameNode = game
        while node.variations:
            nxt = node.variations[0]
            main.add((b.epd(), nxt.move.uci()))
            b.push(nxt.move)
            node = nxt
        self.main_by_game.append(main)

        def walk(n: chess.pgn.GameNode, bb: chess.Board) -> None:
            for ch in n.variations:
                self.chapter.setdefault(bb.epd(), set()).add(ch.move.uci())
                bb.push(ch.move)
                walk(ch, bb)
                bb.pop()

        walk(game, game.board())

    # ---- GM games (cached Masters PGNs + chapter model games) ----
    def _load_gm_games(self, games: list[chess.pgn.Game]) -> None:
        pgns: list[str] = []
        if CACHE_DB.is_file():
            try:
                with sqlite3.connect(CACHE_DB) as conn:
                    rows = conn.execute("SELECT payload FROM api_cache WHERE cache_key LIKE 'master_pgn|%'").fetchall()
                for (payload,) in rows:
                    try:
                        pgns.append(str(json.loads(payload).get("pgn", "")))
                    except ValueError:
                        continue
            except sqlite3.Error:
                pass
        parsed: list[chess.pgn.Game] = []
        for txt in pgns:
            g = chess.pgn.read_game(io.StringIO(txt))
            if g is not None:
                parsed.append(g)
        from export_fact_sheet import classify_game

        parsed += [g for g in games if classify_game(g) == "model"]
        seen: set[tuple[str, ...]] = set()
        for g in parsed:
            mvs = list(g.mainline_moves())
            key = tuple(m.uci() for m in mvs)
            if not mvs or key in seen:
                continue
            seen.add(key)
            gid = len(self.gm_games)
            w_raw = g.headers.get("White", "").strip()
            b_raw = g.headers.get("Black", "").strip()
            if not b_raw and " vs" in w_raw.lower():
                m_vs = re.search(r"([A-Za-zÀ-ÿ\-\s]+?)\s+vs\.?\s+([A-Za-zÀ-ÿ\-\s]+?)(?:,|\||$)", w_raw)
                if m_vs:
                    w_raw, b_raw = m_vs.group(1), m_vs.group(2)
            w_toks = {t.lower() for t in re.split(r"[,\s]+", w_raw) if len(t) >= 3 and t.lower() not in {"model", "game"}}
            b_toks = {t.lower() for t in re.split(r"[,\s]+", b_raw) if len(t) >= 3 and t.lower() not in {"model", "game"}}
            b = g.board()
            sans: list[str] = []
            for i, mv in enumerate(mvs):
                if i <= 120:
                    self.gm_index.setdefault(b.epd(), []).append((gid, i))
                sans.append(_norm(b.san(mv)))
                b.push(mv)
            self.gm_games.append({"w_toks": w_toks, "b_toks": b_toks, "mvs": mvs, "sans": sans, "init": g.board(), "result": g.headers.get("Result", "*")})

    def gm_by_names(self, n1: str, n2: str) -> dict[str, object] | None:
        a, b = n1.lower(), n2.lower()
        for g in self.gm_games:
            wt: set[str] = g["w_toks"]  # type: ignore[assignment]
            bt: set[str] = g["b_toks"]  # type: ignore[assignment]
            if (a in wt and b in bt) or (a in bt and b in wt):
                return g
        return None

    # ---- DB (offline only: Masters cache + local online DB) ----
    def db_moves(self, board: chess.Board) -> dict[str, tuple[int, float]]:
        """uci -> (games, share %) taking the max share over available sources (no network)."""
        epd = board.epd()
        if epd in self._db_cache:
            return self._db_cache[epd]
        res: dict[str, tuple[int, float]] = {}
        if self.explorer is not None:
            for since in ("None", "2015"):
                data = self.explorer.get(f"masters_epd|{epd}|since={since}|until=None", max_age_sec=10**10)
                if data:
                    tot = sum(int(m.get("white", 0)) + int(m.get("draws", 0)) + int(m.get("black", 0)) for m in data.get("moves", []))
                    for m in data.get("moves", []):
                        n = int(m.get("white", 0)) + int(m.get("draws", 0)) + int(m.get("black", 0))
                        if tot and n:
                            pct = 100.0 * n / tot
                            if m["uci"] not in res or res[m["uci"]][1] < pct:
                                res[m["uci"]] = (n, pct)
                    break
        if self.online_ok and board.ply() <= 30:
            try:
                r = self.online.query(board, "tier", self.ratings, DEFAULT_SPEEDS, moves=20)
                for ms in r.moves:
                    if ms.uci not in res or res[ms.uci][1] < ms.play_pct:
                        res[ms.uci] = (ms.total, ms.play_pct)
            except Exception:
                pass
        self._db_cache[epd] = res
        return res

    # ---- Stockfish ----
    def top(self, board: chess.Board) -> list[EngineLine]:
        if self.sf is None or board.is_game_over():
            return []
        epd = board.epd()
        if epd not in self._top:
            self._top[epd] = self.sf.analyze(board, depth=int(self.cfg["depth"]), multipv=int(self.cfg["multipv"]))
        return self._top[epd]

    def cp_loss(self, board: chess.Board, move: chess.Move) -> int | None:
        tops = self.top(board)
        if not tops:
            return None
        best = tops[0]
        cand = next((l for l in tops if l.move_uci == move.uci()), None)
        if cand is None and self.sf is not None:
            key = (board.epd(), move.uci())
            if key not in self._iso:
                iso = self.sf.analyze(board, depth=int(self.cfg["depth"]), multipv=1, root_moves=[move])
                self._iso[key] = iso[0] if iso else None
            cand = self._iso[key]
        bc, cc = _line_cp(best), _line_cp(cand)
        if bc is None or cc is None:
            return None
        sign = 1 if board.turn == chess.WHITE else -1
        return max(0, (bc - cc) * sign)

    def eval_white(self, board: chess.Board) -> float | None:
        tops = self.top(board)
        cp = _line_cp(tops[0]) if tops else None
        return None if cp is None else cp / 100.0

    # ---- gap lines from a position ----
    def _tree_paths(self, board: chess.Board, main_set: set[tuple[str, str]]) -> list[list[GapStep]]:
        epd = board.epd()
        ck = (epd, id(main_set))
        if ck in self._tree_paths_cache:
            return self._tree_paths_cache[ck]
        maxt = int(self.cfg.get("max_tree_gap_plies", 16))
        paths: list[list[GapStep]] = []
        seen_on_path: set[str] = {epd}

        def dfs(b: chess.Board, acc: list[GapStep]) -> None:
            if len(paths) >= 40:
                return
            kids = self.chapter.get(b.epd())
            if not kids or len(acc) >= maxt:
                if acc:
                    paths.append(list(acc))
                return
            for u in sorted(kids, key=lambda u: (b.epd(), u) not in main_set):
                mv = chess.Move.from_uci(u)
                if mv not in b.legal_moves:
                    continue
                src = "main" if (b.epd(), u) in main_set else "chapter"
                b.push(mv)
                nepd = b.epd()
                if nepd not in seen_on_path:
                    seen_on_path.add(nepd)
                    acc.append(GapStep(mv, src))
                    dfs(b, acc)
                    acc.pop()
                    seen_on_path.remove(nepd)
                b.pop()

        dfs(board.copy(stack=False), [])
        self._tree_paths_cache[ck] = paths
        return paths

    def gap_lines(self, board: chess.Board, main_set: set[tuple[str, str]], include_sf: bool = True) -> Iterable[list[GapStep]]:
        maxg = int(self.cfg["max_gap_plies"])
        maxt = int(self.cfg.get("max_tree_gap_plies", 16))
        # 0) optional claims sidecar lines
        yield from self.claims_lines.get(board.epd(), [])
        # 1) chapter tree (transposition-aware, zero SF cost)
        yield from self._tree_paths(board, main_set)
        # 2) GM games through this position (zero SF cost)
        for gid, idx in self.gm_index.get(board.epd(), [])[:30]:
            mvs: list[chess.Move] = self.gm_games[gid]["mvs"]  # type: ignore[assignment]
            yield [GapStep(m, "gm") for m in mvs[idx : idx + maxt]]
        # 3) DB favourite chain (zero SF cost)
        chain: list[GapStep] = []
        b = board.copy(stack=False)
        for _ in range(maxg):
            db = self.db_moves(b)
            if not db:
                break
            u, (n, _pct) = max(db.items(), key=lambda kv: kv[1][0])
            if n < int(self.cfg["db_min_games"]):
                break
            mv = chess.Move.from_uci(u)
            if mv not in b.legal_moves:
                break
            chain.append(GapStep(mv, "db"))
            b.push(mv)
        if chain:
            yield chain
        # 4) Stockfish PVs (only invoked if requested)
        if include_sf:
            for ln in self.top(board):
                bb = board.copy(stack=False)
                steps: list[GapStep] = []
                for i, s in enumerate(ln.pv_san[:maxg]):
                    try:
                        mv = bb.parse_san(s)
                    except ValueError:
                        break
                    steps.append(GapStep(mv, "sf" if (i > 0 or ln.rank == 1) else "sf-alt"))
                    bb.push(mv)
                if steps:
                    yield steps

    # ---- classification helpers ----
    def opp_plausible(self, board: chess.Board, move: chess.Move) -> tuple[bool, str]:
        u = move.uci()
        k = (board.epd(), u)
        if k in self._opp_plaus_cache:
            return self._opp_plaus_cache[k]
        if u in self.chapter.get(board.epd(), set()):
            res = (True, "chapter")
        elif any(self.gm_games[gid]["mvs"][idx] == move for gid, idx in self.gm_index.get(board.epd(), [])):  # type: ignore[index]
            res = (True, "gm")
        else:
            db = self.db_moves(board).get(u)
            if db and db[0] >= int(self.cfg["db_min_games"]) and db[1] >= float(self.cfg["db_plausible_pct"]):
                res = (True, f"db {db[1]:.0f}%")
            else:
                loss = self.cp_loss(board, move)
                if loss is not None and loss <= int(self.cfg["opp_plausible_cp"]) and any(l.move_uci == u for l in self.top(board)):
                    res = (True, f"sf -{loss}cp")
                else:
                    res = (False, f"sf -{loss}cp" if loss is not None else "unknown")
        self._opp_plaus_cache[k] = res
        return res

    def opp_expected(self, board: chess.Board, move: chess.Move) -> bool:
        k = (board.epd(), move.uci())
        if k in self._opp_exp_cache:
            return self._opp_exp_cache[k]
        db = self.db_moves(board).get(move.uci())
        if db and db[0] >= int(self.cfg["db_min_games"]) and db[1] >= float(self.cfg["db_expected_pct"]):
            self._opp_exp_cache[k] = True
            return True
        loss = self.cp_loss(board, move)
        ok = loss is not None and loss <= int(self.cfg["opp_expected_cp"])
        self._opp_exp_cache[k] = ok
        return ok

    def close(self) -> None:
        if self.sf is not None:
            self.sf.close()


# ----------------------------------------------------------------------------------------------
# Resolver
# ----------------------------------------------------------------------------------------------


@dataclass
class Finding:
    severity: str  # ERROR | FLAG
    code: str
    where: str
    clause: str
    detail: str
    score: float = 0.0

    def line(self) -> str:
        return f"[{self.code}] {self.where}: {self.detail} — \"{self.clause[:110]}\""


@dataclass
class Embedding:
    steps: list[tuple[chess.Board, chess.Move, str, Mention | None]] = field(default_factory=list)
    ok: bool = True
    matched: int = 0
    issues: list[tuple[str, str, float]] = field(default_factory=list)  # (code, detail, score) unstated/gap issues
    end: chess.Board | None = None


def _is_static_piece(board: chess.Board, mt: Mention) -> bool:
    """True when an unannotated piece-square mention refers to a piece already on that square."""
    if mt.number is not None or mt.ann or "x" in mt.san or mt.has_verb or mt.san.startswith("O-O"):
        return False
    if mt.san[0] not in "KQRBN":
        return False
    sq = chess.parse_square(mt.san[-2:])
    p = board.piece_at(sq)
    want = chess.Piece.from_symbol(mt.san[0]).piece_type
    return p is not None and p.piece_type == want and (mt.side is None or p.color == mt.side)


def _match_all(board: chess.Board, mt: Mention) -> list[chess.Move | str]:
    """Return all legal moves matching mention (handling ambiguous SAN like 'Ne7'), or ['static'], or []."""
    if mt.optional and not mt.san.startswith("O-O"):
        sq = chess.parse_square(mt.san[-2:])
        p = board.piece_at(sq)
        want = chess.PAWN if mt.san[0] not in "KQRBN" else chess.Piece.from_symbol(mt.san[0]).piece_type
        if p is not None and p.piece_type == want and (mt.side is None or p.color == mt.side):
            return ["static"]
    if _is_static_piece(board, mt):
        return ["static"]
    if mt.side is not None and board.turn != mt.side:
        return []
    if mt.number is not None and board.fullmove_number != mt.number:
        return []
    san = mt.san
    try:
        mvs = [board.parse_san(san)]
    except chess.AmbiguousMoveError:
        dest = chess.parse_square(san[-2:])
        pt = chess.Piece.from_symbol(san[0]).piece_type
        mvs = [mv for mv in board.legal_moves if mv.to_square == dest and board.piece_type_at(mv.from_square) == pt]
    except ValueError:
        return []
    if "x" in san:
        mvs = [mv for mv in mvs if board.is_capture(mv)]
    return mvs


def _match(board: chess.Board, mt: Mention) -> chess.Move | None | str:
    hits = _match_all(board, mt)
    return hits[0] if hits else None


class Resolver:
    def __init__(self, sources: Sources, our: chess.Color, cfg: dict[str, float | int]) -> None:
        self.src = sources
        self.our = our
        self.cfg = cfg

    def _check_gap(self, board: chess.Board, step: GapStep) -> tuple[str, str, float] | None:
        if step.source in ("main",):
            return None
        mover = board.turn
        if mover == self.our:
            if step.source == "sf":
                return None
            loss = self.src.cp_loss(board, step.move)
            if loss is not None and loss > int(self.cfg["gap_our_cp"]):
                return ("UNSOUND-GAP", f"unnamed {board.san(step.move)} (from {step.source}) loses {loss}cp", float(loss))
            return None
        if step.source == "sf":
            return None
        if self.src.opp_expected(board, step.move):
            return None
        loss = self.src.cp_loss(board, step.move) or 0
        return ("UNSTATED-ASSUMPTION", f"line needs unnamed opponent move {board.san(step.move)} ({step.source}), not an expected reply", 60.0 + loss / 10)

    def _candidates_for(self, P: chess.Board, mt: Mention, main_set: set[tuple[str, str]], allow_sf: bool) -> list[tuple[list[GapStep], chess.Move | str]]:
        out: list[tuple[list[GapStep], chess.Move | str]] = []
        directs = _match_all(P, mt)
        explore_beyond_direct = False
        if directs:
            epd = P.epd()
            ch_kids = self.src.chapter.get(epd, set())
            db_map = self.src.db_moves(P)
            # Order ambiguous directs so chapter/DB moves come first
            directs_sorted = sorted(
                directs,
                key=lambda r: 0 if r == "static" or (isinstance(r, chess.Move) and (r.uci() in ch_kids or r.uci() in db_map)) else 1,
            )
            for d in directs_sorted:
                out.append(([], d))
            # If mt has no explicit move number or side and wasn't actually played in chapter/DB here, also explore gap lines
            if directs[0] != "static" and mt.number is None:
                has_known = any(isinstance(d, chess.Move) and (d.uci() in ch_kids or d.uci() in db_map) for d in directs)
                if not has_known and (mt.side is None or P.turn != mt.side):
                    explore_beyond_direct = True
                elif mt.side is None and P.turn == self.our and not has_known:
                    explore_beyond_direct = True
            if not explore_beyond_direct:
                return out
        seen_keys: set[tuple[tuple[str, ...], str]] = {((), d.uci() if isinstance(d, chess.Move) else "static") for _, d in out}
        for line in self.src.gap_lines(P, main_set, include_sf=allow_sf):
            b = P.copy(stack=False)
            for j, st in enumerate(line):
                b.push(st.move)
                hits = _match_all(b, mt)
                if hits:
                    gap = line[: j + 1]
                    gk = tuple(s.move.uci() for s in gap)
                    for r in hits:
                        rk = r.uci() if isinstance(r, chess.Move) else "static"
                        if (gk, rk) not in seen_keys:
                            seen_keys.add((gk, rk))
                            out.append((gap, r))
                    break

        def _prio(item: tuple[list[GapStep], chess.Move | str]) -> tuple[int, int]:
            gap, r = item
            if not gap:
                return (1 if explore_beyond_direct else 0, 0)
            bonus = 0
            if isinstance(r, chess.Move) and r.uci() in self.src.chapter.get(P.epd(), set()):
                bonus = 0
            if all(s.source == "main" for s in gap):
                return (0, len(gap))
            if all(s.source in ("main", "chapter") for s in gap):
                return (1, len(gap))
            return (2, len(gap) + bonus)

        out.sort(key=_prio)
        return out[:6]

    def embed(self, start: chess.Board, mentions: list[Mention], main_set: set[tuple[str, str]], allow_sf: bool = True) -> Embedding:
        best_fail_matched = -1
        complete_paths: list[list[tuple[chess.Board, chess.Move, str, Mention | None]]] = []
        visits = 0

        def rec(idx: int, P: chess.Board, steps_acc: list[tuple[chess.Board, chess.Move, str, Mention | None]]) -> bool:
            nonlocal best_fail_matched, visits
            visits += 1
            if visits > 100 or len(complete_paths) >= 6:
                return len(complete_paths) > 0
            if idx == len(mentions):
                complete_paths.append(list(steps_acc))
                return True
            mt = mentions[idx]
            cands = self._candidates_for(P, mt, main_set, allow_sf)
            if not cands:
                if idx > best_fail_matched:
                    best_fail_matched = idx
                return False
            for gap, r in cands:
                bb = P.copy(stack=False)
                g_steps: list[tuple[chess.Board, chess.Move, str, Mention | None]] = []
                for st in gap:
                    g_steps.append((bb.copy(stack=False), st.move, st.source, None))
                    bb.push(st.move)
                if r != "static":
                    assert isinstance(r, chess.Move)
                    g_steps.append((bb.copy(stack=False), r, "mention", mt))
                    bb.push(r)
                rec(idx + 1, bb, steps_acc + g_steps)
                if len(complete_paths) >= 6:
                    break
            return len(complete_paths) > 0

        rec(0, start.copy(stack=False), [])
        if not complete_paths:
            return Embedding(ok=False, matched=max(0, best_fail_matched), end=start.copy(stack=False))

        # Only run Stockfish gap-checks on COMPLETE embeddings (never on dead-end search branches)
        best_emb: Embedding | None = None
        best_rank: tuple[int, int] | None = None
        for steps in complete_paths:
            issues: list[tuple[str, str, float]] = []
            unnumbered_blunders = 0
            for b, mv, src, mt in steps:
                if mt is None:
                    iss = self._check_gap(b, GapStep(mv, src))
                    if iss:
                        issues.append(iss)
                elif mt.number is None and b.turn == self.our and not mt.framed_bad:
                    loss = self.src.cp_loss(b, mv)
                    if loss is not None and loss > int(self.cfg["blunder_cp"]):
                        unnumbered_blunders += 1
            end_b = steps[-1][0].copy(stack=False) if steps else start.copy(stack=False)
            if steps:
                end_b.push(steps[-1][1])
            emb = Embedding(steps=steps, ok=True, matched=len(mentions), issues=issues, end=end_b)
            rank = (len(issues), unnumbered_blunders)
            if rank == (0, 0):
                return emb
            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_emb = emb
        assert best_emb is not None
        return best_emb

    # ---- per-mention soundness / plausibility ----
    def judge_mentions(self, emb: Embedding) -> list[tuple[str, str, str, float]]:
        out: list[tuple[str, str, str, float]] = []  # (severity, code, detail, score)
        for b, mv, src, mt in emb.steps:
            if mt is None:
                continue
            san = b.san(mv)
            mover_ours = b.turn == self.our
            loss = self.src.cp_loss(b, mv)
            if mt.framed_bad:
                if loss is not None and loss < int(self.cfg["dismiss_cp"]):
                    out.append(("FLAG", "OVERSOLD-DISMISSAL", f"{san} is framed as bad but SF loss is only {loss}cp", 30.0))
                continue
            if mover_ours:
                if loss is None:
                    continue
                if loss > int(self.cfg["blunder_cp"]):
                    out.append(("ERROR", "UNSOUND", f"our {san} loses {loss}cp vs SF best", float(loss)))
                elif loss > int(self.cfg["soft_cp"]):
                    out.append(("FLAG", "DUBIOUS", f"our {san} loses {loss}cp vs SF best", float(loss)))
            else:
                ok, why = self.src.opp_plausible(b, mv)
                if not ok:
                    out.append(("FLAG", "IMPLAUSIBLE-OPP", f"plan relies on opponent {san} ({why}) which is neither a good nor a common move; frame it as a mistake/trap or drop it", 40.0))
        return out


def _split_branches(clause: str, mentions: list[Mention]) -> list[list[Mention]]:
    """Split parallel alternative mentions (e.g. '5... c5, 5... Nf6, and 5... Bc5' or 'Qe2 or Be3') into branches."""
    if len(mentions) <= 1:
        return [mentions]
    # Find spans of parallel alternatives at adjacent mentions
    branches: list[list[Mention]] = [[mentions[0]]]
    alt_mode = False
    prefix: list[Mention] = []
    for i in range(1, len(mentions)):
        prev, cur = mentions[i - 1], mentions[i]
        between = clause[prev.end : cur.pos]
        same_num = prev.number is not None and cur.number == prev.number and cur.side == prev.side
        is_or = bool(re.fullmatch(r"\s*(?:,?\s*\bor\b|\s*/\s*|\bover\b(?:\s+\w+){0,2})\s*", between, re.I))
        is_list_sep = bool(re.fullmatch(r"\s*(?:,\s*(?:and\s+)?|\band\s+)\s*", between, re.I))
        if same_num and len(between) <= 40:
            if not alt_mode:
                prefix = branches[-1][:-1]
                branches[-1] = prefix + [prev]
                alt_mode = True
            branches.append(list(prefix) + [cur])
        elif is_or and (prev.side == cur.side or prev.side is None or cur.side is None):
            if "over" in between.lower():
                cur.framed_bad = True
            if not alt_mode:
                prefix = branches[-1][:-1]
                branches[-1] = prefix + [prev]
                alt_mode = True
            branches.append(list(prefix) + [cur])
        elif alt_mode and is_list_sep and prev.number is None and cur.number is None and (prev.side == cur.side or (prev.side is None and cur.side is None)) and len(between) <= 8:
            if prev.after_kw and not cur.after_kw:
                cur.after_kw = True
            branches.append(list(prefix) + [cur])
        elif is_or and alt_mode:
            if prev.after_kw and not cur.after_kw:
                cur.after_kw = True
        elif prev.side == chess.BLACK and cur.side == chess.BLACK and prev.number is None and cur.number is None and re.fullmatch(r"\s*(?:,?\s*\band\b|\s*,\s*)\s*", between, re.I):
            # e.g. "...c5 and ...e5"
            if not alt_mode:
                prefix = branches[-1][:-1]
                branches[-1] = prefix + [prev]
                alt_mode = True
            if prev.after_kw and not cur.after_kw:
                cur.after_kw = True
            branches.append(list(prefix) + [cur])
        else:
            alt_mode = False
            branches[-1].append(cur)
    # Propagate after_kw across 'or' branches (e.g. "if dxe6 or ...exd5")
    if len(branches) > 1:
        for b in branches[1:]:
            for idx_m, m in enumerate(b):
                if idx_m < len(branches[0]) and branches[0][idx_m].after_kw:
                    m.after_kw = True
    return branches


def _temporal_orders(mentions: list[Mention]) -> list[list[Mention]]:
    """Generate natural chronological orderings (handling 'X after Y' and 'before X, Y' inversions)."""
    base = list(mentions)
    orders: list[list[Mention]] = []
    # Reorder 'X after Y' -> [Y, X] first when Y has no conflicting later move number
    swapped = list(base)
    changed = False
    i = 1
    while i < len(swapped):
        if swapped[i].after_kw and not swapped[i - 1].after_kw:
            swapped[i - 1], swapped[i] = swapped[i], swapped[i - 1]
            changed = True
            i += 2
            continue
        i += 1
    if changed:
        orders.append(swapped)
    orders.append(base)
    if any(m.number for m in base):
        numbered = sorted(base, key=lambda m: (_ply_index(m.number, m.side) if m.number and m.side is not None else 10**6))
        if numbered not in orders:
            orders.append(numbered)
    # Reorder 'before X, Y' -> [Y, X]
    sw2 = list(base)
    ch2 = False
    i = 0
    while i + 1 < len(sw2):
        if sw2[i].before_kw and not sw2[i + 1].before_kw:
            sw2[i], sw2[i + 1] = sw2[i + 1], sw2[i]
            ch2 = True
            i += 2
            continue
        i += 1
    if ch2 and sw2 not in orders:
        orders.append(sw2)
    return orders


def _intro_extra_boards(games: list[chess.pgn.Game], intro_game: chess.pgn.Game) -> list[tuple[str, chess.Board]]:
    """For intro overview bullets, collect branch boards from the intro RAVs and chapter trainable lines."""
    from export_fact_sheet import classify_game

    extras: list[tuple[str, chess.Board]] = []
    seen: set[str] = set()

    def _add(tag: str, b: chess.Board) -> None:
        e = b.epd()
        if e not in seen:
            seen.add(e)
            extras.append((tag, b))

    # Intro RAVs (at branch point BEFORE RAV leaf and at RAV leaf)
    def _walk_intro(n: chess.pgn.GameNode, b: chess.Board, in_rav: bool) -> None:
        if in_rav and (not n.variations or (n.parent and len(n.parent.variations) > 1)):
            _add("intro-rav", b.copy(stack=False))
        for idx, ch in enumerate(n.variations):
            if idx > 0:
                _add("intro-rav-root", b.copy(stack=False))
            b.push(ch.move)
            _walk_intro(ch, b, in_rav or idx > 0)
            b.pop()

    _walk_intro(intro_game, intro_game.board(), False)
    # Trainable games: first divergence ply and move 6..10 anchors
    for g in games:
        if classify_game(g) != "trainable":
            continue
        b = g.board()
        for ply, mv in enumerate(g.mainline_moves()):
            b.push(mv)
            if 6 <= ply <= 16:
                _add("chapter-tabiya", b.copy(stack=False))
                break
    return extras


def _ply_index(number: int, side: chess.Color) -> int:
    return (number - 1) * 2 + (0 if side == chess.WHITE else 1)


def _orders(mentions: list[Mention], max_perm: int) -> list[list[Mention]]:
    orders = [mentions]
    if any(m.number for m in mentions):
        numbered = sorted(mentions, key=lambda m: (_ply_index(m.number, m.side) if m.number and m.side is not None else 10**6))
        if numbered != mentions:
            orders.append(numbered)
    if 1 < len(mentions) <= max_perm:
        for p in itertools.permutations(mentions):
            lp = list(p)
            if lp not in orders:
                orders.append(lp)
    return orders


def _start_candidates(root: chess.Board, stack: list[chess.Move], mentions: list[Mention]) -> list[tuple[str, chess.Board]]:
    cands: list[tuple[str, chess.Board]] = []

    def board_at(k: int) -> chess.Board:
        b = root.copy(stack=False)
        for mv in stack[:k]:
            b.push(mv)
        return b

    first = mentions[0]
    root_ply = root.ply()
    if first.number and first.side is not None:
        k = _ply_index(first.number, first.side) - root_ply
        if 0 <= k <= len(stack):
            cands.append(("numbered", board_at(k)))
    cands.append(("node", board_at(len(stack))))
    if stack:
        cands.append(("alt", board_at(len(stack) - 1)))
    # past anchoring: first mention equals an earlier move on the path
    b = root.copy(stack=False)
    sans: list[str] = []
    for mv in stack:
        sans.append(_norm(b.san(mv)).rstrip("+#"))
        b.push(mv)
    for k in range(len(stack) - 1, max(-1, len(stack) - 30), -1):
        if sans[k] == first.san:
            cands.append(("past", board_at(k)))
            break
    return cands


def _comment_items(game: chess.pgn.Game) -> Iterable[tuple[chess.pgn.GameNode, str, chess.Board, list[chess.Move], str]]:
    """Yield (node, text, root_board, move_stack, label) for every comment in the game tree."""
    root = game.board()

    def label(node: chess.pgn.GameNode) -> str:
        if node.move is None or node.parent is None:
            return "root"
        b = node.parent.board()
        n = b.fullmove_number
        return f"{n}. {b.san(node.move)}" if b.turn == chess.WHITE else f"{n}... {b.san(node.move)}"

    stack_nodes: list[chess.pgn.GameNode] = [game]
    while stack_nodes:
        node = stack_nodes.pop()
        b = node.board()
        mv_stack = list(b.move_stack)
        if node.comment:
            yield node, node.comment, root, mv_stack, label(node)
        if node.starting_comment and node.parent is not None:
            yield node, node.starting_comment, root, mv_stack[:-1], label(node) + " (pre)"
        stack_nodes.extend(reversed(node.variations))


@dataclass
class ClauseRecord:
    where: str
    clause: str
    status: str  # resolved | unbacked | residual | negated-only | citation
    fen: str = ""


def _suggest_backing(board: chess.Board, missing_san: str, src: Sources) -> str:
    """Search SF top-3 PVs from `board` for `missing_san` to propose a ready-to-paste backing hint."""
    target = _norm(re.sub(r"^\d+\.(?:\.\.)?\s*|\.\.\.\s*", "", missing_san))
    for ln in src.top(board):
        for idx, mv_s in enumerate(ln.pv_san):
            if _norm(mv_s) == target:
                seq = " ".join(ln.pv_san[: idx + 1])
                return f" | SF PV backing: \"{seq}\""
    return " (not in SF top-3 PVs)"


def _check_arrows(
    raw_comment: str,
    board: chess.Board,
    node: chess.pgn.GameNode,
    our: chess.Color,
    src: Sources,
    where: str,
    findings: list[Finding],
) -> None:
    """Verify [%cal ...] arrows map to a legal move, chapter/SF line, or piece attack ray on `board`."""
    for m in re.finditer(r"\[%cal\s+([^\]]+)\]", raw_comment):
        for tok in m.group(1).split(","):
            tok = tok.strip()
            if len(tok) != 5 or tok[0] not in "GBRY":
                continue
            col_tag = tok[0]
            try:
                f_sq = chess.parse_square(tok[1:3])
                t_sq = chess.parse_square(tok[3:5])
            except ValueError:
                continue
            p = board.piece_at(f_sq)
            if p is None:
                continue  # empty-square arrow is already a structural error in validate_chessable
            # Direct attack ray or legal/pseudo-legal move in position or in child RAVs/SF PV
            attacks = t_sq in board.attacks(f_sq)
            legal_uv = any(mv.from_square == f_sq and mv.to_square == t_sq for mv in board.legal_moves)
            in_tree = any(ch.move.from_square == f_sq and ch.move.to_square == t_sq for ch in node.variations)
            if attacks or legal_uv or in_tree:
                continue
            # Also allow same-turn piece maneuver if the square is reachable in <=2 moves of that piece in SF/chapter
            reachable = False
            b_tmp = board.copy(stack=False)
            b_tmp.turn = p.color
            if any(mv.from_square == f_sq and mv.to_square == t_sq for mv in b_tmp.pseudo_legal_moves):
                reachable = True
            elif p.piece_type == chess.KNIGHT:
                # 2-hop knight or pawn push-chain visual route
                for mid in b_tmp.attacks(f_sq):
                    if t_sq in chess.SquareSet.from_square(mid) or abs(chess.square_file(mid) - chess.square_file(t_sq)) in (1, 2):
                        if chess.square_distance(mid, t_sq) <= 2:
                            # check knight 2-move reach
                            nb = chess.Board(None)
                            nb.set_piece_at(mid, p)
                            if t_sq in nb.attacks(mid):
                                reachable = True
                                break
            if not reachable and col_tag in ("G", "B"):
                findings.append(
                    Finding(
                        "FLAG",
                        "ARROW-PROVENANCE",
                        where,
                        tok,
                        f"[{col_tag}] arrow {tok[1:3]}->{tok[3:5]} from {p.symbol()} is not a legal move or attack ray here",
                        30.0,
                    )
                )


def check_game(
    game: chess.pgn.Game,
    gidx: int,
    all_games: list[chess.pgn.Game],
    src: Sources,
    resolver: Resolver,
    cfg: dict[str, float | int],
    findings: list[Finding],
    records: list[ClauseRecord],
    check_arrows: bool = False,
) -> None:
    from claim_lexicon import evaluate_clause
    from export_fact_sheet import classify_game

    kind = classify_game(game)
    title = game.headers.get("White", "")[:40]
    main_set = src.main_by_game[gidx - 1]
    intro_extras: list[tuple[str, chess.Board]] | None = None
    for node, text, root, stack, lab in _comment_items(game):
        where = f"G{gidx} [{kind}] {title} @ {lab}"
        node_board = root.copy(stack=False)
        for mv in stack:
            node_board.push(mv)
        if check_arrows:
            _check_arrows(text, node_board, node, resolver.our, src, where, findings)
        is_intro_overview = kind == "intro" and (node.parent is None or not node.variations)
        prev_end_board: chess.Board | None = None
        in_plan_block = False
        for clause in split_clauses(text):
            if "PLAN FROM HERE" in text or "GATEWAY TO THE MIDDLEGAME" in text:
                if clause.startswith("Verdict") or clause.startswith("Our Plan") or clause.startswith("Watch Out") or clause.startswith("Key Trades"):
                    in_plan_block = True
                elif "SAMPLE CONTINUATIONS" in clause or clause.startswith("Click "):
                    in_plan_block = False
            mentions = extract_mentions(clause)
            # GM citation check (any game kind) — only moves before future-intent verbs belong to historical game
            cite = GM_VS_CITE_RE.search(clause)
            if cite:
                g = src.gm_by_names(cite.group(1), cite.group(2))
                fut_m = re.search(r"\b(?:aims?\s+for|prepar(?:e|es|ing)|eyeing|threatening|hoping\s+for)\b", clause, re.I)
                fut_pos = fut_m.start() if fut_m else len(clause) + 1
                cited = [m for m in mentions if not m.negated and m.pos < fut_pos]
                if g is None:
                    findings.append(Finding("FLAG", "GM-UNCACHED", where, clause, f"cited game {cite.group(1)} vs {cite.group(2)} not in local cache; cannot verify", 20.0))
                elif cited:
                    gsans: list[str] = g["sans"]  # type: ignore[assignment]
                    i = 0
                    missing = []
                    for m in cited:
                        try:
                            i = gsans.index(m.san, i) + 1
                        except ValueError:
                            if m.san not in gsans:
                                missing.append(m.san)
                    if missing:
                        findings.append(Finding("ERROR", "GM-CITATION", where, clause, f"{cite.group(1)} vs {cite.group(2)} never played {missing}", 80.0))
                records.append(ClauseRecord(where, clause, "citation", node_board.fen()))
                prev_end_board = None
                continue
            # model-game note: outcome words must match result, and cited moves must occur in THAT model game in order
            if kind == "model" and node.parent is None:
                res = game.headers.get("Result", "*")
                low = clause.lower()
                if res == "1/2-1/2" and re.search(r"\b(?:wins|won|converts|crushes)\b", low):
                    findings.append(Finding("ERROR", "MODEL-RESULT", where, clause, "note claims a win but the game was drawn", 70.0))
                if res in ("1-0", "0-1") and re.search(r"\b(?:holds|draws|drawn)\b", low):
                    findings.append(Finding("ERROR", "MODEL-RESULT", where, clause, f"note claims a draw but result is {res}", 70.0))
                mb = game.board()
                mg_sans: list[str] = []
                for mv in game.mainline_moves():
                    mg_sans.append(_norm(mb.san(mv)))
                    mb.push(mv)
                mi = 0
                missing_m = []
                for m in mentions:
                    if m.negated:
                        continue
                    try:
                        mi = mg_sans.index(m.san, mi) + 1
                    except ValueError:
                        if m.san not in mg_sans:
                            missing_m.append(m.san)
                if missing_m:
                    findings.append(Finding("ERROR", "MODEL-MOVE", where, clause, f"model note attributes {missing_m} not played in this game", 80.0))
                records.append(ClauseRecord(where, clause, "model-note" if mentions else "residual", node_board.fen()))
                prev_end_board = None
                continue
            prevented = [m for m in mentions if m.prevented and not m.negated]
            for m in prevented:
                _check_prevented(m, node_board, game, node, src, resolver, cfg, findings, where, clause)
            active_all = [m for m in mentions if not m.negated and not m.prevented]
            if not active_all:
                lex_hit, lex_fnds = evaluate_clause(clause, node_board, resolver.our, where, src=src)
                for lf in lex_fnds:
                    findings.append(Finding(lf.severity, lf.code, lf.where, lf.clause, lf.detail, lf.score))
                status = "lexicon" if lex_hit else ("negated-only" if mentions else "residual")
                records.append(ClauseRecord(where, clause, status, node_board.fen()))
                prev_end_board = None
                continue
            # Forward-goal/threat/menu clauses ("10. Qd3 clears d1 for Rd1", "11. Re1 sets up Ne5, Qd3",
            # or unnumbered non-conditional menus inside PLAN FROM HERE):
            # moves BEFORE the goal marker remain concrete; unnumbered moves AFTER are independent goals (UNBACKED still ERROR).
            gm_goal = GOAL_CLAUSE_RE.search(clause)
            goal_pos = gm_goal.start() if gm_goal else None
            is_cond_clause = bool(re.search(r"\b(?:against|meet|if|when|once|after|never\s+play|avoid)\b", clause, re.I))
            is_plan_menu = in_plan_block and not is_cond_clause and not any(m.number is not None for m in active_all) and not any(m.framed_bad for m in active_all)
            if is_plan_menu:
                goal_pos = 0
            concrete_part = [m for m in active_all if goal_pos is None or m.pos < goal_pos or m.number is not None]
            goal_part = [m for m in active_all if goal_pos is not None and m.pos >= goal_pos and m.number is None]
            for m in goal_part:
                m.is_goal = True
            eval_groups: list[tuple[bool, list[Mention]]] = []
            if concrete_part:
                for br in _split_branches(clause, concrete_part):
                    eval_groups.append((False, br))
            if goal_part:
                if any(m.after_kw for m in goal_part):
                    for br in _split_branches(clause, goal_part):
                        eval_groups.append((True, br))
                else:
                    for m in goal_part:
                        eval_groups.append((True, [m]))
            last_end: chess.Board | None = None
            concrete_end: chess.Board | None = None
            for is_goal_clause, active in eval_groups:
                best: Embedding | None = None
                base_orders = _temporal_orders(active)
                starts_cache: dict[int, list[tuple[str, chess.Board]]] = {}
                for o in base_orders:
                    sc = _start_candidates(root, stack, o)
                    if is_goal_clause and concrete_end is not None:
                        sc.insert(0, ("concrete-end", concrete_end))
                    elif prev_end_board is not None:
                        sc.append(("prev", prev_end_board))
                    starts_cache[id(o)] = sc
                if is_intro_overview:
                    if intro_extras is None:
                        intro_extras = _intro_extra_boards(all_games, game)
                for order in base_orders:
                    for _cname, start in starts_cache[id(order)]:
                        emb = resolver.embed(start, order, main_set, allow_sf=False)
                        if emb.ok and not emb.issues:
                            best = emb
                            break
                        if best is None or (emb.ok and not best.ok) or (emb.ok == best.ok and emb.matched > best.matched):
                            best = emb
                    if best is not None and best.ok:
                        break
                if (best is None or not best.ok) and is_intro_overview and intro_extras:
                    for order in base_orders[:1]:
                        for _cname, start in intro_extras:
                            emb = resolver.embed(start, order, main_set, allow_sf=False)
                            if emb.ok and not emb.issues:
                                best = emb
                                break
                            if best is None or (emb.ok and not best.ok) or (emb.ok == best.ok and emb.matched > best.matched):
                                best = emb
                        if best is not None and best.ok:
                            break
                if best is None or not best.ok:
                    orders_2 = list(base_orders)
                    has_temp_cue = any(m.after_kw or m.before_kw for m in active)
                    if has_temp_cue and 1 < len(active) <= int(cfg["max_perm_mentions"]):
                        for p in itertools.permutations(active):
                            lp = list(p)
                            if lp not in orders_2:
                                orders_2.append(lp)
                    for order in orders_2[:2]:
                        sc = _start_candidates(root, stack, order)[:2]
                        if prev_end_board is not None:
                            sc.append(("prev", prev_end_board))
                        for _cname, start in sc:
                            emb = resolver.embed(start, order, main_set, allow_sf=True)
                            if emb.ok and not emb.issues:
                                best = emb
                                break
                            if best is None or (emb.ok and not best.ok) or (emb.ok == best.ok and emb.matched > best.matched):
                                best = emb
                        if best is not None and best.ok:
                            break
                assert best is not None
                if not best.ok:
                    missing = active[best.matched].raw if best.matched < len(active) else "?"
                    hint = _suggest_backing(node_board, missing, src)
                    findings.append(
                        Finding("ERROR", "UNBACKED", where, clause, f"no game line or Stockfish line from this position reaches {missing} (resolved {best.matched}/{len(active)} moves){hint}", 90.0)
                    )
                    records.append(ClauseRecord(where, clause, "unbacked", node_board.fen()))
                    continue
                last_end = best.end
                if not is_goal_clause:
                    concrete_end = best.end
                for code, detail, score in best.issues:
                    findings.append(Finding("FLAG" if is_goal_clause else "ERROR", code, where, clause, detail, score * (0.5 if is_goal_clause else 1.0)))
                for sev, code, detail, score in resolver.judge_mentions(best):
                    # In a forward goal/threat ("clears d1 for Rd1", "threatening Qh5"), an immediate tactical
                    # sacrifice/timing issue is advisory (FLAG) rather than a hard blunder veto.
                    eff_sev = "FLAG" if (is_goal_clause and sev == "ERROR") else sev
                    findings.append(Finding(eff_sev, code, where, clause, detail, score * (0.5 if is_goal_clause else 1.0)))
                _check_eval_claim(clause, best, src, cfg, findings, where)
                _, lex_fnds = evaluate_clause(clause, node_board, resolver.our, where, src=src, eval_board=best.end)
                for lf in lex_fnds:
                    findings.append(Finding(lf.severity, lf.code, lf.where, lf.clause, lf.detail, lf.score))
                records.append(ClauseRecord(where, clause, "resolved", node_board.fen()))
            prev_end_board = last_end


def _check_prevented(m: Mention, node_board: chess.Board, game: chess.pgn.Game, node: chess.pgn.GameNode, src: Sources, resolver: Resolver, cfg: dict[str, float | int], findings: list[Finding], where: str, clause: str) -> None:
    """'stops ...f5': at the first position where that side is to move, the move must be illegal or bad."""
    b = node_board.copy(stack=False)
    side = m.side
    if side is None:
        side = not resolver.our
    if b.turn != side:
        nxt = node.variations[0].move if node.variations else None
        if nxt is None:
            tops = src.top(b)
            nxt = chess.Move.from_uci(tops[0].move_uci) if tops else None
        if nxt is None or nxt not in b.legal_moves:
            return
        b.push(nxt)
    try:
        mv = b.parse_san(m.san)
    except ValueError:
        return  # illegal: prevention holds
    loss = src.cp_loss(b, mv)
    if loss is not None and loss < int(cfg["prevent_cp"]):
        findings.append(Finding("FLAG", "NOT-PREVENTED", where, clause, f"{m.raw} is legal and only loses {loss}cp here", 45.0))


def _check_eval_claim(clause: str, emb: Embedding, src: Sources, cfg: dict[str, float | int], findings: list[Finding], where: str) -> None:
    claims = EVAL_RE.findall(clause)
    if len(claims) != 1 or emb.end is None or not emb.steps:
        return
    sign, val = claims[0]
    claimed = float(val) * (-1 if sign in "-−–" else 1)
    actual = src.eval_white(emb.end)
    if actual is None:
        return
    tol = max(float(cfg["eval_tol_abs"]), float(cfg["eval_tol_rel"]) * abs(claimed))
    if abs(actual - claimed) > tol:
        findings.append(Finding("FLAG", "EVAL-MISMATCH", where, clause, f"claims {claimed:+.2f} but SF gives {actual:+.2f} at the end of the resolved line", 25.0 + 10 * abs(actual - claimed)))


def run(
    pgn_path: Path,
    side: str,
    tier: str = "2000_2500",
    games_sel: set[int] | None = None,
    trainable_only: bool = False,
    cfg: dict[str, float | int] | None = None,
    use_engine: bool = True,
    pgn_text: str | None = None,
    claims_path: Path | None = None,
    ledger_path: Path | None = None,
    emit_residual: Path | None = None,
    check_arrows: bool = False,
) -> tuple[list[Finding], list[ClauseRecord]]:
    from flag_ledger import FlagLedger, write_residual

    cfg = cfg or load_config()
    text = pgn_text if pgn_text is not None else pgn_path.read_text(encoding="utf-8-sig")
    games: list[chess.pgn.Game] = []
    fh = io.StringIO(text)
    while True:
        g = chess.pgn.read_game(fh)
        if g is None:
            break
        games.append(g)
    src = Sources(games, cfg, tier=tier, use_engine=use_engine, claims_path=claims_path)
    our = chess.WHITE if side == "white" else chess.BLACK
    resolver = Resolver(src, our, cfg)
    findings: list[Finding] = []
    records: list[ClauseRecord] = []
    from export_fact_sheet import classify_game

    t_idx = 0
    try:
        for i, g in enumerate(games, 1):
            is_tr = classify_game(g) == "trainable"
            if is_tr:
                t_idx += 1
            if trainable_only and not is_tr:
                continue
            sel_idx = t_idx if trainable_only else i
            if games_sel is not None and sel_idx not in games_sel:
                continue
            check_game(g, i, games, src, resolver, cfg, findings, records, check_arrows=check_arrows)
        if emit_residual is not None:
            def _ev_str(fen: str) -> str:
                ev = src.eval_white(chess.Board(fen))
                return f"{ev:+.2f}" if ev is not None else "?"

            write_residual(emit_residual, records, sf_eval_fn=_ev_str if use_engine else None)
    finally:
        src.close()
    # dedupe identical findings and optionally apply dismissal ledger
    ledger = FlagLedger(ledger_path) if ledger_path else None
    seen: set[tuple[str, str, str]] = set()
    uniq: list[Finding] = []
    for f in findings:
        if ledger and f.severity != "ERROR" and ledger.is_dismissed(f.code, f.where, f.clause):
            continue
        k = (f.code, f.where, f.detail)
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    uniq.sort(key=lambda f: (f.severity != "ERROR", -f.score))
    return uniq, records


def _parse_sel(spec: str | None) -> set[int] | None:
    if not spec:
        return None
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return out


def main() -> int:
    from flag_ledger import format_summary

    ap = argparse.ArgumentParser(description="Move-provenance resolver: every move in prose must be backed by a game or Stockfish line.")
    ap.add_argument("pgn")
    ap.add_argument("--side", choices=["white", "black"], required=True)
    ap.add_argument("--tier", default="2000_2500")
    ap.add_argument("--games", default=None)
    ap.add_argument("--trainable-only", action="store_true")
    ap.add_argument("--depth", type=int, default=None)
    ap.add_argument("--claims", default=None, help="Optional backing claims JSON/YAML sidecar")
    ap.add_argument("--ledger", default=None, help="Optional flag dismissal ledger JSON")
    ap.add_argument("--emit-residual", default=None, help="Write unverified residual clauses to Markdown")
    ap.add_argument("--check-arrows", action="store_true", help="Verify [%cal] arrow provenance")
    ap.add_argument("--summary", action="store_true", help="Print <=25-line ranked summary")
    ap.add_argument("--json", dest="json_out", default=None, help="Write findings + clause records as JSON")
    ap.add_argument("--top", type=int, default=40, help="Print at most N findings (ranked)")
    args = ap.parse_args()
    cfg = load_config()
    if args.depth:
        cfg["depth"] = args.depth
    findings, records = run(
        Path(args.pgn),
        args.side,
        args.tier,
        _parse_sel(args.games),
        args.trainable_only,
        cfg,
        claims_path=Path(args.claims) if args.claims else None,
        ledger_path=Path(args.ledger) if args.ledger else None,
        emit_residual=Path(args.emit_residual) if args.emit_residual else None,
        check_arrows=args.check_arrows,
    )
    n_err = sum(f.severity == "ERROR" for f in findings)
    if args.summary:
        print(format_summary(findings))
    else:
        n_flag = len(findings) - n_err
        stat: dict[str, int] = {}
        for r in records:
            stat[r.status] = stat.get(r.status, 0) + 1
        print(f"PROVENANCE: {n_err} errors, {n_flag} flags | clauses: " + ", ".join(f"{k}={v}" for k, v in sorted(stat.items())))
        for f in findings[: args.top]:
            print(f"{f.severity} {f.line()}")
        if len(findings) > args.top:
            print(f"... {len(findings) - args.top} more (use --json)")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"findings": [asdict(f) for f in findings], "records": [asdict(r) for r in records]}, indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
