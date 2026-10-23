"""Post-apply: terraform/claims-rag-storage (LLD §9 row 1)."""

import json

from tests.deployment.conftest import MANDATORY_TAGS, REGION


def _policy(s3, bucket):
    return json.loads(s3.get_bucket_policy(Bucket=bucket)["Policy"])["Statement"]


def test_claims_bucket_in_region(s3, claims_bucket):
    assert (s3.get_bucket_location(Bucket=claims_bucket)["LocationConstraint"] or "us-east-1") == REGION


def test_claims_bucket_sse_kms_with_rotating_cmk(s3, kms, claims_bucket):
    rule = s3.get_bucket_encryption(Bucket=claims_bucket)["ServerSideEncryptionConfiguration"]["Rules"][0]
    default = rule["ApplyServerSideEncryptionByDefault"]
    assert default["SSEAlgorithm"] == "aws:kms"
    assert rule.get("BucketKeyEnabled") is True
    key = kms.describe_key(KeyId=default["KMSMasterKeyID"])["KeyMetadata"]
    assert key["KeyManager"] == "CUSTOMER"
    assert kms.get_key_rotation_status(KeyId=key["KeyId"])["KeyRotationEnabled"] is True
    aliases = kms.list_aliases(KeyId=key["KeyId"])["Aliases"]
    assert "alias/insurance-claim-rag-claims" in {a["AliasName"] for a in aliases}


def test_claims_bucket_versioned(s3, claims_bucket):
    assert s3.get_bucket_versioning(Bucket=claims_bucket).get("Status") == "Enabled"


def test_both_buckets_block_public_access_and_disable_acls(s3, claims_bucket, logs_bucket):
    for bucket in (claims_bucket, logs_bucket):
        assert all(s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"].values())
        rules = s3.get_bucket_ownership_controls(Bucket=bucket)["OwnershipControls"]["Rules"]
        assert rules[0]["ObjectOwnership"] == "BucketOwnerEnforced"


def test_claims_bucket_logs_to_access_log_bucket(s3, claims_bucket, logs_bucket):
    logging = s3.get_bucket_logging(Bucket=claims_bucket)["LoggingEnabled"]
    assert logging["TargetBucket"] == logs_bucket


def test_access_log_bucket_encrypted_sse_s3(s3, logs_bucket):
    # S3 server access logging supports only SSE-S3 on the target bucket.
    rule = s3.get_bucket_encryption(Bucket=logs_bucket)["ServerSideEncryptionConfiguration"]["Rules"][0]
    assert rule["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"


def test_claims_objects_expire_after_30_days(s3, claims_bucket):
    rules = [
        r
        for r in s3.get_bucket_lifecycle_configuration(Bucket=claims_bucket)["Rules"]
        if r["Status"] == "Enabled"
    ]
    assert any(r.get("Expiration", {}).get("Days") == 30 for r in rules)
    assert any("NoncurrentVersionExpiration" in r for r in rules)


def test_claims_policy_denies_non_tls_non_kms_and_wrong_key(s3, claims_bucket):
    statements = _policy(s3, claims_bucket)
    denies = [s for s in statements if s["Effect"] == "Deny"]
    conditions = json.dumps([s.get("Condition", {}) for s in denies])
    assert "aws:SecureTransport" in conditions
    assert 's3:x-amz-server-side-encryption"' in conditions
    assert "s3:x-amz-server-side-encryption-aws-kms-key-id" in conditions


def test_log_bucket_allows_only_s3_logging_service_from_this_bucket(
    s3, logs_bucket, claims_bucket, account_id
):
    allows = [s for s in _policy(s3, logs_bucket) if s["Effect"] == "Allow"]
    assert len(allows) == 1
    stmt = allows[0]
    assert stmt["Principal"] == {"Service": "logging.s3.amazonaws.com"}
    cond = json.dumps(stmt["Condition"])
    assert f"arn:aws:s3:::{claims_bucket}" in cond and account_id in cond


def test_mandatory_tags(s3, claims_bucket, logs_bucket):
    for bucket in (claims_bucket, logs_bucket):
        tags = {t["Key"] for t in s3.get_bucket_tagging(Bucket=bucket)["TagSet"]}
        assert MANDATORY_TAGS <= tags, f"{bucket} missing {MANDATORY_TAGS - tags}"
