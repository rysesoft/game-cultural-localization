"""v3.4.0 full core extraction, domain aggregates, repository, transport/task aspects and facade cap tests."""

import json
import sys
import unittest
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _helpers import FIXTURES, SCRIPTS, TempDir  # noqa: E402

import build_context_map as bcm  # noqa: E402
import dev.verify_architecture as va  # noqa: E402
import l10n_common as lc  # noqa: E402
from gcl.application.context import ContextPack  # noqa: E402
from gcl.aspects import (  # noqa: E402
    AspectChain, BatchCoalesceAspect, ItemMemoTaskAspect, RateLimitAspect, RetryBackoffAspect,
)
from gcl.composition.container import ServiceContainer  # noqa: E402
from gcl.domain import BlindEntry, CandidateSet, LineVerdict  # noqa: E402
from gcl.domain.errors import L10nError, PermanentProviderError, ProviderError  # noqa: E402
from gcl.domain.models import ChatRequest, ChatResult  # noqa: E402
from gcl.infrastructure.persistence import BatchMemo, JsonVerdictRepository  # noqa: E402


class DomainVerdictModelsTests(unittest.TestCase):
    """Frozen slots=True BlindEntry, CandidateSet and LineVerdict round trips."""

    def test_blind_entry_candidate_set_and_line_verdict_roundtrip(self) -> None:
        entry = BlindEntry.from_dict({"key": "Hud.Save", "target": "Kaydet", "register": "ui", "extra": "ignored"})
        self.assertEqual(entry.to_dict(), {"key": "Hud.Save", "target": "Kaydet", "register": "ui"})
        with self.assertRaises(AttributeError):
            entry.target = "Mutated"  # type: ignore[misc]

        cset = CandidateSet(key="Hud.Save", candidates=("Kaydet", "Sakla"), current_target="Sakla", chosen_index=0, votes_per_candidate=(3, 0))
        self.assertEqual(cset.selected_target, "Kaydet")
        fallback = CandidateSet(key="Hud.Save", candidates=("A",), current_target="Orig", chosen_index=9)
        self.assertEqual(fallback.selected_target, "Orig")

        verdict = LineVerdict.from_dict({
            "key": "Hud.Save", "final_tier": "J1", "score": 4, "status": "rewrite_light",
            "votes": [{"score": 4, "issue_type": "ui_verb", "reason": "Keep verb short"}],
            "rationales": ["Short UI button"], "evidence": {"ban_hits": []},
        })
        self.assertEqual(verdict.score, 4)
        self.assertEqual(verdict.votes[0].issue_type, "ui_verb")
        self.assertEqual(verdict.to_dict()["status"], "rewrite_light")


class VerdictRepositoryTests(unittest.TestCase):
    """Atomic JSON persistence and hydration through JsonVerdictRepository."""

    def test_save_and_load_batch_roundtrip(self) -> None:
        repo = ServiceContainer().verdict_repo
        self.assertIsInstance(repo, JsonVerdictRepository)
        with TempDir() as td:
            path = td / "verdicts.json"
            doc = {"verdicts": [{"key": "K1", "final_tier": "J1", "score": 5, "status": "pass", "votes": [{"score": 5}]}]}
            repo.save_batch(path, doc)
            loaded_doc, models = repo.load_batch(path)
            self.assertEqual(loaded_doc["verdicts"][0]["key"], "K1")
            self.assertEqual(len(models), 1)
            self.assertEqual(models[0].key, "K1")
            bad = td / "bad.json"
            bad.write_text('{"verdicts": "nope"}', encoding="utf-8")
            with self.assertRaises(L10nError):
                repo.load_batch(bad)


