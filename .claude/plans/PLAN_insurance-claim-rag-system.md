# PLAN_insurance-claim-rag-system

Version 1.2 — 2026-10-23 · Status: **DRAFT — section 8 decisions answered; awaiting state-bucket check and approval** (TBT Law 3)

Target architecture: `docs/HLD/claims-processing-architecture.png`. This plan builds the PoC slice of it and keeps
a swap point at every place the diagram's production service replaces a PoC piece.

## 1. Module

| # | Item | Value |
| :- | :- | :- |
| 1 | Repo | `github.com/tsekatm/insurance-claim-rag-system` (public) |
| 2 | What it is | RAG PoC that extracts claim fields, retrieves the matching policy clauses and produces a grounded coverage assessment with a routing decision |
| 3 | Stack | Python 3.12, boto3, PyYAML, numpy; Terraform for all AWS resources |
| 4 | AWS account / region | `443845328805` / `us-east-1` (widest Bedrock model choice) — both held in GitHub environment variables and `tfvars`, never in code |
| 5 | Environments | `dev` only for the PoC |
| 6 | Folder convention | Format follows `nttt-service-desk` component repos (`src/`, `tests/`, `terraform/<folder>/environments/`, `.github/workflows/`, `.claude/`) plus a `docs/` tree (`HLD/`, `LLD/`, `QA/`); only the parts that apply to this project are used |

## 2. Review findings this plan fixes

| # | Finding | Fix in this plan |
| :- | :- | :- |
| 1 | `process_claim(file_path)` builds its own dependencies — the monolith seam | `ClaimsProcessor` takes every dependency in its constructor; one `build_processor(settings)` factory wires them |
| 2 | `ContentValidator` has five responsibilities | Split into `output_validator`, `rules_engine`, `safety` (diagram stages ③ and ⑥) |
| 3 | Business rules hard-coded | Rules and routing thresholds are YAML in `rules/`, versioned like `prompts/` |
| 4 | `rag.py` is reusable but sits in `app/`; chunk+embed+rank in one class | `components/chunker.py` + `components/retriever.py` (`Retriever` protocol) |
| 5 | No swap point for Textract / Knowledge Bases | `DocumentReader` and `Retriever` protocols; PoC implementations now, production implementations named (not built) |
| 6 | Grounding check has nothing to match on | Chunks carry a stable `clause_id`; the assess prompt must cite `clause_id`s |
| 7 | Step ⑦ Choice missing | `components/router.py` → `route: auto_approve \| human_review` with the reason |
| 8 | Guardrails position unclear | Pipeline order fixed (section 5); PII redacted before anything is logged or persisted |
| 9 | SSE-S3 vs diagram SSE-KMS | Customer-managed KMS key, bucket default `aws:kms` with bucket key |
| 10 | `bedrock:Converse` is not an IAM action | Policy uses `bedrock:InvokeModel` on the inference-profile ARNs **and** the foundation-model ARNs they route to |
| 11 | Bucket created with AWS CLI | Terraform only; CLI limited to read-only model discovery |
| 12 | No `tests/` | `tests/` per the Test Pack Location Rule; TDD red→green per component |
| 13 | Steps not shaped for Step Functions | Each step is `dict -> dict`, so each can later become one Lambda / state |

## 3. Repository layout

