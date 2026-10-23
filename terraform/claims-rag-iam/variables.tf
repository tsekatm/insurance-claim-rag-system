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

variable "model_inference_profile_ids" {
  description = "Cross-region inference profiles the runtime may invoke (LLD §4.14 models + judge)."
  type        = list(string)
}

variable "profile_destination_regions" {
  description = "Regions the inference profiles route to (aws bedrock get-inference-profile) — LLD TBC2."
  type        = list(string)
}

variable "embedding_model_ids" {
  description = "On-demand foundation models invoked directly in aws_region (embeddings)."
  type        = list(string)
}

variable "trusted_sso_permission_set" {
  description = "IAM Identity Center permission set whose role may assume the runtime role."
  type        = string
}
