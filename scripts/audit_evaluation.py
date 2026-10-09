"""Inspect/review/compare existing results; never calls a model or writes a database."""

import argparse
import json
from pathlib import Path

from ragagent.domain.evaluation import ManualReview
from ragagent.evaluation.audit import compare_artifacts, inspect_case, review_template, score_review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["template", "review", "compare", "case"])
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--scope")
    parser.add_argument("--id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        results = json.loads(args.results.read_text(encoding="utf-8"))
        if args.action == "template":
            output = review_template(results).model_dump(mode="json")
        elif args.action == "review":
            if args.review is None:
                parser.error("review requires --review")
            output = score_review(
                results, ManualReview.model_validate_json(args.review.read_text(encoding="utf-8"))
            )
        elif args.action == "compare":
            if args.after is None:
                parser.error("compare requires --after")
            output = compare_artifacts(results, json.loads(args.after.read_text(encoding="utf-8")))
        else:
            if args.scope is None or args.id is None:
                parser.error("case requires --scope and --id")
            output = inspect_case(results, args.scope, args.id)
        args.output.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (ValueError, KeyError, TypeError, OSError):
        parser.error(
            "audit_failed: check artifact identities, schema, review labels and file permissions; "
            "raw input/error withheld"
        )


if __name__ == "__main__":
    main()
