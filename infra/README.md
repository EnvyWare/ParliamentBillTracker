# Infrastructure

Terraform for the whole stack. [`docs/deployment.md`](../docs/deployment.md)
is the step-by-step sequence; this file is the **configuration reference**:
what is required, what is optional, and what each option actually creates.

```
infra/
├── bootstrap/                 # OPTIONAL: the Terraform state bucket
├── modules/
│   ├── static_delivery/       # S3 + CloudFront + optional certificate and DNS
│   └── ingestion/             # Lambda + Scheduler + failure queue + alarms
└── environments/prod/         # the root you actually apply
```

## The shortest working configuration

Two variables. Everything else has a default that produces a complete,
working deployment.

```hcl
parliament_session_id    = 40
parliament_session_label = "2026-27"
```

That gives you a private S3 site behind CloudFront on its `*.cloudfront.net`
hostname, a scheduled ingestion Lambda, a failure queue, and four alarms. No
domain, no email, no budget, no logs.

## What is optional

Each row is off unless you switch it on, and switching it off later removes
the resources rather than orphaning them.

| Feature | Turn it on with | What appears | What you give up by leaving it off |
| --- | --- | --- | --- |
| **Custom domain** | `domain_name` | ACM certificate in us-east-1, alias on the distribution | The site is reachable only on its CloudFront hostname |
| **Managed DNS** | `hosted_zone_id` (with `domain_name`) | Validation CNAME, A and AAAA alias records | You add two DNS records by hand at your own provider |
| **Alarm notifications** | `alarm_email` | SNS topic and subscription | The four alarms still exist and still show state in the console; nobody is emailed |
| **Budget alerts** | `budget_alert_email` | AWS Budget with an 80% and 100% notification | No cost alerting. A budget alerts; it is not a cap |
| **CloudFront access logs** | `enable_cloudfront_access_logs` **and** `cloudfront_access_log_bucket_domain_name` | Logging configuration on the distribution | No per-request log. CloudFront metrics still work |
| **Remote state bucket** | apply `infra/bootstrap` | Versioned, encrypted, TLS-only state bucket with native locking | Nothing, if you already operate a state bucket — point `backend.hcl` at it instead |

`hosted_zone_id` without `domain_name`, and access logs without a destination,
are both rejected at plan time rather than silently doing nothing.

## What is tunable

Working defaults; change them if you want different behaviour.

| Variable | Default | Why you might change it |
| --- | --- | --- |
| `schedule_expression` | `rate(30 minutes)` | Faster mostly re-reads unchanged Bills; slower makes the page staler. The page always states its own age |
| `ingestion_enabled` | `true` | Set `false` to pause ingestion without destroying anything. The schedule is disabled, not deleted, and the last snapshot keeps serving |
| `lambda_reserved_concurrency` | `1` | **Must be `null`** on an account whose Lambda concurrency quota is 10 — AWS rejects a reservation that would take unreserved concurrency below 10 |
| `lambda_log_retention_days` | `14` | Longer retention costs more; nothing here needs long-lived logs |
| `archive_retention_days` | `90` | How much snapshot history to keep |
| `aws_region` | `eu-west-2` | Anywhere. The certificate is pinned to us-east-1 regardless, via an aliased provider |
| `project_name`, `environment` | `uk-bill-pipeline`, `prod` | Both appear in every resource name, so a second environment can share an account |
| `monthly_budget_usd` | `5` | Only read when `budget_alert_email` is set |

## What is not configurable, and why

These are guarantees rather than preferences, so they are not exposed as
variables. They are enforced by `terraform test` and
`scripts/check_infra_policy.py`, and a change that removes one fails CI.

- **Both buckets are private.** No public access, no S3 website hosting.
  CloudFront reaches them through Origin Access Control and nothing else can.
- **The ingestion role cannot list a bucket.** It holds `s3:GetObject` on
  exactly the two key patterns it reads. This is why the code treats a `403`
  as "absent" — without `ListBucket`, S3 cannot tell you the difference.
- **No NAT Gateway, VPC endpoint, API Gateway, database, or customer-managed
  KMS key.** The cost target follows from what is absent, not from tuning.
- **A bad run cannot replace a good snapshot.** The publication guards live in
  the Lambda, not in Terraform, and there is no flag to disable them.
- **Buckets refuse `terraform destroy` while they hold objects.**
  `force_destroy` exists in the module and must stay `false` in production.

## The CloudFront pricing plan

Subscribing the distribution to a flat-rate CloudFront plan is a billing
association made in the console. The Terraform AWS provider cannot manage it,
so it is a documented operator step rather than a `null_resource` shelling out.

The plan may attach its own WAF ACL, so the distribution ignores drift on
`web_acl_id` and later plans stay clean. **Remove the plan association before
`terraform destroy`** — a distribution under a plan cannot be deleted.

The stack runs perfectly well on ordinary pay-as-you-go CloudFront.

## Testing without an AWS account

Everything below runs with no credentials and touches nothing.

```bash
make tf-validate   # fmt, validate, and the static policy checks
make tf-test       # 34 policy tests against mocked providers
```

The tests mock the **apply**, not the plan, so assertions see known values
rather than `(known after apply)`.
