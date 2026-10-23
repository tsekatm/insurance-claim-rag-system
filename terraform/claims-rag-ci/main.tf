# CI deploy role for GitHub Actions — LLD §9 row 3.
# APPLIED BY HAND WITH ELEVATED CREDENTIALS ONLY. CI must never apply this folder: a role that can edit its own
# policy can escalate its own privileges (workspace CI Role Self-IAM Bootstrap rule).
# CI applies claims-rag-storage and claims-rag-iam as updates to existing resources; first creation is manual.

data "aws_caller_identity" "current" {}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com" # tsekatm/aws-account-bootstrap terraform/github-oidc
}

data "aws_kms_alias" "state" {
  name = "alias/terraform-state" # tsekatm/aws-account-bootstrap terraform/state-bucket
}

locals {
  account_id      = data.aws_caller_identity.current.account_id
  storage         = data.terraform_remote_state.storage.outputs
  runtime_role    = "arn:aws:iam::${local.account_id}:role/${data.terraform_remote_state.iam.outputs.runtime_role_name}"
  ci_role_arn     = "arn:aws:iam::${local.account_id}:role/insurance-claim-rag-ci-role"
  state_bucket    = "arn:aws:s3:::${var.tf_state_bucket}"
  state_prefix    = "insurance-claim-rag-system/"
  managed_buckets = [local.storage.claims_bucket_arn, "arn:aws:s3:::${local.storage.access_logs_bucket_name}"]
}

resource "aws_iam_role" "ci" {
  name                 = "insurance-claim-rag-ci-role"
  description          = "GitHub Actions deploy role for ${var.github_repository} (${var.github_environment})"
  max_session_duration = 3600
  assume_role_policy   = data.aws_iam_policy_document.ci_trust.json
}

data "aws_iam_policy_document" "ci_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role_policy" "ci" {
  name   = "insurance-claim-rag-ci"
  role   = aws_iam_role.ci.id
  policy = data.aws_iam_policy_document.ci.json
}

data "aws_iam_policy_document" "ci" {
  # ---- Terraform state (this repo's prefix only) ----
  statement {
    sid       = "StateList"
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.state_prefix}*"]
    }
  }

  statement {
    sid       = "StateObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"] # DeleteObject releases the S3 lockfile
    resources = ["${local.state_bucket}/${local.state_prefix}*"]
  }

  statement {
    sid       = "StateKey"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
    resources = [data.aws_kms_alias.state.target_key_arn]
  }

  # ---- claims-rag-storage: update existing buckets (no create, no delete, no object access) ----
  statement {
    sid = "ManageClaimsBuckets"
    actions = [
      "s3:Get*", "s3:List*", "s3:PutBucket*",
      "s3:PutLifecycleConfiguration", "s3:PutEncryptionConfiguration",
    ]
    resources = local.managed_buckets
  }

  statement {
    sid = "ManageClaimsKey"
    actions = [
      "kms:DescribeKey", "kms:GetKeyPolicy", "kms:GetKeyRotationStatus", "kms:ListResourceTags",
      "kms:EnableKeyRotation", "kms:PutKeyPolicy", "kms:TagResource", "kms:UntagResource",
      "kms:UpdateKeyDescription",
    ]
    resources = [local.storage.claims_kms_key_arn]
  }

  statement {
    sid       = "ReadKmsAliases"
    actions   = ["kms:ListAliases"]
    resources = ["*"] # kms:ListAliases supports no resource-level scoping; read-only
  }

  # ---- claims-rag-iam: update the runtime role only ----
  statement {
    sid = "ManageRuntimeRole"
    actions = [
      "iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole", "iam:ListRoleTags", "iam:PutRolePolicy", "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRole", "iam:UpdateRoleDescription", "iam:TagRole", "iam:UntagRole", "iam:SimulatePrincipalPolicy",
    ]
    resources = [local.runtime_role]
  }

  # ---- post-apply tests read this role; read-only, so it cannot change itself ----
  statement {
    sid = "ReadOwnRole"
    actions = [
      "iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
      "iam:ListRoleTags", "iam:SimulatePrincipalPolicy",
    ]
    resources = [local.ci_role_arn]
  }
}
