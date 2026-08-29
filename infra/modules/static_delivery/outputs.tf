output "site_bucket_name" {
  description = "Private bucket holding the built frontend."
  value       = aws_s3_bucket.site.id
}

output "site_bucket_arn" {
  value = aws_s3_bucket.site.arn
}

output "data_bucket_name" {
  description = "Private bucket holding the published snapshot and its archive."
  value       = aws_s3_bucket.data.id
}

output "data_bucket_arn" {
  value = aws_s3_bucket.data.arn
}

output "cloudfront_distribution_id" {
  description = "Needed by the deployment workflow to invalidate the root document."
  value       = aws_cloudfront_distribution.this.id
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.this.domain_name
}

output "site_url" {
  description = "Public entry point. The custom domain when configured, otherwise the CloudFront hostname."
  value       = var.domain_name != null && var.hosted_zone_id != null ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.this.domain_name}"
}

output "data_url" {
  description = "Public URL of the published snapshot, for smoke tests."
  value       = var.domain_name != null && var.hosted_zone_id != null ? "https://${var.domain_name}/data/current.json" : "https://${aws_cloudfront_distribution.this.domain_name}/data/current.json"
}

output "dns_records_to_create" {
  description = <<-EOT
    The DNS records to add by hand when the domain is hosted outside Route 53.
    Null when no custom domain is configured or when Terraform manages the zone.
  EOT
  value = var.domain_name == null || var.hosted_zone_id != null ? null : {
    certificate_validation = {
      type  = one(aws_acm_certificate.this[0].domain_validation_options).resource_record_type
      name  = one(aws_acm_certificate.this[0].domain_validation_options).resource_record_name
      value = one(aws_acm_certificate.this[0].domain_validation_options).resource_record_value
      note  = "Add this first. The certificate stays pending until it resolves. Do not proxy it."
    }
    site = {
      type  = "CNAME"
      name  = var.domain_name
      value = aws_cloudfront_distribution.this.domain_name
      note  = "Points the domain at CloudFront."
    }
  }
}

output "certificate_arn" {
  description = <<-EOT
    ARN of the requested certificate, or null when no custom domain is
    configured. Deployment needs it to poll for issuance while the validation
    record is added by hand.
  EOT
  value       = one(aws_acm_certificate.this[*].arn)
}
