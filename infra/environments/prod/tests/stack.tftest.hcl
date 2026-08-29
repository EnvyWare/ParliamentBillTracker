# Smoke test for the production root.
#
# The detailed policy assertions live with each module. This checks the thing
# only the root can check: that the two modules wire together, that the
# session reaches the function, and that the optional pieces stay optional.
#
# Runs against a mocked apply, so it needs no AWS credentials.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::000000000000:role/mock" }
  }
  mock_resource "aws_lambda_function" {
    defaults = { arn = "arn:aws:lambda:eu-west-2:000000000000:function:mock" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = {
      arn = "arn:aws:sqs:eu-west-2:000000000000:mock"
      url = "https://sqs.eu-west-2.amazonaws.com/000000000000/mock"
    }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:eu-west-2:000000000000:log-group:/aws/lambda/mock" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:eu-west-2:000000000000:mock" }
  }

  # The site and data URLs are built from this, so a random mock string would
  # make the URL assertions meaningless rather than failing them honestly.
  mock_resource "aws_cloudfront_distribution" {
    defaults = { domain_name = "d111111abcdef8.cloudfront.net" }
  }

  # Repeated from the us_east_1 block below. The certificate resources are
  # created through the aliased provider, but the distribution that consumes
  # the ARN is created through the default one, and it validates the ARN shape.
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000"
      domain_validation_options = [{
        domain_name           = "bills.example.com"
        resource_record_name  = "_test.bills.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_test.acm-validations.aws."
      }]
    }
  }

  mock_resource "aws_acm_certificate_validation" {
    defaults = {
      certificate_arn = "arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000"
    }
  }
}

mock_provider "aws" {
  alias = "us_east_1"

  # A generated mock value is a random string, and the provider validates this
  # one as an ARN.
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000"
      domain_validation_options = [{
        domain_name           = "bills.example.com"
        resource_record_name  = "_test.bills.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_test.acm-validations.aws."
      }]
    }
  }

  mock_resource "aws_acm_certificate_validation" {
    defaults = {
      certificate_arn = "arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000"
    }
  }
}

mock_provider "archive" {}

variables {
  parliament_session_id    = 40
  parliament_session_label = "2026-27"

  # Every optional input is pinned to its off value.
  #
  # Not redundant: `terraform test` loads terraform.tfvars automatically, the
  # same as a plan does. Without these, a contributor who has deployed this
  # stack runs the tests against their own domain and notification addresses,
  # and whether the suite passes depends on the machine it runs on. Each run
  # below turns on exactly the one feature it is about.
  domain_name        = null
  hosted_zone_id     = null
  alarm_email        = null
  budget_alert_email = null
  ingestion_enabled  = true
}

run "the_stack_plans_end_to_end" {
  command = apply

  assert {
    condition     = module.ingestion.lambda_function_name == "uk-bill-pipeline-prod-ingest"
    error_message = "The ingestion function should be named from the project and environment."
  }

  assert {
    condition     = output.parliament_session.id == 40
    error_message = "The configured session must be echoed in the outputs."
  }

  assert {
    condition     = length(aws_budgets_budget.monthly) == 0
    error_message = "No budget should be created without a budget email."
  }

  # The site and the generated data live in separate buckets so that a
  # frontend sync --delete cannot reach the published snapshot.
  assert {
    condition     = module.static_delivery.site_bucket_name != module.static_delivery.data_bucket_name
    error_message = "The frontend and the data must not share a bucket."
  }

  assert {
    condition     = endswith(module.static_delivery.data_url, "/data/current.json")
    error_message = "The snapshot must be served from /data/current.json."
  }

  assert {
    condition     = startswith(module.static_delivery.site_url, "https://")
    error_message = "The site must be served over HTTPS."
  }
}

run "notification_inputs_create_their_resources" {
  command = apply

  variables {
    alarm_email        = "alerts@example.com"
    budget_alert_email = "billing@example.com"
    monthly_budget_usd = 5
  }

  assert {
    condition     = length(aws_budgets_budget.monthly) == 1
    error_message = "A budget email must create a budget."
  }

  assert {
    condition     = aws_budgets_budget.monthly[0].limit_amount == "5"
    error_message = "The budget limit must come from the variable."
  }

  # A budget alerts; it does not cap spending. Both an actual and a forecast
  # threshold are configured so an overrun is noticed before it completes.
  assert {
    condition     = length(aws_budgets_budget.monthly[0].notification) == 2
    error_message = "The budget needs both an actual and a forecast notification."
  }

  assert {
    condition     = module.ingestion.alarm_topic_arn != null
    error_message = "An alarm email must create an SNS topic."
  }
}

run "ingestion_can_be_paused" {
  command = apply

  variables {
    ingestion_enabled = false
  }

  assert {
    condition     = module.ingestion.schedule_name == "uk-bill-pipeline-prod-ingest-schedule"
    error_message = "The schedule should still exist when ingestion is paused."
  }
}

# The custom domain is optional, and both halves of that have to hold: absent,
# nothing is requested; present, the alias and the certificate are attached.
run "no_domain_means_no_certificate" {
  command = apply

  assert {
    condition     = module.static_delivery.certificate_arn == null
    error_message = "No certificate should be requested without a domain name."
  }

  assert {
    condition     = endswith(module.static_delivery.site_url, ".cloudfront.net")
    error_message = "Without a domain the site must be served on its CloudFront hostname."
  }
}

run "a_domain_attaches_a_certificate" {
  command = apply

  variables {
    domain_name = "bills.example.com"
  }

  assert {
    condition     = module.static_delivery.certificate_arn != null
    error_message = "A domain name must request a certificate."
  }

  # DNS is a separate decision from the domain. With no hosted zone Terraform
  # creates no records, so it must hand the operator the ones to add.
  assert {
    condition     = module.static_delivery.dns_records_to_create != null
    error_message = "Without a hosted zone the operator must be told which records to add."
  }

  # site_url deliberately stays on the CloudFront hostname until Terraform
  # manages the DNS, because a domain that has been requested is not yet a
  # domain that resolves. Reporting it as live before the operator has added
  # the CNAME would make the smoke test assert against a name that 404s.
  assert {
    condition     = endswith(module.static_delivery.site_url, ".cloudfront.net")
    error_message = "Until DNS is managed, the reported URL must be the hostname that actually resolves."
  }
}
