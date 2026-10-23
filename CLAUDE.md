# insurance-claim-rag-system

RAG proof of concept on Amazon Bedrock: extract claim fields, retrieve the matching policy clauses, produce a
grounded coverage assessment and route the claim. Account `443845328805`, region `us-east-1`.

## Scope

- Plan: `.claude/plans/PLAN_insurance-claim-rag-system.md` · design: `docs/LLD/` · target architecture: `docs/HLD/`
- `src/claims_rag/components/` — reusable pieces with no claims knowledge; `src/claims_rag/app/` — claims logic
- Tests in `tests/`; Terraform in `terraform/` (state in `tsekatm-terraform-state-443845328805`, see
  `tsekatm/aws-account-bootstrap`; backend configs must set `kms_key_id`)
- Explain each step as **What / Why / Risk of not doing it** (learning project)

## Workflow

Inherit the root TBT workflow from the parent CLAUDE.md.

{{include:../../CLAUDE.md}}
