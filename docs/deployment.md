# Deployment

Every step below has been run against a real AWS account. Where something bit
us, the note says so rather than pretending the happy path is the only path.

## Prerequisites

- An AWS account and credentials (`aws sts get-caller-identity` should work).
- Terraform `>= 1.10, < 2.0` on PATH.
- Node.js (see `.nvmrc`) and Python 3.13.
- `make` for the convenience targets. On Windows use Git Bash, or run the
  underlying commands directly — the PowerShell equivalents are at the end.

```bash
make install
make check      # everything below assumes this passes first
```

## 1. Bootstrap the state bucket

Skip this if you already operate a private Terraform state bucket; just point
`backend.hcl` at it instead.

```bash
cd infra/bootstrap
terraform init
terraform apply -var 'owner=your-team' -var 'github_repository=owner/repo'
terraform output backend_configuration
```

This root uses local state, because it is what creates the remote backend. It
makes one versioned, encrypted, TLS-only bucket with `prevent_destroy` set and
native S3 locking. No DynamoDB table: S3 conditional writes replace it.

## 2. Configure the production root

```bash
cd ../environments/prod
cp backend.hcl.example backend.hcl          # paste the output from step 1
cp terraform.tfvars.example terraform.tfvars
```

**Verify the session before every apply.** The Bills API has no dependable
current-session lookup, so it is explicit configuration:

```bash
curl -s "https://bills-api.parliament.uk/api/v1/Bills?Skip=0&Take=1&SortOrder=DateUpdatedDescending" \
  | python -c "import json,sys; print(json.load(sys.stdin)['items'][0]['introducedSessionId'])"
```

```bash
terraform init -backend-config=backend.hcl
```

## 3. Build the artefacts

```bash
cd ../../..
make build
```

`build-lambda` assembles the handler, the snapshot schema and `tzdata` into
`backend/build/lambda` for Terraform to zip. `build-frontend` type-checks and
builds `frontend/dist`.

Terraform zips a directory that must already exist, so **build before you
plan**.

## 4. Apply

```bash
cd infra/environments/prod
terraform plan          # read it
terraform apply
```

Expect roughly 30 resources and about five minutes, most of it CloudFront.

> **Check the exit code.** If you pipe `terraform apply` into `tail` or `grep`,
> the pipeline reports the *filter's* exit status, not Terraform's, and a
> failed apply looks like a successful one. Use `set -o pipefail`, or do not
> pipe.

### Two things that may stop you

**Lambda reserved concurrency.** The design reserves one concurrent execution.
AWS rejects any reservation that would take an account's unreserved
concurrency below 10, so on an account with the reduced quota of 10 this fails
with `InvalidParameterValueException`. Check with:

```bash
aws lambda get-account-settings --query 'AccountLimit.ConcurrentExecutions'
```

If it is 10, either request a quota increase, or set
`lambda_reserved_concurrency = null` and accept that two runs *could* in
principle overlap. Archive writes stay idempotent and replacing `current.json`
is atomic, so the consequence is small — but it is a real reduction in
guarantee, so make it deliberately.

**EventBridge Scheduler trust policy.** Scheduler validates the execution role
when the schedule is created, which is *before* the schedule ARN exists. A
trust policy conditioned on `aws:SourceArn` therefore cannot be satisfied
during that check, and `CreateSchedule` fails with "The execution role you
provide must allow AWS EventBridge Scheduler to assume the role". The module
conditions on `aws:SourceAccount` only, for this reason. It is documented in
the module rather than left as folklore.

## 5. Deploy the frontend

```bash
cd ../../..
scripts/deploy_frontend.sh "$(terraform -chdir=infra/environments/prod output -raw site_bucket_name)" \
                           "$(terraform -chdir=infra/environments/prod output -raw cloudfront_distribution_id)"
```

Fingerprinted assets go up first with a one-year immutable cache, then
`index.html` with revalidation. `data/*` is excluded: that directory holds the
synthetic development fixture, and the real snapshot lives in a different
bucket entirely.

## 6. First ingestion

The schedule fires every 30 minutes; do not wait for it.

```bash
aws lambda invoke \
  --function-name "$(terraform -chdir=infra/environments/prod output -raw ingestion_lambda_name)" \
  --cli-binary-format raw-in-base64-out --payload '{}' \
  --cli-read-timeout 700 /tmp/out.json && cat /tmp/out.json
```

A first run fetches every Bill — around 330 requests, roughly 20 seconds.

## 7. Smoke test

```bash
scripts/smoke_test.sh "$(terraform -chdir=infra/environments/prod output -raw site_url)" \
                      "$(terraform -chdir=infra/environments/prod output -raw site_bucket_name)" \
                      "$(terraform -chdir=infra/environments/prod output -raw data_bucket_name)"
```

It checks the page, the compiled asset and its immutable header, the snapshot
and its short cache header, that the snapshot is schema-valid, live and fresh,
and that anonymous access to both buckets is refused.

## Custom domain

The site works on its `*.cloudfront.net` hostname with no domain at all. There
are two ways to add one.

### Route 53

Set both variables and apply. Terraform requests the certificate, creates the
validation record and the A/AAAA aliases, and attaches the domain.

```hcl
domain_name    = "bills.example.com"
hosted_zone_id = "Z0123456789ABCDEFGHIJ"
```

No hosted zone is created — a zone is a standing monthly charge, and reusing
an existing one is almost always what is wanted.

