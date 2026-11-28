"""Architecture, SOLID, Clean Code, OOP and AOP contract verification tests."""

import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _helpers import SCRIPTS, TempDir, run_cli, write_json  # noqa: E402

DEV_DIR = SCRIPTS / "dev"
if str(DEV_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_DIR))


class ArchitectureFitnessTests(unittest.TestCase):
    """AST layer boundaries, zero cycles, blindness lock, OCP lock, size limits and nav sync."""

    def test_verify_architecture_passes_with_zero_violations(self) -> None:
        import verify_architecture
        self.assertEqual(verify_architecture.verify(check_nav=True), [])


class SpecificationPatternTests(unittest.TestCase):
    """Boolean algebra and domain policy evaluation on Specifications."""

    def test_boolean_composition_and_everyday_policy(self) -> None:
        from gcl.domain.models import JurorVote
        from gcl.domain.specifications import (
            CleanLightPassSpec, CriticalVoteSpec, MaxSpreadSpec, MinScoreSpec, RuleAppliesSpec, TierPassSpec,
            apply_everyday_policy,
        )

        strict = MinScoreSpec(4) & MaxSpreadSpec(1)
        self.assertTrue(strict.is_satisfied_by([5, 5, 4]))
        self.assertFalse(strict.is_satisfied_by([5, 4, 3]))
        self.assertTrue((~CriticalVoteSpec(2)).is_satisfied_by([5, 4, 3]))
        self.assertTrue((CriticalVoteSpec(2) | TierPassSpec()).is_satisfied_by([5, 5, 2]))

        clean_light = CleanLightPassSpec()
        self.assertTrue(clean_light.is_satisfied_by(([5, 5, 4], 0, 0)))
        self.assertFalse(clean_light.is_satisfied_by(([5, 5, 4], 1, 0)))

        rule_spec = RuleAppliesSpec("button", skip_contexts=("formal",))
        self.assertTrue(rule_spec.is_satisfied_by({"button", "ui"}))
        self.assertFalse(rule_spec.is_satisfied_by({"button", "formal"}))

        votes = [JurorVote(5, odd_words=("celestial",)), JurorVote(5, odd_words=("celestial",)), JurorVote(4)]
        updated, applied = apply_everyday_policy(votes, cap=3, min_jurors=2)
        self.assertTrue(applied)
        self.assertEqual([v.score for v in updated], [3, 3, 3])


class LineStateTests(unittest.TestCase):
    """Explicit immutable LineState transitions distinguishing real edits."""

    def test_state_transitions_and_is_actual_change(self) -> None:
        from gcl.domain.line_state import (
            DraftedState, FlaggedForRewriteState, KeptOriginalState, RewrittenState, SettledPassState, UnresolvedState,
        )

        draft = DraftedState("K1", "Hello", "Selam", "Selam", "draft")
        self.assertFalse(draft.is_actual_change)
        settled = draft.settle_pass()
        self.assertIsInstance(settled, SettledPassState)
        self.assertFalse(settled.is_actual_change)

        flagged = draft.flag_rewrite("rewrite")
        self.assertIsInstance(flagged, FlaggedForRewriteState)
        rewritten = flagged.accept_rewrite("Selam millet")
        self.assertIsInstance(rewritten, RewrittenState)
        self.assertTrue(rewritten.is_actual_change)

        kept = flagged.keep_original(("rejected",))
        self.assertIsInstance(kept, KeptOriginalState)
        self.assertFalse(kept.is_actual_change)

        unresolved = flagged.mark_unresolved(("split",))
        self.assertIsInstance(unresolved, UnresolvedState)
        self.assertEqual(unresolved.status, "unresolved")


