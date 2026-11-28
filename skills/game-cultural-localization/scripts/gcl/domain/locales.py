"""Supported locale metadata, alias mapping and expansion ceilings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .errors import L10nError

__layer__ = "domain"
__pattern__ = "Value Object and Registry"
__owns__ = "canonical locales, alias normalization, plural counts and expansion factors"

CANONICAL_LOCALES: Tuple[str, ...] = (
    "en", "tr-TR", "de-DE", "fr", "es-ES", "it-IT", "pt-BR", "pt-PT",
    "pl-PL", "lt-LT", "ru-RU", "ja-JP", "ko-KR", "zh-CN", "zh-Hant",
)

_LOCALE_ALIASES: Dict[str, Tuple[str, Optional[str]]] = {
    "en": ("en", None), "en-us": ("en", None), "en-gb": ("en", None), "en-au": ("en", None), "en-ca": ("en", None),
    "tr": ("tr-TR", None), "tr-tr": ("tr-TR", None),
    "de": ("de-DE", None), "de-de": ("de-DE", None), "de-at": ("de-DE", "at"), "de-ch": ("de-DE", "ch"),
    "fr": ("fr", None), "fr-fr": ("fr", None), "fr-ca": ("fr", "ca"), "fr-be": ("fr", None), "fr-ch": ("fr", None),
    "es": ("es-ES", None), "es-es": ("es-ES", None),
    "it": ("it-IT", None), "it-it": ("it-IT", None),
    "pt-br": ("pt-BR", None), "pt-pt": ("pt-PT", None),
    "pl": ("pl-PL", None), "pl-pl": ("pl-PL", None),
    "lt": ("lt-LT", None), "lt-lt": ("lt-LT", None),
    "ru": ("ru-RU", None), "ru-ru": ("ru-RU", None),
    "ja": ("ja-JP", None), "ja-jp": ("ja-JP", None), "jp": ("ja-JP", None),
    "ko": ("ko-KR", None), "ko-kr": ("ko-KR", None), "kr": ("ko-KR", None),
    "zh": ("zh-CN", None), "zh-cn": ("zh-CN", None), "zh-hans": ("zh-CN", None), "zh-sg": ("zh-CN", None),
    "zh-hans-cn": ("zh-CN", None), "chs": ("zh-CN", None),
    "zh-hant": ("zh-Hant", None), "zh-tw": ("zh-Hant", None), "zh-hant-tw": ("zh-Hant", None), "cht": ("zh-Hant", None),
    "zh-hk": ("zh-Hant", "hk"), "zh-mo": ("zh-Hant", "hk"), "zh-hant-hk": ("zh-Hant", "hk"),
}
_AMBIGUOUS_LOCALES = {"pt": "pt-BR or pt-PT", "es-mx": "es-ES (LatAm Spanish is not covered)", "es-419": "es-ES"}

PLURAL_FORMS: Dict[str, int] = {
    "en": 2, "tr-TR": 2, "de-DE": 2, "fr": 2, "es-ES": 2, "it-IT": 2, "pt-BR": 2, "pt-PT": 2,
    "pl-PL": 3, "lt-LT": 3, "ru-RU": 3, "ja-JP": 1, "ko-KR": 1, "zh-CN": 1, "zh-Hant": 1,
}

EXPANSION_FACTORS: Dict[str, float] = {
    "en": 1.00, "tr-TR": 1.25, "de-DE": 1.35, "fr": 1.30, "es-ES": 1.30, "it-IT": 1.25,
    "pt-BR": 1.30, "pt-PT": 1.30, "pl-PL": 1.30, "lt-LT": 1.30, "ru-RU": 1.30,
    "ja-JP": 1.30, "ko-KR": 1.40, "zh-CN": 1.10, "zh-Hant": 1.10,
}


@dataclass(frozen=True)
class LocaleSpec:
    """Normalized canonical locale plus optional regional variant."""
    canonical: str
    variant: Optional[str] = None

    @property
    def plural_forms(self) -> int:
        return PLURAL_FORMS[self.canonical]

    @property
    def expansion_factor(self) -> float:
        return EXPANSION_FACTORS[self.canonical]


def normalize_locale(raw: str) -> Tuple[str, Optional[str]]:
    """Map a user supplied locale code to (canonical, variant) or raise L10nError."""
    key = (raw or "").strip().replace("_", "-").lower()
    if not key:
        raise L10nError("locale is empty; supported locales: " + ", ".join(CANONICAL_LOCALES))
    if key in _LOCALE_ALIASES:
        return _LOCALE_ALIASES[key]
    if key in _AMBIGUOUS_LOCALES:
        raise L10nError(f"locale '{raw}' is ambiguous; use {_AMBIGUOUS_LOCALES[key]}")
    base = key.split("-")[0]
    hint = ""
    for canon in CANONICAL_LOCALES:
        if canon.lower().split("-")[0] == base:
            hint = f" (did you mean '{canon}'?)"
            break
    raise L10nError(f"unknown locale '{raw}'{hint}; supported: " + ", ".join(CANONICAL_LOCALES))


def parse_locale(raw: str) -> LocaleSpec:
    """Return an immutable LocaleSpec value object for raw."""
    canon, variant = normalize_locale(raw)
    return LocaleSpec(canon, variant)
