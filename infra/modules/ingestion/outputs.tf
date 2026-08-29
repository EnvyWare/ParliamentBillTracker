output "lambda_function_name" {
  description = "Name of the ingestion function, for manual invocation and log lookup."
  value       = aws_lambda_function.ingest.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.ingest.arn
}

output "lambda_role_arn" {
  value = aws_iam_role.lambda.arn
}

output "failure_queue_url" {
  description = "Queue holding invocations that failed after every retry."
  value       = aws_sqs_queue.failures.url
}

output "failure_queue_arn" {
  value = aws_sqs_queue.failures.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}

output "schedule_name" {
  value = aws_scheduler_schedule.ingest.name
}

output "alarm_topic_arn" {
  description = "Alarm topic, when an alarm email was supplied."
  value       = var.alarm_email == null ? null : aws_sns_topic.alarms[0].arn
}
