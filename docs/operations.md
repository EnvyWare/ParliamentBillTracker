# Operations

Everything here assumes AWS credentials for the deployment account and
Terraform on your PATH. Names below use the defaults; substitute your own if
you changed `project_name` or `environment`.

```bash
cd infra/environments/prod
terraform output          # bucket names, function name, queue URL, site URL
```

## Updating the Parliamentary session

**This is the one piece of configuration that goes stale on its own.**

The Bills API has no dependable current-session lookup, so the session is
explicit configuration. Each run checks it against a canary: the single most
recently updated Bill across all sessions. If that Bill belongs to a newer
session, ingestion logs a critical warning and fails without republishing,
which is deliberate — publishing a session that has ended would be worse than
publishing nothing new.

You will see this in the logs:

```
{"event": "session_rollover_detected", "configuredSessionId": 40,
 "observedSessionId": 41, "action": "Update the parliament_session_id ..."}
```

To fix it, confirm the new session first:

```bash
curl -s "https://bills-api.parliament.uk/api/v1/Bills?Skip=0&Take=1&SortOrder=DateUpdatedDescending" \
  | python -c "import json,sys; print(json.load(sys.stdin)['items'][0]['introducedSessionId'])"
```

Then update `infra/environments/prod/terraform.tfvars`:

```hcl
parliament_session_id    = 41
parliament_session_label = "2027-28"
```

and apply:

```bash
terraform apply
```

The next scheduled run publishes the new session. Note that the Bill count
will drop sharply, which normally trips the 30% shrink guard — that guard is
skipped when the session id changes, precisely so a rollover is not blocked.

## Running ingestion by hand

```bash
aws lambda invoke \
  --function-name uk-bill-pipeline-prod-ingest \
  --cli-binary-format raw-in-base64-out \
  --payload '{}' \
  /tmp/out.json && cat /tmp/out.json
```

The response is the invocation summary: counts, request totals, the content
hash, and whether the snapshot changed.

### Forcing a full reconciliation

Normal runs only re-fetch Bills whose `lastUpdate` changed. After you change
the stage mapping table, cached records will still carry the old
classification until the weekly reconciliation catches up. To refresh
everything immediately:

```bash
aws lambda invoke \
  --function-name uk-bill-pipeline-prod-ingest \
  --cli-binary-format raw-in-base64-out \
  --payload '{"forceFullReconciliation": true}' \
  /tmp/out.json
```

This is the only field the function reads from its event. It never accepts a
source URL — that would make it a server-side request forgery primitive.

## Pausing ingestion

```hcl
# terraform.tfvars
ingestion_enabled = false
```

```bash
terraform apply
```

The schedule is disabled rather than destroyed, and the last published
snapshot keeps serving. The site will show its stale-data banner after three
hours, which is correct: the data *is* stale.

## Reading the logs

```bash
# The last hour, most recent first
aws logs tail /aws/lambda/uk-bill-pipeline-prod-ingest --since 1h --format short

# Just the per-run summaries
aws logs filter-log-events \
  --log-group-name /aws/lambda/uk-bill-pipeline-prod-ingest \
  --filter-pattern '{ $.event = "ingestion_summary" }' \
  --query 'events[].message' --output text
```

Every log line is JSON. The fields worth knowing:

| Field | Meaning |
| --- | --- |
| `status` | `succeeded` or `failed` |
| `sourceRecordCount` | Bills the API reported for the session |
| `changedRecordCount` | Bills that needed re-fetching this run |
| `publishedRecordCount` | Bills in the published snapshot |
| `specialOrUnknownCount` | Bills that could not be placed on a route |
| `snapshotChanged` | Whether the content hash moved |
| `fullReconciliation` | Whether this run re-fetched everything |
| `unmappedStageIds` | Stage ids the API publishes that this build does not classify |

Events other than `ingestion_summary` are worth grepping for:
`session_rollover_detected`, `unmapped_stage_ids`,
`previous_snapshot_invalid`, `publication_guard_refused`, `ingestion_failed`.

## The failure queue

Invocations that fail after every retry land here, from both the Scheduler
and the Lambda failure destination.