```text
insurance-claim-rag-system/
├── CLAUDE.md                         # scope + {{include}} of the workspace TBT rules
├── README.md                         # employer/customer-facing overview, diagram, how to run, findings link
├── pyproject.toml · requirements.txt · requirements-dev.txt · .gitignore
├── .claude/{plans,state,logs,snapshots,staging}/
├── .github/workflows/
│   ├── ci.yml                        # PR + push: ruff, mypy, pytest unit, terraform fmt/validate/tflint/checkov
│   └── deploy-dev.yml                # added after step 3: plan → 🛑 environment approval → apply(dev) → post-apply tests
├── docs/
│   ├── HLD/claims-processing-architecture.png   # moved from projects/insurance-claims-rag/
│   ├── LLD/                          # LLD_insurance-claim-rag-system.md (written after this plan is approved)
│   ├── QA/verification/              # SDET verification reports
│   └── FINDINGS.md                   # Step 4 results table + production path
├── src/claims_rag/
│   ├── config.py                     # Settings dataclass loaded from env vars; model ID per step; no hard-coded region
│   ├── components/                   # Step 3 — no business logic, no knowledge of claims
│   │   ├── model_invoker.py          # ModelInvoker.converse / .embed (Converse API, adaptive retries, usage+latency)
│   │   ├── prompt_manager.py         # PromptTemplateManager.get / .render (versioned YAML)
│   │   ├── output_validator.py       # parse_json, validate_schema                      → diagram ③
│   │   ├── rules_engine.py           # RulesEngine.evaluate(data) from rules/*.yaml      → diagram ③
│   │   ├── safety.py                 # redact_pii, check_grounding (Guardrails stand-in) → diagram ⑥
│   │   ├── chunker.py                # split policy text → chunks with clause_id, source, section
│   │   ├── retriever.py              # Retriever protocol; InMemoryRetriever (Titan V2 + cosine) → diagram ④
│   │   ├── document_reader.py        # DocumentReader protocol; ConverseDocumentReader          → diagram ①
│   │   └── router.py                 # Router.decide(assessment, fields) from rules/routing.yaml → diagram ⑦
│   └── app/                          # Step 2 — claims business logic, uses components only via injection
│       ├── uploader.py               # upload_claim, get_document_bytes (SSE-KMS, metadata)
│       ├── steps.py                  # extract_fields, validate_fields, retrieve_clauses, assess_claim, guard_output — each dict → dict
│       └── claims_processor.py       # ClaimsProcessor.process(file_path) runs the steps; build_processor(settings)
├── prompts/
│   ├── extract.yaml                  # name, version, system, user_template, required_vars, params
│   └── assess.yaml
├── rules/
│   ├── business_rules.yaml           # amount > 0, incident_date not in future, policy_number regex
│   └── routing.yaml                  # confidence threshold, high-value amount threshold
├── data/
│   ├── policies/                     # 2–3 synthetic policy text files (motor, home)
│   ├── claims/                       # 3 synthetic claims: clean motor, home exclusion, messy scan
│   └── ground_truth/                 # hand-made expected JSON per claim
├── eval/
│   ├── run_eval.py                   # models × documents × 3 runs → CSV
│   └── results/
├── terraform/
│   ├── .checkov.yml
│   ├── claims-rag-storage/           # KMS CMK + alias, claims bucket, access-log bucket, policies   (apply 1st)
│   └── claims-rag-iam/               # PoC runtime role + least-privilege policy                    (apply 2nd)
│       └── each folder: versions.tf · main.tf · variables.tf · outputs.tf · remote_state.tf
│                        environments/dev.tfvars.example · dev.backend.hcl.example
└── tests/
    ├── __init__.py · conftest.py · fixtures/
    ├── test_model_invoker.py · test_prompt_manager.py · test_output_validator.py
    ├── test_rules_engine.py · test_safety.py · test_chunker.py · test_retriever.py
    ├── test_document_reader.py · test_router.py · test_uploader.py · test_steps.py
    ├── test_claims_processor.py      # wiring: fakes injected, no AWS
    ├── test_integration.py           # real Bedrock + S3 in dev, REQUIRE_DEPLOYMENT_CHECKS=1
    ├── test_post_apply.py            # read-only describe/get on Terraform resources
    └── reports/
```

The current empty root-level files (`config.py`, `components/`, `app/`, `eval/run_eval.py`) move under this
layout; `components/validator.py` and `app/rag.py` are replaced by the split files above.

## 4. Component contracts (summary — full signatures go in the LLD)

