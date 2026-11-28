"""AOP TaskAspect chain for batch memoization, cache priming and parallel batch execution."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, TypeVar, runtime_checkable

from gcl.ports.storage import MemoRepository

__layer__ = "aspects"
__pattern__ = "Decorator and Interceptor (AOP)"
__owns__ = "memoization, cache priming and parallel execution around batched tasks"

T = TypeVar("T")


@runtime_checkable
class TaskAspect(Protocol):
    """Interceptor wrapping single batch execution (e.g. memoization)."""

    def wrap(self, tag: Any, fn: Callable[[Any], Dict[str, Any]]) -> Callable[[Any], Dict[str, Any]]: ...


class MemoizationTaskAspect:
    """Skips LLM calls for already completed batches via MemoRepository."""

    def __init__(self, memo: Optional[MemoRepository]) -> None:
        self._memo = memo

    def wrap(self, tag: Any, fn: Callable[[Any], Dict[str, Any]]) -> Callable[[Any], Dict[str, Any]]:
        if self._memo is None:
            return fn
        memo = self._memo

        def wrapped(batch: Any) -> Dict[str, Any]:
            k = memo.make_key(tag, batch)
            hit = memo.get(k)
            if hit is not None:
                return hit
            res = fn(batch)
            memo.put(k, res)
            return res

        return wrapped


def run_batches_with_aspects(
    batches: Sequence[T],
    fn: Callable[[T], Dict[str, Any]],
    *,
    workers: int = 1,
    memo: Optional[MemoRepository] = None,
    tag: Any = None,
    prime: bool = True,
) -> Dict[str, Any]:
    """Execute batches through MemoizationTaskAspect and cache priming parallel pool."""
    call = MemoizationTaskAspect(memo).wrap(tag, fn)
    out: Dict[str, Any] = {}
    if int(workers) <= 1 or len(batches) <= 1:
        for b in batches:
            out.update(call(b))
        return out
    rest = list(batches)
    if prime:
        out.update(call(rest.pop(0)))
    with ThreadPoolExecutor(max_workers=int(workers)) as ex:
        for res in ex.map(call, rest):
            out.update(res)
    return out
