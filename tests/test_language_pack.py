"""P2: build_language_pack.py, langpack/sources.manifest.json and the five-layer filter."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import ROOT, SCRIPTS, TempDir, run_cli, write_json, write_text  # noqa: E402

import build_language_pack as blp  # noqa: E402
from l10n_common import L10nError  # noqa: E402
from providers import FakeScenario, Router, load_providers_config  # noqa: E402

NO_KEYS = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "DEEPSEEK_API_KEY": "", "GCL_OFFLINE": "1"}
BUNDLED_MANIFEST = SCRIPTS.parent / "langpack" / "sources.manifest.json"

PO_HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
ROUNDTRIP_LINE = "Atölyeyi bu gece kapatmadan önce bütün aletleri yerine koy."
JURY_LINE = "Bu gece çok uzun sürecek gibi görünüyor, değil mi dostum?"


def po(entries: List[Dict[str, Any]]) -> str:
    out = [PO_HEADER]
    for e in entries:
        if e.get("fuzzy"):
            out.append("#, fuzzy\n")
        out.append(f'msgid "{e["en"]}"\nmsgstr "{e["tr"]}"\n\n')
    return "".join(out)


def make_tr_corpus(td: Path, with_missing: bool = False, review_false: bool = True) -> Dict[str, Path]:
    """Manifest + corpus files + reference table for a tr-TR build (one URL source in the cache, others by path)."""
    cache = td / "cache"
    url = "https://example.org/godot/tr.po"
    bundle_po = po([
        {"en": "Settings", "tr": "Ayarlar"},
        {"en": "Cancel", "tr": "İptal"},
        {"en": "Open the map", "tr": "Haritayı aç"},
        {"en": "Old entry", "tr": "Eski kayıt", "fuzzy": True},
        {"en": "Missing", "tr": ""},
        {"en": "Godot Engine", "tr": "Godot Engine"},
        {"en": "X", "tr": "Pencereyi kapatmak için buraya tıklayın lütfen"},
        {"en": "There is already an item here!", "tr": "Burada zaten bir eşya bulunmaktadır!"},
        {"en": "Use {0} now", "tr": "Şimdi kullan"},
        {"en": "Open the map", "tr": "Haritayı aç"},
    ])
    dest = blp.cache_path(cache, "godot-like", url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(bundle_po, encoding="utf-8")
    write_text(td / "en.properties", "settings = Settings\nnight = Close the workshop tonight after you put every tool back.\n"
               "chat = This night looks like it is going to be very long, right friend?\nquit = Quit\n")
    write_text(td / "tr.properties", "settings = Seçenekler\nnight = " + ROUNDTRIP_LINE + "\nchat = " + JURY_LINE + "\nquit = Çık\n")
    write_text(td / "en.ftl", "menu-settings = Settings\nmenu-cancel = Cancel\nhint =\n    Press the button\n    to continue.\n"
               "count = { $n ->\n    [one] one item\n   *[other] many items\n}\n")
    write_text(td / "tr.ftl", "menu-settings = Ayarlar\nmenu-cancel = İptal\nhint =\n    Devam etmek için\n    tuşa bas.\n"
               "count = { $n ->\n    [one] bir eşya\n   *[other] çok eşya\n}\n")
    bulk = [{"key": f"B{i}", "en": f"Crate number {i} is ready", "tr-TR": f"{i} numaralı sandık hazır", "commit": "abc123"} for i in range(501)]
    bulk.append({"key": "C1", "en": "The crate is open", "tr-TR": "Sandık açık", "commit": "def456"})
    write_json(td / "bulk.json", bulk)
    sources: List[Dict[str, Any]] = [
        {"id": "godot-like", "name": "Godot like", "license": "MIT", "license_class": "bundle", "attribution": "MIT test",
         "register": "ui", "review_process": True, "version": "1.0", "format": "po", "files": [{"locale": "tr-TR", "url": url, "sha256": None}]},
        {"id": "props", "name": "Props game", "license": "GPL-3.0", "license_class": "local", "register": "game", "review_process": True,
         "version": "2", "format": "properties", "files": [{"locale": "tr", "path": "tr.properties", "en_path": "en.properties"}]},
        {"id": "fluent", "name": "Fluent game", "license": "GPL-3.0", "license_class": "local", "register": "game", "review_process": True,
         "version": "3", "format": "ftl", "files": [{"locale": "tr-TR", "path": "tr.ftl", "en_path": "en.ftl"}]},
        {"id": "bulky", "name": "Bulk table", "license": "GPL-2.0", "license_class": "local", "register": "game", "review_process": True,
         "version": "4", "format": "table", "files": [{"locale": "tr-TR", "path": "bulk.json"}]},
    ]
    if review_false:
        sources.append({"id": "noreview", "name": "No review", "license": "MIT", "license_class": "bundle", "register": "ui",
                        "review_process": False, "version": "1", "format": "po", "files": [{"locale": "tr-TR", "path": "missing.po"}]})
    if with_missing:
        sources.append({"id": "uncached", "name": "Uncached", "license": "MIT", "license_class": "bundle", "register": "ui",
                        "review_process": True, "version": "1", "format": "po", "files": [{"locale": "tr-TR", "url": "https://example.org/none.po"}]})
    manifest = write_json(td / "sources.manifest.json", {"schema": 1, "sources": sources})
    ref = td / "reference.csv"
    write_text(ref, "key,en,tr-TR,category,speaker\n"
               "UI_SET,Settings,Ayarlar,ui,\n"
               "UI_CANCEL,Cancel,İptal,ui,\n"
               "DLG_1,Take your time kid. The generator is not going anywhere.,Acele etme evlat. Jeneratör bir yere kaçmıyor.,dialogue,Mentor\n"
               "LTR_1,We regret to inform you that the contract was cancelled.,Sözleşmenin iptal edildiğini üzülerek bildiririz.,letter,Bank\n")
    scenario = write_json(td / "scenario.json", {
        "roundtrip": [{"contains": "Atölyeyi bu gece", "back": "Close the workshop tonight after you put every tool back."}],
        "scores": [{"contains": "çok uzun sürecek", "family": "google", "score": 3, "issue_type": "register"}],
    })
    return {"manifest": manifest, "cache": cache, "ref": ref, "scenario": scenario}


def build(paths: Dict[str, Path], td: Path, locale: str = "tr-TR", **kw: Any) -> Dict[str, Any]:
    router = Router(load_providers_config(), dry_run=True, scenario=FakeScenario.load(paths.get("scenario")))
    return blp.build_pack(paths["manifest"], locale, td / "packs", paths["cache"], offline=True, references=[paths["ref"]] if "ref" in paths else [],
                          router=router, mt_check=True, jury_screen=True, min_words=6, registers=("dialogue_casual", "dialogue_formal"), **kw)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class ParserTests(unittest.TestCase):
    def test_properties(self):
        d = blp.parse_properties("# c\n! c\na = b\nkey:value\nmulti = one \\\n    two\nesc = caf\\u00e9\\nline\nspaced\\ key = x\n")
        self.assertEqual(d["a"], "b")
        self.assertEqual(d["key"], "value")
        self.assertEqual(d["multi"], "one two")
        self.assertEqual(d["esc"], "café\nline")
        self.assertEqual(d["spaced key"], "x")

    def test_openttd(self):
        d = blp.parse_openttd("##name Turkish\n# comment\nSTR_A      :Yeşil\nSTR_B.tamlanan :x\nSTR_C   :{BLACK}Mavi\n")
        self.assertEqual(d, {"STR_A": "Yeşil", "STR_C": "{BLACK}Mavi"})

    def test_ftl(self):
        d = blp.parse_ftl("# c\nhello = Merhaba\nmulti =\n    satır bir\n    satır iki\nbtn = Kaydet\n    .tooltip = Dosyayı kaydet\n"
                          "sel = { $n ->\n   *[other] x\n}\n-term = Marka\n")
        self.assertEqual(d["hello"], "Merhaba")
        self.assertEqual(d["multi"], "satır bir\nsatır iki")
        self.assertEqual(d["btn"], "Kaydet")
        self.assertEqual(d["btn.tooltip"], "Dosyayı kaydet")
        self.assertNotIn("sel", d)
        self.assertNotIn("-term", d)

    def test_flatten_json(self):
        self.assertEqual(blp.flatten_json({"a": {"b": "x", "c": ["y", 1]}}), {"a.b": "x", "a.c.0": "y"})

    def test_infer_register(self):
        self.assertEqual(blp.infer_register("ui_button", "Kaydet", "game"), "ui")
        self.assertEqual(blp.infer_register("letter", "Uzun bir mektup metni burada duruyor.", "game"), "dialogue_formal")
        self.assertEqual(blp.infer_register("dialogue", "Acele etme evlat.", "game"), "dialogue_casual")
        self.assertEqual(blp.infer_register("tutorial", "Kaydetmek için tuşa bas.", "game"), "tutorial")
        self.assertEqual(blp.infer_register("", "Tamam", "game"), "ui")
        self.assertEqual(blp.infer_register("", "Hadi ama, bu kadar da zor olamaz değil mi?", "game"), "dialogue_casual")
        self.assertEqual(blp.infer_register("", "Bu bina her gün belirli miktarda enerji üretir ve depolar.", "ui"), "tutorial")


class BundledManifestTests(unittest.TestCase):
    def test_bundled_manifest_is_valid_and_clean(self):
        data = blp.load_manifest(BUNDLED_MANIFEST)
        text = BUNDLED_MANIFEST.read_text(encoding="utf-8").lower()
        self.assertNotIn("opensubtitles", text)
        ids = [s["id"] for s in data["sources"]]
        for needed in ("wesnoth", "0ad", "mindustry", "veloren", "openttd", "kde", "gnome-chess", "libreoffice-calc"):
            self.assertIn(needed, ids)
        for s in data["sources"]:
            self.assertIn(s["license_class"], ("bundle", "local"), s["id"])
            self.assertTrue(s.get("license"), s["id"])
            for f in s["files"]:
                self.assertTrue(f["url"].startswith("https://"), f["url"])
        gpl = [s for s in data["sources"] if "GPL" in s["license"] or "MPL" in s["license"]]
        self.assertTrue(gpl and all(s["license_class"] == "local" for s in gpl))
        locales = {blp.normalize_locale(f["locale"])[0] for s in data["sources"] for f in s["files"]}
        self.assertTrue({"tr-TR", "de-DE"} <= locales)

    def test_excluded_corpus_is_refused(self):
        with TempDir() as td:
            m = write_json(td / "m.json", {"schema": 1, "sources": [{"id": "opensubtitles", "name": "OpenSubtitles", "license_class": "local",
                                                                       "format": "po", "files": []}]})
            with self.assertRaises(L10nError):
                blp.load_manifest(m)
            code, _, err = run_cli("build_language_pack.py", str(m), "--locale", "tr-TR", "--langpack-dir", str(td / "p"), "--offline", env_extra=NO_KEYS)
            self.assertEqual(code, 2)
            self.assertIn("excluded", err)

    def test_gitignore_covers_local_class(self):
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("langpack/*/local/", gi)
        self.assertIn("loc_work/", gi)
        self.assertIn("*.sqlite", gi)


class BuildTests(unittest.TestCase):
    def test_tr_pack_five_layers(self):
        with TempDir() as td:
            paths = make_tr_corpus(td)
            res = build(paths, td)
            self.assertEqual(res["load_failures"], [])
            pack = td / "packs" / "tr-TR"
            m = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
            f = m["filters"]
            # layer 1: policy drop + kept sources
            l1 = f["layer1_source_selection"]
            self.assertEqual([d["id"] for d in l1["dropped"]], ["noreview"])
            self.assertEqual(l1["sources_kept"], 5)  # 4 manifest sources + reference
            # layer 2: every mechanical reason drops at least one row, and rows pass
            l2 = f["layer2_mechanical"]
            for reason in ("empty", "fuzzy", "untranslated", "length_ratio", "ban_list", "technical", "duplicate"):
                self.assertGreaterEqual(l2["dropped"].get(reason, 0), 1, reason)
            self.assertGreater(l2["out"], 0)
            # layer 3: bulk commit and verbatim back-translation
            l3 = f["layer3_mt_detection"]
            self.assertTrue(l3["applied"])
            self.assertEqual(l3["dropped"]["bulk_commit"], 501)
            self.assertEqual(l3["dropped"]["roundtrip_identical"], 1)
            self.assertGreaterEqual(l3["checked"], 2)
            # layer 4: disputed rendering dropped, trusted term kept
            l4 = f["layer4_cross_consistency"]
            self.assertEqual(l4["dropped"], {"disputed": 1})
            self.assertGreaterEqual(l4["trusted"], 1)
            # layer 5: one line below the pass mark, sample written
            l5 = f["layer5_jury_prescreen"]
            self.assertEqual(l5["dropped"], {"jury_below_pass": 1})
            self.assertGreater(l5["out"], 0)
            bundle = read_jsonl(pack / "warmup.jsonl")
            local = read_jsonl(pack / "local" / "warmup.jsonl")
            texts = {r["text"] for r in bundle + local}
            self.assertIn("Ayarlar", texts)
            self.assertNotIn("Seçenekler", texts)               # disputed
            self.assertNotIn(ROUNDTRIP_LINE, texts)              # MT suspect
            self.assertNotIn(JURY_LINE, texts)                   # jury reject
            self.assertIn("Sandık açık", texts)                  # small commit passes
            self.assertIn("Acele etme evlat. Jeneratör bir yere kaçmıyor.", texts)
            self.assertIn("Devam etmek için\ntuşa bas.", texts)
            regs = {r["text"]: r["register"] for r in bundle + local}
            self.assertEqual(regs["Ayarlar"], "ui")
            self.assertEqual(regs["Acele etme evlat. Jeneratör bir yere kaçmıyor."], "dialogue_casual")
            self.assertEqual(regs["Sözleşmenin iptal edildiğini üzülerek bildiririz."], "dialogue_formal")
            trusted = {r["text"]: r["consistency"] for r in bundle + local}
            self.assertEqual(trusted["İptal"], "trusted")
            for name in ("manifest.json", "trust_card.json", "roundtrip_threshold.json", "LICENSES.md", "local/.gitignore"):
                self.assertTrue((pack / name).is_file(), name)
            trust = json.loads((pack / "trust_card.json").read_text(encoding="utf-8"))
            self.assertEqual((trust["trust_level"], trust["basis"]), ("measured", "professional_reference"))
            self.assertEqual(len(trust["known_limits"]), 6)
            lic = (pack / "LICENSES.md").read_text(encoding="utf-8")
            self.assertIn("Godot like", lic)
            self.assertNotRegex(lic, r"[;–—]")

    def test_local_class_never_leaves_local_dir(self):
        with TempDir() as td:
            paths = make_tr_corpus(td)
            build(paths, td, sample_size=50)
            pack = td / "packs" / "tr-TR"
            local_rows = read_jsonl(pack / "local" / "warmup.jsonl")
            self.assertTrue(local_rows)
            self.assertTrue(all(r["license_class"] == "local" for r in local_rows))
            bundle_rows = read_jsonl(pack / "warmup.jsonl")
            self.assertTrue(all(r["license_class"] == "bundle" for r in bundle_rows))
            bundle_texts = {r["text"] for r in bundle_rows}
            local_only = [r["text"] for r in local_rows if r["text"] not in bundle_texts and len(r["text"]) > 6]
            self.assertTrue(local_only)
            for path in pack.iterdir():
                if path.is_file():
                    content = path.read_text(encoding="utf-8")
                    for text in local_only:
                        self.assertNotIn(json.dumps(text, ensure_ascii=False)[1:-1], content, f"local text leaked into {path.name}")
            sample_local = read_jsonl(pack / "local" / "prescreen_sample.jsonl")
            self.assertTrue(all(s["license_class"] == "local" for s in sample_local))

    def test_deterministic(self):
        with TempDir() as td:
            paths = make_tr_corpus(td)
            build(paths, td)
            pack = td / "packs" / "tr-TR"
            first = {p: (pack / p).read_text(encoding="utf-8") for p in ("warmup.jsonl", "manifest.json", "local/warmup.jsonl", "local/prescreen_sample.jsonl")}
            build(paths, td)
            for p, txt in first.items():
                self.assertEqual((pack / p).read_text(encoding="utf-8"), txt, p)

    def test_de_pack_from_openttd_and_json(self):
        with TempDir() as td:
            cache = td / "cache"
            url_de, url_en = "https://example.org/lang/german.txt", "https://example.org/lang/english.txt"
            for url, body in ((url_de, "##name German\nSTR_SAVE  :Spiel speichern\nSTR_QUIT  :Beenden\nSTR_GO   :Los geht's, Leute!\n"),
                              (url_en, "##name English\nSTR_SAVE  :Save game\nSTR_QUIT  :Quit\nSTR_GO   :Let's go, folks!\n")):
                p = blp.cache_path(cache, "ottd", url)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body, encoding="utf-8")
            write_json(td / "en.json", {"menu": {"save": "Save", "load": "Load game"}})
            write_json(td / "de.json", {"menu": {"save": "Speichern", "load": "Spiel laden"}})
            manifest = write_json(td / "m.json", {"schema": 1, "sources": [
                {"id": "ottd", "name": "OTTD", "license": "GPL-2.0", "license_class": "local", "register": "game", "review_process": True,
                 "version": "14.1", "format": "openttd", "files": [{"locale": "de", "url": url_de, "en_url": url_en}]},
                {"id": "jsonui", "name": "JSON UI", "license": "MIT", "license_class": "bundle", "register": "ui", "review_process": True,
                 "version": "1", "format": "json_nested", "files": [{"locale": "de-DE", "path": "de.json", "en_path": "en.json"}]},
            ]})
            code, out, err = run_cli("build_language_pack.py", str(manifest), "--locale", "de-DE", "--langpack-dir", str(td / "packs"),
                                     "--cache-dir", str(cache), "--offline", "--json", env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertEqual(data["counts"]["bundle"], 2)
            self.assertEqual(data["counts"]["local"], 3)
            self.assertFalse(data["filters"]["layer3_mt_detection"]["applied"])
            self.assertFalse(data["filters"]["layer5_jury_prescreen"]["applied"])
            trust = json.loads((td / "packs" / "de-DE" / "trust_card.json").read_text(encoding="utf-8"))
            self.assertEqual(trust["trust_level"], "estimated")

    def test_hash_pin_mismatch_and_lock(self):
        with TempDir() as td:
            paths = make_tr_corpus(td, review_false=False)
            data = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            data["sources"][0]["files"][0]["sha256"] = "0" * 64
            write_json(paths["manifest"], data)
            res = build(paths, td)
            self.assertEqual([d["id"] for d in res["load_failures"]], ["godot-like"])
            self.assertIn("sha256 mismatch", res["load_failures"][0]["reason"])
            data["sources"][0]["files"][0]["sha256"] = None
            write_json(paths["manifest"], data)
            build(paths, td, lock_hashes=True)
            locked = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            self.assertRegex(locked["sources"][0]["files"][0]["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(locked["sources"][1]["files"][0]["en_sha256"], r"^[0-9a-f]{64}$")


class CliTests(unittest.TestCase):
    def test_exit_codes(self):
        with TempDir() as td:
            paths = make_tr_corpus(td)
            base = [str(paths["manifest"]), "--locale", "tr", "--langpack-dir", str(td / "packs"), "--cache-dir", str(paths["cache"]), "--offline",
                    "--reference", str(paths["ref"])]
            code, out, err = run_cli("build_language_pack.py", *base, "--mt-check", "--jury-screen", "--dry-run", "--fake-scenario", str(paths["scenario"]),
                                     "--budget-log", str(td / "budget.jsonl"), env_extra=NO_KEYS)
            self.assertEqual(code, 0, err)
            self.assertIn("Layer 5 jury pre-screen", out)
            self.assertTrue((td / "budget.jsonl").is_file())
            sub = td / "second"
            sub.mkdir()
            paths2 = make_tr_corpus(sub, with_missing=True)
            code, out, err = run_cli("build_language_pack.py", str(paths2["manifest"]), "--locale", "tr-TR", "--langpack-dir", str(td / "packs2"),
                                     "--cache-dir", str(paths2["cache"]), "--offline", env_extra=NO_KEYS)
            self.assertEqual(code, 1, err)
            self.assertIn("not cached", out)
            code, _, err = run_cli("build_language_pack.py", *base, "--mt-check", env_extra=NO_KEYS)  # no key, no --dry-run
            self.assertEqual(code, 2)
            self.assertIn("DEEPSEEK_API_KEY", err)
            self.assertEqual(run_cli("build_language_pack.py", str(paths["manifest"]), "--locale", "xx-XX", env_extra=NO_KEYS)[0], 2)
            self.assertEqual(run_cli("build_language_pack.py", "--locale", "tr-TR", env_extra=NO_KEYS)[0], 2)

    def test_help_flags_documented(self):
        doc = (SCRIPTS / "CLI_REFERENCE.md").read_text(encoding="utf-8")
        self.assertTrue("build_language_pack.py" in doc, "build_language_pack.py missing from CLI_REFERENCE.md")
        code, help_text, _ = run_cli("build_language_pack.py", "--help")
        self.assertEqual(code, 0)
        for flag in sorted(set(re.findall(r"(?m)^\s+(--[a-z][a-z0-9-]+)", help_text))):
            self.assertIn(flag, doc, f"build_language_pack.py: {flag} missing from CLI_REFERENCE.md")


if __name__ == "__main__":
    unittest.main()
