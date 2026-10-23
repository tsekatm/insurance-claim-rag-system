# Claims document storage — LLD §9 row 1. Diagram: "S3 claims bucket (SSE-KMS, private)" and "AWS KMS".

data "aws_caller_identity" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  claims_name  = "insurance-claim-rag-claims-${var.environment}"
  logs_name    = "insurance-claim-rag-access-logs-${var.environment}"
  claims_arn   = "arn:aws:s3:::${local.claims_name}"
  logs_arn     = "arn:aws:s3:::${local.logs_name}"
  every_caller = [{ type = "*", identifiers = ["*"] }]
}

# ---- claims encryption key ----------------------------------------------------------------------------

resource "aws_kms_key" "claims" {
  description             = "Encrypts claim documents in ${local.claims_name}"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.claims_key.json

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "claims" {
  name          = "alias/insurance-claim-rag-claims"
  target_key_id = aws_kms_key.claims.key_id
}

# Key use is granted by IAM policies in this account (runtime role, CI role); no cross-account access.
data "aws_iam_policy_document" "claims_key" {
  #checkov:skip=CKV_AWS_111:AWS default key policy; "*" in a key policy is this key only, use is granted by IAM
  #checkov:skip=CKV_AWS_109:AWS default key policy; administration stays with this account's IAM
  #checkov:skip=CKV_AWS_356:"*" in a key policy is this key only
  statement {
    sid       = "EnableIamPolicies"
    actions   = ["kms:*"]
    resources = ["*"] # in a key policy "*" means this key only

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.account_id}:root"]
    }
  }
}

# ---- access-log bucket --------------------------------------------------------------------------------

resource "aws_s3_bucket" "logs" {
  #checkov:skip=CKV_AWS_145:S3 server access logging supports only SSE-S3 on the target bucket
  #checkov:skip=CKV_AWS_144:single-region PoC; logs are disposable
  #checkov:skip=CKV2_AWS_62:no consumer for log-bucket events
  bucket = local.logs_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 server access logging supports only SSE-S3 on the target bucket.
resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "expire-access-logs"
    status = "Enabled"
    filter {}

    expiration {
      days = var.access_log_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.logs]
}

resource "aws_s3_bucket_policy" "logs" {
  bucket     = aws_s3_bucket.logs.id
  policy     = data.aws_iam_policy_document.logs.json
  depends_on = [aws_s3_bucket_public_access_block.logs]
}

data "aws_iam_policy_document" "logs" {
  statement {
    sid       = "AllowS3ServerAccessLogsFromClaimsBucket"
    actions   = ["s3:PutObject"]
    resources = ["${local.logs_arn}/claims/*"]

    principals {
      type        = "Service"
      identifiers = ["logging.s3.amazonaws.com"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.claims_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [local.logs_arn, "${local.logs_arn}/*"]

    dynamic "principals" {
      for_each = local.every_caller
      content {
        type        = principals.value.type
        identifiers = principals.value.identifiers
      }
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

# ---- claims bucket ------------------------------------------------------------------------------------

resource "aws_s3_bucket" "claims" {
  #checkov:skip=CKV_AWS_144:single-region PoC holding synthetic data only; versioning covers recovery
  #checkov:skip=CKV2_AWS_62:PoC uploads and processes in one call; EventBridge trigger is the production path (HLD)
  bucket = local.claims_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "claims" {
  bucket = aws_s3_bucket.claims.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "claims" {
  bucket                  = aws_s3_bucket.claims.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "claims" {
  bucket = aws_s3_bucket.claims.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "claims" {
  bucket = aws_s3_bucket.claims.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.claims.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_logging" "claims" {
  bucket        = aws_s3_bucket.claims.id
  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "claims/"

  depends_on = [aws_s3_bucket_policy.logs]
}

resource "aws_s3_bucket_lifecycle_configuration" "claims" {
  bucket = aws_s3_bucket.claims.id

  rule {
    id     = "expire-claim-documents"
    status = "Enabled"
    filter {}

    expiration {
      days = var.claims_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  depends_on = [aws_s3_bucket_versioning.claims]
}

resource "aws_s3_bucket_policy" "claims" {
  bucket     = aws_s3_bucket.claims.id
  policy     = data.aws_iam_policy_document.claims.json
  depends_on = [aws_s3_bucket_public_access_block.claims]
}

data "aws_iam_policy_document" "claims" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [local.claims_arn, "${local.claims_arn}/*"]

    dynamic "principals" {
      for_each = local.every_caller
      content {
        type        = principals.value.type
        identifiers = principals.value.identifiers
      }
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid       = "DenyNonKmsUploads"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${local.claims_arn}/*"]

    dynamic "principals" {
      for_each = local.every_caller
      content {
        type        = principals.value.type
        identifiers = principals.value.identifiers
      }
    }

    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }

  statement {
    sid       = "DenyOtherKmsKeys"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${local.claims_arn}/*"]

    dynamic "principals" {
      for_each = local.every_caller
      content {
        type        = principals.value.type
        identifiers = principals.value.identifiers
      }
    }

    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = [aws_kms_key.claims.arn]
    }
  }
}
