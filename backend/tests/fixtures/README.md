# Test fixtures

## Licensing

`stages_catalogue.json` is a verbatim copy of the UK Parliament Bills API
`/Stages` response, retrieved on 29 August 2026.

> Contains Parliamentary information licensed under the
> [Open Parliament Licence v3.0](https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/).

**This file is Parliamentary information and is excluded from the repository's
MIT grant.** See `THIRD_PARTY_NOTICES.md` in the repository root.

It is checked in so the stage-mapping test can prove that every stage id the
API publishes is classified by `bill_pipeline.stage_map`, without the test
suite needing network access.

## Everything else here is synthetic

`synthetic_source.py` builds API-shaped objects from invented Bills. No real
Bill title, member name, party or identifier appears in it. It is original
work covered by the repository's MIT licence, and it is the single source for:

- the backend golden contract tests, and
- `frontend/public/data/current.json`, the example snapshot that lets the
  frontend run locally with no AWS account and no internet access.

Regenerate the frontend example snapshot after changing it:

```bash
make fixtures
```

The synthetic snapshot is marked `"synthetic": true` and `"status":
"synthetic"` so the running application labels it as example data rather than
presenting it as live Parliamentary information.
