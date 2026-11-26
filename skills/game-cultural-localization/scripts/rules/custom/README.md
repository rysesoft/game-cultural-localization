# Project-specific linter rules

Drop any `*.json` file in this folder (or pass `--rules <dir>` / `"rules_dir"` in `l10n.config.json`) to add
rules for your own game. Each file follows [rules.schema.json](../rules.schema.json):

```json
{
  "locale": "de-DE",
  "rules": [
    {
      "id": "PROJ-DE-NO-SIE",
      "severity": "WARN",
      "pattern": "\\bSie\\b",
      "flags": "",
      "message": "This project addresses the player with 'du'",
      "context": "any",
      "examples": { "match": ["Haben Sie Zeit?"], "nomatch": ["Hast du Zeit?"] }
    }
  ]
}
```

* The `locale` field selects which `--locale` run loads the file; aliases (`de`, `de_DE`) are accepted.
* Rule ids must be unique across built-in + custom files (a duplicate id aborts with exit 2).
* `examples` are optional but recommended: `tests/test_rules_selftest.py` verifies every rule file found here as well.
* To suppress a rule on one string, add an `lqa_ignore` field to that row (`"lqa_ignore": "DE-EHE, PROJ-DE-NO-SIE"`).
