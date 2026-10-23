"""Post-apply: terraform/claims-rag-iam and terraform/claims-rag-ci (LLD §9 rows 2–3).

Negative tests use iam:SimulatePrincipalPolicy — read-only, nothing is invoked.
"""

import json
import urllib.parse

import pytest

from tests.deployment.conftest import ENVIRONMENT, MANDATORY_TAGS, REGION

RUNTIME_ROLE = "insurance-claim-rag-runtime-role"
CI_ROLE = "insurance-claim-rag-ci-role"
ALLOWED_PROFILES = [
    "us.anthropic.claude-haiku-5-5",
    "us.anthropic.claude-sonnet-5-5",
    "us.anthropic.claude-opus-5-5",
    "us.amazon.nova-pro-v1:0",
    "us.amazon.nova-lite-v1:0",
]


def _role(iam, name):
    return iam.get_role(RoleName=name)["Role"]


def _trust(role):
    doc = role["AssumeRolePolicyDocument"]
    return json.loads(urllib.parse.unquote(doc)) if isinstance(doc, str) else doc


def _inline_statements(iam, name):
    statements = []
    for policy_name in iam.list_role_policies(RoleName=name)["PolicyNames"]:
        doc = iam.get_role_policy(RoleName=name, PolicyName=policy_name)["PolicyDocument"]
        statements += doc["Statement"]
    return statements


def _decision(iam, role_arn, action, resource):
    result = iam.simulate_principal_policy(
        PolicySourceArn=role_arn, ActionNames=[action], ResourceArns=[resource]
    )["EvaluationResults"][0]
    return result["EvalDecision"]


# ---- runtime role -------------------------------------------------------------------------------------


def test_runtime_role_trusts_only_sso_administrator(iam, account_id):
    role = _role(iam, RUNTIME_ROLE)
    (stmt,) = _trust(role)["Statement"]
    assert stmt["Principal"] == {"AWS": f"arn:aws:iam::{account_id}:root"}
    assert "AWSReservedSSO_AdministratorAccess_" in json.dumps(stmt["Condition"])
    assert role["MaxSessionDuration"] == 3600


@pytest.mark.parametrize("role_name", [RUNTIME_ROLE, CI_ROLE])
def test_no_wildcard_only_actions_and_no_managed_policies(iam, role_name):
    assert iam.list_attached_role_policies(RoleName=role_name)["AttachedPolicies"] == []
    for stmt in _inline_statements(iam, role_name):
        actions = stmt["Action"] if isinstance(stmt["Action"], list) else [stmt["Action"]]
        assert "*" not in actions and not any(a.endswith(":*") for a in actions), stmt


def test_runtime_resources_never_wildcard(iam):
    for stmt in _inline_statements(iam, RUNTIME_ROLE):
        resources = stmt["Resource"] if isinstance(stmt["Resource"], list) else [stmt["Resource"]]
        assert "*" not in resources, stmt


def test_runtime_can_put_and_get_claim_objects_only(iam, claims_bucket):
    arn = _role(iam, RUNTIME_ROLE)["Arn"]
    assert _decision(iam, arn, "s3:PutObject", f"arn:aws:s3:::{claims_bucket}/claims/c1/a.pdf") == "allowed"
    assert _decision(iam, arn, "s3:GetObject", f"arn:aws:s3:::{claims_bucket}/claims/c1/a.pdf") == "allowed"
    assert _decision(iam, arn, "s3:PutObject", f"arn:aws:s3:::{claims_bucket}/other/a.pdf") != "allowed"
    assert (
        _decision(iam, arn, "s3:DeleteObject", f"arn:aws:s3:::{claims_bucket}/claims/c1/a.pdf") != "allowed"
    )


@pytest.mark.parametrize("profile", ALLOWED_PROFILES)
def test_runtime_can_invoke_each_allowed_profile(iam, account_id, profile):
    arn = _role(iam, RUNTIME_ROLE)["Arn"]
    resource = f"arn:aws:bedrock:{REGION}:{account_id}:inference-profile/{profile}"
    assert _decision(iam, arn, "bedrock:InvokeModel", resource) == "allowed"


@pytest.mark.parametrize("region", ["us-east-1", "us-east-2", "us-west-2"])
def test_runtime_can_invoke_foundation_models_in_profile_regions(iam, region):
    arn = _role(iam, RUNTIME_ROLE)["Arn"]
    resource = f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-sonnet-5-5"
    assert _decision(iam, arn, "bedrock:InvokeModel", resource) == "allowed"


def test_runtime_can_invoke_titan_embeddings(iam):
    arn = _role(iam, RUNTIME_ROLE)["Arn"]
    resource = f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
    assert _decision(iam, arn, "bedrock:InvokeModel", resource) == "allowed"


def test_runtime_denied_unlisted_model(iam, account_id):
    arn = _role(iam, RUNTIME_ROLE)["Arn"]
    resource = f"arn:aws:bedrock:{REGION}:{account_id}:inference-profile/us.anthropic.claude-opus-4-8"
    assert _decision(iam, arn, "bedrock:InvokeModel", resource) != "allowed"


# ---- CI role ------------------------------------------------------------------------------------------


def test_ci_role_trusts_only_this_repo_dev_environment(iam, account_id):
    (stmt,) = _trust(_role(iam, CI_ROLE))["Statement"]
    assert stmt["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert stmt["Principal"] == {
        "Federated": f"arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com"
    }
    cond = stmt["Condition"]["StringEquals"]
    assert cond["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert cond["token.actions.githubusercontent.com:sub"] == (
        f"repo:tsekatm/insurance-claim-rag-system:environment:{ENVIRONMENT}"
    )


def test_ci_role_cannot_modify_itself(iam):
    arn = _role(iam, CI_ROLE)["Arn"]
    for action in ("iam:PutRolePolicy", "iam:UpdateAssumeRolePolicy", "iam:AttachRolePolicy"):
        assert _decision(iam, arn, action, arn) != "allowed", action


def test_ci_role_cannot_create_buckets_or_read_claims(iam, claims_bucket):
    arn = _role(iam, CI_ROLE)["Arn"]
    assert _decision(iam, arn, "s3:CreateBucket", "arn:aws:s3:::some-other-bucket") != "allowed"
    assert _decision(iam, arn, "s3:GetObject", f"arn:aws:s3:::{claims_bucket}/claims/c1/a.pdf") != "allowed"


def test_ci_role_can_manage_runtime_role_policy(iam):
    ci_arn = _role(iam, CI_ROLE)["Arn"]
    runtime_arn = _role(iam, RUNTIME_ROLE)["Arn"]
    assert _decision(iam, ci_arn, "iam:PutRolePolicy", runtime_arn) == "allowed"


@pytest.mark.parametrize("role_name", [RUNTIME_ROLE, CI_ROLE])
def test_roles_tagged(iam, role_name):
    tags = {t["Key"] for t in iam.list_role_tags(RoleName=role_name)["Tags"]}
    assert MANDATORY_TAGS <= tags, f"{role_name} missing {MANDATORY_TAGS - tags}"
