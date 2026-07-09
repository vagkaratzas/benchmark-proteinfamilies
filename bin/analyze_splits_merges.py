#!/usr/bin/env python3
"""Directional split/merge topology metrics on resolved universe_id sets.

Association rules:

recall(G,O) = |G intersect O| / |O|, so recall_denom=|O|.
precision(G,O) = |G intersect O| / |G|, so precision_denom=|G|.
An edge is considered only when |G intersect O| >= min_intersection_size.

Splits are counted within a db_layer: one O has >=2 generated G passing the
precision threshold, and every counted G adds at least one member of O beyond
the union of all other associated Gs.

Merges are counted within a db_layer: one G has >=2 originals O passing the
recall threshold, and every counted O adds at least one member of G beyond the
union of all other associated originals.

Both contribution checks compare against the union of all other associated
families, not against previous rows, making the result independent of input
file order. All sets are keyed on universe_id.
"""

import argparse
import csv
import itertools
from collections import defaultdict
from pathlib import Path

from benchmark_ids import load_registry
from post_common import (
    discover_alignment_files,
    family_files_from_metadata,
    resolve_records,
    strip_known_extension,
    verify_universe_checksum,
)


SUMMARY_FIELDS = [
    "sample",
    "tool",
    "universe_sha256",
    "association_threshold",
    "min_intersection_size",
    "original_overlap_jaccard_threshold",
    "n_splits",
    "n_merges",
    "n_one_to_one",
    "n_vanished",
    "n_spurious",
    "n_cross_db_matches",
    "n_merges_excl_overlapping_originals",
    "n_high_overlap_original_pairs",
]

