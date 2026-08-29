# Policy tests for the static delivery module.
#
# These run against a mocked apply, so they need no AWS credentials and no
# network. Mocked providers supply computed values, which is what lets the
# assertions read attributes that are only known after apply.

# A rendered policy document is computed, and a random mock value would fail
# the bucket policy's own JSON validation. The statement blocks themselves are
# configuration, so they stay assertable.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

# ACM lives in us-east-1. Mocked resources need a real ARN shape, because
# CloudFront validates the certificate ARN it is given.
mock_provider "aws" {
  alias = "us_east_1"

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000"
      domain_validation_options = [{
        domain_name           = "bills.example.com"
        resource_record_name  = "_test.bills.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_test.acm-validations.aws."
      }]
    }
  }

  mock_resource "aws_acm_certificate_validation" {
    defaults = {
      certificate_arn = "arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000"
    }
  }
}

variables {
  project_name = "ukbp"
  environment  = "test"
  account_id   = "000000000000"
}

run "both_buckets_block_all_public_access" {
  command = apply

  assert {
    condition = alltrue([
      for block in values(aws_s3_bucket_public_access_block.this) :
      block.block_public_acls && block.block_public_policy &&
      block.ignore_public_acls && block.restrict_public_buckets
    ])
    error_message = "Every S3 Block Public Access setting must be enabled on both buckets."
  }

  assert {
    condition     = length(aws_s3_bucket_public_access_block.this) == 2
    error_message = "Both the site bucket and the data bucket must block public access."
  }
}

run "buckets_disable_acls_and_encrypt_at_rest" {
  command = apply

  assert {
    condition = alltrue([
      for controls in values(aws_s3_bucket_ownership_controls.this) :
      controls.rule[0].object_ownership == "BucketOwnerEnforced"
    ])
    error_message = "ACLs must be disabled entirely via BucketOwnerEnforced."
  }

  # rule is a set here, so it is walked rather than indexed.
  assert {
    condition = alltrue(flatten([
      for config in values(aws_s3_bucket_server_side_encryption_configuration.this) : [
        for rule in config.rule : [
          for encryption in rule.apply_server_side_encryption_by_default :
          encryption.sse_algorithm == "AES256"
        ]
      ]
    ]))
    error_message = "Both buckets must use SSE-S3. A customer-managed key would be a standing charge."
  }

  assert {
    condition = alltrue([
      for versioning in values(aws_s3_bucket_versioning.this) :
      versioning.versioning_configuration[0].status == "Enabled"
    ])
    error_message = "Versioning must be enabled so a bad snapshot can be recovered."
  }
}

run "production_buckets_cannot_be_emptied_by_destroy" {
  command = apply

  assert {
    condition     = aws_s3_bucket.site.force_destroy == false && aws_s3_bucket.data.force_destroy == false
    error_message = "force_destroy must stay false in production."
  }
}

run "cloudfront_is_the_only_public_entry_point" {
  command = apply

  assert {
    condition     = aws_cloudfront_origin_access_control.this.signing_behavior == "always"
    error_message = "Origin Access Control must always sign requests to S3."
  }

  assert {
    condition     = aws_cloudfront_origin_access_control.this.signing_protocol == "sigv4"
    error_message = "Origin Access Control must use SigV4, not the legacy origin access identity."
  }

  assert {
    condition = alltrue([
      for origin in aws_cloudfront_distribution.this.origin :
      origin.origin_access_control_id != null && origin.origin_access_control_id != ""
    ])
    error_message = "Every origin must reach S3 through Origin Access Control."
  }

  # The origin domain names are only known after apply, so the related
  # property - that S3 website hosting is never configured at all - is
  # asserted statically by scripts/check_infra_policy.py instead.
}

run "viewers_are_https_only" {
  command = apply

  assert {
    condition     = aws_cloudfront_distribution.this.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "The default behaviour must redirect viewers to HTTPS."
  }

  assert {
    condition = alltrue([
      for behavior in aws_cloudfront_distribution.this.ordered_cache_behavior :
      behavior.viewer_protocol_policy == "redirect-to-https"
    ])
    error_message = "Every ordered behaviour must redirect viewers to HTTPS."
  }
}

