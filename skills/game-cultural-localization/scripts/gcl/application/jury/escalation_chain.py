"""Chain of Responsibility jury escalation (J1 -> BudgetCap -> J2 -> Roundtrip -> J3 -> Deliberation)."""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from collections.abc import Callable, Sequence
from typing import Any

from gcl.application.tasks.concrete_tasks import score_entries
from gcl.application.tasks.vote_codec import everyday_rule
from gcl.domain.errors import L10nError

from .policy import STATUSES, TIERS, EscalationTally, agrees, classify, is_clean_light_pass, juror_view, status_for

__layer__ = "application"
__pattern__ = "Chain of Responsibility"
__owns__ = "tiered mixed family jury voting, budget cap enforcement and deliberation dispatch"

type Deliberator = Callable[[dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any] | None]


def _tier_votes(router: Any, tier: str, entries: Sequence[dict[str, Any]], locale: str, **kw: Any) -> dict[str, list[dict[str, Any]]]:
    """Collect votes from all three vendor families for one tier and apply everyday_rule."""
    members = router.jury(tier)
    fams = [m.family for m in members]
    if len(set(fams)) != len(fams):
        raise L10nError(f"jury {tier} has two members from the same family ({', '.join(fams)})")
    view = [juror_view(e) for e in entries]
    out: dict[str, list[dict[str, Any]]] = {e["key"]: [] for e in entries}
    workers = int(kw.get("workers", 1))
    system, batch_size, memo = str(kw.get("system", "")), kw.get("batch_size"), kw.get("memo")
    extra_opts: dict[str, Any] = {}
    if kw.get("item_memo") is not None:
        extra_opts["item_memo"] = kw["item_memo"]
    if kw.get("salvage_truncated"):
        extra_opts["salvage_truncated"] = True
    score_fn = kw.get("score_fn") or score_entries

    def one(m: Any) -> dict[str, dict[str, Any]]:
        return score_fn(m.provider, view, locale, tier=tier, system=system, batch_size=batch_size, workers=workers, memo=memo, **extra_opts)

    if workers > 1 and len(members) > 1:
        with ThreadPoolExecutor(max_workers=len(members)) as ex:
            results = list(ex.map(one, members))
    else:
        results = [one(m) for m in members]
    for m, votes in zip(members, results):
        for key, v in votes.items():
            out[key].append({"key": key, "tier": tier, "member": m.index, "family": m.family, "model": m.provider.model, **v})
    for key_votes in out.values():
        everyday_rule(key_votes)
    return out


@dataclass(slots=True)
class JuryBatchContext:
    """Mutable execution state passed along jury TierHandler chain."""

    entries: Sequence[dict[str, Any]]
    by_key: dict[str, dict[str, Any]]
    order: list[str]
    locale: str
    router: Any
    system: str
    agreement: dict[str, int]
    caps: dict[str, Any]
    budget_caps: bool
    tally: EscalationTally
    batch_size: int | None
    workers: int
    memo: Any
    roundtrip_fn: Callable[[Sequence[dict[str, Any]]], dict[str, dict[str, Any]]] | None
    deliberator: Deliberator | None
    score_fn: Callable[..., dict[str, dict[str, Any]]] = score_entries
    clean_light_pass: bool = False
    item_memo: Any = None
    salvage_truncated: bool = False
    votes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    settled: dict[str, dict[str, Any]] = field(default_factory=dict)
    to_j2: list[str] = field(default_factory=list)
    to_j3: list[str] = field(default_factory=list)
    open_keys: list[str] = field(default_factory=list)
    j3_votes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    halted: dict[str, Any] | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    def settle(self, key: str, tier: str, score: int, status: str, rationales: Sequence[str], extra: dict[str, Any] | None = None) -> None:
        self.settled[key] = {
            "key": key, "final_tier": tier, "score": score, "status": status,
            "votes": self.votes[key], "evidence": self.evidence[key], "rationales": list(rationales), **(extra or {}),
        }

    def settle_tier_pass(self, key: str, tier: str, tier_votes: Sequence[dict[str, Any]]) -> None:
        scores = [v["score"] for v in tier_votes]
        score = min(scores)
        clean = self.clean_light_pass and is_clean_light_pass(tier_votes, self.evidence[key].get("ban_hits", ()))
        self.settle(key, tier, score, "pass" if clean else status_for(score), [v["reason"] for v in tier_votes])

    def cap_check(self, stage: str, keys: Sequence[str], limit: float) -> dict[str, Any] | None:
        total = len(self.order)
        self.stats[f"to_{stage}_ratio"] = round(len(keys) / total, 4) if total else 0.0
        count = (self.tally.to_j2 if stage == "J2" else self.tally.to_j3) + len(keys)
        judged = self.tally.lines + total
        ratio = round(count / judged, 4) if judged else 0.0
        self.stats[f"run_to_{stage}_ratio"] = ratio
        min_judged, min_escalated = int(self.caps.get("min_judged", 0)), int(self.caps.get("min_escalated", 0))
        if self.budget_caps and keys and ratio > limit and judged >= min_judged and count >= min_escalated:
            head = ", ".join(list(keys)[:10])
            tail = f" and {len(keys) - 10} more" if len(keys) > 10 else ""
            return {
                "stage": stage, "ratio": ratio, "cap": limit, "lines": count, "judged": judged, "keys": list(keys),
                "reason": f"{count} of {judged} lines judged in this run would go to {stage} ({ratio:.0%} > {limit:.0%}), "
                          f"check Pass 1 or the prompt. Lines of this batch that would go there: {head}{tail}",
            }
        return None


