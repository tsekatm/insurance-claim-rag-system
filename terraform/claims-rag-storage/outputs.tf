output "claims_bucket_name" {
  description = "CLAIMS_BUCKET for the application."
  value       = aws_s3_bucket.claims.id
}

output "claims_bucket_arn" {
  description = "For IAM policies."
  value       = aws_s3_bucket.claims.arn
}

output "claims_kms_key_arn" {
  description = "CLAIMS_KMS_KEY_ID for the application; also scopes the runtime role's kms permissions."
  value       = aws_kms_key.claims.arn
}

output "access_logs_bucket_name" {
  description = "Server access log bucket."
  value       = aws_s3_bucket.logs.id
}
