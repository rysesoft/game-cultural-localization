"""P1: providers package, providers.config.json, fake provider, router, budget log, providers_check CLI."""
from __future__ import annotations

import json
import os
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest import mock

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_json  # noqa: E402

import providers  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import (  # noqa: E402
    FakeProvider, FakeScenario, MissingKeyError, ModelNotFoundError, ProviderError, Router, as_legacy, envelope, extract_json,
    get_provider, load_providers_config,
)
from providers.base import BudgetLog, FromLegacy, RateLimiter, backoff_delay, post_json, redact, urllib_transport  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
EXPECTED_IDS = {
    "haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5",
    "hydrogen": "gemini-4-hydrogen", "neon": "gemini-4-neon", "carbon": "gemini-4-carbon",
    "v4flash": "deepseek-flash", "v4pro": "deepseek-v4-pro",
}


def bundled_config_dict() -> Dict[str, Any]:
    return json.loads((SCRIPTS / "providers.config.json").read_text(encoding="utf-8"))


class ScriptedTransport:
    """Fake HTTP transport: returns queued (status, body, headers) and records every request."""

    def __init__(self, replies: List[Tuple[int, Any, Dict[str, str]]]) -> None:
        self.replies = list(replies)
        self.requests: List[Dict[str, Any]] = []

    def __call__(self, url: str, headers: Dict[str, str], body: bytes, timeout: float) -> Tuple[int, bytes, Dict[str, str]]:
        self.requests.append({"url": url, "headers": dict(headers), "body": json.loads(body.decode("utf-8"))})
        status, data, hdrs = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(data, Exception):
            raise data
        raw = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        return status, raw, hdrs