class TierHandler(ABC):
    """Base Chain of Responsibility handler for jury escalation stages."""

    def __init__(self) -> None:
        self._next: TierHandler | None = None

    def set_next(self, nxt: TierHandler) -> TierHandler:
        self._next = nxt
        return nxt

    def handle(self, ctx: JuryBatchContext) -> None:
        self.process(ctx)
        if self._next is not None and ctx.halted is None:
            self._next.handle(ctx)

    @abstractmethod
    def process(self, ctx: JuryBatchContext) -> None:
        """Process one escalation stage updating ctx."""

class J1TierHandler(TierHandler):
    def process(self, ctx: JuryBatchContext) -> None:
        tv = _tier_votes(ctx.router, "J1", ctx.entries, ctx.locale, system=ctx.system, batch_size=ctx.batch_size, workers=ctx.workers, memo=ctx.memo, score_fn=ctx.score_fn, item_memo=ctx.item_memo, salvage_truncated=ctx.salvage_truncated)
        for k in ctx.order:
            ctx.votes[k].extend(tv[k])
            scores = [v["score"] for v in tv[k]]
            c = classify(scores, ctx.agreement)
            if c == "pass":
                ctx.settle_tier_pass(k, "J1", tv[k])
            elif c == "critical":
                ctx.to_j3.append(k)
            else:
                ctx.to_j2.append(k)
        ctx.stats["J1"] = {
            "lines": len(ctx.order),
            "settled": len(ctx.order) - len(ctx.to_j2) - len(ctx.to_j3),
            "to_J2": len(ctx.to_j2),
            "critical_to_J3": len(ctx.to_j3),
        }
        ctx.halted = (
            ctx.cap_check("J2", ctx.to_j2, float(ctx.caps["escalate_j2_ratio"]))
            or ctx.cap_check("J3", ctx.to_j3, float(ctx.caps["escalate_j3_ratio"]))
        )


class J2TierHandler(TierHandler):
    def process(self, ctx: JuryBatchContext) -> None:
        if not ctx.to_j2:
            return
        items = [ctx.by_key[k] for k in ctx.to_j2]
        tv = _tier_votes(ctx.router, "J2", items, ctx.locale, system=ctx.system, batch_size=ctx.batch_size, workers=ctx.workers, memo=ctx.memo, score_fn=ctx.score_fn, item_memo=ctx.item_memo, salvage_truncated=ctx.salvage_truncated)
        moved = 0
        for k in ctx.to_j2:
            ctx.votes[k].extend(tv[k])
            scores = [v["score"] for v in tv[k]]
            if classify(scores, ctx.agreement) == "pass":
                ctx.settle_tier_pass(k, "J2", tv[k])
            else:
                ctx.to_j3.append(k)
                moved += 1
        ctx.stats["J2"] = {"lines": len(ctx.to_j2), "settled": len(ctx.to_j2) - moved, "to_J3": moved}
        ctx.to_j3 = [k for k in ctx.order if k in set(ctx.to_j3)]
        ctx.halted = ctx.cap_check("J3", ctx.to_j3, float(ctx.caps["escalate_j3_ratio"]))


class RoundtripEnricherHandler(TierHandler):
    def process(self, ctx: JuryBatchContext) -> None:
        if not ctx.to_j3 or ctx.roundtrip_fn is None:
            return
        for k, ev in ctx.roundtrip_fn([ctx.by_key[k] for k in ctx.to_j3]).items():
            if k in ctx.evidence:
                ctx.evidence[k]["roundtrip"] = ev


class J3TierHandler(TierHandler):
    def process(self, ctx: JuryBatchContext) -> None:
        if not ctx.to_j3:
            return
        items = [ctx.by_key[k] for k in ctx.to_j3]
        tv = _tier_votes(ctx.router, "J3", items, ctx.locale, system=ctx.system, batch_size=ctx.batch_size, workers=ctx.workers, memo=ctx.memo, score_fn=ctx.score_fn, item_memo=ctx.item_memo, salvage_truncated=ctx.salvage_truncated)
        ctx.j3_votes = tv
        for k in ctx.to_j3:
            ctx.votes[k].extend(tv[k])
        ctx.open_keys = [k for k in ctx.to_j3 if not agrees([v["score"] for v in tv[k]], ctx.agreement)]


