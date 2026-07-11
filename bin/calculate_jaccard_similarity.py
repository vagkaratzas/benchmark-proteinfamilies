#!/usr/bin/env python3
"""Jaccard similarity between every generated family and every curated original.

Similarity is computed on resolved `universe_id` sets, so it measures membership overlap and is
blind to how a tool wrote its headers.

Jaccard is symmetric and one-to-one: it says how well two families pair up, but it cannot tell a
tool that split one curated family into five from one that merged five into one. That is what
analyze_splits_merges.py is for -- do not read this score as a topology metric.

Aborts if too many of the tool's IDs came back unmapped or ambiguous (`--max_unmapped_fraction`,
`--max_ambiguous_fraction`), because a low score caused by broken ID resolution looks exactly like
a low score caused by a bad tool.
"""

import argparse
import csv
import multiprocessing as mp
import os
import statistics
import sys
from pathlib import Path

from benchmark_ids import load_registry, resolve
from post_common import (
    discover_alignment_files,
    family_files_from_metadata,
    resolve_records,
    strip_known_extension,
    verify_universe_checksum,
    write_rejected,
)


LOW_COVERAGE_WARNING_FRACTION = 0.1


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calculate Jaccard similarity between use-case MSAs and original family FASTAs."
    )
    parser.add_argument(
        "--use_case_dir",
        required=True,
        help="Folder containing use-case MSA files.",
    )
    parser.add_argument(
        "--original_base_dir",
        required=True,
        help="Base folder containing original family FASTA files organized by database.",
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help="Sampled metadata CSV with at least db and dbkey columns.",
    )
    parser.add_argument(
        "--id_registry", required=True, help="PRE id_registry.tsv for ID resolution."
    )
    parser.add_argument(
        "--pre_universe_fasta",
        required=True,
        help="PRE combined_decoy.faa used to build the registry.",
    )
    parser.add_argument(
        "--pre_universe_sha256",
        required=True,
        help="PRE universe.sha256 checksum file.",
    )
    parser.add_argument(
        "--output_file",
        required=True,
        help="Output TSV file for the similarity results.",
    )
    parser.add_argument("--unmapped_file", default="unmapped.tsv")
    parser.add_argument("--ambiguous_file", default="ambiguous.tsv")
    parser.add_argument("--qc_file", default="jaccard_qc.tsv")
    parser.add_argument(
        "--cluster_file",
        default=None,
        help="Optional 2-column rep-to-member clustering TSV to include in ID observability artifacts.",
    )
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    parser.add_argument(
        "--similarity_threshold",
        type=float,
        default=0.5,
        help="Similarity threshold to filter matches (default: 0.5).",
    )
    parser.add_argument("--max_unmapped_fraction", type=float, default=0.05)
    parser.add_argument("--max_ambiguous_fraction", type=float, default=0.01)
    parser.add_argument("--min_universe_coverage", type=float, default=None)
    parser.add_argument(
        "--num_workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Number of worker processes for use-case family parsing.",
    )
    return parser.parse_args()


def jaccard_similarity(set1, set2):
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union) if union else 0.0


def load_original_families(original_base_dir, metadata, registry):
    originals = {}
    original_index = {}
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
        key = (db_layer, family)
        originals[key] = {
            "db_layer": db_layer,
            "family": family,
            "path": path,
            "members": members,
        }
        for universe_id in members:
            original_index.setdefault(universe_id, set()).add(key)
    return originals, original_index


_WORKER_REGISTRY = None
_WORKER_ORIGINALS = None
_WORKER_ORIGINAL_INDEX = None
_WORKER_THRESHOLD = None
_WORKER_SAMPLE = None
_WORKER_TOOL = None
_WORKER_UNIVERSE_SHA256 = None


def init_worker(
    registry,
    originals,
    original_index,
    similarity_threshold,
    sample,
    tool,
    universe_sha256,
):
    global _WORKER_REGISTRY
    global _WORKER_ORIGINALS
    global _WORKER_ORIGINAL_INDEX
    global _WORKER_THRESHOLD
    global _WORKER_SAMPLE
    global _WORKER_TOOL
    global _WORKER_UNIVERSE_SHA256

    _WORKER_REGISTRY = registry
    _WORKER_ORIGINALS = originals
    _WORKER_ORIGINAL_INDEX = original_index
    _WORKER_THRESHOLD = similarity_threshold
    _WORKER_SAMPLE = sample
    _WORKER_TOOL = tool
    _WORKER_UNIVERSE_SHA256 = universe_sha256


