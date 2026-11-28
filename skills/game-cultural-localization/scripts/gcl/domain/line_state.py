"""Immutable State pattern for localization line lifecycle transitions."""

from dataclasses import dataclass

__layer__ = "domain"
__pattern__ = "State"
__owns__ = "line lifecycle states eliminating ambiguous rewrite counters"


@dataclass(frozen=True, slots=True)
class LineState:
    """Base immutable state for one key during pipeline execution."""
    key: str
    source: str
    initial_target: str
    current_target: str
    status: str

    @property
    def is_actual_change(self) -> bool:
        """True only when current_target changed from initial_target."""
        return self.current_target != self.initial_target


@dataclass(frozen=True, slots=True)
class DraftedState(LineState):
    """Line after Pass 1 or initial draft preservation."""

    def settle_pass(self) -> SettledPassState:
        return SettledPassState(self.key, self.source, self.initial_target, self.current_target, "pass")

    def flag_rewrite(self, status: str) -> FlaggedForRewriteState:
        return FlaggedForRewriteState(self.key, self.source, self.initial_target, self.current_target, status)


@dataclass(frozen=True, slots=True)
class SettledPassState(LineState):
    """Line approved by the jury without Pass 2 changes."""

@dataclass(frozen=True, slots=True)
class FlaggedForRewriteState(LineState):
    """Line entering Pass 2 tournament."""

    def accept_rewrite(self, new_text: str) -> RewrittenState:
        return RewrittenState(self.key, self.source, self.initial_target, new_text, self.status)

    def keep_original(self, reasons: tuple[str, ...] = ()) -> KeptOriginalState:
        return KeptOriginalState(self.key, self.source, self.initial_target, self.initial_target, self.status, reasons=reasons)

    def mark_unresolved(self, reasons: tuple[str, ...] = ()) -> UnresolvedState:
        return UnresolvedState(self.key, self.source, self.initial_target, self.initial_target, "unresolved", reasons=reasons)


@dataclass(frozen=True, slots=True)
class RewrittenState(LineState):
    """Line validated and updated with a confirmed Pass 2 rewrite."""


@dataclass(frozen=True, slots=True)
class KeptOriginalState(LineState):
    """Line where blind pick kept Pass 1 or candidate failed recheck."""
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnresolvedState(LineState):
    """Line requiring explicit developer decision."""
    reasons: tuple[str, ...] = ()
