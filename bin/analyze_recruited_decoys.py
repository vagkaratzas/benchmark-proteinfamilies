#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path

from benchmark_ids import load_registry, resolve
from post_common import (
    discover_alignment_files,
    iter_alignment_records,
    strip_known_extension,
    verify_universe_checksum,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Count registry-labelled decoy sequences in MSAs and output stats."
    )
    parser.add_argument(
        "--msa_folder",
        required=True,
        help="Folder containing MSA files.",
    )
    parser.add_argument("--id_registry", required=True)
    parser.add_argument("--pre_universe_fasta", required=True)
    parser.add_argument("--pre_universe_sha256", required=True)
    parser.add_argument("--output_csv", required=True, help="Output CSV filename.")
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    return parser.parse_args()


def process_msa_file(msa_path, registry):
    total_sequences = 0
    decoy_sequences = 0
    unmapped = 0
    ambiguous = 0

    for record in iter_alignment_records(msa_path):
        total_sequences += 1
        resolution = resolve(record.id, registry, str(record.seq))
        if resolution.status == "resolved" and resolution.universe_id is not None:
            if registry.rows[resolution.universe_id].get("source_type") == "decoy":
                decoy_sequences += 1
        elif resolution.status == "ambiguous":
            ambiguous += 1
        else:
            unmapped += 1

    percentage = (decoy_sequences / total_sequences * 100) if total_sequences else 0
    return {
        "family": strip_known_extension(msa_path.name),
        "decoy_count": decoy_sequences,
        "total_sequences": total_sequences,
        "decoy_percentage": percentage,
        "unmapped_count": unmapped,
        "ambiguous_count": ambiguous,
    }


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    registry = load_registry(args.id_registry, args.pre_universe_fasta)

    results = []
    for msa_file in discover_alignment_files(args.msa_folder):
        results.append(process_msa_file(msa_file, registry))

    results.sort(key=lambda row: row["decoy_percentage"], reverse=True)

    with Path(args.output_csv).open("w", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "sample",
                "tool",
                "universe_sha256",
                "family",
                "decoy_count",
                "total_sequences",
                "decoy_percentage",
                "unmapped_count",
                "ambiguous_count",
            ],
        )
        writer.writeheader()
        for row in results:
            row["sample"] = args.sample
            row["tool"] = args.tool
            row["universe_sha256"] = universe_sha256
            writer.writerow(row)


if __name__ == "__main__":
    main()