OVERLAP_FIELDS = [
    "sample",
    "tool",
    "universe_sha256",
    "db_layer",
    "original_family_a",
    "original_family_b",
    "intersection_size",
    "union_size",
    "jaccard",
    "is_high_overlap",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze directional split/merge topology for generated families."
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
    parser.add_argument("--original_overlap_file", required=True)
    parser.add_argument("--mqc_csv", default="split_merge_summary_mqc.csv")
    parser.add_argument("--association_threshold", type=float, default=0.1)
    parser.add_argument("--min_intersection_size", type=int, default=3)
    parser.add_argument("--original_overlap_jaccard_threshold", type=float, default=0.5)
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


def build_edges(generated, originals, association_threshold, min_intersection_size):
    edges = []
    for g_family in generated:
        g_members = g_family["members"]
        for o_family in originals:
            o_members = o_family["members"]
            intersection = g_members & o_members
            if len(intersection) < min_intersection_size:
                continue
            precision = len(intersection) / len(g_members) if g_members else 0.0
            recall = len(intersection) / len(o_members) if o_members else 0.0
            split_association = precision >= association_threshold
            merge_association = recall >= association_threshold
            if not split_association and not merge_association:
                continue
            edges.append(
                {
                    "generated": g_family["family"],
                    "original": o_family["family"],
                    "db_layer": o_family["db_layer"],
                    "generated_members": g_members,
                    "original_members": o_members,
                    "intersection": intersection,
                    "precision": precision,
                    "recall": recall,
                    "split_association": split_association,
                    "merge_association": merge_association,
                }
            )
    return edges


def unique_split_contributors(edges):
    contributors = []
    for edge in edges:
        other_union = set()
        for other in edges:
            if other is edge:
                continue
            other_union.update(other["generated_members"] & edge["original_members"])
        contribution = edge["intersection"] - other_union
        if contribution:
            contributors.append(edge)
    return contributors


def unique_merge_contributors(edges):
    contributors = []
    for edge in edges:
        other_union = set()
        for other in edges:
            if other is edge:
                continue
            other_union.update(other["original_members"] & edge["generated_members"])
        contribution = edge["intersection"] - other_union
        if contribution:
            contributors.append(edge)
    return contributors


def original_overlap_rows(originals, sample, tool, universe_sha256, threshold):
    rows = []
    high_overlap_pairs = set()
    by_layer = defaultdict(list)
    for original in originals:
        by_layer[original["db_layer"]].append(original)

    for db_layer, layer_originals in by_layer.items():
        for left, right in itertools.combinations(layer_originals, 2):
            intersection_size = len(left["members"] & right["members"])
            union_size = len(left["members"] | right["members"])
            jaccard = intersection_size / union_size if union_size else 0.0
            is_high_overlap = jaccard >= threshold
            if is_high_overlap:
                high_overlap_pairs.add(
                    frozenset(
                        [
                            (db_layer, left["family"]),
                            (db_layer, right["family"]),
                        ]
                    )
                )
            rows.append(
                {
                    "sample": sample,
                    "tool": tool,
                    "universe_sha256": universe_sha256,
                    "db_layer": db_layer,
                    "original_family_a": left["family"],
                    "original_family_b": right["family"],
                    "intersection_size": intersection_size,
                    "union_size": union_size,
                    "jaccard": f"{jaccard:.6f}",
                    "is_high_overlap": str(is_high_overlap).lower(),
                }
            )
    return rows, high_overlap_pairs


def has_high_overlap(contributors, high_overlap_pairs):
    originals = [(edge["db_layer"], edge["original"]) for edge in contributors]
    for left, right in itertools.combinations(originals, 2):
        if frozenset([left, right]) in high_overlap_pairs:
            return True
    return False


def summarize(
    generated,
    originals,
    edges,
    high_overlap_pairs,
    association_threshold,
    min_intersection_size,
    original_overlap_jaccard_threshold,
    sample,
    tool,
    universe_sha256,
):
    all_associations = edges
    split_edges = [edge for edge in edges if edge["split_association"]]
    merge_edges = [edge for edge in edges if edge["merge_association"]]

    assoc_by_original = defaultdict(list)
    assoc_by_generated_layer = defaultdict(list)
    all_assoc_by_layer = defaultdict(list)
    generated_layers = defaultdict(set)

    for edge in all_associations:
        all_assoc_by_layer[edge["db_layer"]].append(edge)
        generated_layers[edge["generated"]].add(edge["db_layer"])

    for edge in split_edges:
        assoc_by_original[(edge["db_layer"], edge["original"])].append(edge)
    for edge in merge_edges:
        assoc_by_generated_layer[(edge["generated"], edge["db_layer"])].append(edge)

    n_splits = 0
    for original_key, candidate_edges in assoc_by_original.items():
        del original_key
        if len(candidate_edges) < 2:
            continue
        contributors = unique_split_contributors(candidate_edges)
        if len(contributors) >= 2:
            n_splits += 1

    n_merges = 0
    n_merges_excl_overlapping_originals = 0
    for generated_key, candidate_edges in assoc_by_generated_layer.items():
        del generated_key
        if len(candidate_edges) < 2:
            continue
        contributors = unique_merge_contributors(candidate_edges)
        if len(contributors) >= 2:
            n_merges += 1
            if not has_high_overlap(contributors, high_overlap_pairs):
                n_merges_excl_overlapping_originals += 1

    n_one_to_one = 0
    associated_originals = set()
    associated_generated = set()
    for db_layer, layer_edges in all_assoc_by_layer.items():
        original_degree = defaultdict(set)
        generated_degree = defaultdict(set)
        for edge in layer_edges:
            original_degree[edge["original"]].add(edge["generated"])
            generated_degree[edge["generated"]].add(edge["original"])
            associated_originals.add((db_layer, edge["original"]))
            associated_generated.add(edge["generated"])
        for edge in layer_edges:
            if (
                len(original_degree[edge["original"]]) == 1
                and len(generated_degree[edge["generated"]]) == 1
            ):
                n_one_to_one += 1

    original_keys = {
        (original["db_layer"], original["family"]) for original in originals
    }
    generated_keys = {generated_family["family"] for generated_family in generated}
    n_vanished = len(original_keys - associated_originals)
    n_spurious = len(generated_keys - associated_generated)
    n_cross_db_matches = sum(
        1 for edge in all_associations if len(generated_layers[edge["generated"]]) > 1
    )

    return {
        "sample": sample,
        "tool": tool,
        "universe_sha256": universe_sha256,
        "association_threshold": f"{association_threshold:.6f}",
        "min_intersection_size": min_intersection_size,
        "original_overlap_jaccard_threshold": (
            f"{original_overlap_jaccard_threshold:.6f}"
        ),
        "n_splits": n_splits,
        "n_merges": n_merges,
        "n_one_to_one": n_one_to_one,
        "n_vanished": n_vanished,
        "n_spurious": n_spurious,
        "n_cross_db_matches": n_cross_db_matches,
        "n_merges_excl_overlapping_originals": (n_merges_excl_overlapping_originals),
        "n_high_overlap_original_pairs": len(high_overlap_pairs),
    }


def write_summary(path, row, include_comments):
    with Path(path).open("w", newline="") as handle:
        if include_comments:
            handle.write("# metric_key=universe_id; parent_id_not_used=true\n")
            handle.write(
                "# precision_denom=|G| for split associations; "
                "recall_denom=|O| for merge associations; "
                "unique_contribution=member beyond union of all other "
                "associated families\n"
            )
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow(row)


def write_overlap(path, rows):
    with Path(path).open("w", newline="") as handle:
        handle.write(
            "# original_family_overlap_baseline=pairwise_jaccard_within_db_layer; "
            "metric_key=universe_id\n"
        )
        writer = csv.DictWriter(handle, fieldnames=OVERLAP_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_mqc_csv(path, row):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerow(row)


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    registry = load_registry(args.id_registry, args.pre_universe_fasta)
    generated = load_generated_families(generated_files(args), registry)
    originals = load_original_families(args.original_base_dir, args.metadata, registry)
    overlap_rows, high_overlap_pairs = original_overlap_rows(
        originals,
        args.sample,
        args.tool,
        universe_sha256,
        args.original_overlap_jaccard_threshold,
    )
    edges = build_edges(
        generated,
        originals,
        args.association_threshold,
        args.min_intersection_size,
    )
    summary = summarize(
        generated,
        originals,
        edges,
        high_overlap_pairs,
        args.association_threshold,
        args.min_intersection_size,
        args.original_overlap_jaccard_threshold,
        args.sample,
        args.tool,
        universe_sha256,
    )
    write_summary(args.output_file, summary, include_comments=True)
    write_overlap(args.original_overlap_file, overlap_rows)
    write_mqc_csv(args.mqc_csv, summary)


if __name__ == "__main__":
    main()