def candidate_original_keys(members, originals, original_index, similarity_threshold):
    if similarity_threshold <= 0:
        return set(originals)

    candidates = set()
    for universe_id in members:
        candidates.update(original_index.get(universe_id, set()))
    return candidates


def process_use_case_file(use_case_fasta):
    use_case_fasta = Path(use_case_fasta)
    use_case_basename = strip_known_extension(use_case_fasta.name)
    members, fragments, unmapped, ambiguous, n_raw = resolve_records(
        use_case_fasta,
        _WORKER_REGISTRY,
        f"use_case:{use_case_basename}",
    )

    rows = []
    for key in candidate_original_keys(
        members, _WORKER_ORIGINALS, _WORKER_ORIGINAL_INDEX, _WORKER_THRESHOLD
    ):
        original = _WORKER_ORIGINALS[key]
        similarity = jaccard_similarity(members, original["members"])
        if similarity >= _WORKER_THRESHOLD:
            rows.append(
                {
                    "sample": _WORKER_SAMPLE,
                    "tool": _WORKER_TOOL,
                    "universe_sha256": _WORKER_UNIVERSE_SHA256,
                    "use_case_basename": use_case_basename,
                    "original_basename": original["family"],
                    "similarity_score": f"{similarity:.3f}",
                    "use_case_layer": "use_case",
                    "db_layer": original["db_layer"],
                }
            )

    rows.sort(
        key=lambda row: (
            row["use_case_basename"],
            row["db_layer"],
            row["original_basename"],
            row["similarity_score"],
        )
    )
    return {
        "members": members,
        "fragments": fragments,
        "unmapped": unmapped,
        "ambiguous": ambiguous,
        "n_raw": n_raw,
        "rows": rows,
    }


def resolve_cluster_observations(cluster_file, registry):
    unmapped = []
    ambiguous = []
    if not cluster_file:
        return unmapped, ambiguous
    path = Path(cluster_file)
    if not path.exists() or path.stat().st_size == 0:
        return unmapped, ambiguous

    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            fields = line.rstrip("\n").split()
            for role, raw_id in zip(("cluster_rep", "cluster_member"), fields[:2]):
                resolution = resolve(raw_id, registry)
                if resolution.status == "resolved":
                    continue
                row = {
                    "raw_id": raw_id,
                    "candidates": ",".join(sorted(resolution.candidates)),
                    "reason": f"{role}:{resolution.status}",
                }
                if resolution.status == "ambiguous":
                    ambiguous.append(row)
                else:
                    unmapped.append(row)
    return unmapped, ambiguous


def write_qc(
    path,
    args,
    universe_sha256,
    registry,
    n_raw,
    members,
    fragments,
    unmapped,
    ambiguous,
):
    fragment_values = list(fragments.values())
    mean_fragments = statistics.mean(fragment_values) if fragment_values else 0
    median_fragments = statistics.median(fragment_values) if fragment_values else 0
    universe_size = len(registry.rows)
    universe_coverage = len(members) / universe_size if universe_size else 0.0
    unmapped_fraction = len(unmapped) / n_raw if n_raw else 0.0
    ambiguous_fraction = len(ambiguous) / n_raw if n_raw else 0.0

    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "sample",
                "tool",
                "universe_sha256",
                "membership_source",
                "n_raw_ids",
                "n_members_total",
                "universe_size",
                "universe_coverage",
                "unmapped_fraction",
                "ambiguous_fraction",
                "n_unmapped",
                "n_ambiguous",
                "mean_fragments",
                "median_fragments",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "sample": args.sample,
                "tool": args.tool,
                "universe_sha256": universe_sha256,
                "membership_source": "MSA",
                "n_raw_ids": n_raw,
                "n_members_total": len(members),
                "universe_size": universe_size,
                "universe_coverage": f"{universe_coverage:.6f}",
                "unmapped_fraction": f"{unmapped_fraction:.6f}",
                "ambiguous_fraction": f"{ambiguous_fraction:.6f}",
                "n_unmapped": len(unmapped),
                "n_ambiguous": len(ambiguous),
                "mean_fragments": f"{mean_fragments:.6f}",
                "median_fragments": f"{median_fragments:.6f}",
            }
        )

    return unmapped_fraction, ambiguous_fraction, universe_coverage


