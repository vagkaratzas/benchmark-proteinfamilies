#!/usr/bin/env python3
"""Fraction of curated families, per database layer, that a tool matched at least once.

Complements the sequence-level coverage: a tool can recover most curated *sequences* while still
reconstructing few curated *families*, and the two numbers separate those failure modes.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from post_common import family_files_from_metadata, verify_universe_checksum


def parse_args():
    parser = argparse.ArgumentParser(
        description="Count hit original families per database based on similarity results."
    )
    parser.add_argument(
        "--similarity_results",
        required=True,
        help="Path to the TSV file with similarity results.",
    )
    parser.add_argument(
        "--original_families_dir",
        required=True,
        help="Base directory containing original family FASTA files organized by database.",
    )
    parser.add_argument(
        "--metadata", required=True, help="Sampled metadata CSV with db/dbkey columns."
    )
    parser.add_argument("--pre_universe_fasta", required=True)
    parser.add_argument("--pre_universe_sha256", required=True)
    parser.add_argument(
        "--output_file", required=True, help="Output TSV file for the summary report."
    )
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    return parser.parse_args()


def extract_hit_families(similarity_results_path):
    hit_families = defaultdict(set)
    with Path(similarity_results_path).open() as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            db = row.get("db_layer", "").strip().lower()
            family = row.get("original_basename", "").strip()
            if db and family:
                hit_families[db].add(family)
    return hit_families


def count_hits_per_database(original_base_dir, metadata, hit_families):
    totals = defaultdict(set)
    for db, family, _path, _row in family_files_from_metadata(
        original_base_dir, metadata
    ):
        totals[db].add(family)

    rows = []
    for db in sorted(totals):
        total = len(totals[db])
        hits = len(totals[db] & hit_families.get(db, set()))
        coverage = hits / total if total else 0.0
        rows.append(
            {
                "database": db,
                "hits": hits,
                "total": total,
                "coverage_fraction": f"{coverage:.6f}",
            }
        )
    return rows


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    hit_families = extract_hit_families(args.similarity_results)
    rows = count_hits_per_database(
        args.original_families_dir, args.metadata, hit_families
    )

    with Path(args.output_file).open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "sample",
                "tool",
                "universe_sha256",
                "database",
                "hits",
                "total",
                "coverage_fraction",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for row in rows:
            row["sample"] = args.sample
            row["tool"] = args.tool
            row["universe_sha256"] = universe_sha256
            writer.writerow(row)


if __name__ == "__main__":
    main()
