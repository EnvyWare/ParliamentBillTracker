variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment name, used in resource names."
  type        = string
}

variable "account_id" {
  description = "AWS account id, appended to bucket names to make them globally unique."
  type        = string
}

variable "snapshot_prefix" {
  description = "Key prefix for immutable archive snapshots in the data bucket."
  type        = string
  default     = "archive/snapshots/"
}

variable "archive_retention_days" {
  description = "How long immutable archive snapshots are kept."
  type        = number
  default     = 90
}

variable "current_version_retention_days" {
  description = "How long non-current versions of data/current.json are kept."
  type        = number
  default     = 14
}

variable "site_version_retention_days" {
  description = "How long non-current versions of frontend objects are kept."
  type        = number
  default     = 30
}

variable "domain_name" {
  description = "Optional custom domain. The site works on its CloudFront hostname without one."
  type        = string
  default     = null
}

variable "hosted_zone_id" {
  description = <<-EOT
    Existing Route 53 hosted zone id for domain_name. No zone is created,
    because a hosted zone is a standing monthly charge.

    Leave null when the domain is hosted elsewhere, for example on Cloudflare.
    Terraform then requests the certificate and attaches the alias, and the two
    DNS records - the ACM validation CNAME and the CNAME pointing at the
    distribution - are added by hand. Both are published as outputs.
  EOT
  type        = string
  default     = null
}

variable "price_class" {
  description = <<-EOT
    CloudFront price class. PriceClass_All is the default because a restricted
    class can conflict with the CloudFront flat-rate plan's requirements.
  EOT
  type        = string
  default     = "PriceClass_All"

  validation {
    condition     = contains(["PriceClass_All", "PriceClass_200", "PriceClass_100"], var.price_class)
    error_message = "price_class must be one of PriceClass_All, PriceClass_200 or PriceClass_100."
  }
}

variable "enable_access_logs" {
  description = "CloudFront standard access logs. Off by default: they cost storage and are rarely needed here."
  type        = bool
  default     = false
}

variable "access_log_bucket_domain_name" {
  description = "Bucket domain name for CloudFront access logs, when they are enabled."
  type        = string
  default     = null
}

variable "force_destroy" {
  description = "Allow terraform destroy to empty the buckets. Must stay false in production."
  type        = bool
  default     = false
}
