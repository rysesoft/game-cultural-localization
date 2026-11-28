"""Shared CLI argument parsing, exit code boundary and JSON/text reporting helpers."""

import json
import sys
from pathlib import Path
from typing import Any

from gcl.domain.errors import EXIT_USAGE, L10nError, __version__

from .io_utils import ensure_utf8_stdio

__layer__ = "infrastructure"
__pattern__ = "CLI Facade Support"
__owns__ = "unified argparse options, input resolution, JSON/text emission and error trapping"


def add_common_args(ap: Any, tool_name: str) -> None:
    """Attach standard flags shared across all localization CLI scripts."""
    ap.add_argument("--version", action="version", version=f"{tool_name} {__version__}")
    ap.add_argument("--config", help="Project config file (l10n.config.json); explicit CLI flags override it")
    ap.add_argument("--json", nargs="?", const=True, default=None, metavar="FILE",
                    help="Emit a machine-readable JSON report (to stdout, or to FILE when a path is given)")
    ap.add_argument("--output", help="Also write the printed report to this file (UTF-8)")
    ap.add_argument("--max-report", type=int, default=None, help="Max findings to print per severity in text mode (default: unlimited)")
    ap.add_argument("--debug", action="store_true", help="Show Python tracebacks for internal errors")


def add_input_argument(ap: Any, help_text: str, name: str = "input") -> None:
    """Accept main file either positionally or via --<name>."""
    ap.add_argument(f"{name}_pos", nargs="?", metavar=name.upper(), help=help_text)
    ap.add_argument(f"--{name}", dest=f"{name}_opt", metavar=name.upper(), help=f"Same as the positional {name.upper()}")


def resolve_input(ap: Any, args: Any, name: str = "input") -> str:
    """Merge positional and option input spellings or abort with usage error."""
    pos = getattr(args, f"{name}_pos", None)
    opt = getattr(args, f"{name}_opt", None)
    if pos and opt and pos != opt:
        ap.error(f"conflicting values for {name.upper()}: positional '{pos}' vs --{name} '{opt}'")
    value = opt or pos
    if not value:
        ap.error(f"the {name.upper()} file is required (positional {name.upper()} or --{name})")
    setattr(args, name, value)
    return value


def emit_report(text: str, payload: dict[str, Any], json_opt: Any, output: str | None) -> None:
    """Print or write text and optional JSON report."""
    if json_opt:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        if isinstance(json_opt, str):
            Path(json_opt).write_text(body + "\n", encoding="utf-8")
            print(text.splitlines()[0] if text else "")
            print(f"  JSON report written to {json_opt}")
        else:
            print(body)
    else:
        print(text)
    if output:
        Path(output).write_text((json.dumps(payload, ensure_ascii=False, indent=2) if json_opt else text) + "\n", encoding="utf-8")


def run_main(fn: Any) -> None:
    """Run script main entrypoint converting L10nError into clean exit 2."""
    ensure_utf8_stdio()
    try:
        code = fn()
    except L10nError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:
        if "--debug" in sys.argv:
            raise
        print(f"internal error: {type(exc).__name__}: {exc} (re-run with --debug for a traceback)", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    sys.exit(int(code or 0))
