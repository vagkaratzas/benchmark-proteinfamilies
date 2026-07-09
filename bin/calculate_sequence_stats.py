#!/usr/bin/env python3

import argparse
import csv
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from benchmark_ids import load_registry, resolve
from post_common import (
    discover_alignment_files,
    verify_universe_checksum,
    write_rejected,
    iter_alignment_records,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse alignment files and count original and decoy sequence matches."
    )
    parser.add_argument("--alignment_folder", required=True)
    parser.add_argument("--id_registry", required=True)
    parser.add_argument("--pre_universe_fasta", required=True)
    parser.add_argument("--pre_universe_sha256", required=True)
    parser.add_argument("--output_prefix", default="sequence")
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    parser.add_argument(
        "--num_workers",
        type=int,
        default=os.cpu_count() or 1,
        help="Number of worker processes for alignment parsing.",
    )
    return parser.parse_args()


_WORKER_REGISTRY = None


def init_worker(registry):
    global _WORKER_REGISTRY
    _WORKER_REGISTRY = registry


def process_alignment_file(path):
    original_count = defaultdict(int)
    decoy_count = defaultdict(int)
    unknown = []
    path = Path(path)

    for record in iter_alignment_records(path):
        resolution = resolve(record.id, _WORKER_REGISTRY, str(record.seq))
        if resolution.status != "resolved" or resolution.universe_id is None:
            unknown.append(
                {
                    "raw_id": record.id,
                    "candidates": ",".join(sorted(resolution.candidates)),
                    "reason": f"{path.name}:{resolution.status}",
                }
            )
            continue

        source_type = _WORKER_REGISTRY.rows[resolution.universe_id].get("source_type")
        if source_type == "family":
            original_count[resolution.universe_id] += 1
        elif source_type == "decoy":
            decoy_count[resolution.universe_id] += 1

    return original_count, decoy_count, unknown


def write_counts_file(path, counts, universe_sha256, sample, tool):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sample", "tool", "universe_sha256", "universe_id", "count"],
            delimiter="\t",
        )
        writer.writeheader()
        for universe_id, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        ):
            writer.writerow(
                {
                    "sample": sample,
                    "tool": tool,
                    "universe_sha256": universe_sha256,
                    "universe_id": universe_id,
                    "count": count,
                }
            )


def write_summary(
    path,
    original_count,
    decoy_count,
    unknown,
    universe_sha256,
    sample,
    tool,
):
    original_found = sum(1 for count in original_count.values() if count > 0)
    decoy_found = sum(1 for count in decoy_count.values() if count > 0)
    total_original_matches = sum(original_count.values())
    total_decoy_matches = sum(decoy_count.values())

    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "sample",
                "tool",
                "universe_sha256",
                "total_original_matches",
                "total_decoy_matches",
                "total_unknown_sequences",
                "unique_original_found",
                "unique_original_total",
                "unique_decoy_found",
                "unique_decoy_total",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "sample": sample,
                "tool": tool,
                "universe_sha256": universe_sha256,
                "total_original_matches": total_original_matches,
                "total_decoy_matches": total_decoy_matches,
                "total_unknown_sequences": len(unknown),
                "unique_original_found": original_found,
                "unique_original_total": len(original_count),
                "unique_decoy_found": decoy_found,
                "unique_decoy_total": len(decoy_count),
            }
        )


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    registry = load_registry(args.id_registry, args.pre_universe_fasta)

    original_count = defaultdict(int)
    decoy_count = defaultdict(int)
    for universe_id, row in registry.rows.items():
        if row.get("source_type") == "family":
            original_count[universe_id] = 0
        elif row.get("source_type") == "decoy":
            decoy_count[universe_id] = 0

    alignment_files = discover_alignment_files(args.alignment_folder)
    num_workers = max(1, args.num_workers)
    if num_workers == 1 or len(alignment_files) <= 1:
        init_worker(registry)
        worker_results = [process_alignment_file(path) for path in alignment_files]
    else:
        with ProcessPoolExecutor(
            max_workers=num_workers,
            initializer=init_worker,
            initargs=(registry,),
        ) as executor:
            worker_results = list(executor.map(process_alignment_file, alignment_files))

    unknown = []
    for original_delta, decoy_delta, file_unknown in worker_results:
        for universe_id, count in original_delta.items():
            original_count[universe_id] += count
        for universe_id, count in decoy_delta.items():
            decoy_count[universe_id] += count
        unknown.extend(file_unknown)

    prefix = args.output_prefix
    write_counts_file(
        f"{prefix}_original_counts.txt",
        original_count,
        universe_sha256,
        args.sample,
        args.tool,
    )
    write_counts_file(
        f"{prefix}_decoy_counts.txt",
        decoy_count,
        universe_sha256,
        args.sample,
        args.tool,
    )
    write_summary(
        f"{prefix}_summary.txt",
        original_count,
        decoy_count,
        unknown,
        universe_sha256,
        args.sample,
        args.tool,
    )
    write_rejected(f"{prefix}_unknown_sequences.txt", unknown)


if __name__ == "__main__":
    main()
