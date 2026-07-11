#!/usr/bin/env python3
"""Fraction of curated sequences, per database layer, that a tool recovered.

The denominator is the curated originals actually present in the universe (from the registry), not
the size of the source database -- PRE only sampled part of it.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from benchmark_ids import load_registry
from post_common import (
    family_files_from_metadata,
    resolve_records,
    verify_universe_checksum,
)


def load_original_hits(original_counts_file):
    found = set()
    with Path(original_counts_file).open() as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            count = int(row.get("count", "0") or 0)
            if count > 0:
                found.add(row["universe_id"])
    return found


def compute_match_stats(metadata, msa_root, found_proteins, registry):
    db_to_members = defaultdict(set)
    for db, family, path, _row in family_files_from_metadata(msa_root, metadata):
        members, _frags, _unmapped, _ambiguous, _n_raw = resolve_records(
            path,
            registry,
            f"original:{db}/{family}",
            fail_on_unresolved=True,
        )
        db_to_members[db].update(members)
    rows = []
    for db in sorted(db_to_members):
        total_unique = db_to_members[db]
        matched = total_unique.intersection(found_proteins)
        total_count = len(total_unique)
        matched_count = len(matched)
        percentage = (matched_count / total_count) * 100 if total_count else 0
        rows.append(
            {
                "db": db,
                "match_percentage": f"{percentage:.1f}",
                "matched": matched_count,
                "total": total_count,
            }
        )
    return rows


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute DB-level sequence coverage from metadata and original hit counts."
    )
    parser.add_argument("--metadata", required=True, help="Path to metadata CSV")
    parser.add_argument(
        "--original_counts", required=True, help="Path to original count TSV"
    )
    parser.add_argument(
        "--msa_root",
        required=True,
        help="Root directory containing sampled FASTA subfolders by DB layer",
    )
    parser.add_argument("--id_registry", required=True)
    parser.add_argument("--pre_universe_fasta", required=True)
    parser.add_argument("--pre_universe_sha256", required=True)
    parser.add_argument("--output", required=True, help="Output TSV path")
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    return parser.parse_args()


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    registry = load_registry(args.id_registry, args.pre_universe_fasta)
    found_proteins = load_original_hits(args.original_counts)
    rows = compute_match_stats(args.metadata, args.msa_root, found_proteins, registry)

    with Path(args.output).open("w", newline="") as out:
        writer = csv.DictWriter(
            out,
            fieldnames=[
                "sample",
                "tool",
                "universe_sha256",
                "db",
                "match_percentage",
                "matched",
                "total",
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
