"""Ranked findings summary, persistent dismissal ledger, and residual.md emitter.

- Ranked summary: errors first, then flags sorted by descending severity score (cp loss / risk).
- Dismissal ledger (`cache/<ch>_flag_ledger.json`): suppresses dismissed flags only while the
  normalized (where, clause, code) hash is unchanged; editing the prose automatically re-opens them.
- Residual emitter (`cache/<ch>_residual.md`): writes ONLY clauses that neither resolved via
  move provenance nor matched a deterministic lexicon predicate, paired with a 1-line board summary.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import chess


def flag_key(code: str, where: str, clause: str) -> str:
    norm_where = " ".join(where.split())
    norm_clause = " ".join(clause.split())
    raw = f"{code}|{norm_where}|{norm_clause}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


class FlagLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict[str, str]] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.entries = {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
            except (ValueError, OSError):
                pass

    def is_dismissed(self, code: str, where: str, clause: str) -> bool:
        k = flag_key(code, where, clause)
        entry = self.entries.get(k)
        return bool(entry and entry.get("status") == "dismissed")

    def dismiss(self, code: str, where: str, clause: str, reason: str) -> str:
        k = flag_key(code, where, clause)
        self.entries[k] = {"status": "dismissed", "code": code, "where": where, "clause": clause[:120], "reason": reason}
        self.save()
        return k

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8")


def compact_board_line(fen: str, sf_eval: str = "?") -> str:
    b = chess.Board(fen) if fen else chess.Board()
    wp = ",".join(chess.square_name(s) for s in sorted(b.pieces(chess.PAWN, chess.WHITE)))
    bp = ",".join(chess.square_name(s) for s in sorted(b.pieces(chess.PAWN, chess.BLACK)))
    return f"Pawns W:[{wp}] B:[{bp}] | SF {sf_eval}"


import re

BOILERPLATE_RE = re.compile(
    r"^(?:our\s+plan|watch\s+out|key\s+trades\s*(?:&|and)\s*endgame|click\b.*|welcome\s+to\s+chapter.*|"
    r"mark\s+this\s+entry.*|(?:notice|check|watch|see)\s+.*(?:below|here|alternatives?|tries|deviations?))$",
    re.I,
)


def write_residual(
    out_path: Path,
    records: Iterable[object],
    sf_eval_fn=None,
) -> int:
    """Emit residual.md containing only clauses not verified by provenance or lexicon."""
    lines = [
        "# Residual Unverified Prose Claims (Verifier Input)",
        "",
        "Only sentences with no deterministically verified move or lexicon predicate appear below.",
        "",
    ]
    count = 0
    for rec in records:
        if getattr(rec, "status", "") != "residual":
            continue
        cl = getattr(rec, "clause", "").strip()
        if len(cl.split()) <= 2 or BOILERPLATE_RE.match(cl):
            continue
        count += 1
        fen = getattr(rec, "fen", "")
        ev_s = sf_eval_fn(fen) if (sf_eval_fn and fen) else "?"
        lines.append(f"- `{getattr(rec, 'where', '')}` | {compact_board_line(fen, ev_s)} | \"{cl}\"")
    if count == 0:
        lines.append("*(0 residual claims — every sentence was deterministically verified.)*")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def format_summary(findings: list[object], max_lines: int = 25, top_flags: int = 10) -> str:
    errs = [f for f in findings if getattr(f, "severity", "") == "ERROR"]
    flags = [f for f in findings if getattr(f, "severity", "") != "ERROR"]
    errs.sort(key=lambda f: -float(getattr(f, "score", 0.0)))
    flags.sort(key=lambda f: -float(getattr(f, "score", 0.0)))

    counts: dict[str, int] = {}
    for f in flags:
        c = str(getattr(f, "code", "FLAG"))
        counts[c] = counts.get(c, 0) + 1

    out: list[str] = [f"SUMMARY: {len(errs)} error(s), {len(flags)} flag(s)"]
    for e in errs[: max(0, max_lines - 4)]:
        out.append(f"  ERROR {e.line()}")  # type: ignore[attr-defined]
    if len(errs) > max(0, max_lines - 4):
        out.append(f"  ... +{len(errs) - max(0, max_lines - 4)} more errors")
    rem = max(0, max_lines - len(out) - 2)
    show_n = min(top_flags, rem)
    if flags and show_n > 0:
        out.append("TOP FLAGS (ranked):")
        for fl in flags[:show_n]:
            out.append(f"  FLAG  {fl.line()}")  # type: ignore[attr-defined]
    if counts:
        out.append("FLAG COUNTS: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return "\n".join(out)