run "only_safe_methods_are_served" {
  command = apply

  assert {
    condition = alltrue(concat(
      [for method in aws_cloudfront_distribution.this.default_cache_behavior[0].allowed_methods : contains(["GET", "HEAD"], method)],
      flatten([for behavior in aws_cloudfront_distribution.this.ordered_cache_behavior :
      [for method in behavior.allowed_methods : contains(["GET", "HEAD"], method)]])
    ))
    error_message = "This is a read-only site. Only GET and HEAD may be allowed."
  }
}

run "published_data_has_its_own_behaviour_and_origin" {
  command = apply

  assert {
    condition     = length(aws_cloudfront_distribution.this.ordered_cache_behavior) == 1
    error_message = "There should be exactly one extra behaviour, for the published data."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.ordered_cache_behavior[0].path_pattern == "/data/*"
    error_message = "The snapshot must be served by its own /data/* behaviour."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.ordered_cache_behavior[0].target_origin_id == "data-origin"
    error_message = "The /data/* behaviour must point at the data bucket, not the site bucket."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.default_cache_behavior[0].target_origin_id == "site-origin"
    error_message = "The default behaviour must serve the frontend."
  }
}

run "a_missing_snapshot_is_not_rewritten_as_html" {
  command = apply

  # A 403/404 mapped to index.html would hand the frontend a page of HTML
  # where it expected JSON, turning a missing snapshot into a parse error
  # instead of a clear failure.
  assert {
    condition     = length(aws_cloudfront_distribution.this.custom_error_response) == 0
    error_message = "No custom error response should rewrite errors to index.html."
  }
}

run "no_domain_means_the_default_certificate" {
  command = apply

  assert {
    condition     = aws_cloudfront_distribution.this.viewer_certificate[0].cloudfront_default_certificate == true
    error_message = "Without a custom domain the distribution must use its own certificate."
  }

  assert {
    condition     = length(aws_acm_certificate.this) == 0 && length(aws_route53_record.alias) == 0
    error_message = "No certificate or DNS record should be created when no domain is configured."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.this.aliases) == 0
    error_message = "No alias should be set when no domain is configured."
  }
}

run "lifecycle_rules_keep_storage_bounded" {
  command = apply

  assert {
    condition     = length(aws_s3_bucket_lifecycle_configuration.data.rule) == 2
    error_message = "The data bucket needs rules for archive expiry and for old current.json versions."
  }

  assert {
    condition = anytrue([
      for rule in aws_s3_bucket_lifecycle_configuration.data.rule :
      rule.id == "expire-archive-snapshots" && rule.status == "Enabled"
    ])
    error_message = "Archive snapshots must expire."
  }

  assert {
    condition = anytrue([
      for rule in aws_s3_bucket_lifecycle_configuration.site.rule :
      rule.status == "Enabled" && length(rule.abort_incomplete_multipart_upload) > 0
    ])
    error_message = "Incomplete multipart uploads must be aborted so they cannot accumulate."
  }
}

run "a_custom_domain_wires_up_certificate_and_dns" {
  command = apply

  variables {
    domain_name    = "bills.example.com"
    hosted_zone_id = "Z0123456789ABCDEFGHIJ"
  }

  # A mocked certificate has no validation options, so they are supplied here.
  # ACM only ever populates these after the certificate exists, which is why
  # the module reads them with count rather than a for_each over them.
  assert {
    condition     = length(aws_acm_certificate.this) == 1
    error_message = "A custom domain must request a certificate."
  }

  assert {
    condition     = length(aws_route53_record.alias) == 2
    error_message = "A custom domain needs both an A and an AAAA alias record."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.viewer_certificate[0].minimum_protocol_version == "TLSv1.2_2021"
    error_message = "A custom domain must enforce a modern minimum TLS version."
  }

  assert {
    condition     = contains(aws_cloudfront_distribution.this.aliases, "bills.example.com")
    error_message = "The custom domain must be an alias on the distribution."
  }
}
