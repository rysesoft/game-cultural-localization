"""ContextPack prompts, juror leak detection, coverage summary and scan_summary Markdown rendering."""

import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gcl.domain.errors import L10nError

__layer__ = "application"
__pattern__ = "Application Service"
__owns__ = "ContextPack prompt enrichment, jury leak checking and scan summary formatting"

JUROR_FIELDS = ("screen", "element", "player_action", "inserted", "limit", "speaker", "listener", "register_hint")
JURY_MAP = "CONTEXT_MAP.jury.md"
JURY_NOTES = "line_notes.jury.json"
WRITER_FIELDS = JUROR_FIELDS + ("notes",)
MAP_HEADER = (
    "# Context map of this game\n\n"
    "Read this map before the first line. It describes the game, its world, its systems and its screens, as a professional "
    "translator learns them from the code before translating. It never decides a word for you. The same source word takes "
    "different words in your language depending on where the game shows it, so judge and write every line for its place. "
    "An item may carry a `context` object with the screen and the element that show the line, what the player is doing, "
    "what the code inserts next to it, the room it has, the speaker and the listener. Read it before you judge or write the "
    "line. `screen` and `element` tell a button from a title, a toast or a letter, `player_action` tells what the player "
    "wants in that moment. `inserted` names what the code puts next to the text when the game runs, a name, a number, a "
    "unit or another text. The line must still read right together with it, a label the code follows with a colon and a "
    "number takes no punctuation of its own, and a sentence the code ends with a name must take that name in the grammar "
    "of your language. `limit` is the room the line has. `speaker` and `listener` set the voice and the form of address."
)
APPENDIX_HEADER = (
    "# Decisions of the existing {locale} version\n\n"
    "The published {locale} version of the game made these choices. Stay consistent with them unless the context of a line "
    "says otherwise. Keep the form of address it sets for every character, a character who speaks formally to the player "
    "does so to the last line."
)
_WORD = re.compile(r"[^\W\d_]{4,}")


def _read_utf8(path: Path) -> str:
    p = str(path.resolve())
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _plain_labels(notes: dict[str, dict[str, Any]]) -> dict[str, str]:
    plain: dict[str, list[str]] = defaultdict(list)
    for label in notes:
        if ":" in label:
            plain[label.split(":", 1)[1]].append(label)
    return {k: v[0] for k, v in plain.items() if len(v) == 1}


