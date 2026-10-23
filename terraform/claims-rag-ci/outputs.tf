output "ci_role_arn" {
  description = "Set as secrets.AWS_ROLE_ARN in the GitHub dev environment."
  value       = aws_iam_role.ci.arn
}
