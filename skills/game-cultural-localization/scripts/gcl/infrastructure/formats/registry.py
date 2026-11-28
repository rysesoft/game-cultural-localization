"""Strategy Registry for table loading and exporting across localization file formats."""

from pathlib import Path

from gcl.domain.errors import L10nError
from gcl.domain.models import Row
from gcl.ports.formats import ExportResult, TableFormatStrategy, TableLoadOptions

from .csv_format import CsvTableFormat
from .io_utils import read_text_bom
from .json_format import JsonTableFormat
from .po_format import PoTableFormat
from .unity_yaml_reader import load_unity_rows
from .unity_yaml_writer import export_unity

__layer__ = "infrastructure"
__pattern__ = "Registry"
__owns__ = "OCP table format registry for reading and writing localized tables"

SUPPORTED_INPUT_SUFFIXES: tuple[str, ...] = (".json", ".csv", ".tsv", ".po", ".asset", ".yaml", ".yml")


class UnityTableFormat:
    """TableFormatStrategy for Unity Localization .asset, .yaml and .yml tables."""
    suffixes = (".asset", ".yaml", ".yml")

    def read_rows(self, path: Path, options: TableLoadOptions) -> list[Row]:
        return load_unity_rows(path, options.src_input, options.shared_table)

    def write_export(self, final_texts: dict[str, str], template: Path, out_dir: Path, *, dst_field: str, key_field: str) -> ExportResult:
        res = export_unity(final_texts, [template], None, out_dir)
        return ExportResult(tuple(res["files"]), int(res["placed"]), (), int(res["unchanged"]), tuple(res["not_placed"]))


class TableFormatRegistry:
    """Extensible registry mapping file suffixes to TableFormatStrategy instances."""

    def __init__(self) -> None:
        self._strategies: dict[str, TableFormatStrategy] = {}

    def register(self, strategy: TableFormatStrategy) -> None:
        for suf in strategy.suffixes:
            self._strategies[suf.lower()] = strategy

    def suffixes(self) -> tuple[str, ...]:
        return tuple(self._strategies.keys())

    def get(self, path: Path) -> TableFormatStrategy:
        suf = path.suffix.lower()
        strat = self._strategies.get(suf)
        if strat is None:
            names = ", ".join(self._strategies.keys())
            raise L10nError(f"{path}: unsupported input format '{suf}'; supported: {names}")
        return strat


DEFAULT_FORMAT_REGISTRY = TableFormatRegistry()
for _fmt in (JsonTableFormat(), CsvTableFormat(), PoTableFormat(), UnityTableFormat()):
    DEFAULT_FORMAT_REGISTRY.register(_fmt)


def load_table_options(path: Path, options: TableLoadOptions | None = None, registry: TableFormatRegistry = DEFAULT_FORMAT_REGISTRY) -> list[Row]:
    """Load rows from any registered localization table format."""
    opt = options or TableLoadOptions()
    return registry.get(path).read_rows(path, opt)


def load_target_rows(input_path: Path, dst_field: str = "dst", key_field: str = "key", registry: TableFormatRegistry = DEFAULT_FORMAT_REGISTRY) -> list[tuple[str, str]]:
    """Load (key, target_text) from supported tables or fall back to plain text file."""
    if input_path.suffix.lower() in registry.suffixes():
        opts = TableLoadOptions(dst_field=dst_field, key_field=key_field, target_only=True)
        return [(r.key, r.dst) for r in load_table_options(input_path, opts, registry)]
    return [(input_path.name, read_text_bom(input_path))]