| Component | Public surface | Depends on |
| :- | :- | :- |
| `ModelInvoker` | `converse(model_id, system, user_text, document=None, temperature, max_tokens) -> {text, input_tokens, output_tokens, latency_ms, model_id}`; `embed(model_id, text) -> list[float]` (Titan V2 body — documented as model-specific) | injected `bedrock-runtime` client |
| `PromptTemplateManager` | `get(name, version=None)`, `render(name, variables, version=None) -> (system, user)` | `prompts/` dir |
| `output_validator` | `parse_json(text) -> dict` (raises `ValidationError`), `validate_schema(data, required) -> list[str]` | — |
| `RulesEngine` | `evaluate(data) -> list[str]` | `rules/business_rules.yaml` |
| `safety` | `redact_pii(text) -> str`, `check_grounding(cited_ids, chunks) -> bool` | — |
| `chunker` | `chunk(text, source, size, overlap) -> list[Chunk]` (`clause_id`, `source`, `section`, `text`) | — |
| `Retriever` (protocol) | `index(chunks)`, `retrieve(query, k) -> list[{clause_id, text, source, score}]` | `InMemoryRetriever` uses `ModelInvoker.embed` |
| `DocumentReader` (protocol) | `read(doc_bytes, fmt) -> DocumentInput` | `ConverseDocumentReader` passes bytes as a Converse document block |
| `Router` | `decide(assessment, fields) -> {route, reasons}` | `rules/routing.yaml` |

Production implementations named in FINDINGS.md, not built: `TextractDocumentReader`, `KnowledgeBaseRetriever`,
Bedrock Guardrails in place of `safety`, Step Functions in place of `ClaimsProcessor`, A2I, DynamoDB, SNS/SES.

## 5. Pipeline order (maps to the diagram)

`upload → fetch → ① read → ② extract (Haiku) → ③ validate schema + rules → ④ retrieve clauses → ⑤ assess + summarise (Sonnet) → ③ validate output → ⑥ grounding check + PII redaction → ⑦ route`

Result: fields, assessment, cited `clause_id`s, confidence, route + reasons, and per-step latency and tokens.
⑧–⑩ (A2I, DynamoDB, SNS/SES) are out of scope; the `route` field is the hand-off point.

## 6. Terraform

| Folder | Resources | Notes |
| :- | :- | :- |
| `claims-rag-storage` | `aws_kms_key` (rotation on) + alias; claims bucket `insurance-claim-rag-claims-dev` (SSE-KMS + bucket key, versioning, public-access block, `BucketOwnerEnforced`, TLS-only policy, deny unencrypted PUT, lifecycle); access-log bucket | `prevent_destroy` on buckets and key; six mandatory tags via `default_tags` |
| `claims-rag-iam` | Runtime role + policy: `s3:PutObject`/`GetObject` on `claims/*`; `kms:GenerateDataKey`/`Decrypt` on the key with `kms:ViaService = s3.<region>`; `bedrock:InvokeModel` on the chosen inference-profile and foundation-model ARNs only | No `*` actions or resources; reads storage outputs via `remote_state.tf` |

Quality gates before any plan is shown: `fmt -check`, `validate`, `tflint`, `checkov`. `terraform plan` is
presented to you and applied only after approval. Model access in the Bedrock console stays a manual step.

## 7. Build order (TDD: red → green → refactor for every row)

| # | Step | Gate |
| :- | :- | :- |
| 1 | Restructure scaffold to section 3; move diagram to `docs/HLD/`; CLAUDE.md, README skeleton, pyproject, CI lint/test job | commit |
| 2 | Write `docs/LLD/LLD_insurance-claim-rag-system.md` (full signatures, schemas, YAML formats) | 🛑 you approve the LLD |
| 3 | Terraform `claims-rag-storage` → `claims-rag-iam` (incl. CI OIDC role); local plan → approval → apply; post-apply tests | 🛑 you approve each `terraform plan` |
| 3a | `deploy-dev.yml` (best practice: OIDC, no long-lived keys; `vars.*`/`secrets.*` only; `dev` GitHub environment with required reviewer; plan artefact applied as reviewed; concurrency lock; pinned action SHAs; least-privilege `permissions:`) | 🛑 you confirm the first green run |
| 4 | `model_invoker` → `prompt_manager` → `output_validator` → `rules_engine` → `safety` → `chunker` → `retriever` → `document_reader` → `router` (unit tests with fakes, no AWS) | unit suite green |
| 5 | Synthetic data: 2–3 policies, 3 claims, ground-truth JSON | 🛑 you review the documents |
| 6 | `uploader` → `steps` → `claims_processor`; integration test against dev | integration green |
| 7 | `eval/run_eval.py` across Claude Sonnet, Claude Haiku, Nova Pro, Nova Lite × 3 runs | CSV produced |
| 8 | `docs/FINDINGS.md` + README results; SDET verification report in `docs/QA/verification/` | 🛑 final review |

