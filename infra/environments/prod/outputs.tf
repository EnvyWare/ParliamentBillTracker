# Deployment outputs.
#
# Deliberately no credentials and no internal identifiers beyond what the
# deployment workflow and the operator runbook actually need.

output "site_bucket_name" {
  description = "Frontend bucket. The deployment workflow syncs frontend/dist here."
  value       = module.static_delivery.site_bucket_name
}

output "data_bucket_name" {
  description = "Data bucket. Only the ingestion function writes to it."
  value       = module.static_delivery.data_bucket_name
}

output "cloudfront_distribution_id" {
  description = "Used to invalidate the root document after a frontend deployment."
  value       = module.static_delivery.cloudfront_distribution_id
}

output "cloudfront_domain_name" {
  value = module.static_delivery.cloudfront_domain_name
}

output "site_url" {
  description = "Public entry point."
  value       = module.static_delivery.site_url
}

output "data_url" {
  description = "Published snapshot URL, used by the smoke test."
  value       = module.static_delivery.data_url
}

output "ingestion_lambda_name" {
  description = "For manual invocation and log lookup. See docs/operations.md."
  value       = module.ingestion.lambda_function_name
}

output "failure_queue_url" {
  description = "Queue holding invocations that failed after every retry."
  value       = module.ingestion.failure_queue_url
}

output "ingestion_log_group_name" {
  value = module.ingestion.log_group_name
}

output "parliament_session" {
  description = "The session this deployment publishes, echoed back so a mistake is obvious."
  value = {
    id    = var.parliament_session_id
    label = var.parliament_session_label
  }
}

output "dns_records_to_create" {
  description = "DNS records to add by hand when the domain is hosted outside Route 53."
  value       = module.static_delivery.dns_records_to_create
}

output "certificate_arn" {
  description = "ARN of the custom domain certificate, or null when none is configured."
  value       = module.static_delivery.certificate_arn
}
