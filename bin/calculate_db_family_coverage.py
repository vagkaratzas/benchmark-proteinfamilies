#!/usr/bin/env python3

import argparse
import os
import glob
import csv


def parse_args():
    parser = argparse.ArgumentParser(
        description="Count hits of original families per database based on similarity results."
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
        "--output_file", required=True, help="Output CSV file for the summary report."
    )
    return parser.parse_args()


def extract_hit_families(similarity_results_path):
    """Extract unique original_basename entries from the similarity results."""
    hit_families = set()
    with open(similarity_results_path) as f:
        next(f)  # Skip header
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                hit_families.add(parts[1])
    return hit_families


def count_hits_per_database(original_base_dir, hit_families):
    """Count how many original family FASTA files are in the hit set per database."""
    db_layers = ["hamap", "ncbifam", "panther", "pfam"]
    hits_summary = {}

    for db in db_layers:
        db_path = os.path.join(original_base_dir, db)
        fasta_files = glob.glob(os.path.join(db_path, "*.fasta"))
        base_filenames = {os.path.splitext(os.path.basename(f))[0] for f in fasta_files}

        hits = len(base_filenames & hit_families)
        hits_summary[db.upper()] = hits  # Uppercase as in output example

    return hits_summary


def write_summary(output_file, hits_summary):
    """Write the summary to a CSV file."""
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["database", "hits"])
        for db, count in hits_summary.items():
            writer.writerow([db, count])


def main():
    args = parse_args()

    hit_families = extract_hit_families(args.similarity_results)
    hits_summary = count_hits_per_database(args.original_families_dir, hit_families)
    write_summary(args.output_file, hits_summary)


if __name__ == "__main__":
    main()
