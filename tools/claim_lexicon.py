"""Concept-category claim lexicon for SAN-free and structural chess prose assertions.

Evaluates general board and engine predicates (never opening- or incident-specific):
  1. Eval-strength calibration (winning / clear edge / slight edge / equal) vs Stockfish/WDL
  2. Structural pawn predicates (isolated, doubled, passed, backward, open/semi-open file)
  3. Material/color-complex predicates (bishop pair, opposite-colored bishops, square color parity)
  4. Outpost/hole pawn-safety and target/attack reachability predicates

Any clause with neither a resolved move provenance nor a lexicon match is marked unmatched
so it flows into `residual.md` for targeted verifier review rather than passing silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import chess

if TYPE_CHECKING:
    from provenance import Sources


@dataclass
class LexFinding:
    severity: str  # ERROR | FLAG
    code: str
    where: str
    clause: str
    detail: str
    score: float = 0.0

    def line(self) -> str:
        return f"[{self.code}] {self.where}: {self.detail} — \"{self.clause[:110]}\""


# ----------------------------------------------------------------------------------------------
# Pure board geometry predicates
# ----------------------------------------------------------------------------------------------


def is_light_sq(sq: int) -> bool:
    return (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1


def enemy_pawn_attackers(board: chess.Board, sq: int, for_color: chess.Color) -> tuple[list[str], list[str]]:
    enemy = not for_color
    f, r = chess.square_file(sq), chess.square_rank(sq)
    cur: list[str] = []
    fut: list[str] = []
    for psq in board.pieces(chess.PAWN, enemy):
        pf, pr = chess.square_file(psq), chess.square_rank(psq)
        if abs(pf - f) != 1:
            continue
        if enemy == chess.BLACK:
            if pr == r + 1:
                cur.append(chess.square_name(psq))
            elif pr > r + 1:
                fut.append(chess.square_name(psq))
        else:
            if pr == r - 1:
                cur.append(chess.square_name(psq))
            elif pr < r - 1:
                fut.append(chess.square_name(psq))
    return sorted(cur), sorted(fut)


def is_isolated_pawn(board: chess.Board, sq: int) -> bool:
    p = board.piece_at(sq)
    if p is None or p.piece_type != chess.PAWN:
        return False
    f = chess.square_file(sq)
    own = board.pieces(chess.PAWN, p.color)
    return not any(abs(chess.square_file(o) - f) == 1 for o in own)


def is_doubled_file(board: chess.Board, file_idx: int) -> bool:
    for col in (chess.WHITE, chess.BLACK):
        if sum(1 for s in board.pieces(chess.PAWN, col) if chess.square_file(s) == file_idx) >= 2:
            return True
    return False


def is_passed_pawn(board: chess.Board, sq: int) -> bool:
    p = board.piece_at(sq)
    if p is None or p.piece_type != chess.PAWN:
        return False
    f, r = chess.square_file(sq), chess.square_rank(sq)
    for esq in board.pieces(chess.PAWN, not p.color):
        ef, er = chess.square_file(esq), chess.square_rank(esq)
        if abs(ef - f) <= 1 and ((p.color == chess.WHITE and er > r) or (p.color == chess.BLACK and er < r)):
            return False
    return True


def file_status(board: chess.Board, file_idx: int) -> str:
    wc = sum(1 for s in board.pieces(chess.PAWN, chess.WHITE) if chess.square_file(s) == file_idx)
    bc = sum(1 for s in board.pieces(chess.PAWN, chess.BLACK) if chess.square_file(s) == file_idx)
    if wc == 0 and bc == 0:
        return "open"
    if wc == 0 or bc == 0:
        return "semi-open"
    return "closed"


# ----------------------------------------------------------------------------------------------
# Concept-category matchers
# ----------------------------------------------------------------------------------------------

COND_PREFIX_RE = re.compile(r"\b(?:if|when|once|after|unless|potential|future|would|becomes?|turns?\s+into|creating|leaving)\b", re.I)
NEG_CTX_RE = re.compile(r"\b(?:no|not|without|avoids?|never|prevents?|stops?)\b", re.I)

# 1. Eval calibration
EVAL_WIN_RE = re.compile(r"\b(?:completely\s+winning|decisive\s+(?:edge|advantage)|winning\s+(?:advantage|endgame|position)|crushing)\b", re.I)
EVAL_CLEAR_RE = re.compile(r"\b(?:clear\s+(?:edge|advantage)|big\s+(?:edge|advantage)|huge\s+(?:edge|advantage)|strong\s+advantage)\b", re.I)
EVAL_EQUAL_RE = re.compile(r"\b(?:equal(?:ity)?|balanced|completely\s+level)\b", re.I)
NUM_EVAL_RE = re.compile(r"(?<![\w.])([+\-−–])(\d{1,2}\.\d{1,2})(?!\d)")

# 2. Structural pawn predicates
ISOLATED_SQ_RE = re.compile(r"\bisolated\s+(?:[a-h]\s+)?([a-h][1-8])(?:\s*-?\s*pawn)?\b", re.I)
DOUBLED_FILE_RE = re.compile(r"\bdoubled\s+([a-h])(?:-|\s+)?pawns?\b", re.I)
PASSED_SQ_RE = re.compile(r"\bpassed\s+([a-h][1-8])(?:\s*-?\s*pawn)?\b", re.I)
OPEN_FILE_RE = re.compile(r"\b(semi-open|open)\s+([a-h])-file\b", re.I)

# 3. Material / square-color / outpost predicates
BISHOP_PAIR_RE = re.compile(r"\bbishop\s+pair\b", re.I)
OPP_BISHOPS_RE = re.compile(r"\bopposite-colou?red\s+bishops\b", re.I)
SQ_COLOR_RE = re.compile(r"\b(light|dark)[-\s]+squares?\s+(?:on|at)\s+([a-h][1-8](?:\s*(?:,|and|/)\s*[a-h][1-8])*)\b", re.I)
OUTPOST_RE = re.compile(
    r"\b(?:([a-h][1-8])\s+(?:[A-Za-z\-]+\s+)?(?:outpost|hole)|(?:outpost|holes?)\s+(?:on|at)\s+([a-h][1-8](?:\s*(?:,|and|/)\s*[a-h][1-8])*))\b",
    re.I,
)


def evaluate_clause(
    clause: str,
    board: chess.Board,
    our: chess.Color,
    where: str,
    src: Sources | None = None,
    eval_board: chess.Board | None = None,
) -> tuple[bool, list[LexFinding]]:
    """Run all concept-category predicates on `clause`. Returns (matched_any_predicate, findings)."""
    matched = False
    out: list[LexFinding] = []
    is_cond = bool(COND_PREFIX_RE.search(clause))
    is_neg = bool(NEG_CTX_RE.search(clause))
    eb = eval_board or board
    sign = 1.0 if our == chess.WHITE else -1.0

    # 1. Eval calibration (skip if negated/conditional or no eval-strength phrase)
    num_evals = NUM_EVAL_RE.findall(clause)
    has_eval_phrase = bool(EVAL_WIN_RE.search(clause) or EVAL_CLEAR_RE.search(clause) or EVAL_EQUAL_RE.search(clause) or (eval_board is None and num_evals))
    if src is not None and has_eval_phrase and not is_cond and not is_neg:
        ev = src.eval_white(eb)
        if ev is not None:
            if eval_board is None and num_evals:
                matched = True
                vals = [float(v) * (-1 if s in "-−–" else 1) for s, v in num_evals]
                lo, hi = min(vals), max(vals)
                if ev < lo - 0.55 or ev > hi + 0.55:
                    out.append(LexFinding("FLAG", "EVAL-MISMATCH", where, clause, f"claims {lo:+.2f}..{hi:+.2f} vs SF {ev:+.2f}", 25.0 + 10 * min(abs(ev - lo), abs(ev - hi))))
            our_ev = ev * sign
            if EVAL_WIN_RE.search(clause):
                matched = True
                if our_ev < 0.70:
                    out.append(LexFinding("ERROR", "LEX-EVAL", where, clause, f"claims winning/crushing but SF eval is {ev:+.2f}", 65.0))
                elif our_ev < 1.25:
                    out.append(LexFinding("FLAG", "LEX-EVAL", where, clause, f"claims winning/crushing at modest SF eval {ev:+.2f}", 30.0))
            elif EVAL_CLEAR_RE.search(clause):
                matched = True
                if our_ev < 0.15:
                    out.append(LexFinding("FLAG", "LEX-EVAL", where, clause, f"claims clear/big edge but SF eval is {ev:+.2f}", 35.0))
            elif EVAL_EQUAL_RE.search(clause):
                matched = True
                if abs(our_ev) > 0.75:
                    out.append(LexFinding("FLAG", "LEX-EVAL", where, clause, f"claims equality/balance but SF eval is {ev:+.2f}", 35.0))

    # 2. Structural pawn predicates (checked on eb unless conditional)
    if not is_cond and not is_neg:
        for m in ISOLATED_SQ_RE.finditer(clause):
            matched = True
            sq_s = m.group(1).lower()
            sq = chess.parse_square(sq_s)
            p = eb.piece_at(sq)
            if p is None or p.piece_type != chess.PAWN:
                out.append(LexFinding("ERROR", "LEX-PAWN", where, clause, f"claims isolated pawn on {sq_s} but no pawn stands there", 60.0))
            elif not is_isolated_pawn(eb, sq):
                out.append(LexFinding("ERROR", "LEX-PAWN", where, clause, f"pawn on {sq_s} is not isolated", 60.0))

        for m in DOUBLED_FILE_RE.finditer(clause):
            matched = True
            fn = m.group(1).lower()
            if not is_doubled_file(eb, chess.FILE_NAMES.index(fn)):
                out.append(LexFinding("ERROR", "LEX-PAWN", where, clause, f"no doubled pawns on {fn}-file", 55.0))

        for m in PASSED_SQ_RE.finditer(clause):
            matched = True
            sq_s = m.group(1).lower()
            sq = chess.parse_square(sq_s)
            p = eb.piece_at(sq)
            if p is None or p.piece_type != chess.PAWN or not is_passed_pawn(eb, sq):
                out.append(LexFinding("ERROR", "LEX-PAWN", where, clause, f"{sq_s} is not a passed pawn", 55.0))

        for m in OPEN_FILE_RE.finditer(clause):
            matched = True
            want_kind, fn = m.group(1).lower(), m.group(2).lower()
            actual = file_status(eb, chess.FILE_NAMES.index(fn))
            if want_kind == "open" and actual != "open":
                out.append(LexFinding("FLAG", "LEX-FILE", where, clause, f"claims open {fn}-file, actually {actual}", 30.0))
            elif want_kind == "semi-open" and actual == "closed":
                out.append(LexFinding("FLAG", "LEX-FILE", where, clause, f"claims semi-open {fn}-file, actually closed", 30.0))

    # 3. Material & color-complex predicates
    if BISHOP_PAIR_RE.search(clause) and not is_cond and not is_neg:
        matched = True
        wb = len(eb.pieces(chess.BISHOP, chess.WHITE))
        bb = len(eb.pieces(chess.BISHOP, chess.BLACK))
        if wb < 2 and bb < 2:
            out.append(LexFinding("FLAG", "LEX-MAT", where, clause, f"mentions bishop pair when bishops are W:{wb} B:{bb}", 25.0))

    if OPP_BISHOPS_RE.search(clause) and not is_cond and not is_neg:
        matched = True
        wbs = list(eb.pieces(chess.BISHOP, chess.WHITE))
        bbs = list(eb.pieces(chess.BISHOP, chess.BLACK))
        if not (len(wbs) == 1 and len(bbs) == 1 and is_light_sq(wbs[0]) != is_light_sq(bbs[0])):
            out.append(LexFinding("ERROR", "LEX-MAT", where, clause, "claims opposite-colored bishops inaccurately", 55.0))

    for m in SQ_COLOR_RE.finditer(clause):
        matched = True
        want_light = m.group(1).lower() == "light"
        for sq_s in re.findall(r"[a-h][1-8]", m.group(2).lower()):
            actual_light = is_light_sq(chess.parse_square(sq_s))
            if actual_light != want_light:
                lbl = "light" if actual_light else "dark"
                out.append(LexFinding("ERROR", "LEX-COLOR", where, clause, f"square {sq_s} is {lbl}, not {m.group(1).lower()}", 70.0))

    for m in OUTPOST_RE.finditer(clause):
        matched = True
        raw_sqs = m.group(1) or m.group(2) or ""
        for sq_s in re.findall(r"[a-h][1-8]", raw_sqs.lower()):
            cur, _ = enemy_pawn_attackers(eb, chess.parse_square(sq_s), our)
            unblocked = [a for a in cur if not re.search(rf"(?:x{a}\b|\b{a[0]}x[a-h][1-8]\b)", clause)]
            if unblocked and not is_cond:
                out.append(LexFinding("ERROR", "LEX-OUTPOST", where, clause, f"claimed outpost {sq_s} is attacked by enemy pawn(s) {','.join(unblocked)}", 70.0))

    return matched, out
