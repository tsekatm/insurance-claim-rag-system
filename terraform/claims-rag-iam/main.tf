# Runtime role for the PoC — LLD §9 row 2. Assumed by the developer's SSO session; no long-lived keys.

data "aws_caller_identity" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  storage       = data.terraform_remote_state.storage.outputs
  profile_arns  = [for id in var.model_inference_profile_ids : "arn:aws:bedrock:${var.aws_region}:${local.account_id}:inference-profile/${id}"]
  model_ids     = [for id in var.model_inference_profile_ids : trimprefix(id, "us.")] # profile "us.x" serves model "x"
  routed_models = flatten([for r in var.profile_destination_regions : [for m in local.model_ids : "arn:aws:bedrock:${r}::foundation-model/${m}"]])
  direct_models = [for m in var.embedding_model_ids : "arn:aws:bedrock:${var.aws_region}::foundation-model/${m}"]
}

resource "aws_iam_role" "runtime" {
  name                 = "insurance-claim-rag-runtime-role"
  description          = "insurance-claim-rag-system PoC runtime: claims bucket objects, claims key, listed Bedrock models"
  max_session_duration = 3600
  assume_role_policy   = data.aws_iam_policy_document.runtime_trust.json
}

data "aws_iam_policy_document" "runtime_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.account_id}:root"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = ["arn:aws:iam::${local.account_id}:role/aws-reserved/sso.amazonaws.com/*AWSReservedSSO_${var.trusted_sso_permission_set}_*"]
    }
  }
}

resource "aws_iam_role_policy" "runtime" {
  name   = "insurance-claim-rag-runtime"
  role   = aws_iam_role.runtime.id
  policy = data.aws_iam_policy_document.runtime.json
}

data "aws_iam_policy_document" "runtime" {
  statement {
    sid       = "ClaimsObjects"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${local.storage.claims_bucket_arn}/claims/*"]
  }

  statement {
    sid       = "ClaimsKey"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [local.storage.claims_kms_key_arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${var.aws_region}.amazonaws.com"]
    }
  }

  # bedrock:InvokeModel also authorises the Converse API (there is no bedrock:Converse action).
  statement {
    sid       = "InvokeProfiles"
    actions   = ["bedrock:InvokeModel"]
    resources = local.profile_arns
  }

  statement {
    sid       = "InvokeFoundationModels"
    actions   = ["bedrock:InvokeModel"]
    resources = concat(local.routed_models, local.direct_models)
  }
}
