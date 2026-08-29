/**
 * Private S3 origins served through CloudFront with Origin Access Control.
 *
 * The frontend and the generated data live in separate buckets on purpose. A
 * frontend deployment runs `aws s3 sync --delete` against the site bucket, and
 * that command must be structurally incapable of deleting the snapshot the
 * ingestion function publishes.
 *
 * Neither bucket has S3 website hosting or any public read. CloudFront is the
 * only way in, and it reaches S3 over the regional REST endpoint using SigV4.
 */

terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 6.0"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  site_bucket = "${local.name_prefix}-site-${var.account_id}"
  data_bucket = "${local.name_prefix}-data-${var.account_id}"
  # A custom domain always needs a certificate and an alias. Terraform only
  # manages the DNS records when a Route 53 zone is supplied; with the domain
  # hosted elsewhere the two records are added by hand and ACM simply waits.
  use_domain   = var.domain_name != null
  manage_dns   = var.domain_name != null && var.hosted_zone_id != null
  origin_site  = "site-origin"
  origin_data  = "data-origin"
  data_prefix  = "data"
  bucket_names = [local.site_bucket, local.data_bucket]
}

# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "site" {
  bucket        = local.site_bucket
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket" "data" {
  bucket        = local.data_bucket
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = toset(local.bucket_names)
  bucket   = each.value

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  depends_on = [aws_s3_bucket.site, aws_s3_bucket.data]
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = toset(local.bucket_names)
  bucket   = each.value

  rule {
    # ACLs are disabled entirely. Nothing in this design needs them, and their
    # absence removes a whole class of accidental public exposure.
    object_ownership = "BucketOwnerEnforced"
  }

  depends_on = [aws_s3_bucket.site, aws_s3_bucket.data]
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = toset(local.bucket_names)
  bucket   = each.value

  rule {
    apply_server_side_encryption_by_default {
      # SSE-S3 rather than a customer-managed key: there is no secret here, and
      # a KMS key would be a standing monthly charge.
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }

  depends_on = [aws_s3_bucket.site, aws_s3_bucket.data]
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = toset(local.bucket_names)
  bucket   = each.value

  versioning_configuration {
    status = "Enabled"
  }

  depends_on = [aws_s3_bucket.site, aws_s3_bucket.data]
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket     = aws_s3_bucket.site.id
  depends_on = [aws_s3_bucket_versioning.this]

  rule {
    id     = "expire-noncurrent-frontend-objects"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.site_version_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket     = aws_s3_bucket.data.id
  depends_on = [aws_s3_bucket_versioning.this]

  rule {
    id     = "expire-archive-snapshots"
    status = "Enabled"

    filter {
      prefix = var.snapshot_prefix
    }

    expiration {
      days = var.archive_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "expire-noncurrent-current-json"
    status = "Enabled"

    filter {
      prefix = "${local.data_prefix}/"
    }

    noncurrent_version_expiration {
      # Enough history to recover a bad snapshot by hand, no more.
      noncurrent_days = var.current_version_retention_days
    }
  }
}

# ---------------------------------------------------------------------------
# CloudFront
# ---------------------------------------------------------------------------

resource "aws_cloudfront_origin_access_control" "this" {
  name                              = "${local.name_prefix}-oac"
  description                       = "SigV4 access from CloudFront to the private S3 origins"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "optimised" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  comment             = "${local.name_prefix} static delivery"
  default_root_object = "index.html"
  price_class         = var.price_class
  aliases             = local.use_domain ? [var.domain_name] : []

  origin {
    origin_id                = local.origin_site
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.this.id
  }

  origin {
    origin_id                = local.origin_data
    domain_name              = aws_s3_bucket.data.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.this.id
  }

  default_cache_behavior {
    target_origin_id           = local.origin_site
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimised.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
  }

  # The snapshot is served from its own bucket through the same hostname, so
  # the browser fetches /data/current.json same-origin and never needs CORS.
  ordered_cache_behavior {
    path_pattern               = "/${local.data_prefix}/*"
    target_origin_id           = local.origin_data
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimised.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
  }

  # Deliberately no custom_error_response mapping 403/404 to index.html. The
  # application routes with query parameters, not paths, and a missing JSON
  # snapshot must surface as an error rather than as a page of HTML that the
  # frontend would then fail to parse.

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = local.use_domain ? null : true
    acm_certificate_arn            = local.use_domain ? aws_acm_certificate_validation.this[0].certificate_arn : null
    ssl_support_method             = local.use_domain ? "sni-only" : null
    minimum_protocol_version       = local.use_domain ? "TLSv1.2_2021" : null
  }

  dynamic "logging_config" {
    for_each = var.enable_access_logs && var.access_log_bucket_domain_name != null ? [1] : []
    content {
      bucket          = var.access_log_bucket_domain_name
      include_cookies = false
      prefix          = "cloudfront/"
    }
  }

  lifecycle {
    # A CloudFront pricing plan may attach a plan-owned WAF ACL outside
    # Terraform. Ignoring it here stops every later plan showing drift for
    # something this configuration does not manage. See docs/deployment.md.
    ignore_changes = [web_acl_id]
  }
}

# ---------------------------------------------------------------------------
# Bucket policies: CloudFront only, and only for what it must read
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "site" {
  statement {
    sid    = "AllowCloudFrontRead"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    # GetObject only. No ListBucket, so a misconfigured request cannot
    # enumerate the bucket.
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.this.arn]
    }
  }

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [aws_s3_bucket.site.arn, "${aws_s3_bucket.site.arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

data "aws_iam_policy_document" "data" {
  statement {
    sid    = "AllowCloudFrontReadPublishedData"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions = ["s3:GetObject"]

    # Only data/* is exposed. archive/* stays private, reachable by an
    # operator with credentials but never through the CDN.
    resources = ["${aws_s3_bucket.data.arn}/${local.data_prefix}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.this.arn]
    }
  }

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [aws_s3_bucket.data.arn, "${aws_s3_bucket.data.arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket     = aws_s3_bucket.site.id
  policy     = data.aws_iam_policy_document.site.json
  depends_on = [aws_s3_bucket_public_access_block.this]
}

resource "aws_s3_bucket_policy" "data" {
  bucket     = aws_s3_bucket.data.id
  policy     = data.aws_iam_policy_document.data.json
  depends_on = [aws_s3_bucket_public_access_block.this]
}

# ---------------------------------------------------------------------------
# Optional custom domain
# ---------------------------------------------------------------------------

# CloudFront viewer certificates must live in us-east-1 regardless of where
# everything else is, which is why the aliased provider exists.
resource "aws_acm_certificate" "this" {
  count = local.use_domain ? 1 : 0

  provider          = aws.us_east_1
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Exactly one certificate for exactly one domain, so this uses count rather
# than for_each over domain_validation_options. Keying a for_each off those
# options is the documented pattern but it fails on a first apply, because
# the validation records are not known until the certificate exists.
resource "aws_route53_record" "certificate_validation" {
  count = local.manage_dns ? 1 : 0

  zone_id         = var.hosted_zone_id
  name            = tolist(aws_acm_certificate.this[0].domain_validation_options)[0].resource_record_name
  type            = tolist(aws_acm_certificate.this[0].domain_validation_options)[0].resource_record_type
  records         = [tolist(aws_acm_certificate.this[0].domain_validation_options)[0].resource_record_value]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  count = local.use_domain ? 1 : 0

  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.this[0].arn

  # With external DNS there is no Terraform-managed record to point at, so
  # this simply waits for the certificate to become ISSUED once the record has
  # been added wherever the domain is hosted.
  validation_record_fqdns = local.manage_dns ? aws_route53_record.certificate_validation[*].fqdn : []

  timeouts {
    create = "20m"
  }
}

resource "aws_route53_record" "alias" {
  for_each = local.manage_dns ? toset(["A", "AAAA"]) : toset([])

  zone_id = var.hosted_zone_id
  name    = var.domain_name
  type    = each.value

  alias {
    name                   = aws_cloudfront_distribution.this.domain_name
    zone_id                = aws_cloudfront_distribution.this.hosted_zone_id
    evaluate_target_health = false
  }
}
