"""Python 3.15 native syntax, universal slots=True dataclasses, StrEnum, zstd and subinterpreter gate tests."""

import ast
import dataclasses
import importlib
import json
import pkgutil
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _helpers import SCRIPTS, TempDir, write_json  # noqa: E402

DEV_DIR = SCRIPTS / "dev"
if str(DEV_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_DIR))

import py315_audit  # noqa: E402
import orchestrator_stub as orch  # noqa: E402
from gcl.application.jury.policy import EscalationTally, status_for  # noqa: E402
from gcl.application.pipeline.config import JuryPipelineOptions, PipelineHooks, PipelineState  # noqa: E402
from gcl.application.pipeline.dedup import DedupEnv, JuryBatchPlan, Pass1BatchPlan  # noqa: E402
from gcl.application.rewrite.tournament import TournamentOptions  # noqa: E402
from gcl.domain.errors import L10nError  # noqa: E402
from gcl.domain.line_state import DraftedState, KeptOriginalState, SettledPassState  # noqa: E402
from gcl.domain.models import (  # noqa: E402
    ChatRequest, JurorVote, JuryTier, LineStatus, RawVendorReply, ServiceTier, ThinkingEffort, TokenUsage,
)
from gcl.domain.specifications import CleanLightPassSpec, MinScoreSpec  # noqa: E402
from gcl.infrastructure.persistence.memo_store import AtomicJsonMemoRepository  # noqa: E402
from gcl.ports.events import LLMCallObserved, StageCompleted  # noqa: E402


class SlottedDataclassTests(unittest.TestCase):
    """Every dataclass across gcl and scripts enforces __slots__ with zero instance __dict__."""

    def test_all_gcl_dataclasses_have_slots_and_no_instance_dict(self) -> None:
        checked = 0
        for _, mod_name, _ in pkgutil.walk_packages([str(SCRIPTS / "gcl")], "gcl."):
            mod = importlib.import_module(mod_name)
            for obj in vars(mod).values():
                if isinstance(obj, type) and dataclasses.is_dataclass(obj) and obj.__module__ == mod_name:
                    self.assertTrue(hasattr(obj, "__slots__"), f"{mod_name}.{obj.__name__} missing __slots__")
                    checked += 1
        self.assertGreaterEqual(checked, 35)

        hooks = PipelineHooks(
            load_source_rows=lambda *_a: [], preflight=lambda *_a: None, default_langpack_dir=lambda: Path("."),
            trust_level=lambda _p: ("rule_based", None), load_threshold=lambda *_a: (None, None),
            open_memo=lambda p: AtomicJsonMemoRepository(p), open_tm=lambda p: p, register_of=lambda _r: "ui",
            load_warmup_sample=lambda *_a: [], render_warmup=lambda _s: "", system_prompt=lambda *_a: "",
            load_context_views=lambda *_a: (None, None), build_critic_prompt=lambda *_a: ("", {}),
            build_pass2_systems=lambda *_a: ("", ""), prepare_blind_slice=lambda *_a: [],
            roundtrip_evidence=lambda *_a, **_k: {}, make_deliberator=lambda *_a: lambda *_x: None,
            run_jury=lambda *_a, **_k: {}, load_pass2_sources=lambda *_a: {}, run_pass2=lambda *_a, **_k: {},
            write_change_report=lambda *_a, **_k: {}, batch_budget=lambda *_a: None,
            translate_rows=lambda *_a, **_k: {}, phase3_gate=lambda *_a: {}, parity=object(),
        )
        instances = [
            TokenUsage(10, 5),
            RawVendorReply("ok", TokenUsage()),
            ChatRequest("sys", "usr"),
            JurorVote(5),
            DraftedState("K1", "Save", "Kaydet", "Kaydet", "draft"),
            SettledPassState("K1", "Save", "Kaydet", "Kaydet", "pass"),
            KeptOriginalState("K1", "Save", "Kaydet", "Kaydet", "rewrite", ("kept",)),
            LLMCallObserved("J1", "google", "flash", "gemini", 1, 2, 3, True),
            StageCompleted("jury", 1),
            JuryPipelineOptions(),
            hooks,
            PipelineState("tr-TR", Path("."), "en", "dst", "key", "auto", "auto"),
            TournamentOptions("P2", "CR"),
            MinScoreSpec(4),
            MinScoreSpec(4) & CleanLightPassSpec(),
            EscalationTally(),
            Pass1BatchPlan(),
            JuryBatchPlan({}, [], {}),
            DedupEnv("tr-TR", lambda _r: "ui", None, None, object(), JuryPipelineOptions()),
        ]
        for obj in instances:
            self.assertFalse(hasattr(obj, "__dict__"), f"{type(obj).__name__} unexpectedly created __dict__")


