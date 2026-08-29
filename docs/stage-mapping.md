# Stage mapping

<!--
  GENERATED FILE - do not edit by hand.
  Produced by scripts/generate_stage_mapping_docs.py from
  backend/src/bill_pipeline/stage_map.py. Run `make docs` after changing
  the table.
-->

How each stage the UK Parliament Bills API publishes is placed on the
process chart. Mapping is by numeric `stageId` only: a stage is never
identified by its description, so renaming one cannot silently move a Bill,
and a stage introduced after this build surfaces as `unknown` rather than
being guessed at.

- Stage catalogue last reviewed against the API: **2026-08-29**
- Stage ids published by `/Stages`: **49**
- Stage ids classified by this build: **49**

## How a category behaves

| Category | Effect on a Bill's position |
| --- | --- |
| Direct | Replaces the Bill's position with the normalised node. |
| Ancillary | Runs alongside the process. The Bill stays at the most recent canonical stage, `mappingMode` becomes `previous_canonical`, and `nonStandardRoute` is set. |
| Private-Bill examination | Same anchoring rule. With no earlier canonical stage the Bill becomes `special_procedure`. |
| Unmapped | `unknown`, with the raw stage label retained and a run warning raised. Publication still proceeds. |

### Anchoring to the previous canonical stage

An ancillary stage does not tell you where a Bill is, only what happened to
it. To place such a Bill the code finds the current occurrence in the Bill's
own stage history by its occurrence id (`currentStage.id`, not the reusable
`stageId`), walks backwards through the earlier occurrences, and anchors to
the first directly mapped stage it finds. That search crosses session
boundaries, which is what places a carried-over Bill correctly. The real
stage label is kept in `stage.detail` so nothing is lost.

## Every published stage

| Stage id | Source name | House | Category | Normalised node |
| ---: | --- | --- | --- | --- |
| 1 | 1st reading | Lords | Direct | `lords_first_reading` |
| 2 | 2nd reading | Lords | Direct | `lords_second_reading` |
| 3 | Committee stage | Lords | Direct | `lords_committee` |
| 4 | Report stage | Lords | Direct | `lords_report` |
| 5 | 3rd reading | Lords | Direct | `lords_third_reading` |
| 6 | 1st reading | Commons | Direct | `commons_first_reading` |
| 7 | 2nd reading | Commons | Direct | `commons_second_reading` |
| 8 | Committee stage | Commons | Direct | `commons_committee` |
| 9 | Report stage | Commons | Direct | `commons_report` |
| 10 | 3rd reading | Commons | Direct | `commons_third_reading` |
| 11 | Royal Assent | Unassigned | Direct | `royal_assent` |
| 12 | Consideration of Lords amendments | Commons | Direct | `ping_pong` |
| 13 | Consideration of Commons amendments and / or reasons | Lords | Direct | `ping_pong` |
| 14 | Programme motion | Commons | Ancillary | anchors to previous |
| 15 | Money resolution | Commons | Ancillary | anchors to previous |
| 16 | Lords Examiners | Unassigned | Private-Bill examination | anchors to previous |
| 17 | Commons Examiners | Unassigned | Private-Bill examination | anchors to previous |
| 18 | Carry-over motion | Commons | Ancillary | anchors to previous |
| 19 | Carry-over motion | Lords | Ancillary | anchors to previous |
| 20 | Motion to suspend Bill till next session considered | Commons | Ancillary | anchors to previous |
| 21 | Bill reintroduced | Commons | Ancillary | anchors to previous |
| 22 | Bill reintroduced | Lords | Ancillary | anchors to previous |
| 23 | Petition to introduce a Private Bill presented to Parliament | Unassigned | Private-Bill examination | anchors to previous |
| 24 | Order of Commitment discharged | Lords | Direct | `lords_committee` |
| 25 | Second reading committee | Commons | Direct | `commons_second_reading` |
| 26 | Order of Commitment discharged | Commons | Direct | `commons_committee` |
| 27 | Committee negatived | Lords | Direct | `lords_committee` |
| 28 | Guillotine motion | Commons | Ancillary | anchors to previous |
| 29 | Allocation of time motion | Commons | Ancillary | anchors to previous |
| 30 | Second reading committee | Lords | Direct | `lords_second_reading` |
| 31 | Motion to suspend Bill till next session approved | Commons | Ancillary | anchors to previous |
| 32 | Motion to revive Bill | Commons | Ancillary | anchors to previous |
| 33 | Motion to suspend Bill till next session approved | Lords | Ancillary | anchors to previous |
| 34 | Motion to revive Bill | Lords | Ancillary | anchors to previous |
| 35 | Instruction to Committee on the Bill | Lords | Direct | `lords_committee` |
| 36 | Ways and Means resolution | Commons | Ancillary | anchors to previous |
| 37 | Instruction | Commons | Ancillary | anchors to previous |
| 38 | Legislative Grand Committee | Commons | Ancillary | anchors to previous |
| 39 | Reconsideration | Commons | Direct | `ping_pong` |
| 40 | Consequential consideration | Commons | Direct | `ping_pong` |
| 41 | Examination for compliance with Standing Orders | Unassigned | Private-Bill examination | anchors to previous |
| 42 | Consideration of Lords message | Commons | Direct | `ping_pong` |
| 43 | Select Committee stage | Commons | Direct | `commons_committee` |
| 44 | Second House Examination | Commons | Ancillary | anchors to previous |
| 46 | Lords Special Public Bill Committee | Lords | Direct | `lords_committee` |
| 47 | Committal (to a Select Committee) | Commons | Direct | `commons_committee` |
| 48 | Committee stage (re-committed clauses and schedules) | Commons | Direct | `commons_committee` |
| 49 | Committee of the whole House | Commons | Direct | `commons_committee` |
| 50 | Power of public bill committee to send for persons, papers and records | Commons | Direct | `commons_committee` |

## Notes on individual stages

### Stage 38: Legislative Grand Committee

Not enumerated in the original specification tables, which covered 48 of the 49 published stage ids. Classified as ancillary by the implementation because it runs alongside the main stages rather than replacing one, matching the specification's own definition of the ancillary category. See docs/stage-mapping.md.


## Drift

Every stage id in the checked-in catalogue is classified.

`backend/tests/test_stage_map.py` fails if the catalogue fixture gains an
id the table does not cover, and if a stage is renamed upstream. Live
ingestion keeps working either way: it publishes the affected Bill as
`unknown`, raises a run warning, and leaves the rest of the snapshot
untouched.

## Refreshing this file

```bash
curl -s 'https://bills-api.parliament.uk/api/v1/Stages?Skip=0&Take=100' \
  > backend/tests/fixtures/stages_catalogue.json
make docs
```

Then run the tests: a newly published stage will fail
`test_every_published_stage_id_is_classified` until it is classified
deliberately in `stage_map.py`.
