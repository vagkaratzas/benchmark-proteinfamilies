#!/usr/bin/env python3
"""Compute one EXPLORATORY scorecard per benchmark run.

Components are all keyed on universe_id:

mean_f1: mean best F1 over matched originals. Denominator is the number of
matched original families with at least one non-empty generated intersection.
family_coverage: matched original families / total original families.
sequence_coverage: recovered original universe_ids / total original universe_ids.
1 - decoy_recruitment_rate: decoy_recruitment_rate is unique recruited decoy
universe_ids / unique generated universe_ids.
1 - split_merge_rate: split_merge_rate is (n_splits + n_merges) divided by
n_one_to_one + n_splits + n_merges + n_vanished + n_spurious.

parent_id coverage is emitted as auxiliary QC only. It is not a component and
does not affect the composite or ranking.
"""

import argparse
import csv
import json
from pathlib import Path

from benchmark_ids import load_registry
from post_common import (
    discover_alignment_files,
    family_files_from_metadata,
    resolve_records,
    strip_known_extension,
    verify_universe_checksum,
)


COMPONENTS = [
    "mean_f1",
    "family_coverage",
    "sequence_coverage",
    "no_decoy_recruitment",
    "no_split_merge",
]

FIELDNAMES = [
    "sample",
    "tool",
    "universe_sha256",
    "composite_exploratory",
    "mean_f1",
    "mean_f1_matched_originals",
    "family_coverage",
    "family_coverage_matched_originals",
    "family_coverage_total_originals",
    "sequence_coverage",
    "sequence_coverage_recovered_universe_ids",
    "sequence_coverage_total_original_universe_ids",
    "no_decoy_recruitment",
    "decoy_recruitment_rate",
    "decoy_recruitment_unique_decoy_ids",
    "decoy_recruitment_total_generated_universe_ids",
    "no_split_merge",
    "split_merge_rate",
    "split_merge_events",
    "split_merge_denominator",
    "parent_id_coverage_aux",
    "parent_id_coverage_recovered_parent_ids",
    "parent_id_coverage_total_parent_ids",
    "scorecard_weights",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute an exploratory scorecard for one POST run."
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
    parser.add_argument("--family_metrics", required=True)
    parser.add_argument("--split_merge_summary", required=True)
    parser.add_argument("--output_file", required=True)
    parser.add_argument("--mqc_csv", default="scorecard_mqc.csv")
    parser.add_argument("--weights", default="")
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    return parser.parse_args()


def generated_files(args):
    if args.use_case_files:
        return [Path(path) for path in args.use_case_files]
    return discover_alignment_files(args.use_case_dir)


def read_table(path, delimiter="\t"):
    with Path(path).open(newline="") as handle:
        return list(
            csv.DictReader(
                (line for line in handle if not line.startswith("#")),
                delimiter=delimiter,
            )
        )


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


def load_generated_members(files, registry):
    members = set()
    for path in files:
        resolved, _frags, unmapped, ambiguous, _n_raw = resolve_records(
            path,
            registry,
            f"use_case:{strip_known_extension(path.name)}",
        )
        if unmapped or ambiguous:
            print(
                f"Warning: unresolved generated IDs in {path}: "
                f"{len(unmapped)} unmapped, {len(ambiguous)} ambiguous"
            )
        members.update(resolved)
    return members


def parent_ids(universe_ids, registry):
    parents = set()
    for universe_id in universe_ids:
        parent_id = registry.rows[universe_id].get("parent_id") or universe_id
        if parent_id == "-":
            parent_id = universe_id
        parents.add(parent_id)
    return parents


def parse_weights(raw_weights):
    if raw_weights is None:
        raw_weights = ""
    text = str(raw_weights).strip()
    if not text or text.lower() in {"null", "none"}:
        return {component: 1.0 for component in COMPONENTS}

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if parsed is None:
        parsed = {}
        text = text.strip("[]{}")
        for item in text.split(","):
            if not item.strip():
                continue
            if "=" in item:
                key, value = item.split("=", 1)
            elif ":" in item:
                key, value = item.split(":", 1)
            else:
                raise ValueError(f"Invalid scorecard weight item: {item}")
            parsed[key.strip().strip("\"'")] = float(value)

    weights = {component: 0.0 for component in COMPONENTS}
    for component, value in parsed.items():
        if component not in weights:
            raise ValueError(f"Unknown scorecard component weight: {component}")
        weights[component] = float(value)
    if sum(weights.values()) <= 0:
        raise ValueError("scorecard_weights must sum to a positive value")
    return weights


def best_f1_by_original(metric_rows):
    best = {}
    for row in metric_rows:
        key = (row["db_layer"], row["original_family"])
        best[key] = max(best.get(key, 0.0), float(row["f1"]))
    return best


def split_merge_rate(split_summary):
    n_splits = int(split_summary.get("n_splits", 0))
    n_merges = int(split_summary.get("n_merges", 0))
    n_one_to_one = int(split_summary.get("n_one_to_one", 0))
    n_vanished = int(split_summary.get("n_vanished", 0))
    n_spurious = int(split_summary.get("n_spurious", 0))
    events = n_splits + n_merges
    denominator = n_one_to_one + n_splits + n_merges + n_vanished + n_spurious
    rate = events / denominator if denominator else 0.0
    return min(rate, 1.0), events, denominator


def format_weights(weights):
    return ";".join(f"{component}={weights[component]:.6g}" for component in COMPONENTS)


def scorecard_row(args, universe_sha256, registry):
    metric_rows = read_table(args.family_metrics)
    split_rows = read_table(args.split_merge_summary)
    split_summary = split_rows[0] if split_rows else {}
    originals = load_original_families(args.original_base_dir, args.metadata, registry)
    generated_members = load_generated_members(generated_files(args), registry)

    original_keys = {(row["db_layer"], row["family"]) for row in originals}
    original_members = set()
    for original in originals:
        original_members.update(original["members"])

    recovered_original_members = original_members & generated_members
    best_f1 = best_f1_by_original(metric_rows)
    matched_originals = set(best_f1)

    mean_f1 = sum(best_f1.values()) / len(best_f1) if best_f1 else 0.0
    family_coverage = (
        len(matched_originals) / len(original_keys) if original_keys else 0.0
    )
    sequence_coverage = (
        len(recovered_original_members) / len(original_members)
        if original_members
        else 0.0
    )

    generated_decoys = {
        universe_id
        for universe_id in generated_members
        if registry.rows[universe_id].get("source_type") == "decoy"
    }
    decoy_recruitment_rate = (
        len(generated_decoys) / len(generated_members) if generated_members else 0.0
    )
    no_decoy_recruitment = 1.0 - decoy_recruitment_rate

    sm_rate, sm_events, sm_denominator = split_merge_rate(split_summary)
    no_split_merge = 1.0 - sm_rate

    original_parents = parent_ids(original_members, registry)
    recovered_parents = parent_ids(recovered_original_members, registry)
    parent_id_coverage_aux = (
        len(recovered_parents) / len(original_parents) if original_parents else 0.0
    )

    components = {
        "mean_f1": mean_f1,
        "family_coverage": family_coverage,
        "sequence_coverage": sequence_coverage,
        "no_decoy_recruitment": no_decoy_recruitment,
        "no_split_merge": no_split_merge,
    }
    weights = parse_weights(args.weights)
    weight_sum = sum(weights.values())
    composite = (
        sum(components[component] * weights[component] for component in COMPONENTS)
        / weight_sum
    )

    return {
        "sample": args.sample,
        "tool": args.tool,
        "universe_sha256": universe_sha256,
        "composite_exploratory": f"{composite:.6f}",
        "mean_f1": f"{mean_f1:.6f}",
        "mean_f1_matched_originals": len(best_f1),
        "family_coverage": f"{family_coverage:.6f}",
        "family_coverage_matched_originals": len(matched_originals),
        "family_coverage_total_originals": len(original_keys),
        "sequence_coverage": f"{sequence_coverage:.6f}",
        "sequence_coverage_recovered_universe_ids": (len(recovered_original_members)),
        "sequence_coverage_total_original_universe_ids": len(original_members),
        "no_decoy_recruitment": f"{no_decoy_recruitment:.6f}",
        "decoy_recruitment_rate": f"{decoy_recruitment_rate:.6f}",
        "decoy_recruitment_unique_decoy_ids": len(generated_decoys),
        "decoy_recruitment_total_generated_universe_ids": len(generated_members),
        "no_split_merge": f"{no_split_merge:.6f}",
        "split_merge_rate": f"{sm_rate:.6f}",
        "split_merge_events": sm_events,
        "split_merge_denominator": sm_denominator,
        "parent_id_coverage_aux": f"{parent_id_coverage_aux:.6f}",
        "parent_id_coverage_recovered_parent_ids": len(recovered_parents),
        "parent_id_coverage_total_parent_ids": len(original_parents),
        "scorecard_weights": format_weights(weights),
    }


def write_scorecard(path, row, include_comments):
    with Path(path).open("w", newline="") as handle:
        if include_comments:
            handle.write(
                "# EXPLORATORY composite: weights and association_threshold "
                "are not validated on real runs\n"
            )
            handle.write(
                "# denominators: mean_f1=matched_original_families; "
                "family_coverage=total_original_families; "
                "sequence_coverage=unique_original_universe_ids; "
                "decoy_recruitment_rate=unique_generated_universe_ids; "
                "split_merge_rate=n_one_to_one+n_splits+n_merges+"
                "n_vanished+n_spurious\n"
            )
            handle.write(
                "# parent_id_coverage_aux=unique_recovered_parent_ids/"
                "unique_original_parent_ids; not_a_scorecard_component=true\n"
            )
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, delimiter="\t")
        writer.writeheader()
        writer.writerow(row)


def write_mqc_csv(path, row):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerow(row)


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    registry = load_registry(args.id_registry, args.pre_universe_fasta)
    row = scorecard_row(args, universe_sha256, registry)
    write_scorecard(args.output_file, row, include_comments=True)
    write_mqc_csv(args.mqc_csv, row)


if __name__ == "__main__":
    main()