## 7a. Assignment requirements → where they are met

### Testing steps (from the brief)

| # | Brief says | Build step | Evidence |
| :- | :- | :- | :- |
| 1 | Create sample claim documents | 5 | `data/claims/` — clean motor (PDF), home exclusion (DOCX), messy scan (image-only PDF), plus a TXT claim; `data/ground_truth/*.json` |
| 2 | Upload to your S3 bucket | 6 | `uploader.upload_claim` → `s3://insurance-claim-rag-claims-dev/claims/{claim_id}/…` (SSE-KMS); integration test asserts the object + metadata |
| 3 | Run the processor on different document types | 6–7 | PDF, DOCX, TXT and scanned PDF each run end to end; per-format pass/fail in the results CSV |
| 4 | Compare results from different models | 7 | Claude Sonnet, Claude Haiku, Nova Pro, Nova Lite × every claim × 3 runs |
| 5 | Document your findings | 8 | `docs/FINDINGS.md` + README results section |

### Evaluation criteria (from the brief)

| Criterion | Measured by | Output |
| :- | :- | :- |
| Accuracy of information extraction | Field-by-field match vs ground truth (exact for IDs/dates/amounts, normalised for names); valid-JSON rate | Accuracy % per model × field × document type |
| Quality of generated summaries | 1–5 rubric (correctness, coverage decision, cites clauses, concise) scored by a stronger model as judge, spot-checked by hand; grounding check pass rate | Mean score per model |
| Processing time and efficiency | `latency_ms` per step and end to end; input/output tokens → cost per claim at on-demand prices; consistency across 3 runs | p50/max latency, $ per claim |
| Code organization and reusability | Components with no claims knowledge, injected dependencies, swap points (`DocumentReader`, `Retriever`); shown by swapping a model or prompt version via config only, with no code change | Short section in FINDINGS.md with the demo |

### Issues in the brief's sample code — fixed by design

| Sample code issue | Fix in this repo |
| :- | :- |
| `anthropic.claude-v2` + legacy text-completion body (one model family only) | Converse API in `ModelInvoker` — same call for Claude and Nova; current model IDs from config |
| Clients created at import time, model hard-coded | Clients injected; model ID per step in `Settings` |
| `decode('utf-8')` on the S3 object — PDFs/DOCX break | `DocumentReader` sends the bytes as a Converse document block with the right format |
| Extracted "JSON" kept as a raw string, never parsed or checked | `output_validator.parse_json` + `validate_schema`, then `RulesEngine` |
| Summary at temperature 0.7 — results vary run to run | Temperatures come from the prompt YAML (0 for extraction, low for assessment) |
| Summary not grounded in the policy | Retrieval of policy clauses + cited `clause_id`s + grounding check |
| Templates hard-coded in a class, no versions, no required-variable check | `PromptTemplateManager` over versioned YAML with `required_vars` |
| No retries, no error handling | Adaptive retries + backoff on throttling in `ModelInvoker`; typed errors |
| Model comparison measures only time and output length | `eval/run_eval.py` measures all four evaluation criteria above |

## 8. Decisions

| # | Question | Decision (2026-10-23) |
| :- | :- | :- |
| 1 | Code layout | `src/claims_rag/` |
| 2 | Terraform remote state | None existed → created by `tsekatm/aws-account-bootstrap` (`dcb6de7`): `tsekatm-terraform-state-443845328805`, S3 native locking; every backend config here must set `kms_key_id = alias/terraform-state` |
| 3 | Authentication | SSO (`personal-dev` profile) assumes the runtime role locally; separate CI OIDC role for GitHub Actions |
| 4 | Non-applicable workspace parts | Not included — `nttt-service-desk` was a format reference only |
| 5 | Deploy workflow | After the Terraform step (3a), following best practices |
| 6 | Scanned-claim support | Check Converse document-block behaviour at step 4; if image-only PDFs are not read, record it as a failure case |