class TransportAndTaskAspectsTests(unittest.TestCase):
    """RateLimit, RetryBackoff, BatchCoalesce and ItemMemoTaskAspect behavior."""

    def test_transport_aspects_chain_and_fail_fast(self) -> None:
        waits: list[int] = []
        sleeps: list[float] = []
        attempts = {"n": 0}
        batch_hits: list[str] = []

        def core(req: ChatRequest) -> ChatResult:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ProviderError("transient 503")
            return ChatResult(req.user, 10, 5, "m", 1)

        def batch_fn(req: ChatRequest) -> ChatResult:
            batch_hits.append(req.user)
            return ChatResult("batched:" + req.user, 5, 2, "m", 1)

        chain = AspectChain(core, [
            RateLimitAspect(lambda: waits.append(1)),
            RetryBackoffAspect(max_attempts=3, delay_fn=lambda i, _e: 0.25 * (i + 1), sleep_fn=sleeps.append),
            BatchCoalesceAspect(batch_fn, enabled_fn=lambda: False),
        ])
        res = chain.invoke(ChatRequest(system="s", user="u1"))
        self.assertEqual(res.text, "u1")
        self.assertEqual((len(waits), sleeps, attempts["n"]), (1, [0.25], 2))

        batch_chain = AspectChain(core, [BatchCoalesceAspect(batch_fn, enabled_fn=lambda: True)])
        self.assertEqual(batch_chain.invoke(ChatRequest(system="s", user="b1")).text, "batched:b1")
        self.assertEqual(batch_chain.invoke(ChatRequest(system="s", user="u2", options={"bypass_batch": True})).text, "u2")
        self.assertEqual(batch_hits, ["b1"])

        def perm(_req: ChatRequest) -> ChatResult:
            attempts["n"] += 1
            raise PermanentProviderError("HTTP 401 unauthorized")

        perm_chain = AspectChain(perm, [RetryBackoffAspect(max_attempts=4, delay_fn=lambda _i, _e: 1.0, sleep_fn=sleeps.append)])
        with self.assertRaises(PermanentProviderError):
            perm_chain.invoke(ChatRequest(system="s", user="x"))
        self.assertEqual(len(sleeps), 1)

    def test_item_memo_task_aspect_partition_and_store(self) -> None:
        with TempDir() as td:
            memo = BatchMemo(td / "memo.json")
            aspect = ItemMemoTaskAspect(memo)
            items = [{"key": "A", "target": "Bir"}, {"key": "B", "target": "Iki"}]
            cached, pending, kmap = aspect.partition("jury", items)
            self.assertEqual((cached, len(pending), sorted(kmap)), ({}, 2, ["A", "B"]))
            aspect.store(kmap, {"A": {"score": 5}, "B": {"score": 4}})
            cached2, pending2, kmap2 = aspect.partition("jury", items)
            self.assertEqual(pending2, [])
            self.assertEqual(kmap2, {})
            self.assertEqual(cached2["B"]["score"], 4)


class FontContextAndFacadeCapTests(unittest.TestCase):
    """In process FontScannerPort, ContextPack isolation, version lockstep and 260 line facade cap."""

    def test_in_process_font_scanner_and_context_pack(self) -> None:
        container = ServiceContainer()
        rep = container.font_scanner.scan(FIXTURES / "glyphs.json", "dst", None, [FIXTURES / "Bebas SDF.asset"])
        self.assertEqual(rep["exit_code"], 1)
        self.assertGreater(rep["summary"]["missing"], 0)

        pack = ContextPack(
            text="# Game Map",
            notes={"K1": {"screen": "HUD", "notes": "Studio chose X"}},
            appendix="Studio appendix",
            locale="tr-TR",
        )
        self.assertNotIn("notes", pack.line("K1", writer=False))
        self.assertIn("notes", pack.line("K1", writer=True))
        self.assertTrue(bcm.ContextPack is ContextPack)

    def test_facade_line_cap_and_v34_lockstep(self) -> None:
        self.assertEqual(va.MAX_FACADE_LINES, 260)
        plugin = json.loads((lc.SCRIPTS_DIR.parents[2] / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], "3.4.0")
        self.assertEqual(lc.__version__, "3.4.0")
        for path in sorted(SCRIPTS.glob("*.py")):
            if path.name.endswith(".workflow.py"):
                continue
            lines = len(path.read_text(encoding="utf-8-sig").splitlines())
            self.assertLessEqual(lines, 260, f"{path.name} has {lines} lines > 260")