class Py315AuditBanTests(unittest.TestCase):
    """py315_audit flags legacy idioms while allowing PEP 649/695 and Literal[...]."""

    def test_rejects_legacy_idioms_and_accepts_modern_syntax(self) -> None:
        bad_snippets = [
            ("future", "from __future__ import annotations\nx: int = 1\n", False),
            ("legacy_typing", "from typing import Optional, Dict, TypeVar\nT = TypeVar('T')\n", False),
            ("bare_dc", "from dataclasses import dataclass\n@dataclass\nclass Box:\n    x: int\n", False),
            ("frozen_no_slots", "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass Box:\n    x: int\n", False),
            ("os_walk", "import os\ndef walk_all(p):\n    return list(os.walk(p))\n", False),
            ("quoted_ann", 'def f(x: "Box") -> list["Box"]:\n    return []\n', False),
            ("old_doc", '"""Legacy header.\n\nPython 3.9+, standard library only.\n"""\nx = 1\n', False),
        ]
        for label, code, is_test in bad_snippets:
            tree = ast.parse(code)
            errs = py315_audit.check_modern_python(tree, code, f"{label}.py", is_test=is_test)
            self.assertTrue(errs, f"expected violation for {label}")

        test_doc = '"""Test file allowing Python 3.9+ text in doc."""\nx: int | None = None\n'
        self.assertEqual(py315_audit.check_modern_python(ast.parse(test_doc), test_doc, "t.py", is_test=True), [])

        good = (
            "from dataclasses import dataclass\n"
            "from typing import Literal\n\n"
            "type Choice = Literal['pass', 'rewrite']\n\n"
            "@dataclass(frozen=True, slots=True)\n"
            "class Entry[T]:\n"
            "    value: T | None\n"
            "    mode: Literal['pass', 'rewrite'] = 'pass'\n"
        )
        self.assertEqual(py315_audit.check_modern_python(ast.parse(good), good, "good.py", is_test=False), [])


class Py315StdlibFeaturesTests(unittest.TestCase):
    """StrEnum values, native compression.zstd memo store and InterpreterPoolExecutor Phase 3 gate."""

    def test_domain_strenums_and_status_for(self) -> None:
        self.assertEqual(JuryTier.J1, "J1")
        self.assertEqual(ThinkingEffort.HIGH, "high")
        self.assertEqual(ServiceTier.FLEX, "flex")
        self.assertEqual(status_for(5), LineStatus.PASS)
        self.assertEqual(status_for(4), LineStatus.REWRITE_LIGHT)
        self.assertEqual(status_for(3), LineStatus.REWRITE)
        self.assertEqual(status_for(1), LineStatus.CRITICAL)
        payload = json.loads(json.dumps({"status": LineStatus.REWRITE_LIGHT, "tier": JuryTier.J2}))
        self.assertEqual(payload, {"status": "rewrite_light", "tier": "J2"})

    def test_atomic_memo_zstd_roundtrip_and_corrupt_error(self) -> None:
        with TempDir() as td:
            zpath = td / "items.json.zst"
            repo = AtomicJsonMemoRepository(zpath)
            repo.put("k1", {"target": "Merhaba Türkçe"})
            repo.put_many({"k2": "Çıkış", "k3": [1, 2, 3]})
            self.assertTrue(zpath.is_file())
            self.assertEqual(zpath.read_bytes()[:4], b"\x28\xb5\x2f\xfd")

            reopened = AtomicJsonMemoRepository(zpath)
            self.assertEqual(len(reopened), 3)
            self.assertEqual(reopened.get("k1"), {"target": "Merhaba Türkçe"})
            self.assertEqual(reopened.get("k2"), "Çıkış")
            self.assertEqual(reopened.hits, 2)

            bad_zst = td / "corrupt.json.zst"
            bad_zst.write_bytes(b"not-valid-zstd-payload")
            with self.assertRaises(L10nError):
                AtomicJsonMemoRepository(bad_zst)

    def test_phase3_gate_multi_batch_subinterpreters(self) -> None:
        with TempDir() as td:
            f1 = write_json(td / "final_batch_01.json", [{"key": "UI_1", "en": "Save game", "tr-TR": "Oyunu kaydet"}])
            f2 = write_json(td / "final_batch_02.json", [{"key": "UI_2", "en": "Load {0}", "tr-TR": "Yükle"}])
            f3 = write_json(td / "final_batch_03.json", [{"key": "UI_3", "en": "Exit menu", "tr-TR": "Menüden çık"}])
            state = PipelineState("tr-TR", td, "en", "dst", "key", "auto", "auto")
            summary = orch.phase3_gate(state, [f1, f2, f3], [])
            self.assertEqual(summary["errors"], 1)
            self.assertFalse(summary["passed"])
            for idx in ("01", "02", "03"):
                self.assertTrue((td / f"lqa_tr-TR_{idx}.json").is_file())
