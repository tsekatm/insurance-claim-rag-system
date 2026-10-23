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

variable "claims_retention_days" {
  description = "Days before uploaded claim documents expire (synthetic data only)."
  type        = number
  default     = 30
}

variable "access_log_retention_days" {
  description = "Days before S3 server access logs expire."
  type        = number
  default     = 90
}
