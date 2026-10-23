# Upstream outputs are read from their Terraform state — never retyped into tfvars.

variable "tf_state_bucket" {
  description = "Shared Terraform state bucket (vars.TF_STATE_BUCKET in CI)."
  type        = string
}

variable "tf_state_region" {
  description = "The state bucket's region — not the resources' region."
  type        = string
}

data "terraform_remote_state" "storage" {
  backend = "s3"
  config = {
    bucket = var.tf_state_bucket
    key    = "insurance-claim-rag-system/claims-rag-storage/terraform.tfstate"
    region = var.tf_state_region
  }
}

data "terraform_remote_state" "iam" {
  backend = "s3"
  config = {
    bucket = var.tf_state_bucket
    key    = "insurance-claim-rag-system/claims-rag-iam/terraform.tfstate"
    region = var.tf_state_region
  }
}
