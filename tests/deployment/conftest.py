"""Shared fixtures for post-apply tests. Read-only AWS calls; missing credentials are a hard failure."""

import os

import boto3
import pytest

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
REGION = os.environ.get("AWS_REGION", "us-east-1")
MANDATORY_TAGS = {"Project", "Phase", "Environment", "Component", "ManagedBy", "CostCenter"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/deployment/" in str(item.fspath):
            item.add_marker(pytest.mark.deployment)


@pytest.fixture(scope="session")
def account_id() -> str:
    try:
        return str(boto3.client("sts", region_name=REGION).get_caller_identity()["Account"])
    except Exception as exc:  # hard-fail: no credentials means the gate did not run
        pytest.fail(f"No AWS credentials — post-apply gate cannot run: {exc}")


@pytest.fixture(scope="session")
def s3(account_id: str):  # noqa: ANN201 - boto3 client
    return boto3.client("s3", region_name=REGION)


@pytest.fixture(scope="session")
def iam(account_id: str):  # noqa: ANN201
    return boto3.client("iam")


@pytest.fixture(scope="session")
def kms(account_id: str):  # noqa: ANN201
    return boto3.client("kms", region_name=REGION)


@pytest.fixture(scope="session")
def claims_bucket() -> str:
    return f"insurance-claim-rag-claims-{ENVIRONMENT}"


@pytest.fixture(scope="session")
def logs_bucket() -> str:
    return f"insurance-claim-rag-access-logs-{ENVIRONMENT}"
