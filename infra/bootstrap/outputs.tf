output "state_bucket_name" {
  description = "Bucket to configure as the Terraform S3 backend."
  value       = aws_s3_bucket.state.id
}

output "state_bucket_arn" {
  description = "ARN of the state bucket, for granting the deployment role access."
  value       = aws_s3_bucket.state.arn
}

output "backend_configuration" {
  description = "Ready-made backend.hcl contents for infra/environments/prod."
  value       = <<-EOT
    bucket       = "${aws_s3_bucket.state.id}"
    key          = "uk-bill-pipeline/prod/terraform.tfstate"
    region       = "${var.aws_region}"
    encrypt      = true
    use_lockfile = true
  EOT
}