def _load_notes(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(_read_utf8(path).lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        raise L10nError(f"{path}: invalid JSON at line {exc.lineno}: {exc.msg}")
    if not isinstance(data, dict):
        raise L10nError(f"{path}: expected an object {{key: line note}}")
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


@dataclass(slots=True)
class ContextPack:
    """CONTEXT_MAP.md, per-key line notes and locale appendix for model prompts."""

    text: str = ""
    notes: dict[str, dict[str, Any]] = field(default_factory=dict)
    appendix: str = ""
    locale: str = ""
    source: str = ""
    jury_text: str = ""
    jury_notes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _plain: dict[str, str] = field(init=False, repr=False)
    _jury_plain: dict[str, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._plain = _plain_labels(self.notes)
        self._jury_plain = _plain_labels(self.jury_notes)

    def line(self, key: str, writer: bool = False) -> dict[str, str]:
        """Return context fields for one key obeying blind juror segregation."""
        notes, plain = (self.jury_notes, self._jury_plain) if not writer and self.jury_notes else (self.notes, self._plain)
        n = notes.get(key) or notes.get(plain.get(key, ""), {})
        return {f: str(n[f]) for f in (WRITER_FIELDS if writer else JUROR_FIELDS) if n.get(f)}

    def system(self, base: str, writer: bool = False) -> str:
        """Append context map and writer-only appendix onto base system prompt."""
        text = self.jury_text if not writer and self.jury_text else self.text
        if not text:
            return base
        out = base.rstrip() + "\n\n" + MAP_HEADER + "\n\n" + text.strip() + "\n"
        if writer and self.appendix:
            out += "\n" + APPENDIX_HEADER.format(locale=self.locale) + "\n\n" + self.appendix.strip() + "\n"
        return out

    def enrich(self, items: Sequence[dict[str, Any]], key_field: str = "key", writer: bool = False) -> int:
        """Attach context dicts to items missing them and return enriched count."""
        n = 0
        for it in items:
            if it.get("context"):
                continue
            ctx = self.line(str(it.get(key_field, "")), writer)
            if ctx:
                it["context"] = ctx
                n += 1
        return n


def load_context(map_path: Path | None, locale: str = "") -> ContextPack:
    """Build ContextPack from CONTEXT_MAP.md and adjacent jury/line-note files."""
    if map_path is None:
        return ContextPack()
    map_path = Path(map_path)
    if not map_path.is_file():
        raise L10nError(f"--context-map file not found: {map_path}")
    text = _read_utf8(map_path).lstrip("\ufeff")
    if not text.strip():
        raise L10nError(f"{map_path}: the context map is empty")
    notes = _load_notes(map_path.with_name("line_notes.json"))
    appendix_path = map_path.with_name(f"{map_path.stem}.{locale}.md") if locale else None
    appendix = _read_utf8(appendix_path).lstrip("\ufeff") if appendix_path is not None and appendix_path.is_file() else ""
    jury_path = map_path.with_name(JURY_MAP)
    jury_text = _read_utf8(jury_path).lstrip("\ufeff") if jury_path.is_file() else ""
    return ContextPack(text, notes, appendix, locale, map_path.name, jury_text, _load_notes(map_path.with_name(JURY_NOTES)))


def _words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(text or "")}


def target_only_words(rows: Sequence[Any]) -> set[str]:
    """Words of length >= 4 in target texts absent from source texts."""
    src: set[str] = set()
    tgt: set[str] = set()
    for r in rows:
        src |= _words(r.src)
        tgt |= _words(r.dst)
    return tgt - src


def check_leak(pack: ContextPack, rows: Sequence[Any], quote_min: int = 25) -> dict[str, Any]:
    """Scan jurors' context view for existing-translation vocabulary or quoted source lines."""
    vocab = target_only_words(rows)
    texts: list[tuple[str, str]] = [("map", pack.jury_text or pack.text)]
    for key in (pack.jury_notes or pack.notes):
        texts.append((key, " ".join(pack.line(key).values())))
    hits: Counter[str] = Counter()
    first: dict[str, str] = {}
    leaky_notes = 0
    for name, text in texts:
        found = _words(text) & vocab
        if found and name != "map":
            leaky_notes += 1
        for w in found:
            hits[w] += 1
            first.setdefault(w, name)
    sources = {r.src.strip().casefold() for r in rows if len(r.src.strip()) >= quote_min}
    juror_text = "\n".join(t for _, t in texts).casefold()
    return {
        "view": "jury" if pack.jury_text or pack.jury_notes else "user map",
        "words": [[w, n, first[w]] for w, n in hits.most_common()],
        "notes_with_leaks": leaky_notes, "notes": len(texts) - 1,
        "quoted_source_lines": sorted(s for s in sources if s in juror_text),
    }


def summary(scan: dict[str, Any], wanted: Sequence[str] | None = None) -> dict[str, Any]:
    """Summarize per-table coverage, concatenation lines and missing/unused keys."""
    keys = scan["keys"]
    per_table: dict[str, dict[str, Any]] = defaultdict(lambda: {"keys": 0, "used": 0, "classes": Counter()})
    for _k, info in keys.items():
        t = per_table[info["table"]]
        t["keys"] += 1
        t["used"] += 1 if info["usages"] else 0
        for u in info["usages"]:
            t["classes"][u["class"] or "unknown"] += 1
    out: dict[str, Any] = {
        "tables": {
            name: {"keys": t["keys"], "used": t["used"], "classes": [c for c, _ in t["classes"].most_common(4)]}
            for name, t in sorted(per_table.items())
        },
        "keys": len(keys), "used": sum(1 for i in keys.values() if i["usages"]),
        "concat_lines": len({(c["file"], c["line"]) for i in keys.values() for c in i["code"] if c["concat"]}),
        "dangling_references": scan.get("unresolved_references", 0),
        "missing_table_references": scan.get("missing_table_references", {}),
    }
    if "use_trace" in scan:
        out["with_uses"] = sum(1 for i in keys.values() if i.get("uses"))
        out["loaded_not_shown"] = sorted(k for k, i in keys.items() if i.get("loaded_not_shown"))
    if wanted is not None:
        shared_names: dict[str, list[str]] = defaultdict(list)
        for k, info in keys.items():
            if info.get("name"):
                shared_names[info["name"]].append(k)
        out["wanted"] = len(wanted)
        out["wanted_missing"] = [
            k for k in wanted
            if not keys.get(k, {}).get("usages") and not any(keys[x]["usages"] for x in shared_names.get(k, []))
        ]
    return out


def render_summary(scan: dict[str, Any], s: dict[str, Any]) -> str:
    """Render scan_summary.md in house style."""
    lines = [
        f"# Context scan of {scan['project']}", "",
        f"Engine {scan['engine']}. {s['keys']} keys in {len(scan['tables'])} string tables, {s['used']} of them have at least one usage in a prefab, scene or data asset.",
        f"{s['concat_lines']} code lines glue a localized text to something else (a name, a number or another text). They belong in the transcreation ledger as concatenation seams.",
    ]
    if s.get("dangling_references"):
        lines.append(f"{s['dangling_references']} references point to a key (by id or by name) that its table no longer has. The game shows nothing or a fallback there, list them as game bugs.")
    if s.get("missing_table_references"):
        gone = ", ".join(f"{t} ({n})" for t, n in s["missing_table_references"].items())
        lines.append(f"References to tables the project no longer has, usually an old system that was replaced. {gone}.")
    if "with_uses" in s:
        lines.append(
            f"The use trace found the code that reads the text of {s['with_uses']} keys, with the method, the conditions around "
            f"the line and the text glued on. {len(s['loaded_not_shown'])} keys are loaded into a variable the code never reads, "
            "so the game never shows them. The trace is a heuristic search of the C# code, read the code before you list such a key as a game bug."
        )
    lines.append("")
    if "wanted" in s:
        lines.append(f"Of the {s['wanted']} keys of the reference table, {s['wanted'] - len(s['wanted_missing'])} have a usage and {len(s['wanted_missing'])} have none.")
        lines.append("")
    lines += ["| Table | Keys | With usage | Main classes |", "|---|---|---|---|"]
    for name, t in s["tables"].items():
        lines.append(f"| {name} | {t['keys']} | {t['used']} | {', '.join(t['classes']) or 'none found'} |")
    if s.get("wanted_missing"):
        lines += ["", "Keys without a usage (first 40). The agents look for them in the code by name.", ""]
        lines += [f"- `{k}`" for k in s["wanted_missing"][:40]]
    if s.get("loaded_not_shown"):
        lines += ["", "Keys loaded but never shown (first 40). Each one is a game bug or a leftover, ask the user before anyone translates it.", ""]
        lines += [f"- `{k}`" for k in s["loaded_not_shown"][:40]]
    return "\n".join(lines) + "\n"
