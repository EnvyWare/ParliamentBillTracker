variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment name, used in resource names."
  type        = string
}

variable "lambda_source_dir" {
  description = <<-EOT
    Directory containing the built Lambda package. Produced by `make build`,
    which copies the handler, the snapshot schema and the bundled time zone
    database into one directory for Terraform to zip.
  EOT
  type        = string
}

variable "data_bucket_name" {
  description = "Name of the private data bucket the snapshot is published to."
  type        = string
}

variable "data_bucket_arn" {
  description = "ARN of the data bucket, used to scope the execution role."
  type        = string
}

variable "snapshot_prefix" {
  description = "Key prefix for immutable archive snapshots."
  type        = string
  default     = "archive/snapshots/"
}

variable "bills_api_base" {
  description = "Base URL of the UK Parliament Bills API. Configuration-controlled, never event-controlled."
  type        = string
  default     = "https://bills-api.parliament.uk/api/v1"
}

variable "parliament_session_id" {
  description = "Numeric id of the Parliamentary session to publish. Verify before every deployment."
  type        = number
}

variable "parliament_session_label" {
  description = "Human-readable session label, for example 2026-27."
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression controlling how often ingestion runs."
  type        = string
  default     = "rate(30 minutes)"
}

variable "ingestion_enabled" {
  description = "Whether the schedule is enabled. Disable to pause ingestion without destroying anything."
  type        = bool
  default     = true
}

variable "refresh_interval_minutes" {
  description = "Interval the function reports in its own configuration, kept in step with the schedule."
  type        = number
  default     = 30
}

variable "http_timeout_seconds" {
  description = "Read timeout for a single source request."
  type        = number
  default     = 15
}

variable "max_concurrent_requests" {
  description = "Upper bound on concurrent requests to Parliament. Deliberately small: it is a public service."
  type        = number
  default     = 5

  validation {
    condition     = var.max_concurrent_requests >= 1 && var.max_concurrent_requests <= 10
    error_message = "Keep source fan-out between 1 and 10 requests."
  }
}

variable "full_reconcile_after_days" {
  description = "How often every Bill's detail and history is re-fetched regardless of change."
  type        = number
  default     = 7
}

variable "schema_version" {
  description = "Snapshot schema version the function publishes."
  type        = number
  default     = 1
}

variable "reserved_concurrency" {
  description = <<-EOT
    Reserved concurrent executions for the ingestion function.

    One is the intended value: combined with content-addressed archive keys it
    makes an at-least-once duplicate delivery completely safe, and it stops two
    runs ever racing to replace current.json.

    Set it to null on an account whose total Lambda concurrency quota is at or
    near AWS's floor of 10 unreserved executions, where any reservation is
    rejected. The design still holds without it - archive writes stay
    idempotent, replacing current.json is atomic, and the 600-second timeout is
    far shorter than the 30-minute schedule - but the guarantee becomes a very
    strong likelihood rather than a certainty.
  EOT
  type        = number
  default     = 1

  validation {
    condition     = var.reserved_concurrency == null || var.reserved_concurrency >= 1
    error_message = "reserved_concurrency must be null or at least 1."
  }
}

variable "memory_size" {
  description = "Lambda memory in MB."
  type        = number
  default     = 512
}

variable "timeout_seconds" {
  description = "Lambda timeout. The first run fetches every Bill, so this needs headroom."
  type        = number
  default     = 600
}

variable "log_retention_days" {
  description = "CloudWatch log retention. Short by default because logs cost money and age badly."
  type        = number
  default     = 14
}

variable "log_level" {
  description = "Python log level for the handler."
  type        = string
  default     = "INFO"
}

variable "missing_run_window_seconds" {
  description = <<-EOT
    Window with no invocations that counts as the schedule having stopped.
    Comfortably longer than the schedule interval so an ordinary retry does
    not trip it.
  EOT
  type        = number
  default     = 10800 # three hours, matching the frontend's stale threshold
}

variable "alarm_email" {
  description = "Address for alarm notifications. No topic is created when this is null."
  type        = string
  default     = null
}

variable "repository_url" {
  description = "Repository URL, sent in the User-Agent so Parliament can identify this client."
  type        = string
}
