"""3.1.0 cost levers: larger batches with a character budget, cache priming, empty Pass 1 targets, batched
deliberation re-votes, the parallel Pass 2 recheck, batch API mode (Anthropic and Google) and its price."""
from __future__ import annotations

import json
import threading
import time
import unittest
from typing import Any, Dict, List, Tuple

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import TempDir, write_json  # noqa: E402

import budget_report as br  # noqa: E402
import deliberate as dl  # noqa: E402
import llm_tasks as lt  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import ChatResult, FakeScenario, Router, load_providers_config, split_envelope  # noqa: E402
from providers.anthropic import AnthropicProvider  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from providers.batch import AnthropicBatchBackend, BatchCollector, GoogleBatchBackend  # noqa: E402
from providers.google import GoogleProvider  # noqa: E402


class BudgetChunkTests(unittest.TestCase):
    def test_rows_and_characters_both_limit_a_batch(self):
        items = [{"k": i, "t": "x" * n} for i, n in enumerate([10, 10, 10, 50, 10, 10])]
        got = lt.chunked_budget(items, 3, 40, lambda it: it["t"])
        self.assertEqual([[it["k"] for it in b] for b in got], [[0, 1, 2], [3], [4, 5]])

    def test_an_item_over_the_budget_goes_alone_and_order_is_kept(self):
        items = [{"k": i, "t": "y" * n} for i, n in enumerate([5, 500, 5])]
        got = lt.chunked_budget(items, 100, 100, lambda it: it["t"])
        self.assertEqual([[it["k"] for it in b] for b in got], [[0], [1], [2]])
        self.assertEqual([it["k"] for b in got for it in b], [0, 1, 2])

    def test_defaults_are_larger_than_before(self):
        self.assertGreaterEqual(lt.BATCH_ROWS["pass1"], 80)
        self.assertGreaterEqual(lt.BATCH_ROWS["jury"], 80)
        self.assertGreaterEqual(lt.BATCH_ROWS["pass2"], 25)

    def test_score_entries_sends_fewer_calls(self):
        calls: List[int] = []

        class P:
            model = "m"

            def complete(self, system: str, user: str, **kw: Any) -> ChatResult:
                _i, p = split_envelope(user)
                calls.append(len(p["entries"]))
                return ChatResult(json.dumps({"votes": [{"key": e["key"], "score": 5} for e in p["entries"]]}), 1, 1, "m", 0)
        entries = [{"key": f"k{i}", "target": "kısa bir satır"} for i in range(150)]
        out = lt.score_entries(P(), entries, "tr-TR")
        self.assertEqual(len(out), 150)
        self.assertEqual(calls, [100, 50])


class PrimingTests(unittest.TestCase):
    def test_first_batch_runs_alone_then_the_rest_in_parallel(self):
        events: List[Tuple[str, int]] = []
        lock = threading.Lock()

        def fn(b: int) -> Dict[str, Any]:
            with lock:
                events.append(("start", b))
            time.sleep(0.02)
            with lock:
                events.append(("end", b))
            return {str(b): b}
        out = lt.run_batches([0, 1, 2, 3], fn, workers=4)
        self.assertEqual(out, {"0": 0, "1": 1, "2": 2, "3": 3})
        self.assertEqual(events[:2], [("start", 0), ("end", 0)])

    def test_no_priming_when_asked_or_for_a_batched_provider(self):
        class Batched:
            batched = True
        self.assertFalse(lt.primes(Batched()))
        self.assertTrue(lt.primes(object()))
        events: List[Tuple[str, int]] = []
        lock = threading.Lock()
        gate = threading.Barrier(2, timeout=2)

        def fn(b: int) -> Dict[str, Any]:
            with lock:
                events.append(("start", b))
            gate.wait()  # both batches must be running at once, a primed first batch would time out here
            return {str(b): b}
        self.assertEqual(lt.run_batches([0, 1], fn, workers=2, prime=False), {"0": 0, "1": 1})


