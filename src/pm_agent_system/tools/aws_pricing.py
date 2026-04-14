"""AWS Pricing API tool for Agent 3 cost flagging.

Uses the public AWS Price List API via boto3 to look up current pricing
for AWS services. The Pricing API endpoint is only available in
us-east-1 and ap-south-1.

Rate limit: 10 requests/second (not a practical concern for BRD
generation, which typically makes 2-5 lookups per run).
"""

import json
import logging
from typing import Optional

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from crewai.tools import BaseTool
from pydantic import Field

logger = logging.getLogger(__name__)

# Map natural service names to AWS service codes.
SERVICE_CODE_MAP = {
    "lambda": "AWSLambda",
    "dynamodb": "AmazonDynamoDB",
    "s3": "AmazonS3",
    "ec2": "AmazonEC2",
    "cognito": "AmazonCognito",
    "api gateway": "AmazonApiGateway",
    "apigateway": "AmazonApiGateway",
    "cloudfront": "AmazonCloudFront",
    "sqs": "AWSQueueService",
    "sns": "AmazonSNS",
    "eventbridge": "AmazonEventBridge",
    "rds": "AmazonRDS",
    "aurora": "AmazonRDS",
    "ecs": "AmazonECS",
    "opensearch": "AmazonES",
    "bedrock": "AmazonBedrock",
    "sagemaker": "AmazonSageMaker",
}

SUPPORTED_SERVICES = (
    "Lambda, DynamoDB, S3, EC2, Cognito, API Gateway, CloudFront, "
    "SQS, SNS, EventBridge, RDS, ECS, OpenSearch, Bedrock, SageMaker"
)

MAX_PRODUCT_FAMILIES = 10


def _resolve_service_code(name: str) -> str:
    """Resolve a natural name like 'lambda' to an AWS service code."""
    key = name.strip().lower()
    return SERVICE_CODE_MAP.get(key, name)


def _build_client(region: str = "us-east-1") -> boto3.client:
    """Create a Pricing API client.

    Tries unsigned (no credentials) first. If that fails at call time,
    the caller should retry with default credentials.
    """
    try:
        return boto3.client(
            "pricing",
            region_name=region,
            config=Config(signature_version=UNSIGNED),
        )
    except Exception:
        # Fall back to default credential chain.
        return boto3.client("pricing", region_name=region)


def _extract_pricing(products: list[dict], service_code: str) -> str:
    """Parse pricing API response into a readable summary."""
    if not products:
        return f"No pricing data returned for {service_code}."

    families: dict[str, list[str]] = {}

    for product_json in products:
        product = json.loads(product_json) if isinstance(product_json, str) else product_json
        attributes = product.get("product", {}).get("attributes", {})
        family = attributes.get("productFamily", "Other")
        terms = product.get("terms", {})

        for term_type in ("OnDemand", "Reserved"):
            term_group = terms.get(term_type, {})
            for _offer_key, offer in term_group.items():
                for _dim_key, dimension in offer.get("priceDimensions", {}).items():
                    desc = dimension.get("description", "")
                    price_per_unit = dimension.get("pricePerUnit", {})
                    usd = price_per_unit.get("USD", "")
                    unit = dimension.get("unit", "")
                    if usd and desc:
                        entry = f"  - {desc}: ${usd} per {unit}"
                        families.setdefault(family, []).append(entry)

    if not families:
        return f"Pricing data for {service_code} was returned but contained no parseable price dimensions."

    lines = [f"AWS {service_code} Pricing (current):"]

    shown = 0
    for family_name, entries in sorted(families.items()):
        if shown >= MAX_PRODUCT_FAMILIES:
            remaining = len(families) - shown
            lines.append(
                f"\n... and {remaining} more product families. "
                f"See https://aws.amazon.com/pricing/ for full details."
            )
            break
        lines.append(f"\n{family_name}:")
        # Deduplicate and limit entries per family.
        seen = set()
        for entry in entries[:15]:
            if entry not in seen:
                seen.add(entry)
                lines.append(entry)
        if len(entries) > 15:
            lines.append(f"  ... ({len(entries) - 15} more pricing dimensions)")
        shown += 1

    return "\n".join(lines)


class AWSPricingTool(BaseTool):
    name: str = "aws_pricing_lookup"
    description: str = (
        "Looks up current AWS service pricing from the official AWS Price List API. "
        "Use this when flagging cost-relevant decisions in the BRD. "
        "Input: an AWS service name (e.g., 'DynamoDB', 'Lambda', 'S3'). "
        "Returns: pricing dimensions, tiers, and per-unit costs for the specified service in us-east-1."
    )

    region: str = Field(default="us-east-1", exclude=True)

    def _run(self, service_code: str, region: Optional[str] = None) -> str:
        """Query AWS Price List API for a service's pricing.

        Args:
            service_code: AWS service name (natural name like 'Lambda' or
                API code like 'AWSLambda').
            region: AWS region to filter pricing for. Defaults to us-east-1.
        """
        target_region = region or self.region
        resolved = _resolve_service_code(service_code)

        try:
            client = _build_client()
        except Exception as exc:
            return (
                f"Failed to create AWS Pricing API client: {exc}. "
                f"Check your AWS credentials or look up pricing at "
                f"https://aws.amazon.com/pricing/"
            )

        try:
            response = client.get_products(
                ServiceCode=resolved,
                Filters=[
                    {
                        "Type": "TERM_MATCH",
                        "Field": "regionCode",
                        "Value": target_region,
                    },
                ],
                MaxResults=100,
            )
        except client.exceptions.NotFoundException:
            return (
                f"Could not find pricing for '{service_code}' "
                f"(resolved to '{resolved}'). "
                f"Try one of: {SUPPORTED_SERVICES}."
            )
        except Exception as exc:
            error_code = getattr(getattr(exc, "response", {}), "get", lambda *a: None)(
                "Error", {}
            )
            if isinstance(error_code, dict):
                error_code = error_code.get("Code", "")

            if "InvalidParameterValue" in str(exc) or "ValidationException" in str(exc):
                return (
                    f"Could not find pricing for '{service_code}' "
                    f"(resolved to '{resolved}'). "
                    f"Try one of: {SUPPORTED_SERVICES}."
                )

            return (
                f"AWS Pricing API error: {exc}. "
                f"Look up pricing at https://aws.amazon.com/{service_code.lower()}/pricing/"
            )

        products = response.get("PriceList", [])
        return _extract_pricing(products, resolved)
