"""Precision of the anti-broker filter on a hand-labelled sample (spec §1: target ≥ 0.92).

Usage: uv run python scripts/precision.py sample.csv
"""
import csv
import sys


def main(path: str) -> int:
    with open(path, newline="") as f:
        labels = [row["label"].strip().lower() for row in csv.DictReader(f)]
    unlabelled = sum(1 for lab in labels if lab not in ("owner", "broker"))
    if unlabelled:
        print(f"{unlabelled} rows unlabelled (use owner or broker)", file=sys.stderr)
        return 1
    owners = labels.count("owner")
    print(f"precision={owners / len(labels):.2f} ({owners}/{len(labels)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
