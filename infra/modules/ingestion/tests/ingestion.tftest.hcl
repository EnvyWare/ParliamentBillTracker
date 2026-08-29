# Policy tests for the ingestion module.
#
# These run against a mocked apply, so they need no AWS credentials and no
# built Lambda package. The assertions concentrate on the properties that keep
# a fault in ingestion from becoming a fault in the published site.

# AWS validates the shape of several of these values, so the mocks supply
# realistic ARNs rather than the random strings a bare mock would generate.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::000000000000:role/mock-ingest-role"
    }
  }

  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:eu-west-2:000000000000:function:ukbp-test-ingest"
    }
  }

  mock_resource "aws_sqs_queue" {
    defaults = {
      arn = "arn:aws:sqs:eu-west-2:000000000000:ukbp-test-ingest-failures"
      url = "https://sqs.eu-west-2.amazonaws.com/000000000000/ukbp-test-ingest-failures"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:eu-west-2:000000000000:log-group:/aws/lambda/ukbp-test-ingest"
    }
  }

  mock_resource "aws_sns_topic" {
    defaults = {
      arn = "arn:aws:sns:eu-west-2:000000000000:ukbp-test-ingest-alarms"
    }
  }
}

mock_provider "archive" {}

variables {
  project_name             = "ukbp"
  environment              = "test"
  lambda_source_dir        = "."
  data_bucket_name         = "ukbp-test-data-000000000000"
  data_bucket_arn          = "arn:aws:s3:::ukbp-test-data-000000000000"
  parliament_session_id    = 40
  parliament_session_label = "2026-27"
  repository_url           = "https://github.com/EnvyWare/uk-bill-pipeline"
}

run "the_function_runs_outside_a_vpc" {
  command = apply

  # A VPC would require a NAT Gateway for outbound internet access, which is
  # the single largest avoidable cost in this design, and would buy nothing:
  # the function talks only to a public API and to S3.
  assert {
    condition     = length(aws_lambda_function.ingest.vpc_config) == 0
    error_message = "The ingestion function must not be attached to a VPC."
  }
}

run "the_function_runs_one_at_a_time" {
  command = apply

  # Reserved concurrency of one, combined with content-addressed archive
  # keys, is what makes an at-least-once duplicate delivery harmless.
  assert {
    condition     = aws_lambda_function.ingest.reserved_concurrent_executions == 1
    error_message = "Reserved concurrency must default to exactly 1."
  }
}

run "the_reservation_can_be_dropped_where_the_account_forbids_it" {
  command = apply

  variables {
    reserved_concurrency = null
  }

  # AWS refuses any reservation that would take unreserved concurrency below
  # 10, which makes reservations impossible on a quota-limited account.
  assert {
    condition     = aws_lambda_function.ingest.reserved_concurrent_executions == -1
    error_message = "A null reservation must map to the provider's -1, not to 0."
  }
}

run "the_runtime_matches_the_deployment_target" {
  command = apply

  assert {
    condition     = aws_lambda_function.ingest.runtime == "python3.13"
    error_message = "The function must run on Python 3.13."
  }

  assert {
    condition     = contains(aws_lambda_function.ingest.architectures, "arm64")
    error_message = "The function must run on arm64."
  }

  assert {
    condition     = aws_lambda_function.ingest.timeout == 600
    error_message = "The first run fetches every Bill, so the timeout needs headroom."
  }

  assert {
    condition     = aws_lambda_function.ingest.memory_size == 512
    error_message = "Memory should stay at the documented 512 MB."
  }
}

run "no_provisioned_concurrency_is_configured" {
  command = apply

  # Provisioned concurrency is billed continuously. A job that runs twice an
  # hour has no use for it.
  assert {
    condition     = aws_lambda_function.ingest.reserved_concurrent_executions > 0
    error_message = "Reserved concurrency, not provisioned concurrency, is what this design uses."
  }
}

