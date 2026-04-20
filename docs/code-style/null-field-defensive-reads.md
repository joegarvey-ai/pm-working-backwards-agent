# Defensive Reads at Input Boundaries

**Rule:** When reading from a dict whose values may be `None` — parsed input briefs, artifact frontmatter, CrewAI task context, anything that has crossed a parser/serializer boundary — use `(d.get(key) or default)`, **not** `d.get(key, default)`.

## Why

`dict.get(key, default)` returns the default **only when the key is absent**. A key that is present with value `None` passes `None` straight through. If the next operation is `.strip()`, `.lower()`, or any other method call, the code crashes with `AttributeError: 'NoneType' object has no attribute ...`.

The `(d.get(key) or default)` idiom handles both cases: an absent key and a present-but-`None` value both resolve to the default.

```python
# Bug: crashes when inputs["field"] is None
if not inputs.get("field", "").strip():
    ...

# Fix: tolerates absent key, empty string, and None
if not (inputs.get("field") or "").strip():
    ...
```

## Historical context

Two null-field crashes shipped to main in April 2026, both from the same pattern mismatch:

- [`91fcd27`](https://github.com/joegarvey-ai/pm-working-backwards-agent/commit/91fcd27) — `main.py` in `validate_input`: crashed when `parse_markdown_input` returned `None` for a markdown section that was present in the brief but empty after HTML-comment stripping.
- [`3e55378`](https://github.com/joegarvey-ai/pm-working-backwards-agent/commit/3e55378) — `vault.py` in `get_product_slug` and `get_initiative`: same pattern, same cause, different file.

Both bugs shipped within 24 hours. Both were caught only when an end-to-end run was attempted against the packaged example. Neither had test coverage of the `None` path. Both fixes were a one-line `(x or "")` transform at the read site.

## Enforcement

Run this grep before every push. Expected result: **zero matches**.

```bash
git grep -nE 'get\([^,]*, *""\)\.'
```

If the grep returns any hits, each one is a potential `AttributeError` waiting for a `None` input to trigger it. Either:

1. Convert the call to `(d.get(key) or default)`, or
2. Add explicit test coverage for the `None` path, confirming the surrounding code either handles `None` correctly or that the dict's producer guarantees no `None` values.

## When this rule doesn't apply

The rule protects against **unknown-provenance dicts** that crossed a parser/deserializer boundary. It does not need to apply when `None` is impossible by construction:

- Static config dicts where every value is a literal string
- Enum or constant maps where `None` values are impossible by type
- Dicts built inline a few lines above the read site with all-string values
- Dicts typed with a `TypedDict` that forbids optional `None` values

Over-applying the rule adds visual noise. Under-applying it ships bugs. When in doubt, add `(x or default)` — the cost of a slightly noisier read is lower than the cost of a production `AttributeError`.