class EmptyTargetTests(unittest.TestCase):
    def test_an_empty_target_for_a_source_is_asked_again(self):
        replies = [{"rows": [{"key": "a", "target": ""}, {"key": "b", "target": "bee"}, {"key": "c", "target": ""}]},
                   {"rows": [{"key": "a", "target": "ay"}]}]
        sent: List[List[str]] = []

        class P:
            model = "m"

            def complete(self, system: str, user: str, **kw: Any) -> ChatResult:
                _i, p = split_envelope(user)
                sent.append([r["key"] for r in p["rows"]])
                return ChatResult(json.dumps(replies.pop(0)), 1, 1, "m", 0)
        rows = [{"key": "a", "source": "A"}, {"key": "b", "source": "B"}, {"key": "c", "source": ""}]
        out = lt.translate_rows(P(), rows, "de-DE")
        self.assertEqual(out, {"a": "ay", "b": "bee", "c": ""})
        self.assertEqual(sent, [["a", "b", "c"], ["a"]])

    def test_a_row_that_stays_empty_fails_loudly(self):
        class P:
            model = "m"

            def complete(self, system: str, user: str, **kw: Any) -> ChatResult:
                _i, p = split_envelope(user)
                return ChatResult(json.dumps({"rows": [{"key": r["key"], "target": " "} for r in p["rows"]]}), 1, 1, "m", 0)
        with self.assertRaises(L10nError):
            lt.translate_rows(P(), [{"key": "a", "source": "A"}], "de-DE")


ENTRIES = [{"key": f"L{i}", "target": f"Satır {i} burada duruyor ve biraz uzun.", "register": "ui"} for i in range(5)]


def j3_votes(key: str, scores: List[int]) -> List[Dict[str, Any]]:
    fams = ("anthropic", "deepseek", "google")
    return [{"key": key, "tier": "J3", "member": i, "family": fams[i], "model": f"m{i}", "score": s,
             "issue_type": "none" if s == 5 else "other", "reason": f"first {s}", "suggested": ""} for i, s in enumerate(scores)]


class BatchedDeliberationTests(unittest.TestCase):
    def setUp(self):
        self.scenario = FakeScenario({"deliberate": [{"key": "L1", "score": 4}, {"key": "L3", "model": "claude-opus-5-5", "score": 2}]})
        self.items = [(e, j3_votes(e["key"], [5, 3, 2]), {}) for e in ENTRIES]

    def _router(self) -> Router:
        return Router(load_providers_config(), dry_run=True, scenario=self.scenario)

    def test_same_outcome_as_line_by_line_with_far_fewer_calls(self):
        r1 = self._router()
        one = dl.make_deliberator(r1, "tr-TR", "SYS")
        single = {e["key"]: one(e, v, ev) for e, v, ev in self.items}
        calls_single = sum(len(f.calls) for f in r1._fakes.values())
        r2 = self._router()
        many = dl.make_deliberator(r2, "tr-TR", "SYS").many(self.items)
        calls_many = sum(len(f.calls) for f in r2._fakes.values())
        self.assertEqual({k: (v["score"], v["status"]) for k, v in many.items()},
                         {k: (v["score"], v["status"]) for k, v in single.items()})
        self.assertEqual(calls_single, 15)
        self.assertEqual(calls_many, 3)
        self.assertEqual({c["task"] for f in r2._fakes.values() for c in f.calls}, {"deliberate_many"})

    def test_payload_of_a_line_is_the_one_revote_sends(self):
        scrub = dl.name_scrubber(load_providers_config())
        by_member = {int(v["member"]): v for v in self.items[0][1]}
        p = dl.revote_payload(self.items[0][0], by_member, 1, dl.evidence_package({}), scrub)
        self.assertEqual(p["own"]["score"], 3)
        self.assertEqual([o["juror"] for o in p["others"]], ["A", "B"])
        self.assertNotIn("source", json.dumps(p))

    def test_run_jury_uses_the_batched_round(self):
        import jury
        sc = FakeScenario({"scores": [{"key": "L2", "tier": "J1", "score": 2}, {"key": "L2", "tier": "J2", "score": 2},
                                      {"key": "L2", "tier": "J3", "model": "claude-opus-5-5", "score": 5},
                                      {"key": "L2", "tier": "J3", "model": "gemini-4-carbon", "score": 2},
                                      {"key": "L2", "tier": "J3", "model": "deepseek-v4-pro", "score": 3}]})
        router = Router(load_providers_config(), dry_run=True, scenario=sc)
        res = jury.run_jury(ENTRIES, "tr-TR", router, system="SYS", deliberator=dl.make_deliberator(router, "tr-TR", "SYS"),
                            budget_caps=False)
        tasks = [c["task"] for f in router._fakes.values() for c in f.calls]
        self.assertIn("deliberate_many", tasks)
        self.assertNotIn("deliberate", tasks)
        v = next(x for x in res["verdicts"] if x["key"] == "L2")
        self.assertEqual(v["final_tier"], "deliberation")