def warn_and_gate(args, unmapped_fraction, ambiguous_fraction, universe_coverage):
    # Fail the run rather than report. An unresolved ID does not raise on its own -- it just
    # quietly shrinks a set and drags the score toward zero, which is indistinguishable from a tool
    # that genuinely reconstructed nothing. These two gates are what turn that silence into an error.
    if unmapped_fraction > args.max_unmapped_fraction:
        raise SystemExit(
            f"unmapped_fraction {unmapped_fraction:.6f} exceeds "
            f"max_unmapped_fraction {args.max_unmapped_fraction:.6f}"
        )
    if ambiguous_fraction > args.max_ambiguous_fraction:
        raise SystemExit(
            f"ambiguous_fraction {ambiguous_fraction:.6f} exceeds "
            f"max_ambiguous_fraction {args.max_ambiguous_fraction:.6f}"
        )

    if unmapped_fraction:
        print(f"Warning: unmapped_fraction={unmapped_fraction:.6f}", file=sys.stderr)
    if ambiguous_fraction:
        print(f"Warning: ambiguous_fraction={ambiguous_fraction:.6f}", file=sys.stderr)
    if universe_coverage < LOW_COVERAGE_WARNING_FRACTION:
        print(
            f"Warning: universe_coverage={universe_coverage:.6f} is low; "
            "confirm msa_dir points at full-family MSAs, not seed MSAs",
            file=sys.stderr,
        )
    if (
        args.min_universe_coverage is not None
        and universe_coverage < args.min_universe_coverage
    ):
        raise SystemExit(
            f"universe_coverage {universe_coverage:.6f} is below "
            f"min_universe_coverage {args.min_universe_coverage:.6f}"
        )


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    registry = load_registry(args.id_registry, args.pre_universe_fasta)
    originals, original_index = load_original_families(
        args.original_base_dir, args.metadata, registry
    )

    all_members = set()
    all_fragments = {}
    all_unmapped = []
    all_ambiguous = []
    n_raw_total = 0
    use_case_files = discover_alignment_files(args.use_case_dir)
    num_workers = max(1, args.num_workers)

    worker_args = (
        registry,
        originals,
        original_index,
        args.similarity_threshold,
        args.sample,
        args.tool,
        universe_sha256,
    )

    if num_workers == 1 or len(use_case_files) <= 1:
        init_worker(*worker_args)
        use_case_results = [process_use_case_file(path) for path in use_case_files]
    else:
        with mp.Pool(
            processes=num_workers, initializer=init_worker, initargs=worker_args
        ) as pool:
            use_case_results = pool.map(process_use_case_file, use_case_files)

    output_rows = []
    for result in use_case_results:
        n_raw_total += result["n_raw"]
        all_members.update(result["members"])
        all_unmapped.extend(result["unmapped"])
        all_ambiguous.extend(result["ambiguous"])
        for universe_id, count in result["fragments"].items():
            all_fragments[universe_id] = max(all_fragments.get(universe_id, 0), count)
        output_rows.extend(result["rows"])

    output_rows.sort(
        key=lambda row: (
            row["use_case_basename"],
            row["db_layer"],
            row["original_basename"],
            row["similarity_score"],
        )
    )

    with open(args.output_file, "w", newline="") as out_f:
        writer = csv.DictWriter(
            out_f,
            fieldnames=[
                "sample",
                "tool",
                "universe_sha256",
                "use_case_basename",
                "original_basename",
                "similarity_score",
                "use_case_layer",
                "db_layer",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(output_rows)

    cluster_unmapped, cluster_ambiguous = resolve_cluster_observations(
        args.cluster_file, registry
    )
    write_rejected(args.unmapped_file, all_unmapped + cluster_unmapped)
    write_rejected(args.ambiguous_file, all_ambiguous + cluster_ambiguous)
    unmapped_fraction, ambiguous_fraction, universe_coverage = write_qc(
        args.qc_file,
        args,
        universe_sha256,
        registry,
        n_raw_total,
        all_members,
        all_fragments,
        all_unmapped,
        all_ambiguous,
    )
    warn_and_gate(args, unmapped_fraction, ambiguous_fraction, universe_coverage)


if __name__ == "__main__":
    main()
