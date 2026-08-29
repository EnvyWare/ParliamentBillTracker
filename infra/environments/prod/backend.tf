# Remote state, configured at init time from backend.hcl so no account
# identifier is committed:
#
#   terraform init -backend-config=backend.hcl
#
# Locking uses native S3 conditional writes (use_lockfile), so there is no
# DynamoDB table to pay for or to keep in step.
terraform {
  backend "s3" {}
}
