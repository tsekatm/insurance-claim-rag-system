# Verification report — Step 4: reusable components

**Date**: 2026-10-24 · **Scope**: `src/claims_rag/components/*`, `src/claims_rag/errors.py` (LLD §4.2–4.10, §8)
**Verdict**: PASS for step 4 scope (unit tests with fakes; nothing deployed — components first touch AWS in step 6)

| # | Gate | Result | Evidence |
| :- | :- | :- | :- |
| 1 | TDD red | every test file failed at collection (module missing) before its implementation was written | local run per component |
| 2 | Unit (green) | 150 passed, 0 failed, 0 skipped; coverage 99% | `pytest -m "not integration and not deployment"` |
| 3 | Static checks | `ruff format --check` ✅ · `ruff check` ✅ · `mypy --strict src` ✅ (16 files) | local run; CI on the PR |
| 4 | Deployed checks | not applicable to step 4 — no AWS calls; the post-apply suite is unchanged (31 passed on run 40074315806) | step 3 report |

## Tests per component

| Component | Tests | What they prove |
| :- | -: | :- |
| `errors` | 14 | every error subclasses `ClaimsRagError`; `ModelInvocationError` keeps model and code; `ProcessingError` names the step |
| `model_invoker` | 15 | Converse request shape (system, inferenceConfig, document/text/image blocks first); exactly one payload; name sanitising; `ClientError` → `ModelInvocationError` with **one** call (no hand-written retry); adaptive retries passed to botocore; Titan V2 body; `to_dict` never carries document bytes |
| `prompt_manager` | 16 | latest version compared numerically (1.10 > 1.9); literal JSON braces survive; values are not re-substituted; missing/extra variables; 7 malformed-file cases fail at construction |
| `output_validator` | 14 | fenced and surrounded JSON parsed; non-objects rejected; missing/wrong-type messages; `bool` never accepted as a number |
| `rules_engine` | 26 | each rule type incl. `2026-02-30` and future dates; nulls reported once (by `required`); full-match regex; 6 malformed-file cases |
| `safety` | 16 | email, SA ID and phone forms masked; policy numbers, dates and amounts untouched; idempotent; grounding with unknown and missing citations |
| `chunker` | 5 | clause never mixed with its neighbour; split sections get `#n` ids, stay within `size`, overlap carried, nothing lost; duplicate sections rejected |
| `retriever` | 6 | cosine ranking with unnormalised fake embeddings; `k` > index; errors before index, `k < 1`, empty and zero vectors |
| `document_reader` | 17 | formats and 4.5 MB limit; text-layer PDF delegated; image-only PDF → PNG pages at scale 2; short text layer counts as scanned; page limit; invalid PDF |
| `router` | 16 | each review trigger alone, boundaries (0.75, 50 000) not triggers, every triggered reason listed, 5 malformed-file cases |

## Found during the step

| # | Finding | Resolution |
| :- | :- | :- |
| 1 | Router reasons used `:g`, which rounds to 6 significant digits — `50000.01` printed as `50000`, a misleading review reason | Exact formatting helper; the red test that caught it stays |
| 2 | First `from_region` test inspected `client.meta.config.retries`, which botocore rewrites (drops `mode`) — the test, not the code, was wrong | Test now captures the `Config` passed to `boto3.client` |
| 3 | `pypdfium2` ships no type hints | Per-module `ignore_missing_imports` override in `pyproject.toml` (that module only) |
| 4 | Pillow 13.0.0 was 8 days old | Pinned 12.3.0; pypdfium2 5.14.0 |

## LLD changes (v1.2)

`DocumentInput.mode` records the document mode; page images over 3.75 MB are rejected; dependency pins; the
router also sends a claim with **no decision** to human review (an auto-approve without a decision would be
wrong). The dev GitHub environment no longer has a required reviewer (owner decision, 2026-10-24).

## Not yet verified (later steps)

`Settings` (§4.1) and the app layer (uploader, steps, processor) — step 6, with the integration test against dev.
