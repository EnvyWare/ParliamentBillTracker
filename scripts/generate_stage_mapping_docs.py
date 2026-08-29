#!/usr/bin/env python3
"""Generate docs/stage-mapping.md from the stage table and the API catalogue.

The mapping is the part of this project most likely to drift from its
documentation, so the documentation is generated rather than maintained by
hand. `make check` runs this with --check and fails if the committed file no
longer matches the table.

Usage::

    python scripts/generate_stage_mapping_docs.py
    python scripts/generate_stage_mapping_docs.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from bill_pipeline.stage_map import (  # noqa: E402
    CATALOGUE_REVIEWED,
    STAGE_RULES,
    StageCategory,
    unmapped_ids,
)

CATALOGUE = REPO_ROOT / "backend" / "tests" / "fixtures" / "stages_catalogue.json"
OUTPUT = REPO_ROOT / "docs" / "stage-mapping.md"

CATEGORY_LABEL = {
    StageCategory.DIRECT: "Direct",
    StageCategory.ANCILLARY: "Ancillary",
    StageCategory.PRIVATE_EXAMINATION: "Private-Bill examination",
}


def render() -> str:
    with CATALOGUE.open(encoding="utf-8") as handle:
        catalogue = json.load(handle)
    published = {entry["id"]: entry for entry in catalogue["items"]}

    lines: list[str] = [
        "# Stage mapping",
        "",
        "<!--",
        "  GENERATED FILE - do not edit by hand.",
        "  Produced by scripts/generate_stage_mapping_docs.py from",
        "  backend/src/bill_pipeline/stage_map.py. Run `make docs` after changing",
        "  the table.",
        "-->",
        "",
        "How each stage the UK Parliament Bills API publishes is placed on the",
        "process chart. Mapping is by numeric `stageId` only: a stage is never",
        "identified by its description, so renaming one cannot silently move a Bill,",
        "and a stage introduced after this build surfaces as `unknown` rather than",
        "being guessed at.",
        "",
        f"- Stage catalogue last reviewed against the API: **{CATALOGUE_REVIEWED}**",
        f"- Stage ids published by `/Stages`: **{len(published)}**",
        f"- Stage ids classified by this build: **{len(STAGE_RULES)}**",
        "",
        "## How a category behaves",
        "",
        "| Category | Effect on a Bill's position |",
        "| --- | --- |",
        "| Direct | Replaces the Bill's position with the normalised node. |",
        "| Ancillary | Runs alongside the process. The Bill stays at the most recent "
        "canonical stage, `mappingMode` becomes `previous_canonical`, and "
        "`nonStandardRoute` is set. |",
        "| Private-Bill examination | Same anchoring rule. With no earlier canonical "
        "stage the Bill becomes `special_procedure`. |",
        "| Unmapped | `unknown`, with the raw stage label retained and a run warning "
        "raised. Publication still proceeds. |",
        "",
        "### Anchoring to the previous canonical stage",
        "",
        "An ancillary stage does not tell you where a Bill is, only what happened to",
        "it. To place such a Bill the code finds the current occurrence in the Bill's",
        "own stage history by its occurrence id (`currentStage.id`, not the reusable",
        "`stageId`), walks backwards through the earlier occurrences, and anchors to",
        "the first directly mapped stage it finds. That search crosses session",
        "boundaries, which is what places a carried-over Bill correctly. The real",
        "stage label is kept in `stage.detail` so nothing is lost.",
        "",
        "## Every published stage",
        "",
        "| Stage id | Source name | House | Category | Normalised node |",
        "| ---: | --- | --- | --- | --- |",
    ]

    for stage_id in sorted(published):
        entry = published[stage_id]
        rule = STAGE_RULES.get(stage_id)
        if rule is None:
            lines.append(
                f"| {stage_id} | {entry['name']} | {entry['house']} | "
                f"**Unmapped** | `unknown` |"
            )
            continue
        node = f"`{rule.node.value}`" if rule.node is not None else "anchors to previous"
        lines.append(
            f"| {stage_id} | {entry['name']} | {entry['house']} | "
            f"{CATEGORY_LABEL[rule.category]} | {node} |"
        )

    notes = [(rule.stage_id, rule) for rule in STAGE_RULES.values() if rule.note]
    if notes:
        lines += ["", "## Notes on individual stages", ""]
        for stage_id, rule in sorted(notes):
            lines += [f"### Stage {stage_id}: {rule.source_name}", "", rule.note, ""]

    missing = unmapped_ids(set(published))
    lines += ["", "## Drift", ""]
    if missing:
        lines += [
            "The API currently publishes stage ids this build does not classify:",
            "",
            *[f"- `{stage_id}`" for stage_id in missing],
            "",
            "Bills at those stages are published as `unknown` and shown in the",
            "unclassified section until the table is updated.",
        ]
    else:
        lines += [
            "Every stage id in the checked-in catalogue is classified.",
            "",
            "`backend/tests/test_stage_map.py` fails if the catalogue fixture gains an",
            "id the table does not cover, and if a stage is renamed upstream. Live",
            "ingestion keeps working either way: it publishes the affected Bill as",
            "`unknown`, raises a run warning, and leaves the rest of the snapshot",
            "untouched.",
        ]

    lines += [
        "",
        "## Refreshing this file",
        "",
        "```bash",
        "curl -s 'https://bills-api.parliament.uk/api/v1/Stages?Skip=0&Take=100' \\",
        "  > backend/tests/fixtures/stages_catalogue.json",
        "make docs",
        "```",
        "",
        "Then run the tests: a newly published stage will fail",
        "`test_every_published_stage_id_is_classified` until it is classified",
        "deliberately in `stage_map.py`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the file is out of date.")
    args = parser.parse_args()

    rendered = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print(f"{OUTPUT.relative_to(REPO_ROOT)} is out of date; run 'make docs'", file=sys.stderr)
            return 1
        print(f"{OUTPUT.relative_to(REPO_ROOT)} is up to date")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