class RecheckTests(unittest.TestCase):
    def test_parallel_recheck_gives_the_same_lines(self):
        import pass2_rewrite as p2
        verdicts = [{"key": e["key"], "status": "rewrite", "score": 3, "final_tier": "J1", "votes": [], "evidence": {}, "rationales": ["x"]}
                    for e in ENTRIES]
        sources = {e["key"]: {"en": f"Line {e['key']}", "target": e["target"]} for e in ENTRIES}

        def run(workers: int) -> List[Tuple[str, str, Any]]:
            router = Router(load_providers_config(), dry_run=True)
            res = p2.rewrite_lines(verdicts, sources, "tr-TR", router, pass2_system="P2", pick_system="PICK", workers=workers)
            return [(l["key"], l["new"], l.get("recheck")) for l in res["lines"]]
        self.assertEqual(run(1), run(4))


# --------------------------------------------------------------------------- #
# batch API mode
# --------------------------------------------------------------------------- #
class Http:
    """Fake POST and GET transports keyed by URL. A handler gets (method, url, body) and returns (status, body)."""

    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.log: List[Tuple[str, str, Any]] = []
        self.lock = threading.Lock()

    def post(self, url: str, headers: Dict[str, str], body: bytes, timeout: float) -> Tuple[int, bytes, Dict[str, str]]:
        data = json.loads(body.decode("utf-8"))
        with self.lock:
            self.log.append(("POST", url, data))
        status, out = self.handler("POST", url, data)
        return status, out if isinstance(out, bytes) else json.dumps(out).encode("utf-8"), {}

    def get(self, url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, bytes, Dict[str, str]]:
        with self.lock:
            self.log.append(("GET", url, None))
        status, out = self.handler("GET", url, None)
        return status, out if isinstance(out, bytes) else json.dumps(out).encode("utf-8"), {}


def anthropic_handler(fail_ids: Tuple[str, ...] = ()) -> Any:
    state = {"polls": 0, "reqs": []}

    def handle(method: str, url: str, body: Any) -> Tuple[int, Any]:
        if method == "POST" and url.endswith("/v1/messages/batches"):
            state["reqs"] = body["requests"]
            return 200, {"id": "msgbatch_1", "processing_status": "in_progress"}
        if method == "GET" and url.endswith("/batches/msgbatch_1"):
            state["polls"] += 1
            if state["polls"] < 2:
                return 200, {"id": "msgbatch_1", "processing_status": "in_progress"}
            return 200, {"id": "msgbatch_1", "processing_status": "ended", "results_url": "https://api.anthropic.com/v1/messages/batches/msgbatch_1/results"}
        if method == "GET" and url.endswith("/msgbatch_1/results"):
            lines = []
            for r in reversed(state["reqs"]):  # results come in any order
                cid = r["custom_id"]
                if cid in fail_ids:
                    lines.append({"custom_id": cid, "result": {"type": "errored", "error": {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}}})
                else:
                    user = r["params"]["messages"][0]["content"]
                    lines.append({"custom_id": cid, "result": {"type": "succeeded", "message": {
                        "content": [{"type": "thinking", "thinking": "t"}, {"type": "text", "text": "echo:" + user}],
                        "usage": {"input_tokens": 10, "output_tokens": 4, "cache_read_input_tokens": 90}}}})
            return 200, "\n".join(json.dumps(x) for x in lines).encode("utf-8")
        return 404, {"error": "unexpected " + method + " " + url}
    handle.state = state  # type: ignore[attr-defined]
    return handle