### DNS hosted elsewhere (Cloudflare, and others)

Set `domain_name` and leave `hosted_zone_id` null. Terraform requests the
certificate and attaches the alias; you add two records by hand.

**Do it in this order, or the apply will sit waiting.**

1. Create the certificate on its own, so you can read the validation record
   before anything blocks on it:

   ```bash
   terraform apply -target=module.static_delivery.aws_acm_certificate.this
   terraform output dns_records_to_create
   ```

2. Add both records at your DNS provider:

   | Purpose | Type | Name | Value |
   | --- | --- | --- | --- |
   | ACM validation | CNAME | `_<hash>.bills.example.com` | `_<hash>.acm-validations.aws.` |
   | The site | CNAME | `bills.example.com` | `<id>.cloudfront.net` |

   On Cloudflare, set both to **DNS only** (grey cloud), not proxied.
   Proxying puts a second CDN in front of CloudFront, and with Cloudflare's
   SSL mode set to Flexible it produces a redirect loop.

3. Wait for the certificate to be issued, then finish:

   ```bash
   aws acm describe-certificate --region us-east-1 \
     --certificate-arn "<arn>" --query 'Certificate.Status'
   terraform apply
   ```

The certificate must live in `us-east-1` regardless of where the rest of the
stack is; the module uses an aliased provider for exactly that.

## CloudFront pricing plan

If you subscribe the distribution to a CloudFront flat-rate plan, that is a
billing association made in the console. It is not manageable by the Terraform
AWS provider, so it is a documented one-time operator step rather than a
`null_resource` shelling out.

The plan may attach its own WAF ACL; the distribution ignores drift on
`web_acl_id` so later plans stay clean. **Remove the plan association before
`terraform destroy`** — a distribution under a plan cannot be deleted.

The stack also runs perfectly well on ordinary pay-as-you-go CloudFront.

## GitHub Actions with OIDC

Deployment from CI uses short-lived credentials. There are no stored AWS keys.

1. Add GitHub as an OIDC provider (`token.actions.githubusercontent.com`,
   audience `sts.amazonaws.com`).
2. Create a role whose trust policy is restricted to your exact repository and
   the protected branch or environment:

   ```json
   {
     "Condition": {
       "StringEquals": {
         "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
       },
       "StringLike": {
         "token.actions.githubusercontent.com:sub": "repo:owner/repo:ref:refs/heads/main"
       }
     }
   }
   ```

   A trust policy that omits the `sub` condition is assumable by *any*
   repository on GitHub.
3. Set the role ARN as the `AWS_DEPLOY_ROLE_ARN` repository variable, and
   create a protected `production` environment.

### Repository variables

All of these are GitHub **variables**, not secrets — none is confidential. The
deploy job is skipped entirely when `AWS_DEPLOY_ROLE_ARN` is unset, so a fork
that never configures AWS still gets the full quality gate.

| Variable | Needed? | Effect |
| --- | --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | to deploy at all | Without it the deploy job is skipped, not failed |
| `TF_STATE_BUCKET` | to deploy | The state bucket from step 1 |
| `PARLIAMENT_SESSION_ID` | to deploy | The run fails with a clear message if unset |
| `PARLIAMENT_SESSION_LABEL` | to deploy | Shown in the UI |
| `AWS_REGION` | no | Defaults to `eu-west-2` |
| `TF_STATE_KEY` | no | Defaults to `uk-bill-pipeline/prod/terraform.tfstate` |
| `DOMAIN_NAME`, `HOSTED_ZONE_ID` | no | Custom domain and managed DNS |
| `ALARM_EMAIL`, `BUDGET_ALERT_EMAIL`, `MONTHLY_BUDGET_USD` | no | Notifications and budget |
| `SCHEDULE_EXPRESSION`, `INGESTION_ENABLED` | no | Ingestion cadence, or pause it |
| `LAMBDA_RESERVED_CONCURRENCY` | no | Set to `null` on an account with a quota of 10 |
| `ENABLE_CLOUDFRONT_ACCESS_LOGS` | no | Needs a log bucket set in `terraform.tfvars` |
| `OWNER` | no | Tagging |

An unset GitHub variable is an empty string, not null. The workflow therefore
writes a `.tfvars` line only for variables that are actually set, because
`domain_name = ""` would ask CloudFront for a blank alias rather than leaving
the custom domain switched off.

**Update `PARLIAMENT_SESSION_ID` at each State Opening.** Nothing detects the
rollover for you; ingestion detects a *newer* session and fails the run rather
than publishing a session that has ended, which is a safety net, not a fix.

## Windows equivalents

The Make targets need Git Bash. The underlying commands in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
cd frontend; npm ci; cd ..

.\.venv\Scripts\python.exe -m pytest backend/tests
cd frontend; npm run lint; npm run typecheck; npm test; cd ..

bash scripts/build_lambda.sh (Resolve-Path .\.venv\Scripts\python.exe)
cd frontend; npm run build; cd ..
```

Two Windows-specific traps, both handled in the scripts but worth knowing:

- Git Bash rewrites arguments that look like absolute paths, which turns a
  CloudFront invalidation path of `/` into a Windows directory.
  `MSYS_NO_PATHCONV=1` prevents it.
- `curl` may resolve to the Windows build in `System32`, which does not share
  MSYS's `/tmp`. The scripts use `mktemp -d` rather than a hard-coded path.
