#!/usr/bin/env python3
"""Static policy checks over the Terraform sources.

Some properties are about what is *absent*, and absence cannot be asserted
from a plan: a plan only describes the resources that exist. Those checks live
here, alongside a few textual invariants that are cheap to state and easy to
break silently.

The plan-level assertions live in ``infra/modules/*/tests/*.tftest.hcl`` and
run under ``terraform test`` with mocked providers.

Usage::

    python scripts/check_infra_policy.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INFRA = REPO_ROOT / "infra"

#: Resource types this design deliberately does not use. Each one is either a
#: standing cost, a request-time backend, or a weaker way of doing something
#: the design already does.
FORBIDDEN_RESOURCES: dict[str, str] = {
    "aws_nat_gateway": "A NAT Gateway is the largest avoidable cost here; the Lambda is not in a VPC.",
    "aws_vpc": "Nothing in this design needs a VPC.",
    "aws_api_gateway_rest_api": "There is no request-time API; the snapshot is a static file.",
    "aws_apigatewayv2_api": "There is no request-time API; the snapshot is a static file.",
    "aws_appsync_graphql_api": "There is no request-time API.",
    "aws_db_instance": "There is no database. The published snapshot is the whole data layer.",
    "aws_rds_cluster": "There is no database.",
    "aws_dynamodb_table": "No table is needed: S3 native locking replaces the Terraform lock table.",
    "aws_elasticache_cluster": "There is no cache tier; CloudFront is the cache.",
    "aws_ecs_service": "There is no always-on compute.",
    "aws_ecs_cluster": "There is no always-on compute.",
    "aws_eks_cluster": "There is no always-on compute.",
    "aws_instance": "There is no always-on compute.",
    "aws_lambda_provisioned_concurrency_config": (
        "Provisioned concurrency bills continuously for a job that runs twice an hour."
    ),
    "aws_s3_bucket_website_configuration": (
        "S3 website hosting is publicly readable and cannot be reached through Origin Access Control."
    ),
    "aws_s3_bucket_acl": "ACLs are disabled via BucketOwnerEnforced.",
    "aws_s3_bucket_public_access_block_policy": "Not a real resource; a typo would silently do nothing.",
    "aws_cloudfront_origin_access_identity": (
        "Origin Access Identity is the legacy mechanism; this design uses Origin Access Control."
    ),
    "aws_kms_key": "A customer-managed key is a standing monthly charge, and there are no secrets here.",
    "null_resource": (
        "Shell provisioners are not reproducible. Manual steps are documented instead."
    ),
}

#: Text that must appear somewhere in the Terraform sources.
REQUIRED_TEXT: list[tuple[str, str, str]] = [
    (
        "infra/environments/prod",
        'backend "s3"',
        "Production state must be remote.",
    ),
    (
        "infra/bootstrap",
        "use_lockfile",
        "The state bucket must document native S3 locking rather than a lock table.",
    ),
    (
        "infra/modules/static_delivery",
        "BucketOwnerEnforced",
        "Both buckets must disable ACLs.",
    ),
    (
        "infra/modules/static_delivery",
        "aws:SecureTransport",
        "Both buckets must deny requests that are not over TLS.",
    ),
    (
        "infra/modules/static_delivery",
        "origin_access_control_id",
        "CloudFront must reach S3 through Origin Access Control.",
    ),
]

RESOURCE_PATTERN = re.compile(r'^\s*(?:resource|data)\s+"([a-z0-9_]+)"', re.MULTILINE)


@dataclass
class Finding:
    file: str
    detail: str


def terraform_files() -> list[Path]:
    return sorted(path for path in INFRA.rglob("*.tf") if ".terraform" not in path.parts)


def check_forbidden_resources() -> list[Finding]:
    findings: list[Finding] = []
    for path in terraform_files():
        text = path.read_text(encoding="utf-8")
        for match in RESOURCE_PATTERN.finditer(text):
            resource_type = match.group(1)
            reason = FORBIDDEN_RESOURCES.get(resource_type)
            if reason is not None:
                findings.append(
                    Finding(
                        str(path.relative_to(REPO_ROOT)),
                        f"uses {resource_type}: {reason}",
                    )
                )
    return findings


def check_required_text() -> list[Finding]:
    findings: list[Finding] = []
    for relative, needle, reason in REQUIRED_TEXT:
        directory = REPO_ROOT / relative
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(directory.rglob("*.tf"))
            if ".terraform" not in path.parts
        )
        if needle not in combined:
            findings.append(Finding(relative, f"is missing {needle!r}: {reason}"))
    return findings


def check_production_is_not_destroyable() -> list[Finding]:
    """force_destroy must never be hard-coded true in a module."""
    findings: list[Finding] = []
    for path in terraform_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("force_destroy") and stripped.endswith("true"):
                findings.append(
                    Finding(
                        f"{path.relative_to(REPO_ROOT)}:{number}",
                        "sets force_destroy = true, which would let destroy empty a live bucket",
                    )
                )
    return findings


def check_no_hardcoded_account_ids() -> list[Finding]:
    """A committed account id is a small leak and a large source of confusion."""
    findings: list[Finding] = []
    pattern = re.compile(r"\b\d{12}\b")
    allowed = {"000000000000", "123456789012"}
    for path in terraform_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for candidate in pattern.findall(line):
                if candidate in allowed:
                    continue
                findings.append(
                    Finding(
                        f"{path.relative_to(REPO_ROOT)}:{number}",
                        f"contains what looks like a real AWS account id ({candidate})",
                    )
                )
    return findings


CHECKS = {
    "forbidden resource types": check_forbidden_resources,
    "required security settings": check_required_text,
    "production buckets are not destroyable": check_production_is_not_destroyable,
    "no hard-coded account identifiers": check_no_hardcoded_account_ids,
}


def main() -> int:
    if not INFRA.is_dir():
        print(f"No infra directory at {INFRA}", file=sys.stderr)
        return 1

    total = 0
    for name, check in CHECKS.items():
        findings = check()
        total += len(findings)
        if findings:
            print(f"FAIL  {name}")
            for finding in findings:
                print(f"        {finding.file} {finding.detail}")
        else:
            print(f"ok    {name}")

    if total:
        print(f"\n{total} infrastructure policy violation(s).", file=sys.stderr)
        return 1

    print(f"\nChecked {len(terraform_files())} Terraform files. No policy violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
