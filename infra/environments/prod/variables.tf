# Every variable is labelled with how much attention it needs:
#
#   REQUIRED  no default. Terraform will not plan without it.
#   OPTIONAL  switches a feature on. Left alone, the feature does not exist
#             and no resource is created for it.
#   TUNING    has a working default. Change it if you want different
#             behaviour, ignore it otherwise.
#
# Only two variables are REQUIRED. Everything else has a default that produces
# a complete, working deployment, so `parliament_session_id` and
# `parliament_session_label` are the shortest possible terraform.tfvars.
#
# See infra/README.md for what each optional feature actually creates.

variable "project_name" {
  description = "TUNING. Short project identifier used in resource names and tags."
  type        = string
  default     = "uk-bill-pipeline"
}

variable "environment" {
  description = "TUNING. Deployment environment name. Part of every resource name, so a second environment can share an account."
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "TUNING. Region for everything except the CloudFront certificate, which must be us-east-1."
  type        = string
  default     = "eu-west-2"
}

# ---------------------------------------------------------------------------
# Parliamentary session
# ---------------------------------------------------------------------------

variable "parliament_session_id" {
  description = <<-EOT
    REQUIRED. Numeric id of the session to publish.

    The Bills API has no dependable current-session lookup, so this is
    deployment configuration and must be verified before every apply. The
    ingestion function fails the run rather than publishing if it detects a
    newer session. See docs/operations.md.
  EOT
  type        = number

  validation {
    condition     = var.parliament_session_id > 0
    error_message = "parliament_session_id must be a positive session identifier."
  }
}

variable "parliament_session_label" {
  description = "REQUIRED. Human-readable session label shown in the UI, for example 2026-27."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}(-[0-9]{2})?$", var.parliament_session_label))
    error_message = "parliament_session_label should look like 2026-27."
  }
}

# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

variable "lambda_source_dir" {
  description = "TUNING. Built Lambda package directory, produced by `make build`. Terraform zips a directory that must already exist, so build before you plan."
  type        = string
  default     = "../../../backend/build/lambda"
}

variable "schedule_expression" {
  description = <<-EOT
    TUNING. How often ingestion runs.

    Thirty minutes is a deliberate balance: often enough that the page is
    useful, rare enough to stay well inside the free tier and to be a polite
    consumer of a public API. Anything faster mostly re-reads unchanged Bills.
  EOT
  type        = string
  default     = "rate(30 minutes)"
}

variable "ingestion_enabled" {
  description = <<-EOT
    OPTIONAL. Set false to pause ingestion without destroying anything.

    The schedule is created either way, disabled rather than deleted, so the
    last published snapshot keeps serving and resuming is a one-line change.
  EOT
  type        = bool
  default     = true
}

variable "snapshot_prefix" {
  description = "TUNING. Key prefix for immutable archive snapshots."
  type        = string
  default     = "archive/snapshots/"
}

variable "lambda_reserved_concurrency" {
  description = <<-EOT
    TUNING. Reserved concurrency for the ingestion function.

    Set to null where the account's Lambda quota is too low to permit a
    reservation. AWS rejects any reservation that would take unreserved
    concurrency below 10, so an account with the reduced quota of 10 must use
    null. Two runs could then in principle overlap; archive writes are
    idempotent and replacing current.json is atomic, so the consequence is
    small, but it is a real reduction in guarantee.
  EOT
  type        = number
  default     = 1
}

variable "lambda_log_retention_days" {
  description = "TUNING. CloudWatch log retention for the ingestion function. Logs expire so they cannot accumulate cost indefinitely."
  type        = number
  default     = 14
}

variable "archive_retention_days" {
  description = "TUNING. How long immutable archive snapshots are kept before expiry."
  type        = number
  default     = 90
}

# ---------------------------------------------------------------------------
# Custom domain — entirely optional
# ---------------------------------------------------------------------------

variable "domain_name" {
  description = <<-EOT
    OPTIONAL. Custom domain for the site.

    The site works on its CloudFront hostname with no domain at all. Setting
    this requests an ACM certificate in us-east-1 and attaches the alias.

    With hosted_zone_id, Terraform also creates the DNS records. Without it,
    Terraform creates nothing in DNS and you add two records by hand at
    whichever provider hosts the zone — see docs/deployment.md#custom-domain.
  EOT
  type        = string
  default     = null
}

variable "hosted_zone_id" {
  description = <<-EOT
    OPTIONAL. Existing Route 53 hosted zone id for domain_name.

    No zone is created, because a hosted zone is a standing monthly charge and
    reusing an existing one is almost always what is wanted. Leave null when
    DNS is hosted anywhere else.
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.hosted_zone_id == null || var.domain_name != null
    error_message = "hosted_zone_id does nothing without domain_name. Set both, or neither."
  }
}

# ---------------------------------------------------------------------------
# Notifications and cost — all optional
# ---------------------------------------------------------------------------

variable "alarm_email" {
  description = <<-EOT
    OPTIONAL. Address for CloudWatch alarm notifications.

    The alarms themselves always exist and are always visible in the console.
    This only decides whether they also notify anyone: no SNS topic and no
    subscription are created when null. An SNS subscription stays pending
    until the address is confirmed by email.
  EOT
  type        = string
  default     = null
}

variable "budget_alert_email" {
  description = "OPTIONAL. Address for budget notifications. No AWS Budget is created when null."
  type        = string
  default     = null
}

variable "monthly_budget_usd" {
  description = <<-EOT
    TUNING. Monthly budget threshold in USD. Only read when
    budget_alert_email is set.

    A budget sends alerts. It is not a spending cap and cannot stop AWS
    charging.
  EOT
  type        = number
  default     = 5
}

variable "enable_cloudfront_access_logs" {
  description = <<-EOT
    OPTIONAL. CloudFront standard access logs.

    Off by default: they write billable S3 objects continuously, for a site
    whose whole cost target is effectively zero. Turning them on also requires
    cloudfront_access_log_bucket_domain_name, because no log bucket is created
    here — CloudFront standard logging needs a bucket with ACLs enabled, which
    is a deliberate choice about your own account rather than something this
    stack should impose.
  EOT
  type        = bool
  default     = false

  validation {
    condition     = !var.enable_cloudfront_access_logs || var.cloudfront_access_log_bucket_domain_name != null
    error_message = "enable_cloudfront_access_logs also needs cloudfront_access_log_bucket_domain_name, or logging would be silently switched off."
  }
}

variable "cloudfront_access_log_bucket_domain_name" {
  description = <<-EOT
    OPTIONAL. Destination for CloudFront access logs, as a bucket *domain*
    name, for example my-logs.s3.amazonaws.com. Only read when
    enable_cloudfront_access_logs is true.
  EOT
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------

variable "github_repository" {
  description = "TUNING. owner/repository. Used in tags and in the ingestion User-Agent, so Parliament can identify the client."
  type        = string
  default     = "EnvyWare/ParliamentBillTracker"

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "github_repository must be in owner/repository form."
  }
}

variable "owner" {
  description = "TUNING. Team or person accountable for these resources. Appears on every tag."
  type        = string
  default     = "unset"
}
