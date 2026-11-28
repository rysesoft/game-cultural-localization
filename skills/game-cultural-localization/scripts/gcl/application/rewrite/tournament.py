"""Pass 2 candidate tournament enforcing WriterContextView vs BlindContextView and LineState."""

import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any

from gcl.application.jury.policy import classify
from gcl.application.rewrite.recheck_policy import pick_runner_up, recheck_confirmed
from gcl.application.tasks.concrete_tasks import pass2_candidates, pick_candidates, score_entries
from gcl.application.tasks.prompts import ISSUE_TYPES
from gcl.domain.errors import L10nError
from gcl.domain.house_style import sanitize_prose
from gcl.domain.line_state import FlaggedForRewriteState, LineState
from gcl.ports.context import BlindContextView, WriterContextView
from gcl.ports.formats import TokenParityPort
from gcl.ports.pipeline import CritiqueValidatorPort

__layer__ = "application"
__pattern__ = "State and Segregated Tournament"
__owns__ = "Pass 2 candidate writing, blind J1 candidate selection, validation and J1 confirmation recheck"

DEFAULT_STATUSES: tuple[str, ...] = ("rewrite_light", "rewrite", "critical", "unresolved")
CONTEXT_FIELDS: tuple[str, ...] = ("register", "category", "speaker", "archetype")


@dataclass(frozen=True, slots=True)
class TournamentOptions:
    """Parameter object driving Pass 2 rewrite tournament."""

    pass2_system: str
    pick_system: str
    n: int = 3
    seed: int = 1234
    ph_style: str = "auto"
    tag_style: str = "auto"
    statuses: tuple[str, ...] = DEFAULT_STATUSES
    source_file: str = ""
    workers: int = 1
    writer_context: WriterContextView | None = None
    blind_context: BlindContextView | None = None
    memo: Any = None
    tiered: bool = False
    light_candidates: int = 2
    unanimous_skip_recheck: bool = False
    item_memo: Any = None
    salvage_truncated: bool = False


def _jury_tier(router: Any, tier: str, task_role: str) -> Any:
    try:
        return router.jury(tier, task_role=task_role)
    except TypeError:
        return router.jury(tier)


@dataclass(slots=True)
class _TournamentSelection:
    """Bundled winner selection state passed to parallel J1 confirmation recheck."""

    lines: list[dict[str, Any]]
    rows: Sequence[dict[str, Any]]
    states: dict[str, LineState]
    entries: list[dict[str, Any]]
    valid_ranks: dict[str, list[int]]


def final_votes(verdict: dict[str, Any]) -> list[dict[str, Any]]:
    tier = verdict.get("final_tier")
    return [v for v in verdict.get("votes", []) if v.get("tier") == tier]


def main_issue(verdict: dict[str, Any]) -> str:
    types = [v.get("issue_type") for v in final_votes(verdict) if v.get("issue_type") not in (None, "none")]
    it = Counter(types).most_common(1)[0][0] if types else "other"
    return it if it in ISSUE_TYPES and it != "none" else "other"


