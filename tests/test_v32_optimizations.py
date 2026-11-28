"""v3.2.0 Phase M cost, token and request optimizations plus Python 3.15 contract tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _helpers import TempDir, run_cli, write_json, write_text  # noqa: E402

import budget_report as br  # noqa: E402
import eval_critic as ec  # noqa: E402
import jury as jury_mod  # noqa: E402
import l10n_common as lc  # noqa: E402
import llm_tasks as lt  # noqa: E402
import orchestrator_stub as orch  # noqa: E402
import pass2_rewrite as p2  # noqa: E402
import tm as tmmod  # noqa: E402
from gcl.application.pipeline.stages import write_final_batch  # noqa: E402
from gcl.domain.envelope_codec import salvage_keyed_items  # noqa: E402
from gcl.domain.errors import L10nError, PermanentProviderError  # noqa: E402
from gcl.domain.models import ChatResult, Row  # noqa: E402
from gcl.domain.prompt_compactor import compact_agent_for_api, compact_playbook_for_api  # noqa: E402
from gcl.infrastructure.formats.export_decisions import apply_decisions  # noqa: E402
from gcl.infrastructure.persistence.memo_store import AtomicJsonMemoRepository  # noqa: E402
from providers import FakeScenario, Router, load_providers_config  # noqa: E402


class ScriptedTransport:
    """In memory HTTP POST fake recording request bodies and returning scripted tuples."""

    def __init__(self, replies: List[Tuple[int, Any, Dict[str, str]]]) -> None:
        self._replies = list(replies)
        self.requests: List[Dict[str, Any]] = []

    def __call__(self, url: str, headers: Dict[str, str], body: bytes, timeout: float) -> Tuple[int, bytes, Dict[str, str]]:
        self.requests.append({"url": url, "headers": headers, "body": json.loads(body.decode("utf-8"))})
        status, data, hdrs = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        raw = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        return status, raw, hdrs


class RuntimeAndLayer0Tests(unittest.TestCase):
    """Single Python 3.15 runtime target, version 3.2.0 lockstep, Google 65536 cap and thought/flex telemetry."""

    def test_python_315_and_version_lockstep(self) -> None:
        self.assertGreaterEqual(sys.version_info[:2], (3, 15))
        self.assertEqual(lc.MIN_PYTHON, (3, 15))
        self.assertEqual(lc.__version__, "3.2.0")

    def test_google_cap_and_thought_flex_budget_telemetry(self) -> None:
        cfg = load_providers_config()
        self.assertEqual(cfg.models["hydrogen"].max_output_tokens, 65536)

        with TempDir() as td:
            tr = ScriptedTransport([
                (200, {
                    "candidates": [{"content": {"parts": [{"text": '{"votes": []}'}]}, "finishReason": "STOP"}],
                    "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 50, "thoughtsTokenCount": 200},
                }, {}),
            ])
            router = Router(
                cfg,
                env={"ANTHROPIC_API_KEY": "a", "GOOGLE_API_KEY": "g", "DEEPSEEK_API_KEY": "d"},
                transport=tr,
                sleep=lambda _s: None,
                budget_log=td / "budget.jsonl",
                flex=True,
            )
            res = next(m.provider for m in router.jury("J1") if m.family == "google").complete("SYS", "USR", json_mode=True)
            self.assertEqual(res.thought_tokens, 200)
            req_body = tr.requests[0]["body"]
            self.assertEqual(req_body["generationConfig"]["maxOutputTokens"], 65536)
            self.assertEqual(req_body["generationConfig"]["thinkingConfig"]["thinkingLevel"], "LOW")
            self.assertEqual(req_body["serviceTier"], "flex")
            recs = br.read_records([td / "budget.jsonl"])
            self.assertEqual(recs[0]["thought_tokens"], 200)
            self.assertTrue(recs[0]["flex"])
            prices = br.price_table(cfg)
            tot = br.aggregate(recs, [], prices)[0]
            self.assertEqual(tot["thought_tokens"], 200)
            std = br.cost_of("gemini-4-hydrogen", 1000, 250, prices)
            flex = br.cost_of("gemini-4-hydrogen", 1000, 250, prices, flex=True)
            batched = br.cost_of("gemini-4-hydrogen", 1000, 250, prices, batch=True, flex=True)
            self.assertAlmostEqual(flex, std * 0.5)
            self.assertAlmostEqual(batched, std * 0.5)


class Layer1EffortAndPromptTests(unittest.TestCase):
    """Anthropic adaptive effort, DeepSeek sub-role thinking, prefix-stable prompts and lean API prompts."""

    def test_anthropic_adaptive_effort_and_deepseek_subroles(self) -> None:
        cfg = load_providers_config()
        tr_a = ScriptedTransport([
            (200, {"content": [{"type": "text", "text": "{}"}], "usage": {"input_tokens": 10, "output_tokens": 5}}, {}),
        ])
        tr_d = ScriptedTransport([
            (200, {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 20, "completion_tokens": 8, "completion_tokens_details": {"reasoning_tokens": 3}}}, {}),
        ])
        env = {"ANTHROPIC_API_KEY": "a", "GOOGLE_API_KEY": "g", "DEEPSEEK_API_KEY": "d"}
        ra = Router(cfg, env=env, transport=tr_a, sleep=lambda _s: None)
        ra.for_role("pass2").complete("S", "U")
        abody = tr_a.requests[0]["body"]
        self.assertEqual(abody["thinking"], {"type": "adaptive"})
        self.assertEqual(abody["output_config"], {"effort": "high"})
        self.assertNotIn("temperature", abody)
        self.assertNotIn("budget_tokens", abody)

        rd = Router(cfg, env=env, transport=tr_d, sleep=lambda _s: None)
        pick_ds = next(m.provider for m in rd.jury("J1", task_role="pick") if m.family == "deepseek")
        res = pick_ds.complete("S", "U", json_mode=True)
        self.assertEqual(tr_d.requests[0]["body"]["thinking"], {"type": "disabled"})
        self.assertEqual(res.thought_tokens, 3)
        self.assertEqual(rd.budget.records[0]["role"], "J1")

    def test_prefix_stable_critic_prompt_and_lean_api_pass1_compaction(self) -> None:
        agent_raw = orch.load_agent_prompt("game-culturalizer")
        compacted_agent = compact_agent_for_api(agent_raw)
        self.assertLess(len(compacted_agent), len(agent_raw))
        self.assertNotIn("## Orchestration", compacted_agent)
        self.assertIn("Player gender neutrality", compacted_agent)

        full_sys = orch.system_prompt("game-culturalizer", "tr-TR", "", lean_api=False)
        lean_sys = orch.system_prompt("game-culturalizer", "tr-TR", "", lean_api=True)
        self.assertLess(len(lean_sys), len(full_sys))
        self.assertIn("A1", lean_sys)
        self.assertNotIn("## 12. Linter Coverage Note", lean_sys)

        seen_systems: List[Tuple[str, str]] = []
        rows = [
            {"key": "UI_1", "en": "Open inventory", "category": "ui"},
            {"key": "DLG_1", "en": "Keep calm, kid.", "category": "dialogue", "speaker": "Mentor", "archetype": "A1"},
        ]
        sc = {"scores": [{"key": "DLG_1", "score": 3, "reason": "stiff"}]}
        router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario(sc))
        real_score = jury_mod.score_entries
        real_pick = p2.pick_candidates

        def spy_score(provider, entries, locale, **kw):
            seen_systems.append(("score", str(kw.get("system", ""))))
            return real_score(provider, entries, locale, **kw)

        def spy_pick(provider, items, locale, **kw):
            seen_systems.append(("pick", str(kw.get("system", ""))))
            return real_pick(provider, items, locale, **kw)

        with TempDir() as td:
            src = write_json(td / "src.json", rows)
            from unittest import mock
            with mock.patch.object(jury_mod, "score_entries", spy_score), \
                 mock.patch.object(p2, "pick_candidates", spy_pick), \
                 mock.patch.object(p2, "score_entries", spy_score):
                orch.run_jury_pipeline(src, "tr-TR", td / "w", router, batch_size=1, budget_caps=False, langpack_dir=td / "np")
        unique_sys = {s for _, s in seen_systems}
        self.assertEqual(len(unique_sys), 1)
        self.assertIn("pick", {k for k, _ in seen_systems})


class Layer2JuryAndTournamentTests(unittest.TestCase):
    """CleanLightPassSpec settlement, tiered pass2_light and unanimous 3/3 recheck skip."""

    def test_clean_light_pass_spec_and_guards(self) -> None:
        clean_sc = FakeScenario({"scores": [{"key": "K1", "tier": "J1", "family": "google", "score": 4, "reason": "mild"}]})
        odd_sc = FakeScenario({"scores": [
            {"key": "K1", "tier": "J1", "family": "google", "score": 4, "odd_words": ["müstakbel"]},
            {"key": "K1", "tier": "J2", "family": "google", "score": 4, "odd_words": ["müstakbel"]},
        ]})
        entries = [{"key": "K1", "category": "ui", "target": "Ayarları aç"}]
        r1 = Router(load_providers_config(), dry_run=True, scenario=clean_sc)
        res1 = jury_mod.run_jury(entries, "tr-TR", r1, system="S", clean_light_pass=True)
        self.assertEqual((res1["verdicts"][0]["status"], res1["verdicts"][0]["score"]), ("pass", 4))

        r2 = Router(load_providers_config(), dry_run=True, scenario=odd_sc)
        res2 = jury_mod.run_jury([{"key": "K1", "category": "ui", "target": "Müstakbel ayarları aç"}], "tr-TR", r2, system="S", clean_light_pass=True)
        self.assertEqual(res2["verdicts"][0]["status"], "rewrite_light")

    def test_tiered_pass2_and_unanimous_recheck_skip(self) -> None:
        sources = {
            "L1": {"en": "Open bag", "target": "Çantayı açmak", "category": "ui", "register": "ui"},
            "H1": {"en": "Hold the line.", "target": "Hatta kalınız.", "category": "dialogue", "register": "dialogue_casual"},
        }
        verdicts = [
            {"key": "L1", "final_tier": "J1", "score": 4, "status": "rewrite_light", "votes": [], "evidence": {}, "rationales": ["stiff"]},
            {"key": "H1", "final_tier": "J1", "score": 3, "status": "rewrite", "votes": [], "evidence": {}, "rationales": ["formal"]},
        ]
        sc = FakeScenario({
            "pass2": [
                {"key": "L1", "candidates": ["Çantayı şimdi aç", "Çantayı açın"]},
                {"key": "H1", "candidates": ["Sakın kapatma.", "Ayrılma.", "Bekle."]},
            ],
            "picks": [{"key": "L1", "prefer": "Çantayı şimdi aç"}],
        })
        router = Router(load_providers_config(), dry_run=True, scenario=sc)
        res = p2.rewrite_lines(verdicts, sources, "tr-TR", router, pass2_system="P2", pick_system="CR", tiered=True, unanimous_skip_recheck=True)
        by_key = {l["key"]: l for l in res["lines"]}
        self.assertEqual(len(by_key["L1"]["candidates"]), 3)   # 2 light candidates + 1 current
        self.assertEqual(len(by_key["H1"]["candidates"]), 4)   # 3 opus candidates + 1 current
        self.assertEqual(by_key["L1"]["recheck"], [5, 5, 5])
        models = {r["role"]: r["model"] for r in router.budget.records}
        self.assertEqual(models.get("pass2_light"), "claude-sonnet-5-5")
        self.assertEqual(models.get("pass2"), "claude-opus-5-5")
        # 3/3 unanimous on L1 and 3/3 default pick on H1 skips ALL J1 rescore calls after pick
        j1_picks = [r for r in router.budget.records if r["role"] == "J1"]
        self.assertEqual(len(j1_picks), 3)


class Layer3OptimizationAndSafetyTests(unittest.TestCase):
    """Fast-fail 4xx, truncated JSON salvage, item memo, dedup, TM cache/exact, eval_critic and export guards."""

    def test_permanent_4xx_fails_in_single_attempt_and_salvage_recovers_items(self) -> None:
        calls = 0

        class ClientErr:
            model = "claude-haiku-5-5"

            def complete(self, system: str, user: str, **kw: Any) -> ChatResult:
                nonlocal calls
                calls += 1
                raise PermanentProviderError("http 400 invalid request")

        with self.assertRaises(L10nError):
            lt.translate_rows(ClientErr(), [{"key": "A", "source": "Save"}], "tr-TR")
        self.assertEqual(calls, 1)

        truncated = '{"votes": [{"key": "A", "odd_words": [], "score": 5, "issue_type": "none", "reason": "", "suggested": ""}, {"key": "B", "odd'
        rec = salvage_keyed_items(truncated, "votes")
        self.assertEqual([x["key"] for x in rec], ["A"])

        sent: List[List[str]] = []

        class CutOnce:
            model = "m"

            def complete(self, system: str, user: str, **kw: Any) -> ChatResult:
                keys = [r["key"] for r in json.loads(user.split("\n---\n", 1)[1])["rows"]]
                sent.append(keys)
                if len(keys) == 2:
                    return ChatResult('{"rows": [{"key": "A", "target": "Kaydet"}, {"key": "B", "tar', 1, 100, "m", 0)
                return ChatResult(json.dumps({"rows": [{"key": "B", "target": "Çık"}]}), 1, 10, "m", 0)

        out = lt.translate_rows(CutOnce(), [{"key": "A", "source": "Save"}, {"key": "B", "source": "Exit"}], "tr-TR", salvage_truncated=True)
        self.assertEqual(out, {"A": "Kaydet", "B": "Çık"})
        self.assertEqual(sent, [["A", "B"], ["B"]])

    def test_item_memo_reuses_items_across_batch_sizes(self) -> None:
        calls: List[List[str]] = []

        class SpyProv:
            model = "m"

            def complete(self, system: str, user: str, **kw: Any) -> ChatResult:
                rows = json.loads(user.split("\n---\n", 1)[1])["rows"]
                calls.append([r["key"] for r in rows])
                return ChatResult(json.dumps({"rows": [{"key": r["key"], "target": f"TR:{r['source']}"} for r in rows]}), 1, 1, "m", 0)

        with TempDir() as td:
            imemo = AtomicJsonMemoRepository(td / "items.json")
            rows = [{"key": "K1", "source": "One"}, {"key": "K2", "source": "Two"}]
            first = lt.translate_rows(SpyProv(), rows, "tr-TR", batch_size=2, item_memo=imemo)
            second = lt.translate_rows(SpyProv(), rows + [{"key": "K3", "source": "Three"}], "tr-TR", batch_size=1, item_memo=imemo)
            self.assertEqual(first, {"K1": "TR:One", "K2": "TR:Two"})
            self.assertEqual(second["K3"], "TR:Three")
            self.assertEqual(calls, [["K1", "K2"], ["K3"]])

    def test_context_safe_dedup_tm_cache_and_exact_shortcircuit(self) -> None:
        with TempDir() as td:
            db = td / "tm.sqlite"
            with tmmod.TranslationMemory(db) as t:
                t.add("tr-TR", "REF_SAVE", "Save game", "Oyunu kaydet", category="ui", status="approved")
                t.add("tr-TR", "REF_PLAY_UI", "Play", "Oyna", category="ui", status="approved")
                t.add("tr-TR", "REF_PLAY_MUS", "Play", "Çal", category="audio", status="approved")
                self.assertEqual(t.exact_approved("tr-TR", "Save game", category="ui")["dst"], "Oyunu kaydet")
                self.assertEqual(t.exact_approved("tr-TR", "Play", category="ui")["dst"], "Oyna")
                self.assertEqual(t.exact_approved("tr-TR", "Play", category="audio")["dst"], "Çal")
                self.assertIsNone(t.exact_approved("tr-TR", "Play"))  # ambiguous across contexts must never collide
                nb1 = t.neighbors("tr-TR", "Save game", category="ui")
                nb2 = t.neighbors("tr-TR", "Save game", category="ui")
                self.assertEqual(nb1, nb2)
                self.assertTrue(t._gram_cache)

            src = write_json(td / "src.json", [
                {"key": "TM_SAVE", "en": "Save game", "category": "ui"},
                {"key": "PLAY_1", "en": "Open mission control panel", "category": "ui_button"},
                {"key": "PLAY_2", "en": "Open mission control panel", "category": "ui_button"},
                {"key": "PLAY_AUD", "en": "Open mission control panel", "category": "audio"},
            ])
            router = Router(load_providers_config(), dry_run=True)
            res = orch.run_jury_pipeline(src, "tr-TR", td / "w", router, tm_path=db, budget_caps=False, langpack_dir=td / "np")
            self.assertTrue(res["passed"])
            self.assertIn("1 approved TM exact", "\n".join(res["log"]))
            self.assertIn("1 context deduplicated", "\n".join(res["log"]))
            verdicts = json.loads((td / "w" / "verdicts_tr-TR_01.json").read_text(encoding="utf-8"))["verdicts"]
            self.assertEqual(len(verdicts), 4)
            # Only PLAY_1 and PLAY_AUD should reach pass1 (TM_SAVE short-circuited, PLAY_2 deduplicated with PLAY_1)
            pass1_calls = [r for r in router.budget.records if r["role"] == "pass1"]
            self.assertEqual(len(pass1_calls), 1)
            self.assertEqual(len(router.fake("sonnet").calls), 1)
            p1_by_key = {r["key"]: r["tr-TR"] for r in json.loads((td / "w" / "pass1_batch_01.json").read_text(encoding="utf-8"))}
            self.assertEqual(p1_by_key["TM_SAVE"], "Oyunu kaydet")
            self.assertEqual(p1_by_key["PLAY_1"], "[tr-TR] Open mission control panel")
            self.assertEqual(p1_by_key["PLAY_2"], "[tr-TR] Open mission control panel")
            self.assertEqual(p1_by_key["PLAY_AUD"], "[tr-TR] Open mission control panel")
            item_cache = json.loads((td / "w" / "model_items.json").read_text(encoding="utf-8"))
            self.assertEqual([v for v in item_cache.values() if isinstance(v, str)], ["[tr-TR] Open mission control panel", "[tr-TR] Open mission control panel"])

    def test_eval_critic_skips_unknown_by_default_and_safety_fixes(self) -> None:
        from tests.test_eval_critic import cset, make_pack  # reuse fixture builder
        with TempDir() as td:
            pack = make_pack(td)
            router = Router(load_providers_config(), dry_run=True)
            shots, pairs = ec.split_shots(cset()["pairs"], 4, 0, 1)
            rep_off = ec.evaluate(router, "tr-TR", ["J1"], pairs, shots, warmup=False, pack_dir=pack, seed=1, warmup_count=5, pairwise_min=0.85, langpack_version="x")
            self.assertIsNone(rep_off["members"][0]["unknown_mean"])
            rep_on = ec.evaluate(router, "tr-TR", ["J1"], pairs, shots, warmup=False, pack_dir=pack, seed=1, warmup_count=5, pairwise_min=0.85, langpack_version="x", include_unknown=True)
            self.assertIsNotNone(rep_on["members"][0]["unknown_mean"])

            # write_final_batch excludes kept_by_pick (new == old)
            p1 = [{"key": "A", "en": "Save", "tr-TR": "Kaydet"}]
            rw = {"lines": [{"key": "A", "old": "Kaydet", "new": "Kaydet", "valid": True}]}
            vr = {"verdicts": [{"key": "A", "status": "rewrite_light"}]}
            self.assertEqual(write_final_batch(td / "f.json", p1, rw, vr, "tr-TR"), 0)

            # apply_decisions holds undecided lines back to old
            rep = write_json(td / "changes.json", {"locale": "tr-TR", "lines": [{"key": "A", "old": "eski", "new": "yeni", "decision": ""}]})
            final = {"A": "yeni"}
            st = apply_decisions(final, [rep])
            self.assertEqual((final["A"], st["undecided"]), ("eski", ["A"]))

            # require_juried_context stops if appendix exists without CONTEXT_MAP.jury.md
            cmap = write_text(td / "CONTEXT_MAP.md", "# Game Context\nSome map")
            write_text(td / "CONTEXT_MAP.tr-TR.md", "# tr-TR Appendix\nChoices")
            src = write_json(td / "s.json", [{"key": "A", "en": "Save"}])
            with self.assertRaises(L10nError):
                orch.run_jury_pipeline(src, "tr-TR", td / "w2", Router(load_providers_config(), dry_run=True), context_map=cmap, require_juried_context=True, langpack_dir=td / "np")


if __name__ == "__main__":
    unittest.main()
