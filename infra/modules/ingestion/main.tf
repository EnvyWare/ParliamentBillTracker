/**
 * Scheduled ingestion: one Lambda, one schedule, one failure queue.
 *
 * The function is not in a VPC. It only talks to the public Parliament API
 * and to S3, so a VPC would add a NAT Gateway - the single largest avoidable
 * cost in this design - for no security benefit.
 *
 * Its execution role can read and write exactly two key patterns in the data
 * bucket and nothing else. It has no access to the frontend bucket at all, so
 * a fault here cannot damage the site, and no delete permission anywhere.
 */

terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

locals {
  name          = "${var.project_name}-${var.environment}-ingest"
  log_group     = "/aws/lambda/${local.name}"
  current_key   = "data/current.json"
  archive_glob  = "${var.snapshot_prefix}*"
  schedule_name = "${var.project_name}-${var.environment}-ingest-schedule"
}

# Only the account id is needed, for the ARNs this module builds by hand.
# aws_partition and aws_region data sources were declared here too and never
# read: each one is a provider call on every plan, for a value nothing used.
data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Deployment package
# ---------------------------------------------------------------------------

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = var.lambda_source_dir
  output_path = "${path.module}/.terraform-build/${local.name}.zip"
}

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

# Created here rather than left to Lambda, so retention is set from the first
# invocation and the execution role can be scoped to this exact group.
resource "aws_cloudwatch_log_group" "lambda" {
  name              = local.log_group
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------------------
# Failure queue
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "failures" {
  name                       = "${local.name}-failures"
  message_retention_seconds  = 1209600 # 14 days
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = 60
}

# ---------------------------------------------------------------------------
# Execution role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  # Logging, scoped to this function's own log group.
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"

    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]

    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  # Read the previous snapshot, to decide what actually changed.
  statement {
    sid       = "ReadCurrentSnapshot"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/${local.current_key}"]
  }

  # Publish. Note the absence of s3:DeleteObject and s3:ListBucket: this role
  # can replace the snapshot and add archives, and can do nothing else.
  statement {
    sid       = "PublishSnapshot"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.data_bucket_arn}/${local.current_key}"]
  }

  statement {
    sid     = "WriteArchiveSnapshots"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    # HeadObject is authorised by s3:GetObject on the same key pattern; the
    # handler uses it to skip writing an archive that already exists.
    resources = ["${var.data_bucket_arn}/${local.archive_glob}"]
  }

  statement {
    sid       = "ReadArchiveSnapshots"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/${local.archive_glob}"]
  }

  # Required for the asynchronous failure destination.
  statement {
    sid       = "SendFailureNotification"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.failures.arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# ---------------------------------------------------------------------------
# Function
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "ingest" {
  function_name = local.name
  role          = aws_iam_role.lambda.arn
  handler       = "bill_pipeline.handler.lambda_handler"
  runtime       = "python3.13"
  architectures = ["arm64"]

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  memory_size = var.memory_size
  timeout     = var.timeout_seconds

  # One at a time. Combined with content-addressed archive keys, this makes a
  # duplicate at-least-once delivery harmless. -1 is the provider's value for
  # "no reservation", used where the account quota forbids one.
  reserved_concurrent_executions = var.reserved_concurrency == null ? -1 : var.reserved_concurrency

  ephemeral_storage {
    size = 512
  }

  environment {
    variables = {
      DATA_BUCKET               = var.data_bucket_name
      CURRENT_KEY               = local.current_key
      SNAPSHOT_PREFIX           = var.snapshot_prefix
      BILLS_API_BASE            = var.bills_api_base
      PARLIAMENT_SESSION_ID     = tostring(var.parliament_session_id)
      PARLIAMENT_SESSION_LABEL  = var.parliament_session_label
      REFRESH_INTERVAL_MINUTES  = tostring(var.refresh_interval_minutes)
      HTTP_TIMEOUT_SECONDS      = tostring(var.http_timeout_seconds)
      MAX_CONCURRENT_REQUESTS   = tostring(var.max_concurrent_requests)
      FULL_RECONCILE_AFTER_DAYS = tostring(var.full_reconcile_after_days)
      SCHEMA_VERSION            = tostring(var.schema_version)
      LOG_LEVEL                 = var.log_level
      REPOSITORY_URL            = var.repository_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.lambda]
}

# Route final asynchronous failures to the queue rather than losing them.
resource "aws_lambda_function_event_invoke_config" "ingest" {
  function_name                = aws_lambda_function.ingest.function_name
  maximum_event_age_in_seconds = 3600
  maximum_retry_attempts       = 0 # Scheduler already retries; see below.

  destination_config {
    on_failure {
      destination = aws_sqs_queue.failures.arn
    }
  }
}

# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    # Without this the role could be assumed on behalf of a schedule in any
    # account, which is the classic confused-deputy opening.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    # There is deliberately no aws:SourceArn condition here.
    #
    # EventBridge Scheduler validates this role when the schedule is created,
    # which is before the schedule ARN exists. A condition on that ARN cannot
    # be satisfied during that check, so CreateSchedule fails outright with
    # "The execution role you provide must allow AWS EventBridge Scheduler to
    # assume the role". Verified against this account, not assumed.
    #
    # What is given up is small: another schedule in this same account could
    # assume the role. What it could then do is bounded by the permissions
    # policy below, which allows invoking exactly one function and writing to
    # exactly one queue.
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeIngestionFunctionOnly"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.ingest.arn, "${aws_lambda_function.ingest.arn}:*"]
  }

  statement {
    sid       = "DeliverFailuresToQueueOnly"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.failures.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${local.name}-scheduler-policy"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "ingest" {
  name       = local.schedule_name
  group_name = "default"
  state      = var.ingestion_enabled ? "ENABLED" : "DISABLED"

  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    # The snapshot's freshness indicator is measured in minutes, so the run
    # happens when it says it will.
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.ingest.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ source = "eventbridge-scheduler" })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }

    dead_letter_config {
      arn = aws_sqs_queue.failures.arn
    }
  }
}

# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alarms" {
  count = var.alarm_email == null ? 0 : 1
  name  = "${local.name}-alarms"
}

resource "aws_sns_topic_subscription" "alarms" {
  count = var.alarm_email == null ? 0 : 1

  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
  # The subscription stays pending until the address is confirmed by email.
  # See docs/deployment.md.
}

locals {
  alarm_actions = var.alarm_email == null ? [] : [aws_sns_topic.alarms[0].arn]
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${local.name}-errors"
  alarm_description   = "The ingestion function failed. The previously published snapshot is still being served."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions    = { FunctionName = aws_lambda_function.ingest.function_name }
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# A run that never happens produces no Errors metric at all, so absence of
# invocations is alarmed separately over a window long enough to be certain.
resource "aws_cloudwatch_metric_alarm" "missing_runs" {
  alarm_name          = "${local.name}-no-invocations"
  alarm_description   = "The ingestion schedule appears to have stopped firing."
  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  statistic           = "Sum"
  period              = var.missing_run_window_seconds
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  dimensions    = { FunctionName = aws_lambda_function.ingest.function_name }
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "failure_queue" {
  alarm_name          = "${local.name}-failure-queue"
  alarm_description   = "A failed invocation reached the failure queue and needs looking at."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions    = { QueueName = aws_sqs_queue.failures.name }
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Fires when Lambda cannot even deliver a failure to its destination, which
# would otherwise be a silent loss.
resource "aws_cloudwatch_metric_alarm" "destination_delivery" {
  alarm_name          = "${local.name}-destination-delivery-failures"
  alarm_description   = "Lambda could not deliver a failure record to the failure queue."
  namespace           = "AWS/Lambda"
  metric_name         = "DestinationDeliveryFailures"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions    = { FunctionName = aws_lambda_function.ingest.function_name }
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}
