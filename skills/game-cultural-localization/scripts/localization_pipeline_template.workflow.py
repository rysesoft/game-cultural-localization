"""Antigravity Dynamic Workflow (/run-workflow) template: 4-phase game culturalization pipeline.

HOW TO RUN (Antigravity only):
    /run-workflow Run skills/game-cultural-localization/scripts/localization_pipeline_template.workflow.py
    with args {"locale": "de-DE", "scratch_dir": "loc_work", "batches": ["01", "02"], "plugin_dir": "<plugin path>"}

This file uses the Antigravity workflow DSL documented at
https://antigravity.google/docs/dynamic-workflows : the runtime injects
phase(), log(), agent(), parallel(), pipeline(), args and allows top-level await.
It is therefore NOT a standalone Python module (hence the .workflow.py suffix;
tests compile it with ast.PyCF_ALLOW_TOP_LEVEL_AWAIT).  For an API-independent
orchestration that runs with plain Python, see orchestrator_stub.py.

Phases (canonical numbering, see references/methodology_and_qa.md):
  Phase 0  Pre-flight: locale validation, <LOCALE>_BIBLE.md + transcreation ledger, font scan
  Phase 1  Clean-room culturalization (game-culturalizer, Pass 1) per batch
  Phase 2  make_blind_slice -> blind native-ear critique -> validate_critique -> Pass-2 rewrite
  Phase 3  Automated LQA gate: lqa_linter --fail-on-error, ui_expansion_checker --fail-on-high, font_glyph_scanner

Error handling: parallel() cancels every sibling when one item fails, so each
batch agent returns a structured {"ok", "file", "errors"} object instead of
raising; failed batches are retried once sequentially with pipeline() and the
run aborts with a clear log line if any batch still fails.
"""

import json
import os

LOCALE = (args.get("locale") or "").strip()
SCRATCH = (args.get("scratch_dir") or "loc_work").rstrip("/\\")
BATCHES = list(args.get("batches") or [])
PLUGIN = (args.get("plugin_dir") or ".").rstrip("/\\")
SCRIPTS = f"{PLUGIN}/skills/game-cultural-localization/scripts"
REFS = f"{PLUGIN}/skills/game-cultural-localization/references"
BIBLE = f"{SCRATCH}/{LOCALE}_BIBLE.md"
FONTS = list(args.get("fonts") or [])          # optional: .ttf/.otf/.ttc or TMP .asset paths
PH_STYLE = args.get("placeholder_style") or "auto"   # unity | unreal | godot | icu | printf | python | auto
TAG_STYLE = args.get("tag_style") or "auto"          # tmp | html | bbcode | auto

if not LOCALE:
    raise ValueError("args.locale is required (e.g. de-DE, fr, ja-JP, zh-Hant)")
if not BATCHES:
    raise ValueError("args.batches is empty: nothing to localize (expected e.g. [\"01\", \"02\"])")

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "file": {"type": "string"},
        "errors": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ok", "file", "errors"],
}


