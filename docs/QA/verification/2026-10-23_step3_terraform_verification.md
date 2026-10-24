# Verification report — Step 3: Terraform (storage, runtime IAM, CI role)

**Date**: 2026-10-23 · **Account**: 443845328805 · **Region**: us-east-1 · **Environment**: dev
**Verdict**: PASS for step 3 scope (infrastructure only — no application code deployed yet)

| # | Gate | Result | Evidence |
| :- | :- | :- | :- |
| 1 | TDD red | 31/31 post-apply tests failed before apply; OIDC test 2/2 failed | `pytest tests/deployment -m deployment` |
| 2 | Static checks | fmt ✅ · validate ✅ · tflint 0.65.0 ✅ · checkov 118 passed / 0 failed / 8 skipped (inline, reasoned) | local run |
| 3 | Plans approved | A: github-oidc 1 add · B: storage 17 add · C: iam 2 add · D: ci 2 add — all 0 change / 0 destroy | owner approval 2026-10-23 (C, D on the "exact match" condition) |
| 4 | Apply | 22 resources added across 4 folders | `terraform apply tfplan` per folder |
| 5 | Post-apply (green) | claims 31/31 passed, 0 skipped · bootstrap 10/10 passed, 0 skipped | `pytest -rfEs` |
| 6 | Drift | `plan -detailed-exitcode` = 0 for all 4 folders | local run |
| 7 | CI | static checks for all 3 folders added to `ci.yml` | PR run (see PR) |

## What the post-apply tests prove

- Claims bucket: SSE-KMS with a rotating customer-managed key, bucket key on, versioned, public access blocked,
  ACLs disabled, 30-day expiry, access logs to the log bucket; policy denies non-TLS, non-KMS and other-key uploads.
- Log bucket: SSE-S3 (only option for S3 access-log targets), only `logging.s3.amazonaws.com` from the claims
  bucket in this account may write.
- Runtime role (IAM policy simulator, read-only): allowed — Put/Get under `claims/*`, InvokeModel on the five
  profiles, the foundation models in us-east-1/us-east-2/us-west-2, Titan V2; **denied** — PutObject outside
  `claims/`, DeleteObject, an unlisted model (`us.anthropic.claude-opus-4-8`). Trust: SSO AdministratorAccess only.
- CI role: trust limited to `repo:tsekatm/insurance-claim-rag-system:environment:dev`; **denied** —
  PutRolePolicy / UpdateAssumeRolePolicy / AttachRolePolicy on itself, CreateBucket, GetObject on claims.

## Accepted exceptions

| Item | Reason | Accepted |
| :- | :- | :- |
| CI role `kms:ListAliases` on `"*"` | action has no resource-level scoping; read-only | owner, 2026-10-23 |
| checkov skips (8) | key-policy `"*"` = this key; SSE-S3 required for access-log target; no replication / event consumers in a single-region PoC | inline in `claims-rag-storage/main.tf` |

## Defects found during the step

| # | Defect | Fix |
| :- | :- | :- |
| 1 | A post-apply assertion ended in `or True` (could never fail — TBT Law 13) | Replaced with a real `== "allowed"` assertion before any run |
| 3 | First `deploy-dev` run (40018620692): OIDC `AssumeRoleWithWebIdentity` denied. CloudTrail showed GitHub's immutable subject `repo:tsekatm@86061117/insurance-claim-rag-system@1431391826:environment:dev`; the trust policy expected `repo:tsekatm/insurance-claim-rag-system:environment:dev` | Trust test updated first (red), CI role trust changed to the immutable subject (plan 1 change, approved, applied by hand); post-apply 31/31 |
| 2 | LLD said `CLAIMS_KMS_KEY_ID` = alias ARN; the bucket policy compares the key ARN in the request, so an alias would be denied | LLD corrected to the key ARN (`claims_kms_key_arn` output) |

## Not yet verified (later steps)

Application upload/invoke against these resources (step 6 integration test).

## Step 3a — deploy-dev.yml

- Trigger: push to `main` touching `terraform/claims-rag-{storage,iam}/**`, `tests/deployment/**` or the workflow; also manual.
- GitHub `dev` environment: deployments from `main` only (required reviewer removed 2026-10-24, owner decision; run 40020720952 ran with it); `secrets.AWS_ROLE_ARN`, `vars.AWS_REGION`, `vars.TF_STATE_BUCKET`, `vars.TF_STATE_REGION`.
- Jobs: `quality` (reusable `ci.yml`) → `plan` (plan in job summary; digest of planned changes) → `apply` (re-plan must match the reviewed digest, then apply, then post-apply tests that fail on any skip).
- Config parity check: GitHub vars vs committed `dev.tfvars`.
- First green run: [40020720952](https://github.com/tsekatm/insurance-claim-rag-system/actions/runs/40020720952)
  (head `909264b`, 2026-10-24, triggered by the PR #5 merge). OIDC login as `insurance-claim-rag-ci-role` ✅ ·
  plan: no changes in `claims-rag-storage` and `claims-rag-iam` ✅ · re-plan digest matched the reviewed plan ✅ ·
  apply 0/0/0 ✅ · post-apply 31 passed, 0 skipped (`REQUIRE_DEPLOYMENT_CHECKS=1`) ✅.

**Step 3 verdict: PASS.**
