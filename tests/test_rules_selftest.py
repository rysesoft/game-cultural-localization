"""Rule-file self-test: every rule compiles, every example behaves, ids unique, ban-table coverage >= 70 %."""
from __future__ import annotations

import json
import re
import unittest

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _helpers import SCRIPTS  # noqa: E402

import lqa_linter  # noqa: E402
from l10n_common import CANONICAL_LOCALES, DEFAULT_RULES_DIR, L10nError, Row  # noqa: E402

FLAGS = {"i": re.I, "m": re.M, "x": re.X, "s": re.S}

# Ban-table examples copied from references/<locale>.md §1/§2 ("BAN!" columns). The linter must flag >= 70 % per locale.
BAN_EXAMPLES = {
    "tr-TR": ["Sen bunu yapabilirsin.", "Gemi korsanlar tarafından yakıldı.", "Burada zaten bir eşya bulunmaktadır!", "Bu eşya buraya yerleştirilemez.",
              "Bu alete zaten sahipsin!", "Kondisyonun çok düşük!", "Uyku süresi çok kısa.", "Mevcut siparişi iptal etmeden yükseltme yapamazsın.", "Onarımı gerçekleştir."],
    "de-DE": ["Fokussieren", "KONSTRUIEREN", "Vorwärts bewegen", "GEGENSTÄNDE ENTNEHMEN", "Hier befindet sich bereits ein Gegenstand!",
              "Dieser Gegenstand kann hier nicht platziert werden.", "Du besitzt dieses Werkzeug bereits!", "Deine Ausdauer ist zu niedrig!",
              "Gegenstand veräußern", "Halte X im Lager bereit, indem du es baust.", "Speichere, ehe du gehst.", "Ich hege eine Leidenschaft für Motoren."],
    "fr": ["Procéder à la réparation", "Cet objet ne peut pas être placé à cet endroit.", "Un objet se trouve déjà à cet emplacement !",
           "Vous possédez déjà cet outil !", "Votre endurance est trop faible !", "Les objets ont été transférés vers l'entrepôt.", "Focuser",
           "OBTENIR LES OBJETS", "Déplacer vers l'avant"],
    "es-ES": ["Configuraciones", "Enfocar", "Este objeto no puede ser colocado aquí.", "¡Ya se encuentra un objeto en este lugar!", "¡Ya posees esta herramienta!",
              "¡Tu resistencia es demasiado baja!", "OBTENER OBJETOS", "Mover hacia adelante", "Realizar la reparación", "Computadora"],
    "it-IT": ["Effettuare la riparazione", "Procedere allo smantellamento", "Focalizzare", "Questo oggetto non può essere posizionato qui.",
              "Un oggetto è già presente in questa posizione!", "Possiedi già questo strumento!", "La tua resistenza è troppo bassa!",
              "La durata del sonno è troppo breve.", "OTTIENI OGGETTI", "Muovi in avanti", "Gli oggetti sono stati trasferiti nel magazzino."],
    "pt-BR": ["Definições", "Ecrã", "A carregar...", "Focar", "Este item não pode ser colocado neste local.", "Já existe um item neste local!",
              "Você já possui esta ferramenta!", "Sua resistência está muito baixa!", "OBTER ITENS", "Mover para a frente", "Efetuar o reparo", "Comercializar"],
    "pt-PT": ["Carregando", "Montando", "Configurações", "Salvar", "Tela", "Usuário", "Me ajuda", "Você tem", "Este item não pode ser colocado aqui.",
              "Já se encontra um objeto neste local!", "Já possuis esta ferramenta!", "OBTER ITENS"],
    "pl-PL": ["Ty masz już to narzędzie.", "Twój warsztat posiada trzy stanowiska.", "Fokusuj", "Ten przedmiot nie może zostać umieszczony tutaj.",
              "W tym miejscu znajduje się już przedmiot!", "Posiadasz już to narzędzie!", "Twoja wytrzymałość jest zbyt niska!", "UZYSKAJ PRZEDMIOTY",
              "Poruszaj się do przodu", "Dokonać naprawy", "Zbyć na rynku"],
    "lt-LT": ["Atlikti remontą", "Vykdyti gamybą", "Fokusuoti", "Šis daiktas negali būti čia padėtas.", "Šioje vietoje jau yra daiktas!",
              "Jūs jau turite šį įrankį!", "Tavo ištvermė per žema!", "GAUTI DAIKTUS", "Judėti į priekį", "Perduota į sandėlį", "Realizuoti rinkoje"],
    "ru-RU": ["Осуществлять ремонт", "производить сборку", "Фокусировать", "Данный предмет не может быть размещён здесь.", "В данном месте уже находится предмет!",
              "Вы уже обладаете данным инструментом!", "Ваша выносливость слишком низкая!", "ПОЛУЧИТЬ ПРЕДМЕТЫ", "Двигаться вперёд", "Ты имеешь ключ."],
    "ja-JP": ["あなたは建造することができます", "彼は船を直した", "部品が倉庫へ転送されました", "ここにアイテムを配置することはできません。", "ここにはすでにアイテムが存在します！",
              "このツールはすでに所有しています！", "スタミナが低すぎます！", "フォーカス", "アイテムを取得", "俺はスピードだ！"],
    "ko-KR": ["당신은 할 수 있습니다", "시스템에 의해 파괴되었다", "그녀는 떠났다", "이 아이템은 여기에 배치할 수 없습니다.", "이미 아이템이 존재합니다!",
              "이미 이 도구를 소유하고 있습니다!", "스태미나가 너무 낮습니다!", "포커스", "아이템 획득"],
    "zh-CN": ["你可以去使用扳手来修理", "被海盗所袭击", "无法被放置在这里", "当你完成的时候", "这里已经存在一个物品！", "你已经拥有此工具！", "你的体力过低！",
              "睡眠持续时间太短。", "聚焦", "获取物品", "請設定螢幕解析度"],
    "zh-Hant": ["設置", "默認", "屏幕", "全屏", "分辨率", "鼠標", "空格鍵", "優化", "硅", "信息", "激光", "土辦法", "此處已存在一個物品！", "被海盜所襲擊"],
    "en": ["In order to proceed with the operation, utilize the panel", "Item placement failed in current area.", "TODO: write this"],
}