def collector(backend: Any, **kw: Any) -> BatchCollector:
    return BatchCollector(backend, linger_s=kw.pop("linger_s", 0.15), poll_s=0.0, sleep=time.sleep, **kw)


def run_threads(fn: Any, args: List[Any]) -> List[Any]:
    out: List[Any] = [None] * len(args)

    def go(i: int) -> None:
        try:
            out[i] = fn(args[i])
        except Exception as exc:  # noqa: BLE001
            out[i] = exc
    ts = [threading.Thread(target=go, args=(i,)) for i in range(len(args))]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    return out


class AnthropicBatchTests(unittest.TestCase):
    def _backend(self, http: Http) -> AnthropicBatchBackend:
        prov = AnthropicProvider("claude-haiku-5-5", "secret-key", "https://api.anthropic.com/v1/messages", transport=http.post, sleep=lambda s: None)
        return AnthropicBatchBackend(prov, get=http.get)

    def test_calls_that_arrive_together_share_one_job(self):
        http = Http(anthropic_handler())
        col = collector(self._backend(http))
        res = run_threads(lambda u: col.complete("SYS", u, json_mode=True), [f"u{i}" for i in range(5)])
        self.assertEqual(sorted(r.text for r in res), sorted(f"echo:u{i}" for i in range(5)))
        posts = [x for x in http.log if x[0] == "POST"]
        self.assertEqual(len(posts), 1)
        reqs = posts[0][2]["requests"]
        self.assertEqual(len(reqs), 5)
        self.assertNotIn("stream", reqs[0]["params"])
        self.assertEqual(reqs[0]["params"]["model"], "claude-haiku-5-5")
        self.assertEqual(reqs[0]["params"]["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertTrue(all(r.batch_id == "msgbatch_1" and r.input_tokens == 100 and r.cache_read_tokens == 90 for r in res))
        self.assertEqual(col.jobs, [{"job": "msgbatch_1", "requests": 5, "model": "claude-haiku-5-5"}])

    def test_a_failed_request_fails_only_its_caller(self):
        http = Http(anthropic_handler(fail_ids=("r2",)))
        col = collector(self._backend(http))
        res = run_threads(lambda u: col.complete("SYS", u), ["a", "b", "c"])
        errors = [r for r in res if isinstance(r, ProviderError)]
        self.assertEqual(len(errors), 1)
        self.assertIn("busy", str(errors[0]))
        self.assertEqual(sum(1 for r in res if isinstance(r, ChatResult)), 2)

    def test_a_failed_create_fails_every_caller_without_hanging(self):
        http = Http(lambda m, u, b: (400, {"error": {"message": "bad request"}}))
        col = collector(self._backend(http))
        res = run_threads(lambda u: col.complete("SYS", u), ["a", "b"])
        self.assertTrue(all(isinstance(r, ProviderError) for r in res))
        self.assertTrue(all("secret-key" not in str(r) for r in res))

    def test_max_requests_splits_the_jobs(self):
        ids = iter(range(100))

        def handle(method: str, url: str, body: Any) -> Tuple[int, Any]:
            if method == "POST":
                n = next(ids)
                handle.jobs[f"msgbatch_{n}"] = body["requests"]  # type: ignore[attr-defined]
                return 200, {"id": f"msgbatch_{n}"}
            job = url.split("/batches/")[1].split("/")[0]
            if url.endswith("/results"):
                return 200, "\n".join(json.dumps({"custom_id": r["custom_id"], "result": {"type": "succeeded", "message": {
                    "content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 1}}}}) for r in handle.jobs[job]).encode()  # type: ignore[attr-defined]
            return 200, {"id": job, "processing_status": "ended", "results_url": f"https://api.anthropic.com/v1/messages/batches/{job}/results"}
        handle.jobs = {}  # type: ignore[attr-defined]
        http = Http(handle)
        col = collector(self._backend(http), max_requests=2)
        res = run_threads(lambda u: col.complete("SYS", u), ["a", "b", "c", "d", "e"])
        self.assertTrue(all(isinstance(r, ChatResult) for r in res))
        self.assertEqual(sorted(len(v) for v in handle.jobs.values()), [1, 2, 2])  # type: ignore[attr-defined]


class GoogleBatchTests(unittest.TestCase):
    def _backend(self, http: Http) -> GoogleBatchBackend:
        prov = GoogleProvider("gemini-4-hydrogen", "secret-key", "https://generativelanguage.googleapis.com/v1beta", transport=http.post, sleep=lambda s: None)
        return GoogleBatchBackend(prov, get=http.get)

    def _handler(self, shape: str) -> Any:
        state = {"reqs": [], "polls": 0}

        def reply(r: Dict[str, Any], with_key: bool) -> Dict[str, Any]:
            user = r["request"]["contents"][0]["parts"][0]["text"]
            item = {"response": {"candidates": [{"content": {"parts": [{"text": "think", "thought": True}, {"text": "g:" + user}]}, "finishReason": "STOP"}],
                                 "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 5, "thoughtsTokenCount": 7}}}
            if with_key:
                item["metadata"] = {"key": r["metadata"]["key"]}
            return item

        def handle(method: str, url: str, body: Any) -> Tuple[int, Any]:
            if method == "POST" and url.endswith("/models/gemini-4-hydrogen:batchGenerateContent"):
                state["reqs"] = body["batch"]["inputConfig"]["requests"]["requests"]
                return 200, {"name": "batches/abc", "metadata": {"state": "JOB_STATE_PENDING"}}
            if method == "GET" and url.endswith("/v1beta/batches/abc"):
                state["polls"] += 1
                if state["polls"] < 2:
                    return 200, {"name": "batches/abc", "metadata": {"state": "JOB_STATE_RUNNING"}}
                if shape == "live":  # what Gemini Batch Mode returned on 2026-11-27
                    items = [reply(r, True) for r in state["reqs"]]
                    return 200, {"name": "batches/abc", "done": True,
                                 "metadata": {"state": "BATCH_STATE_SUCCEEDED", "output": {"inlinedResponses": {"inlinedResponses": items}},
                                              "batchStats": {"requestCount": "3", "successfulRequestCount": "3"}},
                                 "response": {"inlinedResponses": {"inlinedResponses": items}}}
                if shape == "reference":
                    items = [reply(r, True) for r in state["reqs"]]
                    return 200, {"name": "batches/abc", "done": True, "metadata": {"state": "BATCH_STATE_SUCCEEDED"},
                                 "response": {"output": {"inlinedResponses": {"inlinedResponses": items}}}}
                items = [reply(r, False) for r in state["reqs"]]  # the guide's shape, no key, input order
                return 200, {"name": "batches/abc", "state": "JOB_STATE_SUCCEEDED", "dest": {"inlinedResponses": items}}
            return 404, {"error": {"message": "unexpected"}}
        return handle

    def test_both_documented_result_shapes_are_read(self):
        for shape in ("live", "reference", "guide"):
            with self.subTest(shape=shape):
                http = Http(self._handler(shape))
                col = collector(self._backend(http))
                res = run_threads(lambda u: col.complete("SYS", u, json_mode=True), ["x", "y", "z"])
                self.assertEqual(sorted(r.text for r in res), ["g:x", "g:y", "g:z"])
                self.assertTrue(all(r.output_tokens == 12 and r.batch_id == "batches/abc" for r in res))
                post = next(x for x in http.log if x[0] == "POST")[2]
                req = post["batch"]["inputConfig"]["requests"]["requests"][0]
                self.assertEqual(req["request"]["systemInstruction"]["parts"][0]["text"], "SYS")
                self.assertEqual(req["request"]["generationConfig"]["responseMimeType"], "application/json")
                # a batch request may ask for 65536 output tokens at most, the real time maximum is refused live
                self.assertEqual(req["request"]["generationConfig"]["maxOutputTokens"], 65536)
                self.assertIn("key", req["metadata"])

    def test_a_failed_job_fails_its_callers(self):
        def handle(method: str, url: str, body: Any) -> Tuple[int, Any]:
            if method == "POST":
                return 200, {"name": "batches/bad"}
            return 200, {"name": "batches/bad", "metadata": {"state": "JOB_STATE_FAILED"}, "error": {"message": "quota"}}
        col = collector(self._backend(Http(handle)))
        res = run_threads(lambda u: col.complete("SYS", u), ["a"])
        self.assertIsInstance(res[0], ProviderError)
        self.assertIn("quota", str(res[0]))


class RouterBatchTests(unittest.TestCase):
    ENV = {"ANTHROPIC_API_KEY": "a-key", "GOOGLE_API_KEY": "g-key", "DEEPSEEK_API_KEY": "d-key"}

    def test_batch_mode_wraps_anthropic_and_google_only_and_logs_the_job(self):
        http = Http(anthropic_handler())
        with TempDir() as td:
            router = Router(load_providers_config(), env=self.ENV, transport=http.post, get_transport=http.get,
                            sleep=lambda s: time.sleep(0.01), batch=True, budget_log=td / "budget.jsonl")
            haiku = router.for_model("haiku", "J1")
            self.assertTrue(haiku.batched)
            self.assertFalse(router.for_model("v4flash", "J1").batched)
            self.assertIs(router.for_model("haiku", "J2")._impl, haiku._impl)  # one collector per model
            haiku._impl.linger_s, haiku._impl.poll_s = 0.05, 0.0
            res = haiku.complete("SYS", "hello")
            self.assertEqual(res.text, "echo:hello")
            rec = json.loads((td / "budget.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertTrue(rec["batch"])
        self.assertEqual(rec["batch_id"], "msgbatch_1")
        self.assertEqual(router.batch_jobs()[0]["requests"], 1)

    def test_no_batch_for_deepseek_in_the_config(self):
        data = json.loads(load_providers_config().path.read_text(encoding="utf-8"))
        data["providers"]["deepseek"]["batch"] = {"price_factor": 0.5}
        with TempDir() as td:
            with self.assertRaises(L10nError):
                load_providers_config(write_json(td / "p.json", data))

    def test_make_router_raises_the_workers_in_batch_mode(self):
        class Args:
            providers_config = None
            dry_run = True
            fake_scenario = None
            budget_log = None
            batch = True
            workers = 4
        args = Args()
        lt.make_router(args, ["J1"])
        self.assertEqual(args.workers, lt.BATCH_WORKERS)


class BudgetBatchTests(unittest.TestCase):
    def test_a_batched_call_costs_half_and_the_report_counts_requests_and_jobs(self):
        prices = br.price_table(load_providers_config())
        full = br.cost_of("claude-sonnet-5-5", 1_000_000, 100_000, prices)
        half = br.cost_of("claude-sonnet-5-5", 1_000_000, 100_000, prices, batch=True)
        self.assertAlmostEqual(half, full / 2)
        self.assertAlmostEqual(br.cost_of("deepseek-flash", 1000, 1000, prices, batch=True), br.cost_of("deepseek-flash", 1000, 1000, prices))
        recs = [{"role": "J1", "provider": "anthropic", "model": "claude-haiku-5-5", "input_tokens": 100, "output_tokens": 10, "batch": True, "batch_id": "b1"},
                {"role": "J1", "provider": "anthropic", "model": "claude-haiku-5-5", "input_tokens": 100, "output_tokens": 10, "batch": True, "batch_id": "b1"},
                {"role": "J1", "provider": "deepseek", "model": "deepseek-flash", "input_tokens": 100, "output_tokens": 10}]
        tot = br.aggregate(recs, [], prices)[0]
        self.assertEqual((tot["calls"], tot["batched"], tot["batch_jobs"]), (3, 2, 1))


if __name__ == "__main__":
    unittest.main()
