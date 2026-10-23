output "runtime_role_arn" {
  description = "role_arn for the local AWS profile that runs the PoC."
  value       = aws_iam_role.runtime.arn
}

output "runtime_role_name" {
  description = "Used by the CI role policy."
  value       = aws_iam_role.runtime.name
}