ANTHROPIC_OK = {"content": [{"type": "text", "text": "{\"ok\": true}"}], "usage": {"input_tokens": 12, "output_tokens": 3}}
GOOGLE_OK = {"candidates": [{"content": {"parts": [{"text": "merhaba"}]}}], "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 2, "thoughtsTokenCount": 5}}
DEEPSEEK_OK = {"choices": [{"message": {"content": "hallo"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 4}}


class ConfigTests(unittest.TestCase):
    def test_bundled_config_ids_and_roles(self):
        cfg = load_providers_config()
        self.assertEqual({a: s.id for a, s in cfg.models.items()}, EXPECTED_IDS)
        self.assertEqual(cfg.providers["anthropic"]["endpoint"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(cfg.providers["google"]["endpoint"], "https://generativelanguage.googleapis.com/v1beta")
        self.assertEqual(cfg.providers["deepseek"]["endpoint"], "https://api.deepseek.com/chat/completions")
        for tier in ("J1", "J2", "J3"):
            fams = [s.provider for s in cfg.jury(tier)]
            self.assertEqual(sorted(fams), ["anthropic", "deepseek", "google"], tier)
        self.assertEqual(cfg.role_model("pass1").alias, "sonnet")
        self.assertEqual(cfg.models["v4pro"].fallback, "v4flash")
        self.assertIsNone(cfg.models["hydrogen"].price_in)
        self.assertEqual(cfg.agreement, {"pass_min": 4, "max_spread": 1, "critical_max": 2})
        self.assertEqual(cfg.roundtrip["min_words"], 6)
        text = (SCRIPTS / "providers.config.json").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{10,}")  # no key material

    def _bad(self, mutate) -> str:
        data = bundled_config_dict()
        mutate(data)
        with TempDir() as td:
            with self.assertRaises(L10nError) as ctx:
                load_providers_config(write_json(td / "p.json", data))
        return str(ctx.exception)

    def test_same_family_in_one_jury_is_rejected(self):
        msg = self._bad(lambda d: d["roles"].__setitem__("J2", ["sonnet", "opus", "neon"]))
        self.assertIn("same family", msg)
        self.assertIn("anthropic", msg)

    def test_invalid_configs(self):
        self.assertIn("unknown provider", self._bad(lambda d: d["providers"].__setitem__("openai", {"env_key": "X", "rps": 1, "endpoint": "https://x"})))
        self.assertIn("env_key", self._bad(lambda d: d["providers"]["google"].pop("env_key")))
        self.assertIn("https", self._bad(lambda d: d["providers"]["google"].__setitem__("endpoint", "ftp://x")))
        self.assertIn("price_in", self._bad(lambda d: d["models"]["haiku"].__setitem__("price_in", "cheap")))
        self.assertIn("chains", self._bad(lambda d: d["models"]["v4flash"].__setitem__("fallback", "haiku")))
        self.assertIn("exactly three", self._bad(lambda d: d["roles"].__setitem__("J1", ["haiku", "v4flash"])))
        self.assertIn("not a model alias", self._bad(lambda d: d["roles"].__setitem__("pass1", "gpt")))
        self.assertIn("unknown key", self._bad(lambda d: d.__setitem__("extra", 1)))
        self.assertIn("ratio", self._bad(lambda d: d["budget_caps"].__setitem__("escalate_j2_ratio", 3)))

    def test_missing_key_raises(self):
        cfg = load_providers_config()
        router = Router(cfg, env={"ANTHROPIC_API_KEY": "a", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "d"})
        with self.assertRaises(MissingKeyError) as ctx:
            router.require(["J1"])
        self.assertIn("GOOGLE_API_KEY", str(ctx.exception))
        self.assertNotIn("ANTHROPIC_API_KEY", str(ctx.exception))
        router.require(["pass1"])  # only anthropic needed
        Router(cfg, dry_run=True, env={}).require(["J1", "J2", "J3"])  # dry run needs no key


class HttpAdapterTests(unittest.TestCase):
    def _make(self, name: str, replies, **kw):
        t = ScriptedTransport(replies)
        sleeps: List[float] = []
        endpoint = {"anthropic": "https://api.anthropic.com/v1/messages", "google": "https://generativelanguage.googleapis.com/v1beta",
                    "deepseek": "https://api.deepseek.com/chat/completions"}[name]
        p = get_provider(name, kw.pop("model", "m-1"), api_key="secret-key-123", endpoint=endpoint, transport=t, sleep=sleeps.append, **kw)
        return p, t, sleeps

    def test_anthropic_request_shape(self):
        p, t, _ = self._make("anthropic", [(200, ANTHROPIC_OK, {})], model="claude-haiku-5-5")
        res = p.complete("SYS", "USER", temperature=0.2, max_tokens=99, json_mode=True)
        req = t.requests[0]
        self.assertEqual(req["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(req["headers"]["x-api-key"], "secret-key-123")
        self.assertEqual(req["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(req["body"]["model"], "claude-haiku-5-5")
        self.assertTrue(req["body"]["system"].startswith("SYS"))
        self.assertIn("JSON", req["body"]["system"])
        self.assertEqual(req["body"]["messages"], [{"role": "user", "content": "USER"}])
        self.assertNotIn("temperature", req["body"])                       # current Claude models reject sampling parameters
        self.assertEqual(req["body"]["max_tokens"], 16000)                  # room for thinking, a larger request keeps its own value
        thinking_reply = {"content": [{"type": "thinking", "thinking": "", "signature": "x"}, {"type": "text", "text": "{\"ok\": true}"}],
                          "usage": {"input_tokens": 12, "output_tokens": 40}}
        p2, t2, _ = self._make("anthropic", [(200, thinking_reply, {})], model="claude-opus-5-5")
        res2 = p2.complete("SYS", "USER", max_tokens=32000)
        self.assertEqual(t2.requests[0]["body"]["max_tokens"], 32000)
        self.assertEqual(res2.text, "{\"ok\": true}")                     # thinking blocks are skipped
        self.assertEqual((res.text, res.input_tokens, res.output_tokens, res.model), ("{\"ok\": true}", 12, 3, "claude-haiku-5-5"))
        self.assertNotIn("secret", repr(p))

    def test_google_request_shape(self):
        p, t, _ = self._make("google", [(200, GOOGLE_OK, {})], model="gemini-4-neon")
        res = p.complete("SYS", "USER", json_mode=True)
        req = t.requests[0]
        self.assertEqual(req["url"], "https://generativelanguage.googleapis.com/v1beta/models/gemini-4-neon:generateContent")
        self.assertEqual(req["headers"]["x-goog-api-key"], "secret-key-123")   # header, never the URL
        self.assertNotIn("secret-key-123", req["url"])
        self.assertEqual(req["body"]["systemInstruction"], {"parts": [{"text": "SYS"}]})
        self.assertEqual(req["body"]["contents"], [{"role": "user", "parts": [{"text": "USER"}]}])
        self.assertEqual(req["body"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual((res.text, res.input_tokens, res.output_tokens), ("merhaba", 9, 7))

    def test_google_errors_never_show_the_key(self):
        p, _, _ = self._make("google", [(400, {"error": {"message": "bad request key=secret-key-123"}}, {})])
        with self.assertRaises(ProviderError) as ctx:
            p.complete("s", "u")
        self.assertNotIn("secret-key-123", str(ctx.exception))
        self.assertEqual(redact("https://x/y?key=abc&z=1"), "https://x/y?key=***&z=1")

    def test_deepseek_request_shape_and_thinking(self):
        p, t, _ = self._make("deepseek", [(200, DEEPSEEK_OK, {})], model="deepseek-flash")
        res = p.complete("SYS", "USER", json_mode=True)
        req = t.requests[0]
        self.assertEqual(req["headers"]["Authorization"], "Bearer secret-key-123")
        self.assertEqual(req["body"]["messages"], [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}])
        self.assertEqual(req["body"]["response_format"], {"type": "json_object"})
        self.assertNotIn("thinking", req["body"])
        self.assertEqual((res.text, res.input_tokens, res.output_tokens), ("hallo", 7, 4))
        p2, t2, _ = self._make("deepseek", [(200, DEEPSEEK_OK, {})], options={"thinking": False})
        p2.complete("s", "u")
        self.assertEqual(t2.requests[0]["body"]["thinking"], {"type": "disabled"})
        self.assertEqual(req["body"]["max_tokens"], 32000)   # thinking counts against the limit, v4-pro filled 16000 live

    def test_every_adapter_leaves_room_for_thinking(self):
        for name, reply, field, floor in (("anthropic", ANTHROPIC_OK, ("max_tokens",), 16000), ("deepseek", DEEPSEEK_OK, ("max_tokens",), 32000),
                                          ("google", GOOGLE_OK, ("generationConfig", "maxOutputTokens"), 32000)):  # gemini-4-carbon hit 16000 live
            p, t, _ = self._make(name, [(200, reply, {}), (200, reply, {})])
            p.complete("s", "u", max_tokens=1024)
            p.complete("s", "u", max_tokens=40000)
            got = []
            for r in t.requests:
                v = r["body"]
                for f in field:
                    v = v[f]
                got.append(v)
            self.assertEqual(got, [floor, 40000], name)

    def test_bundled_config_runs_mechanical_deepseek_roles_without_thinking(self):
        cfg = load_providers_config()
        router = Router(cfg, env={"ANTHROPIC_API_KEY": "a", "GOOGLE_API_KEY": "g", "DEEPSEEK_API_KEY": "d"})
        for role in ("literal", "roundtrip"):
            spec = cfg.role_model(role)
            self.assertEqual(spec.provider, "deepseek")
            self.assertIs(router._thinking(spec, role, False), False, role)
        for tier in ("J1", "J2", "J3"):
            spec = next(s for s in cfg.jury(tier) if s.provider == "deepseek")
            self.assertIsNone(router._thinking(spec, tier, False), tier)   # jurors keep the API default, thinking on

    def test_retry_on_429_and_5xx_with_exponential_backoff(self):
        p, t, sleeps = self._make("anthropic", [(429, {"error": "rate"}, {}), (503, b"busy", {}), (200, ANTHROPIC_OK, {})])
        res = p.complete("s", "u")
        self.assertEqual(len(t.requests), 3)
        self.assertEqual([s for s in sleeps if s >= 1.0], [1.0, 2.0])
        self.assertEqual(res.output_tokens, 3)

    def test_retry_after_header_is_honoured(self):
        p, _, sleeps = self._make("deepseek", [(429, b"", {"retry-after": "3"}), (200, DEEPSEEK_OK, {})])
        p.complete("s", "u")
        self.assertIn(3.0, sleeps)

    def test_gives_up_after_five_attempts(self):
        p, t, sleeps = self._make("google", [(500, b"boom", {})])
        with self.assertRaises(ProviderError) as ctx:
            p.complete("s", "u")
        self.assertEqual(len(t.requests), 5)
        self.assertEqual([s for s in sleeps if s >= 1.0], [1.0, 2.0, 4.0, 8.0])
        self.assertIn("5 attempts", str(ctx.exception))

    def test_network_errors_are_retried(self):
        p, t, _ = self._make("anthropic", [(0, ConnectionResetError("reset"), {}), (200, ANTHROPIC_OK, {})])
        p.complete("s", "u")
        self.assertEqual(len(t.requests), 2)

    def test_client_errors_are_not_retried(self):
        p, t, _ = self._make("anthropic", [(400, {"error": {"message": "max_tokens too large"}}, {})])
        with self.assertRaises(ProviderError):
            p.complete("s", "u")
        self.assertEqual(len(t.requests), 1)
        p, t, _ = self._make("anthropic", [(401, {"error": "invalid x-api-key"}, {})])
        with self.assertRaises(ProviderError) as ctx:
            p.complete("s", "u")
        self.assertIn("authentication", str(ctx.exception))

    def test_model_not_found(self):
        for name, status, body in (("anthropic", 404, {"type": "error", "error": {"type": "not_found_error", "message": "model: x"}}),
                                   ("google", 404, {"error": {"message": "models/x is not found"}}),
                                   ("deepseek", 400, {"error": {"message": "Model Not Exist"}})):
            p, _, _ = self._make(name, [(status, body, {})])
            with self.assertRaises(ModelNotFoundError, msg=name):
                p.complete("s", "u")

    def test_offline_env_blocks_network(self):
        with mock.patch.dict(os.environ, {"GCL_OFFLINE": "1"}):
            with self.assertRaises(ProviderError) as ctx:
                urllib_transport("https://example.invalid", {}, b"{}", 1.0)
        self.assertIn("--dry-run", str(ctx.exception))

    def test_backoff_delay(self):
        self.assertEqual([backoff_delay(i) for i in range(5)], [1.0, 2.0, 4.0, 8.0, 16.0])
        self.assertEqual(backoff_delay(9), 30.0)
        self.assertEqual(backoff_delay(0, "0"), 0.0)

    def test_post_json_rejects_non_json(self):
        t = ScriptedTransport([(200, b"<html>", {})])
        with self.assertRaises(ProviderError):
            post_json("https://x", {}, {}, transport=t, sleep=lambda s: None)


class _MockApi(BaseHTTPRequestHandler):
    """Local stand-in for the three vendor APIs (127.0.0.1 only)."""
    seen: List[Dict[str, Any]] = []
    first_429 = True

    def log_message(self, *a):  # keep test output clean
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        _MockApi.seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        if _MockApi.first_429:
            _MockApi.first_429 = False
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return
        if self.path.startswith("/anthropic"):
            out = ANTHROPIC_OK
        elif self.path.startswith("/google"):
            out = GOOGLE_OK
        else:
            out = DEEPSEEK_OK
        raw = json.dumps(out).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class UrllibIntegrationTests(unittest.TestCase):
    """The three adapters talk real HTTP through urllib to a local mock server (no internet)."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockApi)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_three_providers_over_urllib(self):
        _MockApi.seen.clear()
        _MockApi.first_429 = True
        env = {k: v for k, v in os.environ.items() if k != "GCL_OFFLINE"}
        env.update({"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
        with mock.patch.dict(os.environ, env, clear=True):
            a = get_provider("anthropic", "claude-haiku-5-5", api_key="k1", endpoint=self.base + "/anthropic", rps=1000)
            g = get_provider("google", "gemini-4-neon", api_key="k2", endpoint=self.base + "/google", rps=1000)
            d = get_provider("deepseek", "deepseek-flash", api_key="k3", endpoint=self.base + "/deepseek", rps=1000)
            self.assertEqual(a.complete("s", "u").input_tokens, 12)   # first call gets a 429 and is retried
            self.assertEqual(g.complete("s", "u").text, "merhaba")
            self.assertEqual(d.complete("s", "u").text, "hallo")
        paths = [s["path"] for s in _MockApi.seen]
        self.assertEqual(paths[0], paths[1])  # retried request
        self.assertIn("/google/models/gemini-4-neon:generateContent", paths)
        google_req = next(s for s in _MockApi.seen if s["path"].startswith("/google/"))
        self.assertEqual(google_req["headers"]["x-goog-api-key"], "k2")
        self.assertEqual(_MockApi.seen[0]["headers"]["x-api-key"], "k1")
        self.assertEqual(_MockApi.seen[-1]["headers"]["authorization"], "Bearer k3")


class RouterAndFakeTests(unittest.TestCase):
    def test_dry_run_jury_and_budget_log(self):
        cfg = load_providers_config()
        with TempDir() as td:
            router = Router(cfg, dry_run=True, budget_log=td / "budget.jsonl")
            members = router.jury("J1")
            self.assertEqual([m.family for m in members], ["anthropic", "deepseek", "google"])
            payload = {"task": "jury", "locale": "tr-TR", "tier": "J1", "entries": [{"key": "A", "target": "Kaydet"}]}
            for m in members:
                res = m.provider.complete("sys", envelope("Score.", payload), json_mode=True)
                self.assertEqual(extract_json(res.text)["votes"][0]["score"], 5)
            lines = [json.loads(l) for l in (td / "budget.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 3)
        for rec in lines:
            for k in ("role", "provider", "model", "input_tokens", "output_tokens", "latency_ms"):
                self.assertIn(k, rec)
            self.assertEqual(rec["role"], "J1")
            self.assertGreater(rec["input_tokens"], 0)
        self.assertEqual({r["model"] for r in lines}, {"claude-haiku-5-5", "deepseek-flash", "gemini-4-hydrogen"})

    def test_fallback_on_model_not_found(self):
        cfg = load_providers_config()
        router = Router(cfg, dry_run=True, scenario=FakeScenario({"errors": {"deepseek-v4-pro": "not_found"}}))
        v4pro = [m for m in router.jury("J2") if m.alias == "v4pro"][0].provider
        res = v4pro.complete("s", envelope("x", {"task": "ping"}))
        self.assertEqual(res.model, "deepseek-flash")
        self.assertEqual(v4pro.fallback_from, "deepseek-v4-pro")
        self.assertTrue(any("fallback" in n for n in router.notes))
        self.assertEqual(router.budget.records[-1]["fallback_from"], "deepseek-v4-pro")

    def test_no_fallback_is_a_usage_error(self):
        cfg = load_providers_config()
        router = Router(cfg, dry_run=True, scenario=FakeScenario({"errors": {"claude-opus-5-5": "not_found"}}))
        with self.assertRaises(L10nError) as ctx:
            router.for_role("pass2").complete("s", "u")
        self.assertIn("no fallback", str(ctx.exception))

    def test_fallback_forces_thinking_on_real_path(self):
        data = bundled_config_dict()
        data["providers"]["deepseek"]["thinking"] = {"J2": False}
        with TempDir() as td:
            cfg = load_providers_config(write_json(td / "p.json", data))
        t = ScriptedTransport([(404, {"error": {"message": "Model Not Exist"}}, {}), (200, DEEPSEEK_OK, {})])
        env = {"ANTHROPIC_API_KEY": "a", "GOOGLE_API_KEY": "g", "DEEPSEEK_API_KEY": "d"}
        router = Router(cfg, env=env, transport=t, sleep=lambda s: None)
        prov = router.for_model("v4pro", "J2")
        prov.complete("s", "u")
        self.assertEqual(t.requests[0]["body"]["model"], "deepseek-v4-pro")
        self.assertEqual(t.requests[0]["body"]["thinking"], {"type": "disabled"})
        self.assertEqual(t.requests[1]["body"]["model"], "deepseek-flash")
        self.assertEqual(t.requests[1]["body"]["thinking"], {"type": "enabled"})

    def test_rate_limiter_spacing(self):
        now = [0.0]
        slept: List[float] = []

        def sleep(s: float) -> None:
            slept.append(s)
            now[0] += s
        lim = RateLimiter(4, clock=lambda: now[0], sleep=sleep)
        for _ in range(3):
            lim.wait()
        self.assertEqual(slept, [0.25, 0.25])

    def test_fake_is_deterministic_and_scenario_driven(self):
        user = envelope("Translate.", {"task": "pass1", "locale": "de-DE", "rows": [{"key": "A", "source": "Save"}]})
        a = FakeProvider("m").complete("s", user)
        b = FakeProvider("m").complete("s", user)
        self.assertEqual(a, b)
        self.assertEqual(extract_json(a.text)["rows"][0]["target"], "[de-DE] Save")
        from providers.base import prompt_hash
        sc = FakeScenario({"responses": {prompt_hash("s", user): "CANNED"}})
        self.assertEqual(FakeProvider("m", scenario=sc).complete("s", user).text, "CANNED")
        jury = envelope("Score.", {"task": "jury", "tier": "J1", "entries": [{"key": "K", "target": "Ok"}, {"key": "L", "target": "[tr-TR literal] x"}]})
        votes = extract_json(FakeProvider("m").complete("s", jury).text)["votes"]
        self.assertEqual([v["score"] for v in votes], [5, 2])
        sc = FakeScenario({"scores": [{"key": "K", "family": "google", "score": 3, "issue_type": "register"}]})
        votes = extract_json(FakeProvider("m", family="google", scenario=sc).complete("s", jury).text)["votes"]
        self.assertEqual((votes[0]["score"], votes[0]["issue_type"]), (3, "register"))
        votes = extract_json(FakeProvider("m", family="anthropic", scenario=sc).complete("s", jury).text)["votes"]
        self.assertEqual(votes[0]["score"], 5)
        with self.assertRaises(L10nError):
            FakeScenario({"bogus": 1})

    def test_legacy_wrappers(self):
        legacy = as_legacy(FakeProvider("m"))
        self.assertIsInstance(legacy.complete("s", envelope("x", {"task": "ping"})), str)
        wrapped = FromLegacy(lambda s, u: "hello")
        res = wrapped.complete("sys", "user")
        self.assertEqual((res.text, res.model), ("hello", "legacy"))
        self.assertGreater(res.input_tokens, 0)

    def test_extract_json_tolerates_fences(self):
        self.assertEqual(extract_json("```json\n{\"a\": 1}\n```"), {"a": 1})
        self.assertEqual(extract_json("Sure! {\"a\": [1, 2]} done"), {"a": [1, 2]})
        with self.assertRaises(L10nError):
            extract_json("no json here")

    def test_budget_log_without_path_keeps_records(self):
        log = BudgetLog(None)
        log.write({"role": "x"})
        self.assertEqual(log.records, [{"role": "x"}])


class ProvidersCheckCliTests(unittest.TestCase):
    CFG = str(SCRIPTS / "providers.config.json")

    def test_exit_0_dry_run_ping(self):
        with TempDir() as td:
            code, out, err = run_cli("providers_check.py", self.CFG, "--dry-run", "--ping", "--json", "--budget-log", str(td / "b.jsonl"), env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertEqual(len(data["pings"]), 8)
            self.assertEqual(len((td / "b.jsonl").read_text(encoding="utf-8").splitlines()), 8)

    def test_exit_1_when_fallback_used(self):
        with TempDir() as td:
            sc = write_json(td / "sc.json", {"errors": {"deepseek-v4-pro": "not_found"}})
            code, out, err = run_cli("providers_check.py", "--input", self.CFG, "--roles", "J2", "--dry-run", "--ping", "--fake-scenario", str(sc), env_extra=NO_KEYS)
        self.assertEqual(code, 1, err)
        self.assertIn("fallback", out)

    def test_exit_2_missing_key(self):
        code, _, err = run_cli("providers_check.py", self.CFG, env_extra=NO_KEYS)
        self.assertEqual(code, 2)
        self.assertIn("ANTHROPIC_API_KEY", err)
        self.assertIn("--dry-run", err)

    def test_exit_2_same_family(self):
        data = bundled_config_dict()
        data["roles"]["J1"] = ["haiku", "sonnet", "hydrogen"]
        with TempDir() as td:
            code, _, err = run_cli("providers_check.py", str(write_json(td / "p.json", data)), "--dry-run", env_extra=NO_KEYS)
        self.assertEqual(code, 2)
        self.assertIn("same family", err)

    def test_exit_2_usage(self):
        self.assertEqual(run_cli("providers_check.py", env_extra=NO_KEYS)[0], 2)
        self.assertEqual(run_cli("providers_check.py", self.CFG, "--roles", "J9", "--dry-run", env_extra=NO_KEYS)[0], 2)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertIn("providers_check.py", doc)
        code, help_text, _ = run_cli("providers_check.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertIn(flag, doc, f"providers_check.py: {flag} missing from CLI_REFERENCE.md")
        code, out, err = run_cli("providers_check.py", "--version")
        self.assertEqual(code, 0)
        self.assertRegex(out + err, r"\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
