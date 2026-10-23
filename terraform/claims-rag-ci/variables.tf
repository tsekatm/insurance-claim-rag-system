variable "aws_region" {
  description = "Region for this folder's resources."
  type        = string
}

variable "environment" {
  description = "Environment name; also the S3 bucket name suffix."
  type        = string
}

variable "phase" {
  description = "Phase tag value."
  type        = string
}

variable "cost_center" {
  description = "CostCenter tag value."
  type        = string
}

variable "github_repository" {
  description = "owner/repo whose workflows may assume the CI role."
  type        = string
}

variable "github_environment" {
  description = "GitHub environment the deploy job runs in (required reviewer configured there)."
  type        = string
}
