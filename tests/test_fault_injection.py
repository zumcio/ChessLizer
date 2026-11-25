"""Fault-injection and false-positive benchmark for provenance & validation.

Measures detection rate across programmatically generated random faults of each class
(never tuned to historical incidents) and false-positive rate across multi-opening chapters.

Run:
    python tests/test_fault_injection.py
"""

from __future__ import annotations

import io
import json
import random
import sqlite3
import sys
import unittest
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from chess_env import CACHE_DB, StockfishAnalyzer  # noqa: E402
from provenance import Sources, load_config, run as run_prov  # noqa: E402


# Minimal clean baseline games across two different opening families (White & Black)
CLEAN_PGN_WHITE = """[Event "Test Chapter"]
[Site "Chessable"]
[Date "2026.11.25"]
[Round "1"]
[White "Intro: Central Setup"]
[Black ""]
[Result "*"]

{ Informational intro: 1. d4 d5 2. c4 dxc4 3. e4 e5 4. Nf3 exd4 5. Bxc4 claims central space. } 1. d4 d5 2. c4 dxc4 3. e4 e5 4. Nf3 exd4 5. Bxc4 Nc6 6. O-O { By move 6 we recover the pawn cleanly. } *

[Event "Test Chapter"]
[Site "Chessable"]
[Date "2026.11.25"]
[Round "2"]
[White "1.1 Mainline 6...Be6"]
[Black ""]
[Result "*"]

{ Mainline against 6... Be6. } 1. d4 d5 2. c4 dxc4 3. e4 e5 4. Nf3 exd4 5. Bxc4 Nc6 6. O-O Be6 7. Bxe6 fxe6 8. Qb3 { 8. Qb3 forks e6 and b7. } ( 8. Qb3 Qd7 9. Qxb7 Rb8 10. Qa6 { Natural continuation. } ) *
"""

CLEAN_PGN_BLACK = """[Event "Test Black Chapter"]
[Site "Chessable"]
[Date "2026.11.25"]
[Round "1"]
[White "1.1 Semi-Slav 5.e3 Nbd7"]
[Black ""]
[Result "*"]

{ Solid setup. } 1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Nc3 e6 5. e3 Nbd7 6. Bd3 dxc4 7. Bxc4 b5 8. Bd3 a6 { 8... a6 prepares ...c5. } ( 8... a6 9. e4 c5 10. d5 { Natural center clash. } ) *
"""


def _random_bad_move(sf: StockfishAnalyzer, board: chess.Board, rng: random.Random, min_loss: int = 120) -> tuple[str, int] | None:
    """Dynamically pick a random legal move on `board` that Stockfish rates at >= min_loss cp worse than best."""
    lines = sf.analyze(board, depth=10, multipv=1)
    if not lines or lines[0].score_cp is None:
        return None
    best_cp = lines[0].score_cp
    sign = 1 if board.turn == chess.WHITE else -1
    legal = [mv for mv in board.legal_moves if mv.uci() != lines[0].move_uci]
    rng.shuffle(legal)
    for mv in legal[:8]:
        iso = sf.analyze(board, depth=10, multipv=1, root_moves=[mv])
        if iso and iso[0].score_cp is not None:
            loss = (best_cp - iso[0].score_cp) * sign
            if loss >= min_loss:
                return board.san(mv), loss
    return None


def _random_non_pv_move(sf: StockfishAnalyzer, board: chess.Board, rng: random.Random) -> str | None:
    """Pick a legal move that is neither in SF top-3 nor in the game, or a pseudo-plausible move from another square."""
    tops = {ln.move_uci for ln in sf.analyze(board, depth=10, multipv=3)}
    cands = [board.san(mv) for mv in board.legal_moves if mv.uci() not in tops]
    if not cands:
        return None
    return rng.choice(cands)


class FaultInjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = load_config()
        cls.cfg["depth"] = 12
        cls.rng = random.Random(20261125)
        cls.sf = StockfishAnalyzer()
        cls.sf.open()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.sf.close()

    def test_clean_baselines_zero_errors(self) -> None:
        for side, pgn in (("white", CLEAN_PGN_WHITE), ("black", CLEAN_PGN_BLACK)):
            findings, _ = run_prov(Path("mem.pgn"), side, cfg=self.cfg, pgn_text=pgn)
            errs = [f for f in findings if f.severity == "ERROR"]
            self.assertEqual(errs, [], f"Clean {side} baseline produced errors: {[e.line() for e in errs]}")

    def test_fault_class_unsound_our_moves(self) -> None:
        """Inject N random legal blunders into White & Black comments and verify >= 90% caught."""
        pgns = [("white", CLEAN_PGN_WHITE), ("black", CLEAN_PGN_BLACK)]
        injected = 0
        caught = 0
        for side, pgn_txt in pgns:
            fh = io.StringIO(pgn_txt)
            games = []
            while (g := chess.pgn.read_game(fh)) is not None:
                games.append(g)
            # Sample nodes where it's our turn
            our = chess.WHITE if side == "white" else chess.BLACK
            for g in games:
                b = g.board()
                for mv in g.mainline_moves():
                    if b.turn == our and b.ply() >= 4:
                        bad = _random_bad_move(self.sf, b, self.rng, min_loss=120)
                        if bad:
                            bad_san, _loss = bad
                            mnum = b.fullmove_number
                            pfx = f"{mnum}." if b.turn == chess.WHITE else f"{mnum}..."
                            # Inject blunder as recommended plan at the node before it
                            mut = pgn_txt.replace(
                                "{ Mainline against 6... Be6. }",
                                f"{{ Play {pfx} {bad_san} here! }}",
                            ).replace(
                                "{ Solid setup. }",
                                f"{{ Play {pfx} {bad_san} here! }}",
                            )
                            if mut == pgn_txt:
                                mut = pgn_txt + ""
                            else:
                                injected += 1
                                fnds, _ = run_prov(Path("mem.pgn"), side, cfg=self.cfg, pgn_text=mut)
                                if any(f.severity == "ERROR" and f.code in ("UNSOUND", "UNBACKED") for f in fnds):
                                    caught += 1
                                if injected >= 4:
                                    break
                    b.push(mv)
        self.assertGreaterEqual(injected, 2)
        self.assertEqual(caught, injected, f"Caught {caught}/{injected} injected blunders")

    def test_fault_class_unbacked_hallucinated_moves(self) -> None:
        """Inject random impossible/unplayed SANs across 6 trials -> 100% caught as UNBACKED."""
        impossible = ["Qh5", "Ra7", "Ba8", "Nf8", "Ke3", "g8=Q"]
        caught = 0
        for tok in impossible:
            mut = CLEAN_PGN_WHITE.replace(
                "8. Qb3 forks e6 and b7.",
                f"8. Qb3 forks e6 and b7, preparing {tok}.",
            )
            fnds, _ = run_prov(Path("mem.pgn"), "white", cfg=self.cfg, pgn_text=mut)
            if any(f.code in ("UNBACKED", "UNSOUND", "UNSTATED-ASSUMPTION", "IMPLAUSIBLE-OPP") for f in fnds):
                caught += 1
        self.assertEqual(caught, len(impossible))

    def test_fault_class_unstated_assumption(self) -> None:
        """If a plan needs an unexpected opponent move (suboptimal, not mentioned in prose), flag UNSTATED-ASSUMPTION."""
        # At 8. Qb3, 9. Qxb4 ONLY exists if Black played unmentioned suboptimal 8... Nb4
        mut = CLEAN_PGN_WHITE.replace(
            "8. Qb3 forks e6 and b7.",
            "8. Qb3 forks e6 and b7; follow with 9. Qxb4.",
        )
        mut = mut.replace(
            "( 8. Qb3 Qd7 9. Qxb7 Rb8 10. Qa6 { Natural continuation. } )",
            "( 8. Qb3 Qd7 9. Qxb7 Rb8 10. Qa6 { Natural continuation. } ) ( 8. Qb3 Nb4 9. Qxb4 { Side blunder. } )",
        )
        fnds, _ = run_prov(Path("mem.pgn"), "white", cfg=self.cfg, pgn_text=mut)
        self.assertTrue(
            any(f.code in ("UNSTATED-ASSUMPTION", "UNBACKED") for f in fnds),
            f"Expected UNSTATED-ASSUMPTION or UNBACKED, got: {[f.line() for f in fnds]}",
        )

    def test_fault_class_implausible_opponent(self) -> None:
        """Plan relying on a dynamically chosen bad opponent move (>=120cp) framed neutrally must raise IMPLAUSIBLE-OPP."""
        b = chess.Board()
        for mv_s in "d4 d5 c4 dxc4 e4 e5 Nf3 exd4 Bxc4 Nc6 O-O Be6 Bxe6 fxe6 Qb3".split():
            b.push_san(mv_s)
        bad = _random_bad_move(self.sf, b, self.rng, min_loss=120)
        self.assertIsNotNone(bad)
        bad_san, _ = bad  # type: ignore[misc]
        mut = CLEAN_PGN_WHITE.replace(
            "8. Qb3 forks e6 and b7.",
            f"8. Qb3 prepares meeting 8... {bad_san} cleanly.",
        )
        fnds, _ = run_prov(Path("mem.pgn"), "white", cfg=self.cfg, pgn_text=mut)
        self.assertTrue(
            any(f.code == "IMPLAUSIBLE-OPP" for f in fnds),
            f"Expected IMPLAUSIBLE-OPP for {bad_san}, got: {[f.line() for f in fnds]}",
        )

    def test_fault_class_intro_and_model_errors(self) -> None:
        """Intro blunders and Model Game result/move contradictions must be caught."""
        intro_bad = CLEAN_PGN_WHITE.replace(
            "5. Bxc4 claims central space.",
            "5. Qxd4 allows equality, or try 5. Ba6 winning.",
        )
        f1, _ = run_prov(Path("mem.pgn"), "white", cfg=self.cfg, pgn_text=intro_bad)
        self.assertTrue(any(f.severity == "ERROR" and "[intro]" in f.where for f in f1), f"Got: {[f.line() for f in f1]}")

        model_pgn = CLEAN_PGN_WHITE + """
[Event "Model Test"]
[Site "Test"]
[Date "2024.01.01"]
[Round "3"]
[White "Model Game: Alpha vs Beta"]
[Black ""]
[Result "1/2-1/2"]

{ Alpha wins easily after 1. d4 d5. } 1. d4 d5 2. c4 e6 1/2-1/2
"""
        f2, _ = run_prov(Path("mem.pgn"), "white", cfg=self.cfg, pgn_text=model_pgn)
        self.assertTrue(any(f.code == "MODEL-RESULT" for f in f2))

    def test_fault_class_eval_mismatch(self) -> None:
        """Large eval distortion on a resolved clause must raise EVAL-MISMATCH."""
        mut = CLEAN_PGN_WHITE.replace(
            "8. Qb3 forks e6 and b7.",
            "8. Qb3 Qd7 9. Qxb7 Rb8 10. Qa6 gives +3.50 winning advantage.",
        )
        fnds, _ = run_prov(Path("mem.pgn"), "white", cfg=self.cfg, pgn_text=mut)
        self.assertTrue(any(f.code == "EVAL-MISMATCH" for f in fnds), f"Got: {[f.line() for f in fnds]}")

    def test_fault_class_gm_citations_from_cache(self) -> None:
        """Pick random cached GM games and verify wrong-move attributions raise GM-CITATION."""
        if not CACHE_DB.is_file():
            self.skipTest("No explorer_cache.db present")
        with sqlite3.connect(CACHE_DB) as conn:
            rows = conn.execute("SELECT payload FROM api_cache WHERE cache_key LIKE 'master_pgn|%' LIMIT 6").fetchall()
        if len(rows) < 2:
            self.skipTest("Need >= 2 cached GM games")
        tested = 0
        caught = 0
        for (payload,) in rows:
            raw = str(json.loads(payload).get("pgn", ""))
            g = chess.pgn.read_game(io.StringIO(raw))
            if not g:
                continue
            w = g.headers.get("White", "").split(",")[0].strip().split()[-1]
            b = g.headers.get("Black", "").split(",")[0].strip().split()[-1]
            if not (w.isalpha() and b.isalpha() and len(w) >= 3 and len(b) >= 3):
                continue
            # Inject an impossible/unplayed move attributed to that GM pair
            fake_mv = "Kh3" if "Kh3" not in raw else "Ra8"
            mut = CLEAN_PGN_WHITE.replace(
                "8. Qb3 forks e6 and b7.",
                f"As in {w} vs {b}, {fake_mv} solves everything.",
            )
            fnds, _ = run_prov(Path("mem.pgn"), "white", cfg=self.cfg, pgn_text=mut, use_engine=False)
            tested += 1
            if any(f.code == "GM-CITATION" for f in fnds):
                caught += 1
        self.assertGreaterEqual(tested, 2)
        self.assertEqual(caught, tested)

    def test_lexicon_ledger_residual_and_arrows(self) -> None:
        """Verify claim_lexicon predicates, ledger suppression/re-open, residual emission, and arrow provenance."""
        import tempfile
        from flag_ledger import FlagLedger

        mut = CLEAN_PGN_WHITE.replace(
            "8. Qb3 forks e6 and b7.",
            "8. Qb3 forks e6 and b7. Winning advantage. Isolated d4-pawn. Light square on d4. Outpost on f5. Pure strategic harmony.",
        ).replace(
            "( 8. Qb3",
            "{ [%cal Bb3h5] } ( 8. Qb3",
        )
        with tempfile.TemporaryDirectory() as td:
            res_p = Path(td) / "residual.md"
            led_p = Path(td) / "ledger.json"
            fnds, _recs = run_prov(
                Path("mem.pgn"),
                "white",
                cfg=self.cfg,
                pgn_text=mut,
                emit_residual=res_p,
                check_arrows=True,
            )
            codes = {f.code for f in fnds}
            self.assertIn("LEX-EVAL", codes)
            self.assertIn("LEX-PAWN", codes)
            self.assertIn("LEX-COLOR", codes)
            self.assertIn("LEX-OUTPOST", codes)
            self.assertIn("ARROW-PROVENANCE", codes)
            res_txt = res_p.read_text(encoding="utf-8")
            self.assertIn("Pure strategic harmony", res_txt)
            self.assertNotIn("Winning advantage", res_txt)

            # Ledger suppresses dismissed flag while sentence unchanged, re-opens when sentence changes
            flags = [f for f in fnds if f.severity == "FLAG"]
            if flags:
                led = FlagLedger(led_p)
                led.dismiss(flags[0].code, flags[0].where, flags[0].clause, "intentional")
                fnds2, _ = run_prov(Path("mem.pgn"), "white", cfg=self.cfg, pgn_text=mut, ledger_path=led_p, check_arrows=True)
                self.assertFalse(any(f.code == flags[0].code and f.clause == flags[0].clause for f in fnds2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
