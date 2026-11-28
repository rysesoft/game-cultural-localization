"""Pass 2 J1 recheck confirmation policy and voted runner-up candidate selection."""

from collections.abc import Mapping, Sequence
from typing import Any

from gcl.application.jury.policy import classify
from gcl.domain.line_state import FlaggedForRewriteState

__layer__ = "application"
__pattern__ = "Specification Policy"
__owns__ = "Pass 2 J1 recheck confirmation policy and voted runner-up candidate selection"


def recheck_confirmed(got: Sequence[int], agreement: Mapping[str, int], old_score: int, old_broken: bool) -> bool:
    """Confirm rewrite if J1 agrees pass, or 2/3 majority passes on severe/broken lines without criticals."""
    ag = dict(agreement)
    if classify(got, ag) == "pass":
        return True
    if old_score <= 3 or old_broken:
        passing = sum(1 for s in got if s >= int(ag["pass_min"]))
        return passing >= 2 and min(got) > int(ag["critical_max"])
    return False


def pick_runner_up(line: dict[str, Any], valid_indices: Sequence[int], old_broken: bool) -> int | None:
    """Return next valid non-original candidate index after chosen with votes or parity repair need."""
    chosen = line.get("chosen")
    old_text = line.get("old")
    cands = line.get("candidates") or []
    vcounts = line.get("votes_per_candidate") or []
    seen_chosen = chosen is None
    for idx in valid_indices:
        if idx == chosen:
            seen_chosen = True
            continue
        if not seen_chosen or idx >= len(cands) or cands[idx] == old_text:
            continue
        votes = vcounts[idx] if idx < len(vcounts) else 0
        if votes > 0 or old_broken:
            return idx
    return None


def apply_runner_up_outcomes(
    candidates: Sequence[tuple[dict[str, Any], dict[str, Any], int, bool]],
    failed: Sequence[tuple[dict[str, Any], dict[str, Any], list[int], bool]],
    scores_ru: Sequence[Mapping[str, Any]],
    agreement: Mapping[str, int],
    entries: Sequence[dict[str, Any]],
    states: dict[str, Any],
) -> set[str]:
    """Evaluate runner-up recheck scores and update line statuses and states."""
    entry_by_key = {e["key"]: e for e in entries}
    confirmed: set[str] = set()
    for l, _r, ru, ob in candidates:
        l.pop("_probe_text", None)
        got_ru = [s[l["key"]]["score"] for s in scores_ru]
        if recheck_confirmed(got_ru, agreement, int(l.get("score") or 4), ob):
            l.update(chosen=ru, new=l["candidates"][ru], valid=True, recheck=got_ru)
            if l["key"] in entry_by_key:
                entry_by_key[l["key"]]["suggested"] = l["candidates"][ru]
            confirmed.add(l["key"])
    unconfirmed: set[str] = set()
    for l, r, got, _ob in failed:
        st = FlaggedForRewriteState(l["key"], r["source"], l["old"], l["old"], str(l.get("status")))
        if l["key"] in confirmed:
            states[l["key"]] = st.accept_rewrite(l["new"])
        else:
            unconfirmed.add(l["key"])
            msg = f"J1 did not confirm the rewrite (scores {got}), the old line stays"
            l.update(valid=False, new=l["old"], problems=l["problems"] + [msg])
            states[l["key"]] = st.keep_original((msg,))
    return unconfirmed