run "the_source_api_is_configuration_not_input" {
  command = apply

  assert {
    condition     = aws_lambda_function.ingest.environment[0].variables["BILLS_API_BASE"] == "https://bills-api.parliament.uk/api/v1"
    error_message = "The source API host must come from configuration, never from an event."
  }

  assert {
    condition     = aws_lambda_function.ingest.environment[0].variables["PARLIAMENT_SESSION_ID"] == "40"
    error_message = "The session must be passed to the function explicitly."
  }

  assert {
    condition     = aws_lambda_function.ingest.environment[0].variables["DATA_BUCKET"] == "ukbp-test-data-000000000000"
    error_message = "The function must be pointed at the data bucket."
  }
}

run "the_execution_role_cannot_reach_the_frontend" {
  command = apply

  # Every resource the role can touch lives under the data bucket. The site
  # bucket is not reachable at all, so a fault here cannot damage the site.
  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.lambda.statement : [
        for resource in statement.resources :
        startswith(resource, "arn:aws:s3:::") ? startswith(resource, var.data_bucket_arn) : true
      ]
    ]))
    error_message = "The execution role must not reference any bucket other than the data bucket."
  }

  assert {
    condition = !anytrue(flatten([
      for statement in data.aws_iam_policy_document.lambda.statement : [
        for resource in statement.resources : strcontains(resource, "-site-")
      ]
    ]))
    error_message = "The execution role must never mention the frontend bucket."
  }
}

run "the_execution_role_cannot_delete_or_enumerate" {
  command = apply

  assert {
    condition = !anytrue(flatten([
      for statement in data.aws_iam_policy_document.lambda.statement : [
        for action in statement.actions :
        action == "s3:*" || startswith(action, "s3:Delete") || action == "s3:ListBucket"
      ]
    ]))
    error_message = "The execution role must not have wildcard, delete or list permissions on S3."
  }

  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.lambda.statement : [
        for action in statement.actions : action != "*" && !startswith(action, "iam:") &&
        !startswith(action, "kms:") && !startswith(action, "secretsmanager:") &&
        !startswith(action, "ec2:")
      ]
    ]))
    error_message = "The execution role must not hold IAM, KMS, Secrets Manager or VPC permissions."
  }
}

run "the_execution_role_only_writes_the_two_documented_key_patterns" {
  command = apply

  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.lambda.statement : [
        for action in statement.actions :
        action == "s3:PutObject" ? alltrue([
          for resource in statement.resources :
          endswith(resource, "/data/current.json") || strcontains(resource, "/archive/snapshots/")
        ]) : true
      ]
    ]))
    error_message = "Writes must be limited to current.json and the archive prefix."
  }
}

run "logs_are_pre_created_and_expire" {
  command = apply

  assert {
    condition     = aws_cloudwatch_log_group.lambda.name == "/aws/lambda/ukbp-test-ingest"
    error_message = "The log group must be created by Terraform, not implicitly by Lambda."
  }

  assert {
    condition     = aws_cloudwatch_log_group.lambda.retention_in_days == 14
    error_message = "Log retention must be set, so logs do not accumulate indefinitely."
  }

  # Logging permission is scoped to this function's own group.
  assert {
    condition = anytrue([
      for statement in data.aws_iam_policy_document.lambda.statement :
      contains(statement.actions, "logs:PutLogEvents") &&
      alltrue([for resource in statement.resources : strcontains(resource, "ukbp-test-ingest")])
    ])
    error_message = "Log permissions must be scoped to this function's own log group."
  }
}

