"""P11: tm.py (SQLite TM, character n-gram neighbours with category and speaker tiers, approval flow back)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS, TempDir, run_cli, write_json, write_text  # noqa: E402

import tm as tmmod  # noqa: E402
from l10n_common import L10nError  # noqa: E402

NO_KEYS = {"GCL_OFFLINE": "1"}


def seed(t: tmmod.TranslationMemory) -> None:
    t.add("tr-TR", "D1", "Take your time, kid.", "Acele etme evlat.", category="dialogue", speaker="Mentor", status="approved")
    t.add("tr-TR", "D2", "Take your time, rookie.", "Acele etme çaylak.", category="dialogue", speaker="Rival", status="approved")
    t.add("tr-TR", "D3", "Take your time, kid!", "Yavaş ol evlat!", category="ui", speaker="", status="approved")
    t.add("tr-TR", "D4", "Take your time kid", "Sakin ol evlat", category="dialogue", speaker="Mentor", status="candidate")
    t.add("tr-TR", "U1", "Save game", "Oyunu kaydet", category="ui", status="approved")
    t.add("de-DE", "D1", "Take your time, kid.", "Lass dir Zeit, Kleiner.", category="dialogue", speaker="Mentor", status="approved")


class SimilarityTests(unittest.TestCase):
    def test_trigrams_and_dice(self):
        self.assertEqual(tmmod.dice(tmmod.trigrams("Save game"), tmmod.trigrams("save  GAME")), 1.0)
        self.assertGreater(tmmod.dice(tmmod.trigrams("Take your time, kid."), tmmod.trigrams("Take your time, rookie.")), 0.5)
        self.assertLess(tmmod.dice(tmmod.trigrams("Take your time"), tmmod.trigrams("Open the map")), 0.2)
        self.assertEqual(tmmod.dice([], ["abc"]), 0.0)


class StoreTests(unittest.TestCase):
    def test_neighbors_tiers_and_filters(self):
        with TempDir() as td:
            with tmmod.TranslationMemory(td / "tm.sqlite") as t:
                seed(t)
                nb = t.neighbors("tr-TR", "Take your time, kid.", category="dialogue", speaker="Mentor", k=5)
                keys = [n["key"] for n in nb]
                self.assertEqual(keys[0], "D1")
                self.assertEqual(nb[0]["match"], "category+speaker")
                self.assertEqual(nb[1]["key"], "D2")          # same category, other speaker
                self.assertEqual(nb[1]["match"], "category")
                self.assertEqual(nb[2]["key"], "D3")          # higher similarity than D2 but other category
                self.assertEqual(nb[2]["match"], "any")
                self.assertNotIn("D4", keys)                  # candidate rows are not neighbours by default
                self.assertNotIn("U1", keys)                  # below the similarity floor
                self.assertTrue(all(n["dst"] != "Lass dir Zeit, Kleiner." for n in nb))  # other locale
                with_cand = t.neighbors("tr-TR", "Take your time, kid.", category="dialogue", speaker="Mentor", statuses=("approved", "candidate"))
                self.assertIn("D4", [n["key"] for n in with_cand])
                self.assertNotIn("D1", [n["key"] for n in t.neighbors("tr-TR", "Take your time, kid.", exclude_key="D1")])
                self.assertEqual(len(t.neighbors("tr-TR", "Take your time, kid.", k=2)), 2)
                by_dst = t.neighbors("tr-TR", "Acele etme evlat", on="dst")
                self.assertEqual(by_dst[0]["key"], "D1")
                self.assertEqual(t.neighbors("tr-TR", ""), [])

    def test_upsert_rules_and_persistence(self):
        with TempDir() as td:
            db = td / "tm.sqlite"
            with tmmod.TranslationMemory(db) as t:
                self.assertEqual(t.add("tr-TR", "K", "Save", "Kaydet", status="approved"), "inserted")
                self.assertEqual(t.add("tr-TR", "K", "Save", "Kaydetmek", status="candidate"), "kept")   # approved wins
                self.assertEqual(t.add("tr-TR", "K", "Save", "Kaydet", status="approved"), "kept")
                self.assertEqual(t.add("tr-TR", "K", "Save", "Oyunu kaydet", status="approved"), "updated")
                with self.assertRaises(L10nError):
                    t.add("tr-TR", "K", "Save", "x", status="maybe")
            with tmmod.TranslationMemory(db) as t:
                nb = t.neighbors("tr-TR", "Save", min_similarity=0.5)
                self.assertEqual([n["dst"] for n in nb], ["Oyunu kaydet"])
                self.assertEqual(t.stats(), {"segments": 1, "by_locale": {"tr-TR": {"approved": 1}}})

    def test_corrupt_db(self):
        with TempDir() as td:
            bad = write_text(td / "bad.sqlite", "this is not sqlite" * 50)
            with self.assertRaises(L10nError):
                tmmod.TranslationMemory(bad)

    def test_long_text_query(self):
        with TempDir() as td:
            with tmmod.TranslationMemory(td / "tm.sqlite") as t:
                long_text = " ".join(f"word{i}" for i in range(800))
                t.add("tr-TR", "L", long_text, "uzun", status="approved")
                self.assertEqual(t.neighbors("tr-TR", long_text)[0]["key"], "L")


class CliTests(unittest.TestCase):
    def test_add_query_approve_stats(self):
        with TempDir() as td:
            db = td / "tm.sqlite"
            ref = write_text(td / "ref.csv", "key,en,tr-TR,category,speaker\nD1,\"Take your time, kid.\",Acele etme evlat.,dialogue,Mentor\n"
                                             "U1,Save game,Oyunu kaydet,ui,\nE1,Empty,,ui,\n")
            code, out, err = run_cli("tm.py", str(ref), "--db", str(db), "--locale", "tr", "--mode", "add", "--status", "approved", "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)  # one row skipped (empty target)
            self.assertEqual(json.loads(out)["counts"], {"inserted": 2, "updated": 0, "kept": 0, "skipped": 1})
            q = write_json(td / "q.json", [{"key": "N1", "en": "Take your time, kiddo.", "category": "dialogue", "speaker": "Mentor"}])
            code, out, err = run_cli("tm.py", str(q), "--db", str(db), "--locale", "tr-TR", "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            res = json.loads(out)["results"][0]
            self.assertEqual(res["neighbors"][0]["dst"], "Acele etme evlat.")
            q2 = write_json(td / "q2.json", [{"key": "Z", "en": "Completely different words"}])
            self.assertEqual(run_cli("tm.py", str(q2), "--db", str(db), "--locale", "tr-TR", env_extra=NO_KEYS)[0], 1)
            report = write_json(td / "changes.json", {"locale": "tr-TR", "lines": [
                {"key": "D9", "en": "Hold on, kid.", "old": "Bekle evlat.", "new": "Dur bir dakika evlat.", "decision": "accept", "category": "dialogue"},
                {"key": "D8", "en": "Run!", "old": "Koş!", "new": "Kaç!", "decision": "reject"},
                {"key": "D7", "en": "Wait.", "old": "Bekle.", "new": "Dur.", "decision": ""}]})
            code, out, err = run_cli("tm.py", str(report), "--db", str(db), "--locale", "tr-TR", "--mode", "approve", "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)  # D7 still undecided
            self.assertEqual(json.loads(out)["counts"], {"accepted": 1, "rejected_kept_old": 1, "undecided": 1, "no_source": 0})
            with tmmod.TranslationMemory(db) as t:
                self.assertEqual(t.neighbors("tr-TR", "Hold on, kid.", min_similarity=0.9)[0]["dst"], "Dur bir dakika evlat.")
                self.assertEqual(t.neighbors("tr-TR", "Run!", min_similarity=0.9)[0]["dst"], "Koş!")
            code, out, err = run_cli("tm.py", "--db", str(db), "--mode", "stats", "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["stats"]["by_locale"]["tr-TR"]["approved"], 4)

    def test_exit_2(self):
        with TempDir() as td:
            db = td / "tm.sqlite"
            self.assertEqual(run_cli("tm.py", "--db", str(db), "--mode", "query", "--locale", "tr-TR")[0], 2)  # no input
            q = write_json(td / "q.json", [{"key": "A", "en": "x"}])
            self.assertEqual(run_cli("tm.py", str(q), "--db", str(db))[0], 2)                                   # no locale
            self.assertEqual(run_cli("tm.py", str(q), "--db", str(db), "--locale", "xx")[0], 2)
            notreport = write_json(td / "nr.json", {"foo": 1})
            self.assertEqual(run_cli("tm.py", str(notreport), "--db", str(db), "--locale", "tr-TR", "--mode", "approve")[0], 2)
            self.assertEqual(run_cli("tm.py", str(q), "--db", str(write_text(td / "bad.sqlite", "junk" * 300)), "--locale", "tr-TR")[0], 2)

    def test_jury_uses_tm_evidence(self):
        with TempDir() as td:
            db = td / "tm.sqlite"
            with tmmod.TranslationMemory(db) as t:
                seed(t)
            blind = write_json(td / "blind_tr-TR_01.json", {"entries": [{"key": "N1", "target": "Acele etme evlat.", "category": "dialogue", "speaker": "Mentor"}]})
            src = write_json(td / "pass1.json", [{"key": "N1", "en": "Take your time, kid.", "dst": "Acele etme evlat."}])
            code, _, err = run_cli("jury.py", str(blind), "--locale", "tr-TR", "--dry-run", "--tm", str(db), "--source-table", str(src),
                                   "--langpack-dir", str(td / "np"), env_extra={**NO_KEYS, "ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": ""})
            self.assertEqual(code, 0, err)
            v = json.loads((td / "verdicts_tr-TR_01.json").read_text(encoding="utf-8"))["verdicts"][0]
            self.assertEqual(v["evidence"]["tm_neighbors"][0]["key"], "D1")
            self.assertEqual(v["evidence"]["tm_neighbors"][0]["match"], "category+speaker")

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("tm.py" in doc, "tm.py missing from CLI_REFERENCE.md")
        for script in ("tm.py", "jury.py"):
            code, help_text, _ = run_cli(script, "--help")
            self.assertEqual(code, 0)
            for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
                self.assertTrue(flag in doc, f"{script}: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
