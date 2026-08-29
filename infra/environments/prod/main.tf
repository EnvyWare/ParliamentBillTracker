/**
 * Production stack.
 *
 * Two modules and nothing else: static delivery, and scheduled ingestion.
 * There is no database, no API Gateway, no NAT Gateway and no always-on
 * compute, which is what keeps the running cost at effectively nothing for
 * demonstration traffic.
 */

data "aws_caller_identity" "current" {}

module "static_delivery" {
  source = "../../modules/static_delivery"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  project_name = var.project_name
  environment  = var.environment
  account_id   = data.aws_caller_identity.current.account_id

  snapshot_prefix        = var.snapshot_prefix
  archive_retention_days = var.archive_retention_days

  domain_name    = var.domain_name
  hosted_zone_id = var.hosted_zone_id

  enable_access_logs            = var.enable_cloudfront_access_logs
  access_log_bucket_domain_name = var.cloudfront_access_log_bucket_domain_name
}

module "ingestion" {
  source = "../../modules/ingestion"

  project_name = var.project_name
  environment  = var.environment

  lambda_source_dir = var.lambda_source_dir

  data_bucket_name = module.static_delivery.data_bucket_name
  data_bucket_arn  = module.static_delivery.data_bucket_arn
  snapshot_prefix  = var.snapshot_prefix

  parliament_session_id    = var.parliament_session_id
  parliament_session_label = var.parliament_session_label

  schedule_expression = var.schedule_expression
  ingestion_enabled   = var.ingestion_enabled

  reserved_concurrency = var.lambda_reserved_concurrency
  log_retention_days   = var.lambda_log_retention_days
  alarm_email          = var.alarm_email
  repository_url       = "https://github.com/${var.github_repository}"
}

# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

# A budget sends alerts. It is not a spending cap, and nothing here can stop
# AWS charging: see the cost section of the README.
resource "aws_budgets_budget" "monthly" {
  count = var.budget_alert_email == null ? 0 : 1

  name         = "${var.project_name}-${var.environment}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