class DeliberationHandler(TierHandler):
    def process(self, ctx: JuryBatchContext) -> None:
        if not ctx.to_j3:
            return
        outcomes = _dispatch_deliberation(ctx)
        disputed = 0
        for k in ctx.to_j3:
            j3 = ctx.j3_votes[k]
            scores = [v["score"] for v in j3]
            if agrees(scores, ctx.agreement):
                if ctx.clean_light_pass and is_clean_light_pass(j3, ctx.evidence[k].get("ban_hits", ())):
                    ctx.settle(k, "J3", min(scores), "pass", [v["reason"] for v in j3])
                else:
                    ctx.settle(k, "J3", min(scores), status_for(min(scores)), [v["reason"] for v in j3])
                continue
            disputed += 1
            result = outcomes.get(k)
            if result is None:
                ctx.settle(k, "J3", min(scores), "unresolved", [v["reason"] for v in j3])
            else:
                ctx.votes[k].extend(result.get("revotes", []))
                extra = {"deliberation": result["deliberation"]} if "deliberation" in result else None
                ctx.settle(k, "deliberation", int(result["score"]), str(result["status"]), result.get("rationales", []), extra)
        ctx.stats["J3"] = {"lines": len(ctx.to_j3), "agreed": len(ctx.to_j3) - disputed, "disputed": disputed}


def _dispatch_deliberation(ctx: JuryBatchContext) -> dict[str, Any]:
    d = ctx.deliberator
    if d is None or not ctx.open_keys:
        return {}
    if hasattr(d, "many"):
        return d.many([(ctx.by_key[k], ctx.j3_votes[k], ctx.evidence[k]) for k in ctx.open_keys], workers=ctx.workers, memo=ctx.memo)
    if int(ctx.workers) > 1 and len(ctx.open_keys) > 1:
        with ThreadPoolExecutor(max_workers=int(ctx.workers)) as ex:
            return dict(zip(ctx.open_keys, ex.map(lambda key: d(ctx.by_key[key], ctx.j3_votes[key], ctx.evidence[key]), ctx.open_keys)))
    return {key: d(ctx.by_key[key], ctx.j3_votes[key], ctx.evidence[key]) for key in ctx.open_keys}


def run_jury(entries: Sequence[dict[str, Any]], locale: str, router: Any, **kw: Any) -> dict[str, Any]:
    """Execute J1 -> BudgetCap -> J2 -> Roundtrip -> J3 -> Deliberation escalation pipeline."""
    cfg = router.config
    order = [e["key"] for e in entries]
    by_key = {e["key"]: e for e in entries}
    ban_fn = kw.get("ban_hits_fn")
    bans = ban_fn(entries, locale) if ban_fn else {k: [] for k in order}
    tm_lookup = kw.get("tm_lookup")
    evidence = {
        k: {"ban_hits": bans[k], "tm_neighbors": tm_lookup(by_key[k]) if tm_lookup else [], "roundtrip": {"applied": False, "reason": "not_needed"}}
        for k in order
    }
    ctx = JuryBatchContext(
        entries=entries, by_key=by_key, order=order, locale=locale, router=router,
        system=str(kw.get("system", "")), agreement={k: int(v) for k, v in cfg.agreement.items()},
        caps=cfg.budget_caps, budget_caps=bool(kw.get("budget_caps", True)),
        tally=kw.get("tally") if kw.get("tally") is not None else EscalationTally(),
        batch_size=kw.get("batch_size"), workers=int(kw.get("workers", 1)), memo=kw.get("memo"),
        roundtrip_fn=kw.get("roundtrip_fn"), deliberator=kw.get("deliberator"),
        score_fn=kw.get("score_fn") or score_entries,
        clean_light_pass=bool(kw.get("clean_light_pass", False)),
        item_memo=kw.get("item_memo"),
        salvage_truncated=bool(kw.get("salvage_truncated", False)),
        votes={k: [] for k in order}, evidence=evidence, stats={"lines": len(order)},
    )
    head = J1TierHandler()
    head.set_next(J2TierHandler()).set_next(RoundtripEnricherHandler()).set_next(J3TierHandler()).set_next(DeliberationHandler())
    head.handle(ctx)
    ctx.tally.lines += len(order)
    ctx.tally.to_j2 += int(ctx.stats["J1"]["to_J2"])
    ctx.tally.to_j3 += len(ctx.to_j3)
    pending = [k for k in order if k not in ctx.settled]
    verdicts = [ctx.settled[k] for k in order if k in ctx.settled]
    ctx.stats["status"] = {s: sum(1 for v in verdicts if v["status"] == s) for s in STATUSES}
    ctx.stats["final_tier"] = {t: sum(1 for v in verdicts if v["final_tier"] == t) for t in TIERS + ("deliberation",)}
    return {"verdicts": verdicts, "pending": pending, "halted": ctx.halted, "stats": ctx.stats}
