"""AOP TaskAspect chain for batch memoization, cache priming and parallel batch execution."""

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Sequence
from typing import Any, Protocol, runtime_checkable

from gcl.ports.storage import MemoRepository

__layer__ = "aspects"
__pattern__ = "Decorator and Interceptor (AOP)"
__owns__ = "memoization, cache priming and parallel execution around batched tasks"


@runtime_checkable
class TaskAspect(Protocol):
    """Interceptor wrapping single batch execution (e.g. memoization)."""

    def wrap(self, tag: Any, fn: Callable[[Any], dict[str, Any]]) -> Callable[[Any], dict[str, Any]]: ...


class MemoizationTaskAspect:
    """Skips LLM calls for already completed batches via MemoRepository."""

    def __init__(self, memo: MemoRepository | None) -> None:
        self._memo = memo

    def wrap(self, tag: Any, fn: Callable[[Any], dict[str, Any]]) -> Callable[[Any], dict[str, Any]]:
        if self._memo is None:
            return fn
        memo = self._memo

        def wrapped(batch: Any) -> dict[str, Any]:
            k = memo.make_key(tag, batch)
            hit = memo.get(k)
            if hit is not None:
                return hit
            res = fn(batch)
            memo.put(k, res)
            return res

        return wrapped


class ItemMemoTaskAspect:
    """Partitions and atomically persists individual keyed items across batch sizes."""

    def __init__(
        self,
        memo: MemoRepository | None,
        *,
        id_field: str = "key",
        project_fn: Callable[[Any], Any] | None = None,
    ) -> None:
        self._memo = memo
        self._id_field = id_field
        self._project_fn = project_fn or (lambda item: item)

    def partition(self, tag: Any, items: Sequence[Any]) -> tuple[dict[str, Any], list[Any], dict[str, str]]:
        if self._memo is None:
            return {}, list(items), {}
        cached: dict[str, Any] = {}
        pending: list[Any] = []
        key_map: dict[str, str] = {}
        for it in items:
            iid = str(it[self._id_field])
            ckey = self._memo.make_key(tag, iid, self._project_fn(it))
            hit = self._memo.get(ckey)
            if hit is not None:
                cached[iid] = hit
            else:
                pending.append(it)
                key_map[iid] = ckey
        return cached, pending, key_map

    def store(self, key_map: dict[str, str], fresh: dict[str, Any]) -> None:
        if self._memo is None or not key_map or not fresh:
            return
        to_write = {key_map[k]: v for k, v in fresh.items() if k in key_map}
        if not to_write:
            return
        if hasattr(self._memo, "put_many"):
            self._memo.put_many(to_write)
        else:
            for ck, val in to_write.items():
                self._memo.put(ck, val)


def run_batches_with_aspects[T](
    batches: Sequence[T],
    fn: Callable[[T], dict[str, Any]],
    *,
    workers: int = 1,
    memo: MemoRepository | None = None,
    tag: Any = None,
    prime: bool = True,
) -> dict[str, Any]:
    """Execute batches through MemoizationTaskAspect and cache priming parallel pool."""
    call = MemoizationTaskAspect(memo).wrap(tag, fn)
    out: dict[str, Any] = {}
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