class Pass2Tournament:
    """Coordinates Pass 2 candidate synthesis, blind J1 selection, validation and J1 recheck."""

    def __init__(self, validator: CritiqueValidatorPort, parity: TokenParityPort, **kw: Any) -> None:
        self._validator = validator
        self._parity = parity
        self._pass2_fn = kw.get("pass2_fn") or pass2_candidates
        self._pick_fn = kw.get("pick_fn") or pick_candidates
        self._score_fn = kw.get("score_fn") or score_entries

    def run(
        self,
        verdicts: Sequence[dict[str, Any]],
        sources: dict[str, dict[str, Any]],
        locale: str,
        router: Any,
        opts: TournamentOptions,
    ) -> dict[str, Any]:
        p2_sys = opts.writer_context.build_system(opts.pass2_system) if opts.writer_context else opts.pass2_system
        pk_sys = opts.blind_context.build_system(opts.pick_system) if opts.blind_context else opts.pick_system
        todo = [v for v in verdicts if v.get("status") in opts.statuses]
        missing = [v["key"] for v in todo if v["key"] not in sources]
        if missing:
            raise L10nError(f"keys missing from the source table: {', '.join(missing[:5])}")
        rows = self._prepare_rows(todo, sources, opts.writer_context)
        cands = self._generate_candidates(todo, rows, locale, router, p2_sys, opts) if rows else {}
        items, id_maps = self._shuffle_candidates(rows, cands, opts.seed, opts.blind_context)
        picks = self._run_pickers(router, items, locale, pk_sys, opts)
        sel = self._select_winners(todo, rows, cands, id_maps, picks, locale, opts)
        entries = self._run_recheck(sel, router, locale, pk_sys, opts)
        critique = {
            "locale": locale, "source_file": opts.source_file, "entries": entries,
            "summary": {"total": len(verdicts), "flagged": len(entries), "critical": sum(1 for e in entries if e["score"] <= 2)},
        }
        return {"lines": sel.lines, "critique": critique}

    @staticmethod
    def _prepare_rows(todo: Sequence[dict[str, Any]], sources: dict[str, dict[str, Any]], wctx: WriterContextView | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for v in todo:
            s = sources[v["key"]]
            fv = final_votes(v)
            ban_notes = [f"rule {b.get('rule')}: {b.get('message')}" for b in (v.get("evidence", {}).get("ban_hits") or ()) if b.get("message")]
            raw_rats = list(v.get("rationales", [])) + [n for n in ban_notes if n not in v.get("rationales", ())]
            row: dict[str, Any] = {
                "key": v["key"], "source": s["en"], "target": s["target"],
                **{k: s[k] for k in CONTEXT_FIELDS if s.get(k)},
                "rationales": [r for r in raw_rats if r],
                "suggestions": [x.get("suggested") for x in fv if x.get("suggested")],
                "suggested": next((x.get("suggested") for x in fv if x.get("suggested")), ""),
                "tm": [{"target": t.get("dst", ""), "category": t.get("category", "")} for t in (v.get("evidence", {}).get("tm_neighbors") or [])[:3]],
            }
            odd = list(dict.fromkeys(w for x in fv for w in (x.get("odd_words") or [])))
            if odd:
                row["odd_words"] = odd
            wfields = wctx.line_fields(v["key"]) if wctx is not None else {}
            if wfields:
                row["context"] = wfields
            rows.append(row)
        return rows

    @staticmethod
    def _shuffle_candidates(
        rows: Sequence[dict[str, Any]],
        cands: dict[str, list[str]],
        seed: int,
        bctx: BlindContextView | None,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
        rng = random.Random(seed)
        items: list[dict[str, Any]] = []
        id_maps: dict[str, dict[str, int]] = {}
        for r in rows:
            if r["target"] not in cands[r["key"]]:
                cands[r["key"]] = list(cands[r["key"]]) + [r["target"]]
            texts = cands[r["key"]]
            order = list(range(len(texts)))
            rng.shuffle(order)
            id_maps[r["key"]] = {f"c{i + 1}": idx for i, idx in enumerate(order)}
            bfields = bctx.line_fields(r["key"]) if bctx is not None else {}
            items.append({
                "key": r["key"], **{k: r[k] for k in CONTEXT_FIELDS if r.get(k)},
                **({"context": bfields} if bfields else {}),
                "candidates": [{"id": f"c{i + 1}", "text": texts[idx]} for i, idx in enumerate(order)],
            })
        return items, id_maps

    @staticmethod
    def _task_extra(opts: TournamentOptions) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if opts.item_memo is not None:
            extra["item_memo"] = opts.item_memo
        if opts.salvage_truncated:
            extra["salvage_truncated"] = True
        return extra

    @staticmethod
    def _light_provider(router: Any) -> Any:
        try:
            return router.for_role("pass2_light")
        except L10nError:
            return router.for_role("pass2")

    def _generate_candidates(
        self, todo: Sequence[dict[str, Any]], rows: Sequence[dict[str, Any]], locale: str, router: Any, p2_sys: str, opts: TournamentOptions,
    ) -> dict[str, list[str]]:
        extra = self._task_extra(opts)
        if not opts.tiered:
            return self._pass2_fn(router.for_role("pass2"), rows, locale, n=opts.n, system=p2_sys, workers=opts.workers, memo=opts.memo, **extra)
        status_by_key = {v["key"]: v.get("status") for v in todo}
        light = [r for r in rows if status_by_key.get(r["key"]) == "rewrite_light"]
        heavy = [r for r in rows if status_by_key.get(r["key"]) != "rewrite_light"]
        out: dict[str, list[str]] = {}
        if light:
            out.update(self._pass2_fn(self._light_provider(router), light, locale, n=opts.light_candidates, system=p2_sys, workers=opts.workers, memo=opts.memo, **extra))
        if heavy:
            out.update(self._pass2_fn(router.for_role("pass2"), heavy, locale, n=opts.n, system=p2_sys, workers=opts.workers, memo=opts.memo, **extra))
        return out

    def _run_pickers(self, router: Any, items: list[dict[str, Any]], locale: str, pk_sys: str, opts: TournamentOptions) -> list[tuple[Any, dict[str, str]]]:
        if not items:
            return []
        pickers = _jury_tier(router, "J1", "pick")
        extra = self._task_extra(opts)
        pick = lambda m: self._pick_fn(m.provider, items, locale, system=pk_sys, workers=opts.workers, memo=opts.memo, **extra)
        if int(opts.workers) > 1 and len(pickers) > 1:
            with ThreadPoolExecutor(max_workers=len(pickers)) as ex:
                return list(zip(pickers, ex.map(pick, pickers)))
        return [(m, pick(m)) for m in pickers]

    def _select_winners(
        self, todo: Sequence[dict[str, Any]], rows: Sequence[dict[str, Any]], cands: dict[str, list[str]],
        id_maps: dict[str, dict[str, int]], picks: Sequence[tuple[Any, dict[str, str]]], locale: str, opts: TournamentOptions,
    ) -> _TournamentSelection:
        lines, entries, states, valid_ranks = [], [], {}, {}
        for v, r in zip(todo, rows):
            key, texts, id_map = r["key"], cands[r["key"]], id_maps[r["key"]]
            votes = Counter(id_map[p[key]] for _m, p in picks)
            ranking = sorted(range(len(texts)), key=lambda i: (-votes.get(i, 0), i))
            chosen, valid_ids, problems_all, entry = self._pick_valid(v, r, texts, ranking, locale, opts)
            valid_ranks[key] = valid_ids
            state0 = FlaggedForRewriteState(key, r["source"], r["target"], r["target"], str(v.get("status")))
            states[key] = state0.accept_rewrite(texts[chosen]) if (chosen is not None and texts[chosen] != r["target"]) else state0.keep_original(tuple(problems_all))
            if entry is not None and texts[chosen] != r["target"]:  # type: ignore[index]
                entries.append(entry)
            lines.append({
                "key": key, "en": r["source"], "old": r["target"],
                "new": texts[chosen] if chosen is not None else r["target"],
                "status": v.get("status"), "final_tier": v.get("final_tier"), "score": v.get("score"),
                "candidates": texts, "picks": {f"{m.family}:{m.provider.model}": texts[id_map[p[key]]] for m, p in picks},
                "votes_per_candidate": [votes.get(i, 0) for i in range(len(texts))],
                "chosen": chosen, "valid": chosen is not None, "problems": problems_all,
                "kept_by_pick": chosen is not None and texts[chosen] == r["target"], "selected_by": "J1 blind pick",
            })
        return _TournamentSelection(lines, rows, states, entries, valid_ranks)

    def _pick_valid(
        self, v: dict[str, Any], r: dict[str, Any], texts: Sequence[str], ranking: Sequence[int], locale: str, opts: TournamentOptions,
    ) -> tuple[int | None, list[int], list[str], dict[str, Any] | None]:
        key = r["key"]
        old_broken = self._parity.parity_problems(r["source"], r["target"], opts.ph_style, opts.tag_style)
        problems_all: list[str] = []
        chosen: int | None = None
        chosen_entry: dict[str, Any] | None = None
        valid_ids: list[int] = []
        reason = sanitize_prose((v.get("rationales") or ["jury flagged the line"])[0] or "jury flagged the line") or "jury flagged the line"
        for idx in ranking:
            if texts[idx] == r["target"]:
                if idx == ranking[0] and not old_broken and chosen is None:
                    return idx, [idx], problems_all, None
                continue
            entry = {"key": key, "score": min(int(v.get("score", 4)), 4), "issue_type": main_issue(v), "reason": reason, "suggested": texts[idx]}
            probs = self._validator.validate_single(
                locale=locale, source_file=opts.source_file, entry=entry,
                target_by_key={key: r["target"]}, sources_by_key={key: r["source"]},
                ph_style=opts.ph_style, tag_style=opts.tag_style,
            )
            if not probs:
                valid_ids.append(idx)
                if chosen is None:
                    chosen, chosen_entry = idx, entry
            elif chosen is None:
                problems_all.extend(f"{texts[idx]!r}: {p}" for p in probs)
        return chosen, valid_ids, problems_all, chosen_entry

    def _score_view(
        self, pairs: Sequence[tuple[dict[str, Any], dict[str, Any]]], router: Any, locale: str, pk_sys: str, opts: TournamentOptions,
    ) -> tuple[list[Any], list[dict[str, dict[str, Any]]]]:
        members = _jury_tier(router, "J1", "recheck")
        bctx = opts.blind_context
        view = [
            {"key": l["key"], "target": text_override if (text_override := l.get("_probe_text")) is not None else l["new"],
             **{k: r[k] for k in CONTEXT_FIELDS if r.get(k)},
             **({"context": bctx.line_fields(l["key"])} if bctx is not None and bctx.line_fields(l["key"]) else {})}
            for l, r in pairs
        ]
        extra = self._task_extra(opts)
        rescore = lambda m: self._score_fn(m.provider, view, locale, tier="J1", system=pk_sys, workers=opts.workers, memo=opts.memo, **extra)
        if int(opts.workers) > 1 and len(members) > 1:
            with ThreadPoolExecutor(max_workers=len(members)) as ex:
                return members, list(ex.map(rescore, members))
        return members, [rescore(m) for m in members]

    def _retry_runner_ups(
        self, failed: Sequence[tuple[dict[str, Any], dict[str, Any], list[int], bool]],
        sel: _TournamentSelection, router: Any, locale: str, pk_sys: str, opts: TournamentOptions,
    ) -> set[str]:
        candidates = [
            (l, r, ru, ob) for l, r, _got, ob in failed
            if (ru := pick_runner_up(l, sel.valid_ranks.get(l["key"], ()), ob)) is not None
        ]
        for l, _r, ru, _ob in candidates:
            l["_probe_text"] = l["candidates"][ru]
        scores_ru = self._score_view([(l, r) for l, r, _ru, _ob in candidates], router, locale, pk_sys, opts)[1] if candidates else []
        agreement = {k: int(x) for k, x in router.config.agreement.items()}
        from gcl.application.rewrite.recheck_policy import apply_runner_up_outcomes
        return apply_runner_up_outcomes(candidates, failed, scores_ru, agreement, sel.entries, sel.states)

    def _run_recheck(
        self, sel: _TournamentSelection, router: Any, locale: str, pk_sys: str, opts: TournamentOptions,
    ) -> list[dict[str, Any]]:
        recheck = [(l, r) for l, r in zip(sel.lines, sel.rows) if l["valid"] and l["new"] != l["old"]]
        if not recheck:
            return sel.entries
        members = _jury_tier(router, "J1", "recheck")
        pending_recheck = []
        for l, r in recheck:
            chosen, vcounts = l.get("chosen"), l.get("votes_per_candidate") or []
            if opts.unanimous_skip_recheck and chosen is not None and members and chosen < len(vcounts) and vcounts[chosen] >= len(members):
                l["recheck"] = [5] * len(members)
            else:
                pending_recheck.append((l, r))
        if not pending_recheck:
            return sel.entries
        scores = self._score_view(pending_recheck, router, locale, pk_sys, opts)[1]
        agreement = {k: int(x) for k, x in router.config.agreement.items()}
        failed = []
        for l, r in pending_recheck:
            got = [s[l["key"]]["score"] for s in scores]
            l["recheck"] = got
            old_broken = bool(self._parity.parity_problems(r["source"], l["old"], opts.ph_style, opts.tag_style))
            if not recheck_confirmed(got, agreement, int(l.get("score") or 4), old_broken):
                failed.append((l, r, got, old_broken))
        unconfirmed = self._retry_runner_ups(failed, sel, router, locale, pk_sys, opts) if failed else set()
        return [e for e in sel.entries if e["key"] not in unconfirmed]


def run_tournament(
    verdicts: Sequence[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    locale: str,
    router: Any,
    opts: TournamentOptions,
    validator: CritiqueValidatorPort,
    parity: TokenParityPort,
    **kw: Any,
) -> dict[str, Any]:
    """Execute Pass2Tournament with explicit validator, parity and optional callable hooks."""
    return Pass2Tournament(validator, parity, **kw).run(verdicts, sources, locale, router, opts)
