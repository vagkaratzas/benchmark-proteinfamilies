#!/usr/bin/env python3
"""Per-family precision/recall/F1 metrics on resolved universe_id sets.

For every generated family G and original family O with |G intersect O| > 0,
this script reports:

precision = |G intersect O| / |G|, so precision_denom=|G|.
recall = |G intersect O| / |O|, so recall_denom=|O|.
f1 = harmonic mean of precision and recall, or 0 when tp == 0.
jaccard = |G intersect O| / |G union O|.

All sets are keyed on universe_id. parent_id is deliberately not used.
"""

import argparse
import csv
from pathlib import Path

from benchmark_ids import load_registry
from post_common import (
    discover_alignment_files,
    family_files_from_metadata,
    resolve_records,
    strip_known_extension,
    verify_universe_checksum,
)


FIELDNAMES = [
    "sample",
    "tool",
    "universe_sha256",
    "db_layer",
    "generated_family",
    "original_family",
    "tp",
    "fp",
    "fn",
    "precision",
    "recall",
    "f1",
    "jaccard",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calculate per-family metrics between generated MSAs and originals."
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--use_case_dir",
        help="Folder containing generated MSA/alignment files.",
    )
    input_group.add_argument(
        "--use_case_files",
        nargs="+",
        help="Explicit generated MSA/alignment files, in the supplied order.",
    )
    parser.add_argument("--original_base_dir", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--id_registry", required=True)
    parser.add_argument("--pre_universe_fasta", required=True)
    parser.add_argument("--pre_universe_sha256", required=True)
    parser.add_argument("--output_file", required=True)
    parser.add_argument("--mqc_csv", default="family_metrics_mqc.csv")
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    return parser.parse_args()


def generated_files(args):
    if args.use_case_files:
        return [Path(path) for path in args.use_case_files]
    return discover_alignment_files(args.use_case_dir)


def load_generated_families(files, registry):
    families = []
    for path in files:
        members, _frags, unmapped, ambiguous, _n_raw = resolve_records(
            path,
            registry,
            f"use_case:{strip_known_extension(path.name)}",
        )
        if unmapped or ambiguous:
            print(
                f"Warning: unresolved generated IDs in {path}: "
                f"{len(unmapped)} unmapped, {len(ambiguous)} ambiguous"
            )
        families.append(
            {
                "family": strip_known_extension(path.name),
                "members": members,
                "path": path,
            }
        )
    return families


def load_original_families(original_base_dir, metadata, registry):
    originals = []
    for db_layer, family, path, _row in family_files_from_metadata(
        original_base_dir, metadata
    ):
        members, _frags, unmapped, ambiguous, _n_raw = resolve_records(
            path,
            registry,
            f"original:{db_layer}/{family}",
            fail_on_unresolved=True,
        )
        if unmapped or ambiguous:
            raise ValueError(f"Unresolved original IDs in {path}")
        originals.append(
            {
                "db_layer": db_layer,
                "family": family,
                "members": members,
                "path": path,
            }
        )
    return originals


def metric_row(sample, tool, universe_sha256, generated, original):
    generated_members = generated["members"]
    original_members = original["members"]
    tp = len(generated_members & original_members)
    if tp == 0:
        return None
    fp = len(generated_members) - tp
    fn = len(original_members) - tp
    precision = tp / len(generated_members) if generated_members else 0.0
    recall = tp / len(original_members) if original_members else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    union_size = len(generated_members | original_members)
    jaccard = tp / union_size if union_size else 0.0
    return {
        "sample": sample,
        "tool": tool,
        "universe_sha256": universe_sha256,
        "db_layer": original["db_layer"],
        "generated_family": generated["family"],
        "original_family": original["family"],
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": f"{precision:.6f}",
        "recall": f"{recall:.6f}",
        "f1": f"{f1:.6f}",
        "jaccard": f"{jaccard:.6f}",
    }


def write_metrics(path, rows, include_comments):
    with Path(path).open("w", newline="") as handle:
        if include_comments:
            handle.write("# metric_key=universe_id; parent_id_not_used=true\n")
            handle.write(
                "# precision_denom=|G|; recall_denom=|O|; "
                "f1=harmonic_mean(precision,recall); "
                "jaccard_denom=|G_union_O|\n"
            )
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_mqc_csv(path, rows):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    registry = load_registry(args.id_registry, args.pre_universe_fasta)
    generated = load_generated_families(generated_files(args), registry)
    originals = load_original_families(args.original_base_dir, args.metadata, registry)

    rows = []
    for generated_family in generated:
        for original_family in originals:
            row = metric_row(
                args.sample,
                args.tool,
                universe_sha256,
                generated_family,
                original_family,
            )
            if row is not None:
                rows.append(row)

    rows.sort(
        key=lambda row: (
            row["db_layer"],
            row["original_family"],
            row["generated_family"],
        )
    )
    write_metrics(args.output_file, rows, include_comments=True)
    write_mqc_csv(args.mqc_csv, rows)


if __name__ == "__main__":
    main()