class AopAspectsAndEventBusTests(unittest.TestCase):
    """AOP CallAspect, TaskAspect and EventBus telemetry contracts."""

    def test_secret_redaction_offline_guard_and_fallback_telemetry(self) -> None:
        from gcl.aspects.call_chain import (
            AspectChain, BudgetTelemetryAspect, FallbackModelAspect, OfflineGuardAspect, SecretRedactionAspect,
        )
        from gcl.aspects.event_bus import BudgetLog, BudgetLogSubscriber, InMemoryEventBus
        from gcl.domain.errors import ModelNotFoundError, ProviderError
        from gcl.domain.models import ChatRequest, ChatResult

        bus = InMemoryEventBus()
        blog = BudgetLog()
        bus.subscribe(BudgetLogSubscriber(blog))
        state: dict[str, Any] = {"model": "primary-id", "fallback_from": ""}

        def primary(_req: ChatRequest) -> ChatResult:
            raise ModelNotFoundError("secret-token not found")

        def backup(_req: ChatRequest) -> ChatResult:
            return ChatResult("ok", 10, 5, "fallback-id", 12)

        def switch(_exc: ModelNotFoundError):
            state["fallback_from"] = state["model"]
            state["model"] = "fallback-id"
            return backup

        chain = AspectChain(
            primary,
            (
                SecretRedactionAspect(("secret-token",)),
                BudgetTelemetryAspect(bus, lambda: {"role": "J2", "provider": "deepseek", "alias": "v4pro", **state}),
                FallbackModelAspect(switch),
            ),
        )
        res = chain.invoke(ChatRequest("sys", "usr", role="J2", model="primary-id"))
        self.assertEqual(res.text, "ok")
        self.assertEqual(len(blog.records), 1)
        self.assertEqual(blog.records[0]["fallback_from"], "primary-id")
        self.assertEqual(blog.records[0]["model"], "fallback-id")

        guarded = AspectChain(
            lambda _r: ChatResult("ok", 1, 1, "m", 0),
            (OfflineGuardAspect(), SecretRedactionAspect(("secret-token",))),
        )
        with patch.dict(os.environ, {"GCL_OFFLINE": "1"}):
            with self.assertRaises(ProviderError):
                guarded.invoke(ChatRequest("s", "u"))
            dry_res = guarded.invoke(ChatRequest("s", "u", options={"dry_run": True}))
            self.assertEqual(dry_res.text, "ok")

    def test_memoization_task_aspect_hits_repository(self) -> None:
        from gcl.aspects.task_chain import run_batches_with_aspects
        from gcl.infrastructure.persistence.memo_store import AtomicJsonMemoRepository

        calls = 0

        def work(batch: list[dict[str, str]]) -> dict[str, str]:
            nonlocal calls
            calls += 1
            return {it["key"]: "done" for it in batch}

        with TempDir() as td:
            repo = AtomicJsonMemoRepository(td / "memo.json")
            batches = [[{"key": "K1"}]]
            first = run_batches_with_aspects(batches, work, memo=repo, tag=("t",))
            second = run_batches_with_aspects(batches, work, memo=repo, tag=("t",))
            self.assertEqual(first, {"K1": "done"})
            self.assertEqual(second, {"K1": "done"})
            self.assertEqual(calls, 1)
            self.assertEqual(repo.hits, 1)