run "the_schedule_retries_then_gives_up_to_a_queue" {
  command = apply

  assert {
    condition     = aws_scheduler_schedule.ingest.schedule_expression == "rate(30 minutes)"
    error_message = "The documented schedule is every 30 minutes."
  }

  assert {
    condition     = aws_scheduler_schedule.ingest.flexible_time_window[0].mode == "OFF"
    error_message = "Freshness is reported in minutes, so the run must happen when it says."
  }

  assert {
    condition     = aws_scheduler_schedule.ingest.target[0].retry_policy[0].maximum_retry_attempts == 3
    error_message = "The schedule must retry a failed invocation."
  }

  assert {
    condition     = aws_scheduler_schedule.ingest.target[0].retry_policy[0].maximum_event_age_in_seconds == 3600
    error_message = "A retry must not be attempted indefinitely."
  }

  assert {
    condition     = aws_scheduler_schedule.ingest.target[0].dead_letter_config[0].arn == aws_sqs_queue.failures.arn
    error_message = "Exhausted retries must land in the failure queue, not be dropped."
  }
}

run "the_scheduler_role_is_locked_to_this_account" {
  command = apply

  assert {
    condition = anytrue([
      for statement in data.aws_iam_policy_document.scheduler_assume.statement :
      anytrue([
        for condition in statement.condition :
        condition.variable == "aws:SourceAccount" && condition.test == "StringEquals"
      ])
    ])
    error_message = "The scheduler role must not be assumable from another account."
  }

  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.scheduler.statement : [
        for action in statement.actions :
        action == "lambda:InvokeFunction" || action == "sqs:SendMessage"
      ]
    ]))
    error_message = "The scheduler role may only invoke the function and write to the queue."
  }
}

run "lambda_failures_also_reach_the_queue" {
  command = apply

  assert {
    condition     = aws_lambda_function_event_invoke_config.ingest.destination_config[0].on_failure[0].destination == aws_sqs_queue.failures.arn
    error_message = "A final asynchronous failure must be delivered to the failure queue."
  }
}

run "the_failure_queue_is_encrypted_and_retains_long_enough_to_investigate" {
  command = apply

  assert {
    condition     = aws_sqs_queue.failures.sqs_managed_sse_enabled == true
    error_message = "The failure queue must be encrypted."
  }

  assert {
    condition     = aws_sqs_queue.failures.message_retention_seconds == 1209600
    error_message = "Failures should be kept for the full 14 days."
  }
}

run "alarms_cover_failure_and_silence" {
  command = apply

  assert {
    condition     = aws_cloudwatch_metric_alarm.errors.threshold == 0
    error_message = "Any error at all should raise the alarm."
  }

  # A schedule that stops firing produces no error metric at all, so silence
  # is alarmed separately.
  assert {
    condition     = aws_cloudwatch_metric_alarm.missing_runs.treat_missing_data == "breaching"
    error_message = "Missing invocations must be treated as a problem, not as normal."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.failure_queue.namespace == "AWS/SQS"
    error_message = "A message arriving in the failure queue must raise an alarm."
  }
}

run "no_notification_topic_without_an_address" {
  command = apply

  assert {
    condition     = length(aws_sns_topic.alarms) == 0
    error_message = "No SNS topic should be created when no alarm email is configured."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.errors.alarm_actions) == 0
    error_message = "Alarms should have no actions when there is nowhere to send them."
  }
}

run "an_alarm_address_creates_a_topic_and_wires_it_up" {
  command = apply

  variables {
    alarm_email = "alerts@example.com"
  }

  assert {
    condition     = length(aws_sns_topic.alarms) == 1
    error_message = "An alarm email must create a topic."
  }

  assert {
    condition     = aws_sns_topic_subscription.alarms[0].protocol == "email"
    error_message = "The subscription must be by email."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.errors.alarm_actions) == 1
    error_message = "Alarms must publish to the topic once one exists."
  }
}

run "ingestion_can_be_paused_without_destroying_anything" {
  command = apply

  variables {
    ingestion_enabled = false
  }

  assert {
    condition     = aws_scheduler_schedule.ingest.state == "DISABLED"
    error_message = "Setting ingestion_enabled to false must disable the schedule, not remove it."
  }
}
