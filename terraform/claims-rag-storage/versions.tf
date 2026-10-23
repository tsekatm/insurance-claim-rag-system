terraform {
  required_version = ">= 1.10" # S3 native state locking (use_lockfile)

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # State in tsekatm-terraform-state-{account_id} (tsekatm/aws-account-bootstrap); bucket, key and kms_key_id
  # come from environments/<env>.backend.hcl. Nothing environment-specific is in this file.
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "insurance-claim-rag-system"
      Phase       = var.phase
      Environment = var.environment
      Component   = "storage"
      ManagedBy   = "terraform"
      CostCenter  = var.cost_center
    }
  }
}
