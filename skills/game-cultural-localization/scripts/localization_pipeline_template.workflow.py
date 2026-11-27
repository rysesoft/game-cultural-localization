"""Antigravity Dynamic Workflow (/run-workflow) template: 4-phase game culturalization pipeline.

HOW TO RUN (Antigravity only):
    /run-workflow Run skills/game-cultural-localization/scripts/localization_pipeline_template.workflow.py
    with args {"locale": "de-DE", "scratch_dir": "loc_work", "batches": ["01", "02"], "plugin_dir": "<plugin path>",
               "context_map": "loc_work/context/CONTEXT_MAP.md"}

This file uses the Antigravity workflow DSL documented at
https://antigravity.google/docs/dynamic-workflows : the runtime injects
phase(), log(), agent(), parallel(), pipeline(), args and allows top-level await.
It is therefore NOT a standalone Python module (hence the .workflow.py suffix;
tests compile it with ast.PyCF_ALLOW_TOP_LEVEL_AWAIT).  For an API-independent
orchestration that runs with plain Python, see orchestrator_stub.py.

Phases (canonical numbering, see references/methodology_and_qa.md):
  Phase 0  Pre-flight: the context map must exist (context-cartographer, step 0), locale validation,
           <LOCALE>_BIBLE.md + transcreation ledger, font scan
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
# Context decides every word. The map of the game comes first, no term is ever locked in a list.
CONTEXT_MAP = (args.get("context_map") or f"{SCRATCH}/context/CONTEXT_MAP.md").replace("\\", "/")
CONTEXT_DIR = os.path.dirname(CONTEXT_MAP) or "."
LINE_NOTES = f"{CONTEXT_DIR}/line_notes.json"                 # per key notes of the context scouts
APPENDIX = f"{CONTEXT_DIR}/CONTEXT_MAP.{LOCALE}.md"            # choices of an existing translation, writers only
# The critic reads the jurors' English view. The user's map and notes may be written in the target language by
# scouts who saw an existing translation, and then carry its names (the first tr-TR calibration matched on them).
JURY_MAP = f"{CONTEXT_DIR}/CONTEXT_MAP.jury.md"
JURY_NOTES = f"{CONTEXT_DIR}/line_notes.jury.json"
NEUTRAL_FIELDS = "screen, element, player_action, inserted, limit, speaker, listener and register_hint"
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
            f"Activate the game-cultural-localization skill. Read the context map {CONTEXT_MAP} first, then "
            f"{APPENDIX} if it exists, then {REFS}/{LOCALE}.md (including its Golden Voice Anchors A1-A5) and {BIBLE}. "
            f"For every key read its note in {LINE_NOTES}, it tells where the game shows the line, what the player is "
            f"doing, what the code inserts next to it, the room it has, who speaks and who listens. Translate the "
            f"clean-room batch {SCRATCH}/in_batch_{b}.json into natural, everyday spoken {LOCALE} and write "
            f"{SCRATCH}/pass1_batch_{b}.json with the same keys and a '{LOCALE}' target field. Choose every word for the "
            f"place where the game shows the line. No term is locked in a list, the same source word may need different "
            f"words in different places. Spell proper names as the context map names them. Preserve every placeholder "
            f"({PH_STYLE} style), rich-text tag ({TAG_STYLE} style) and leading or trailing space. Finish with ok=true and "
            f"the output file path, or ok=false and the list of errors."
        )
    if step == "critique":
        return (
            f"You are the blind native-ear critic for {LOCALE}. Read ONLY {SCRATCH}/blind_{LOCALE}_{b}.json "
            f"(a target-only slice with key, category, speaker, archetype and target), the jurors' English view of the "
            f"context map {JURY_MAP}, the fields {NEUTRAL_FIELDS} of these keys in {JURY_NOTES} and {REFS}/{LOCALE}.md. "
            f"Only when {JURY_MAP} does not exist read {CONTEXT_MAP} and {LINE_NOTES} instead. Do NOT open any other "
            f"file, never {APPENDIX}, never a pass1 or final batch and never a source table. The map never quotes source "
            f"lines, so you stay blind to the source wording. Judge every line for the place where the game shows it, and check that it still reads "
            f"right with what the code inserts next to it. First ask of every word whether it belongs to everyday use of {LOCALE}, a rare, "
            f"bookish or dictionary word is not everyday even when it is correct, and a line with such a word scores 3 at most "
            f"(proper names, placeholders, tags and the game's own terms are not judged this way). Read every target aloud as a "
            f"native player and score naturalness 1-5. Write "
            f"{SCRATCH}/critique_{LOCALE}_{b}.json using exactly this schema: {{\"locale\", \"source_file\", "
            f"\"entries\": [{{\"key\", \"score\", \"issue_type\", \"reason\", \"suggested\"}}], "
            f"\"summary\": {{\"total\", \"flagged\", \"critical\"}}}} with only score<5 entries; issue_type is one of "
            f"translationese|register|tense|regional_leak|gender_leak|ui_verb|placeholder_grammar|terminology|other. "
            f"Finish with ok=true and the file path."
        )
    if step == "pass2":
        return (
            f"Activate the game-cultural-localization skill. Read the context map {CONTEXT_MAP}, {APPENDIX} if it exists, "
            f"{BIBLE}, the notes of these keys in {LINE_NOTES}, {SCRATCH}/pass1_batch_{b}.json and the "
            f"validated critique {SCRATCH}/critique_{LOCALE}_{b}.json. Apply every valid native-ear improvement "
            f"while preserving 100% of placeholders, rich-text tags, leading and trailing spaces and punctuation rules. "
            f"Keep names and terms as the context map and the appendix describe them for the place of each line, and "
            f"reject suggestions that rename items or buttons without evidence from the map or the source. Write "
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
        f"Activate the game-cultural-localization skill. First check that the context map {CONTEXT_MAP} exists. If it "
        f"does not, stop at once with ok=false and the error 'context map missing, run context-cartographer (Phase 0 "
        f"step 0) before any translation', nothing is translated or judged before the map exists. "
        f"Validate that '{LOCALE}' is one of the 15 supported locales "
        f"(run: python {SCRIPTS}/lqa_linter.py --version and python {SCRIPTS}/lqa_linter.py --help). "
        f"If {BIBLE} does not exist, create it from {CONTEXT_MAP}, {APPENDIX} if it exists, {REFS}/{LOCALE}.md and "
        f"{REFS}/transcreation_ledger_guide.md: terminology decisions taken from the context map, each tied to the place "
        f"it applies to (collision pairs such as Contract vs Order), never a locked list, per-archetype register (A1 Mentor, A2 Rival, "
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
         f"--context-cols category,speaker,archetype --out {SCRATCH}/blind_{LOCALE}_{b}.json" for b in BATCHES],
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
