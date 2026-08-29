variable "project_name" {
  description = "Short project identifier used in resource names and tags."
  type        = string
  default     = "uk-bill-pipeline"
}

variable "aws_region" {
  description = "Region the state bucket lives in."
  type        = string
  default     = "eu-west-2"
}

variable "state_bucket_name" {
  description = <<-EOT
    Explicit name for the Terraform state bucket. Leave null to derive
    "<project>-tfstate-<account-id>", which is globally unique without
    exposing anything sensitive.
  EOT
  type        = string
  default     = null
}

variable "state_version_retention_days" {
  description = "How long non-current state versions are kept before expiry."
  type        = number
  default     = 90

  validation {
    condition     = var.state_version_retention_days >= 30
    error_message = "Keep at least 30 days of state history so a bad apply can be recovered."
  }
}

variable "github_repository" {
  description = "owner/repository, recorded in the Repository tag."
  type        = string
  default     = "EnvyWare/ParliamentBillTracker"
}

variable "owner" {
  description = "Team or person accountable for these resources."
  type        = string
  default     = "unset"
}