def batch_prompt(step, b):
    """Prompts are tool-agnostic: they describe files to read/write, not editor tool names."""
    if step == "pass1":
        return (
            f"Activate the game-cultural-localization skill. Read {REFS}/{LOCALE}.md (including its Golden Voice "
            f"Anchors A1-A5) and {BIBLE}. Translate the clean-room batch {SCRATCH}/in_batch_{b}.json into natural, "
            f"everyday spoken {LOCALE} and write {SCRATCH}/pass1_batch_{b}.json with the same keys and a '{LOCALE}' "
            f"target field. Preserve every placeholder ({PH_STYLE} style), rich-text tag ({TAG_STYLE} style), "
            f"leading/trailing space and locked glossary term. Finish with ok=true and the output file path, or "
            f"ok=false and the list of errors."
        )
    if step == "critique":
        return (
            f"You are the blind native-ear critic for {LOCALE}. Read ONLY {SCRATCH}/blind_{LOCALE}_{b}.json "
            f"(a target-only slice: key, category/speaker, target) and {REFS}/{LOCALE}.md. Do NOT open any other "
            f"file. Read every target aloud as a native player and score naturalness 1-5. Write "
            f"{SCRATCH}/critique_{LOCALE}_{b}.json using exactly this schema: {{\"locale\", \"source_file\", "
            f"\"entries\": [{{\"key\", \"score\", \"issue_type\", \"reason\", \"suggested\"}}], "
            f"\"summary\": {{\"total\", \"flagged\", \"critical\"}}}} with only score<5 entries; issue_type is one of "
            f"translationese|register|tense|regional_leak|gender_leak|ui_verb|placeholder_grammar|terminology|other. "
            f"Finish with ok=true and the file path."
        )
    if step == "pass2":
        return (
            f"Activate the game-cultural-localization skill. Read {BIBLE}, {SCRATCH}/pass1_batch_{b}.json and the "
            f"validated critique {SCRATCH}/critique_{LOCALE}_{b}.json. Apply every valid native-ear improvement "
            f"while preserving 100% of locked glossary terms, placeholders, rich-text tags, leading/trailing spaces "
            f"and punctuation rules; reject suggestions that rename items/buttons without source evidence. Write "
            f"{SCRATCH}/final_batch_{b}.json. Finish with ok=true and the file path."
        )
    raise ValueError(step)


def shell_prompt(cmds, outputs):
    return (
        "Run the following commands from the primary workspace folder and report ok=true only if every exit code is 0. "
        "Put each non-zero command (with its exit code and the last 20 lines of output) into errors.\n"
        + "\n".join(cmds)
        + f"\nExpected outputs: {', '.join(outputs)}"
    )


async def run_batches(step, type_name, role):
    """parallel() first; retry failed batches sequentially; return the list of failures."""
    results = await parallel(
        BATCHES,
        lambda b: agent(prompt=batch_prompt(step, b), schema=RESULT_SCHEMA, role=f"{LOCALE} {role} {b}", type_name=type_name),
    )
    failed = [b for b, r in zip(BATCHES, results) if not r.get("ok")]
    for b, r in zip(BATCHES, results):
        log(f"{step} batch {b}: {'ok' if r.get('ok') else 'FAILED ' + '; '.join(r.get('errors', []))}")
    if failed:
        retry = await pipeline(
            failed,
            lambda b: agent(prompt=batch_prompt(step, b), schema=RESULT_SCHEMA, role=f"{LOCALE} {role} {b} (retry)", type_name=type_name),
        )
        failed = [b for b, r in zip(failed, retry) if not r.get("ok")]
    return failed


# --------------------------------------------------------------------------- #
phase(f"Phase 0: {LOCALE} pre-flight (bible, ledger, fonts)")
preflight = await agent(
    prompt=(
        f"Activate the game-cultural-localization skill. Validate that '{LOCALE}' is one of the 15 supported locales "
        f"(run: python {SCRIPTS}/lqa_linter.py --version and python {SCRIPTS}/lqa_linter.py --help). "
        f"If {BIBLE} does not exist, create it from {REFS}/{LOCALE}.md and {REFS}/transcreation_ledger_guide.md: "
        f"locked terminology (collision pairs such as Contract vs Order), per-archetype register (A1 Mentor, A2 Rival, "
        f"A3 Rookie, A4 Scientist, A5 Antagonist), player-gender neutrality strategy, and the transcreation ledger. "
        + (f"Then run: python {SCRIPTS}/font_glyph_scanner.py --input {SCRATCH}/in_batch_{BATCHES[0]}.json --dst-field en "
           + " ".join(f"--font \"{f}\"" for f in FONTS) + " and record the result. " if FONTS else "")
        + "Finish with ok=true, file=the bible path, errors=[]."
    ),
    schema=RESULT_SCHEMA,
    role=f"{LOCALE} pre-flight",
    type_name="game-culturalizer",
)
log(f"pre-flight: {preflight}")
if not preflight.get("ok"):
    raise RuntimeError("Phase 0 failed: " + "; ".join(preflight.get("errors", [])))