```bash
QUEUE=$(terraform output -raw failure_queue_url)
aws sqs get-queue-attributes --queue-url "$QUEUE" \
  --attribute-names ApproximateNumberOfMessages

aws sqs receive-message --queue-url "$QUEUE" --max-number-of-messages 10
```

Messages are kept for 14 days. Once you have diagnosed and fixed the cause,
purge them so the alarm clears:

```bash
aws sqs purge-queue --queue-url "$QUEUE"
```

A message in this queue does **not** mean the site is broken. It means a run
failed and the previous snapshot is still being served. Check how old the
published data is before treating it as urgent.

## Recovering a previous snapshot

The data bucket is versioned, and every distinct snapshot is also archived
under `archive/snapshots/<content-hash>.json`.

```bash
DATA=$(terraform output -raw data_bucket_name)

# What versions exist
aws s3api list-object-versions --bucket "$DATA" --prefix data/current.json \
  --query 'Versions[].{Version:VersionId,Modified:LastModified}' --output table

# Inspect one before restoring it
aws s3api get-object --bucket "$DATA" --key data/current.json \
  --version-id "<version-id>" /tmp/candidate.json
python scripts/validate_snapshot.py /tmp/candidate.json

# Restore by copying it back over the current key
aws s3api copy-object --bucket "$DATA" --key data/current.json \
  --copy-source "$DATA/data/current.json?versionId=<version-id>" \
  --cache-control "public,max-age=60,s-maxage=300,must-revalidate" \
  --content-type "application/json; charset=utf-8" \
  --metadata-directive REPLACE
```

Setting the cache headers explicitly matters: `copy-object` does not carry
them across by default, and a snapshot without them would be cached for the
wrong length of time.

The next successful scheduled run will overwrite whatever you restore, so fix
the underlying cause as well.

## Responding to a new or unknown stage id

Parliament occasionally adds a stage. Nothing breaks: affected Bills are
published as `unknown`, shown in the unclassified section with their real
stage name, and a warning appears in the snapshot and the logs.

To classify it deliberately:

1. Refresh the catalogue fixture and regenerate the mapping documentation:

   ```bash
   curl -s 'https://bills-api.parliament.uk/api/v1/Stages?Skip=0&Take=100' \
     > backend/tests/fixtures/stages_catalogue.json
   make docs
   ```

2. `make test` now fails on `test_every_published_stage_id_is_classified`,
   naming the new id.
3. Add it to `_RULES` in `backend/src/bill_pipeline/stage_map.py`. Decide
   between direct and ancillary by asking whether the stage *replaces* a
   Bill's position or *runs alongside* it. Record the reasoning in the rule's
   `note`; it ends up in the generated documentation.
4. `make check`, deploy, then force a full reconciliation so cached records
   pick up the new classification.

Never classify by matching the stage description. That is the one rule the
mapping exists to avoid.

## Rotating retention

Defaults: archives 90 days, non-current `current.json` versions 14 days,
non-current frontend objects 30 days, logs 14 days. All are variables:

```hcl
archive_retention_days    = 180
lambda_log_retention_days = 30
```

Lifecycle changes apply going forward. Objects already past a shortened
window are removed by S3 on its own schedule, not immediately.

## Destroying it

```bash
cd infra/environments/prod
terraform destroy
```

Read this first:

- **Both buckets have `force_destroy = false`**, so `destroy` fails while
  they contain objects. That is deliberate. Empty them by hand once you are
  certain:

  ```bash
  aws s3 rm "s3://$(terraform output -raw site_bucket_name)" --recursive
  aws s3 rm "s3://$(terraform output -raw data_bucket_name)" --recursive
  ```

  Versioned buckets also retain non-current versions and delete markers,
  which `s3 rm --recursive` does not remove. Use `list-object-versions` and
  `delete-objects`, or set `force_destroy = true` and apply before
  destroying.

- **If a CloudFront pricing plan is attached**, remove the plan association
  in the console first. A distribution under a plan cannot be deleted.

- **The state bucket is not destroyed** by this command. It is a separate
  root with `prevent_destroy` set. Remove it deliberately, last, and only if
  you are finished with the project.
