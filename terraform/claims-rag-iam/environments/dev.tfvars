aws_region      = "us-east-1"
environment     = "dev"
phase           = "1"
cost_center     = "personal"
tf_state_bucket = "tsekatm-terraform-state-443845328805"
tf_state_region = "us-east-1"

model_inference_profile_ids = [
  "us.anthropic.claude-haiku-5-5",
  "us.anthropic.claude-sonnet-5-5",
  "us.anthropic.claude-opus-5-5", # evaluation judge
  "us.amazon.nova-pro-v1:0",
  "us.amazon.nova-lite-v1:0",
]
profile_destination_regions = ["us-east-1", "us-east-2", "us-west-2"] # verified 2026-10-23
embedding_model_ids         = ["amazon.titan-embed-text-v2:0"]
trusted_sso_permission_set  = "AdministratorAccess"
