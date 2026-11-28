"""Composition root binding concrete infrastructure adapters to application services."""

from pathlib import Path
from typing import Any

from gcl.application.gates.lint_chain import LintChainRunner
from gcl.application.rewrite.tournament import Pass2Tournament
from gcl.infrastructure.fonts.scanner_adapter import DefaultFontScannerAdapter
from gcl.infrastructure.formats.critique_validator import DefaultCritiqueValidatorAdapter
from gcl.infrastructure.persistence.context_views import BlindContextAdapter, WriterContextAdapter
from gcl.infrastructure.persistence.memo_store import BatchMemo
from gcl.infrastructure.persistence.sqlite_tm import TranslationMemory
from gcl.infrastructure.persistence.verdict_repo import JsonVerdictRepository
from gcl.infrastructure.tokens.parity_adapter import DefaultTokenParityAdapter

__layer__ = "composition"
__pattern__ = "Service Container"
__owns__ = "dependency injection wiring for tokens, critique validation, TM, memo and context views"


class _AnnotatedWriterView(WriterContextAdapter):
    """WriterContextAdapter carrying note_count for Phase 0 reporting."""

    @property
    def note_count(self) -> int:
        return len(getattr(self._pack, "notes", {}) or {})


class ServiceContainer:
    """Lightweight composition root container assembling application services."""

    def __init__(self) -> None:
        self.parity = DefaultTokenParityAdapter()
        self.critique_validator = DefaultCritiqueValidatorAdapter()
        self.font_scanner = DefaultFontScannerAdapter()
        self.verdict_repo = JsonVerdictRepository()

    def create_pass2_tournament(self) -> Pass2Tournament:
        return Pass2Tournament(self.critique_validator, self.parity)

    def create_lint_runner(self) -> LintChainRunner:
        return LintChainRunner()

    @staticmethod
    def open_tm(path: Path) -> TranslationMemory:
        return TranslationMemory(path)

    @staticmethod
    def open_memo(path: Path) -> BatchMemo:
        return BatchMemo(path)

    @staticmethod
    def split_context_pack(pack: Any) -> tuple[WriterContextAdapter | None, BlindContextAdapter | None]:
        if pack is None:
            return None, None
        return _AnnotatedWriterView(pack), BlindContextAdapter(pack)