class GoogleCacheAndRegistryTests(unittest.TestCase):
    """Google cachedContentTokenCount fix and OCP registry extensibility."""

    def test_google_adapter_extracts_cached_and_thought_tokens(self) -> None:
        from gcl.infrastructure.providers.adapters.google_adapter import GoogleProvider

        prov = GoogleProvider("gemini-4-hydrogen", "fake-key", "https://example.test/v1beta")
        rep = prov.parse_reply({
            "candidates": [{"content": {"parts": [{"text": "hello"}]}, "finishReason": "STOP"}],
            "usageMetadata": {
                "promptTokenCount": 120,
                "candidatesTokenCount": 15,
                "thoughtsTokenCount": 25,
                "cachedContentTokenCount": 80,
            },
        })
        self.assertEqual(rep.text, "hello")
        self.assertEqual(rep.usage.input_tokens, 120)
        self.assertEqual(rep.usage.output_tokens, 40)
        self.assertEqual(rep.usage.cache_read_tokens, 80)
        self.assertEqual(rep.usage.thought_tokens, 25)

    def test_open_closed_registries_allow_custom_plugins(self) -> None:
        from gcl.domain.models import PlaceholderSet, Row
        from gcl.infrastructure.formats.registry import TableFormatRegistry
        from gcl.infrastructure.providers.vendor_registry import VendorDescriptor, VendorRegistry
        from gcl.infrastructure.tokens.placeholders import PlaceholderRegistry, extract_placeholders
        from gcl.ports.formats import ExportResult, TableLoadOptions

        class DummyAdapter:
            def __init__(self, model: str, **_kw: Any) -> None:
                self.model = model

        vreg = VendorRegistry()
        vreg.register(VendorDescriptor("custom_vendor", DummyAdapter))
        self.assertTrue(vreg.is_config_vendor("custom_vendor"))
        self.assertEqual(vreg.create("custom_vendor", "m-1").model, "m-1")

        class XyzFormat:
            suffixes = (".xyz",)

            def read_rows(self, path: Path, options: TableLoadOptions) -> list[Row]:
                return []

            def write_export(self, final_texts: dict[str, str], template: Path, out_dir: Path, *, dst_field: str, key_field: str) -> ExportResult:
                return ExportResult((), 0, ())

        freg = TableFormatRegistry()
        freg.register(XyzFormat())
        self.assertIsInstance(freg.get(Path("sample.xyz")), XyzFormat)

        class SigilStrategy:
            style = "custom_sigil"

            def extract(self, text: str) -> PlaceholderSet:
                return PlaceholderSet(("$HP$",) if "$HP$" in text else (), (), ())

        preg = PlaceholderRegistry()
        preg.register(SigilStrategy())
        self.assertEqual(extract_placeholders("HP $HP$", "custom_sigil", registry=preg).top, ("$HP$",))


class ContextSegregationAndCliBatchTests(unittest.TestCase):
    """Interface segregation between writer/blind views and orchestrator --batch CLI flag."""

    def test_blind_vs_writer_context_adapters(self) -> None:
        from gcl.infrastructure.persistence.context_views import BlindContextAdapter, WriterContextAdapter

        class FakePack:
            source = "CONTEXT_MAP.md"
            text = "Neutral map"
            jury_text = "Neutral map"
            appendix = "Turkish style notes"

            def system(self, base: str, writer: bool = False) -> str:
                return base + (" + WRITER_APP" if writer else " + NEUTRAL")

            def line(self, key: str, writer: bool = False) -> dict[str, str]:
                return {"scene": "cockpit", **({"tone": "slang"} if writer else {})}

            def enrich(self, items: list[dict[str, Any]], key_field: str = "key", writer: bool = False) -> int:
                return len(items)

        pack = FakePack()
        blind = BlindContextAdapter(pack)
        writer = WriterContextAdapter(pack)
        self.assertFalse(hasattr(blind, "has_appendix"))
        self.assertEqual(blind.build_system("BASE"), "BASE + NEUTRAL")
        self.assertEqual(blind.line_fields("K1"), {"scene": "cockpit"})
        self.assertTrue(writer.has_appendix)
        self.assertEqual(writer.build_system("BASE"), "BASE + WRITER_APP")
        self.assertEqual(writer.line_fields("K1"), {"scene": "cockpit", "tone": "slang"})

    def test_orchestrator_stub_exposes_batch_flag_and_dry_run(self) -> None:
        code, out, _ = run_cli("orchestrator_stub.py", "--help")
        self.assertEqual(code, 0)
        self.assertIn("--batch", out)
        with TempDir() as td:
            src = write_json(td / "in.json", [{"key": "UI.OK", "en": "Confirm"}])
            code, _o, err = run_cli(
                "orchestrator_stub.py", str(src), "--locale", "tr-TR", "--workdir", str(td / "work"),
                "--dry-run", "--batch", "--json", env_extra={"GCL_OFFLINE": "1"},
            )
            self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