class RuleFileTests(unittest.TestCase):
    def test_every_rule_file_loads_and_examples_hold(self):
        for loc in CANONICAL_LOCALES:
            path = DEFAULT_RULES_DIR / f"{loc}.json"
            self.assertTrue(path.is_file(), path)
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            self.assertEqual(data["locale"], loc)
            ids = set()
            for raw in data["rules"]:
                self.assertNotIn(raw["id"], ids, f"duplicate id {raw['id']} in {loc}")
                ids.add(raw["id"])
                flags = 0
                for ch in raw.get("flags", ""):
                    flags |= FLAGS[ch]
                rx = re.compile(raw["pattern"], flags)
                ex = raw.get("examples", {})
                self.assertTrue(ex.get("match"), f"{loc}/{raw['id']} has no match example")
                for s in ex.get("match", []):
                    self.assertIsNotNone(rx.search(s), f"{loc}/{raw['id']} should match {s!r}")
                for s in ex.get("nomatch", []):
                    self.assertIsNone(rx.search(s), f"{loc}/{raw['id']} must not match {s!r}")
            # loads through the real loader too (incl. custom dir and variant handling)
            self.assertTrue(lqa_linter.load_rules(loc))
            lqa_linter.load_rules(loc, "hk")

    def test_ban_table_coverage(self):
        for loc, examples in BAN_EXAMPLES.items():
            rules = lqa_linter.load_rules(loc)
            opt = lqa_linter.LintOptions(locale=loc, check_untranslated=False)
            hit = 0
            misses = []
            for ex in examples:
                findings = lqa_linter.lint_rows([Row("k", "", ex, {})], rules, opt)
                if any(f.code not in ("EMPTY",) for f in findings):
                    hit += 1
                else:
                    misses.append(ex)
            ratio = hit / len(examples)
            self.assertGreaterEqual(ratio, 0.7, f"{loc}: only {hit}/{len(examples)} ban examples flagged; misses: {misses}")

    def test_known_false_positives_are_clean(self):
        clean = {
            "de-DE": ["Die Ehe von Anna und Max.", "Ehe-Ring", "100% fertig", "Der Platz ist schon belegt!"],
            "fr": ["Niveau 3 · Boss final", "100% des dégâts", "Il fait beau."],
            "it-IT": ["Le lettere esse e ti", "ESSO"],
            "es-ES": ["Modo foto: enfocar la cámara", "100% de daño", "¿Seguro que quieres salir?"],
            "ru-RU": ["Производить детали", "Собирать"],
            "zh-Hant": ["系統設定完成", "解析度"],
            "zh-CN": ["请设置屏幕分辨率", "没问题"],
            "pt-BR": ["Ajude a carregar o caminhão.", "Carregando..."],
            "tr-TR": ["ISINMA", "ÇIKIŞ", "Bu alet sende zaten var!"],
            "ko-KR": ["{0}을(를) 획득했습니다", "할 수 있습니다"],
            "ja-JP": ["建造できます", "ここには置けない。"],
        }
        for loc, examples in clean.items():
            rules = lqa_linter.load_rules(loc)
            opt = lqa_linter.LintOptions(locale=loc, check_untranslated=False)
            for ex in examples:
                findings = [f for f in lqa_linter.lint_rows([Row("k", "", ex, {})], rules, opt) if f.severity == "ERR"]
                self.assertEqual(findings, [], f"{loc}: {ex!r} raised ERR {findings}")

    def test_variant_and_context(self):
        tw = lqa_linter.load_rules("zh-Hant")
        hk = lqa_linter.load_rules("zh-Hant", "hk")
        opt = lqa_linter.LintOptions(locale="zh-Hant", check_untranslated=False)
        sev_tw = {f.code: f.severity for f in lqa_linter.lint_rows([Row("k", "", "激光砲", {})], tw, opt)}
        sev_hk = {f.code: f.severity for f in lqa_linter.lint_rows([Row("k", "", "激光砲", {})], hk, opt)}
        self.assertEqual(sev_tw.get("ZHHANT-HK-TERMS"), "ERR")
        self.assertEqual(sev_hk.get("ZHHANT-HK-TERMS"), "WARN")
        self.assertTrue(any(f.code == "ZHHANT-CANTONESE" for f in lqa_linter.lint_rows([Row("k", "", "佢係邊個？", {})], tw, opt)))
        self.assertFalse(any(f.code == "ZHHANT-CANTONESE" for f in lqa_linter.lint_rows([Row("k", "", "佢係邊個？", {})], hk, opt)))
        de = lqa_linter.load_rules("de-DE")
        opt = lqa_linter.LintOptions(locale="de-DE", check_untranslated=False)
        untagged = lqa_linter.lint_rows([Row("k", "", "Gut gemacht, Junge.", {})], de, opt)
        tagged = lqa_linter.lint_rows([Row("k", "", "Gut gemacht, Junge.", {"player": True})], de, opt)
        self.assertFalse(any(f.code == "DE-GENDERED-ADDRESS" for f in untagged))
        self.assertTrue(any(f.code == "DE-GENDERED-ADDRESS" for f in tagged))
        btn = lqa_linter.lint_rows([Row("BTN_APPLY", "", "Anwenden", {})], de, opt)
        self.assertTrue(any(f.code == "DE-ANWENDEN-BUTTON" for f in btn))
        ignored = lqa_linter.lint_rows([Row("k", "", "Fokussieren", {"lqa_ignore": "DE-FOKUSSIEREN"})], de, opt)
        self.assertFalse(any(f.code == "DE-FOKUSSIEREN" for f in ignored))

    def test_invalid_rule_files_are_rejected(self):
        from _helpers import TempDir, write_json
        with TempDir() as td:
            bad = write_json(td / "bad.json", {"locale": "de-DE", "rules": [{"id": "X", "severity": "ERR", "pattern": "(", "message": "m"}]})
            with self.assertRaises(L10nError):
                lqa_linter.load_rules("de-DE", None, [td])
            dup = write_json(td / "bad.json", {"locale": "de-DE", "rules": [{"id": "DE-EHE", "severity": "ERR", "pattern": "x", "message": "m"}]})
            with self.assertRaises(L10nError):
                lqa_linter.load_rules("de-DE", None, [td])
            write_json(td / "bad.json", {"locale": "de-DE", "rules": [{"id": "X", "severity": "FATAL", "pattern": "x", "message": "m"}]})
            with self.assertRaises(L10nError):
                lqa_linter.load_rules("de-DE", None, [td])
            ok = write_json(td / "ok.json", {"locale": "de", "rules": [{"id": "PROJ-1", "severity": "WARN", "pattern": "\\bSie\\b", "message": "m"}]})
            (td / "bad.json").unlink()
            rules = lqa_linter.load_rules("de-DE", None, [td])
            self.assertIn("PROJ-1", {r.id for r in rules})
            with self.assertRaises(L10nError):
                lqa_linter.load_rules("de-DE", None, [td / "missing"])


if __name__ == "__main__":
    unittest.main()