# --------------------------------------------------------------------------- #
phase(f"Phase 1: {LOCALE} clean-room culturalization (Pass 1)")
failed = await run_batches("pass1", "game-culturalizer", "Pass-1 Culturalizer")
if failed:
    raise RuntimeError(f"Phase 1 failed for batches {failed}")

# --------------------------------------------------------------------------- #
phase(f"Phase 2: {LOCALE} blind native-ear critique + Pass-2 rewrite")
slices = await agent(
    prompt=shell_prompt(
        [f"python {SCRIPTS}/make_blind_slice.py {SCRATCH}/pass1_batch_{b}.json --locale {LOCALE} --target-col {LOCALE} "
         f"--context-cols category,speaker --out {SCRATCH}/blind_{LOCALE}_{b}.json" for b in BATCHES],
        [f"{SCRATCH}/blind_{LOCALE}_{b}.json" for b in BATCHES],
    ),
    schema=RESULT_SCHEMA, role=f"{LOCALE} blind-slice builder", type_name="game-culturalizer",
)
if not slices.get("ok"):
    raise RuntimeError("blind slices failed: " + "; ".join(slices.get("errors", [])))

failed = await run_batches("critique", "native-ear-critic", "Blind Critic")
if failed:
    raise RuntimeError(f"critique failed for batches {failed}")

validation = await agent(
    prompt=shell_prompt(
        [f"python {SCRIPTS}/validate_critique.py {SCRATCH}/critique_{LOCALE}_{b}.json --slice {SCRATCH}/blind_{LOCALE}_{b}.json "
         f"--locale {LOCALE} --placeholder-style {PH_STYLE} --tag-style {TAG_STYLE}" for b in BATCHES],
        ["validation report per batch"],
    ),
    schema=RESULT_SCHEMA, role=f"{LOCALE} critique validator", type_name="game-culturalizer",
)
if not validation.get("ok"):
    raise RuntimeError("critique validation failed: " + "; ".join(validation.get("errors", [])))

failed = await run_batches("pass2", "game-culturalizer", "Pass-2 Editor")
if failed:
    raise RuntimeError(f"Phase 2 Pass-2 failed for batches {failed}")

# --------------------------------------------------------------------------- #
phase(f"Phase 3: {LOCALE} automated LQA gate")
font_flags = " ".join(f"--font \"{f}\"" for f in FONTS)
gate_cmds = []
for b in BATCHES:
    f = f"{SCRATCH}/final_batch_{b}.json"
    gate_cmds.append(f"python {SCRIPTS}/lqa_linter.py --input {f} --locale {LOCALE} --src-field en --dst-field {LOCALE} "
                     f"--placeholder-style {PH_STYLE} --tag-style {TAG_STYLE} --fail-on-error --json {SCRATCH}/lqa_{LOCALE}_{b}.json")
    gate_cmds.append(f"python {SCRIPTS}/ui_expansion_checker.py --input {f} --locale {LOCALE} --src-field en --dst-field {LOCALE} "
                     f"--fail-on-high --json {SCRATCH}/ui_{LOCALE}_{b}.json")
    if FONTS:
        gate_cmds.append(f"python {SCRIPTS}/font_glyph_scanner.py --input {f} --dst-field {LOCALE} {font_flags} --json {SCRATCH}/font_{LOCALE}_{b}.json")
gate = await agent(
    prompt=shell_prompt(gate_cmds, [f"{SCRATCH}/lqa_{LOCALE}_*.json", f"{SCRATCH}/ui_{LOCALE}_*.json"]),
    schema=RESULT_SCHEMA, role=f"{LOCALE} LQA gate", type_name="game-culturalizer",
)
log(f"LQA gate: {gate}")
if not gate.get("ok"):
    raise RuntimeError("Phase 3 LQA gate failed: " + "; ".join(gate.get("errors", [])))
log(f"Pipeline complete for {LOCALE}: {len(BATCHES)} batches -> {SCRATCH}/final_batch_*.json")
