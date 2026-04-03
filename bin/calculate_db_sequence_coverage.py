#!/usr/bin/env python3

import os
import csv
import argparse
from Bio import SeqIO


def load_metadata(metadata_file):
    db_to_ids = {"pfam": set(), "hamap": set(), "panther": set(), "ncbifam": set()}
    with open(metadata_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            db = row["db"].strip().lower()
            dbkey = row["dbkey"].strip().split("/", 1)[0]
            if db in db_to_ids:
                db_to_ids[db].add(dbkey)
    return db_to_ids


def load_original_hits(original_counts_file):
    found_proteins = set()
    with open(original_counts_file, "r") as f:
        for line in f:
            if line.strip() and not line.startswith("Original"):
                parts = line.strip().split("\t")
                if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) > 0:
                    found_proteins.add(parts[0])
    return found_proteins


def extract_protein_ids_from_alignment(file_path):
    protein_ids = set()
    try:
        for record in SeqIO.parse(file_path, "fasta"):
            cleaned_name = record.id.split("/", 1)[0]
            protein_ids.add(cleaned_name)
    except Exception as e:
        print(f"Warning: Couldn't parse {file_path}: {e}")
    return protein_ids


def compute_match_stats(db_to_ids, msa_paths, found_proteins, output_file):
    with open(output_file, "w") as out:
        out.write("db\tmatch_percentage\tmatched\ttotal\n")
        for db, ids in db_to_ids.items():
            msa_folder = msa_paths[db]
            total_unique = set()
            for family_id in ids:
                for filename in os.listdir(msa_folder):
                    if filename.startswith(family_id):
                        full_path = os.path.join(msa_folder, filename)
                        protein_ids = extract_protein_ids_from_alignment(full_path)
                        total_unique.update(protein_ids)
                        break  # only take the first match
            if not total_unique:
                print(f"{db.upper()}: No alignments found.")
                continue

            matched = total_unique.intersection(found_proteins)
            matched_count = len(matched)
            total_count = len(total_unique)
            percentage = (matched_count / total_count) * 100 if total_count else 0
            out.write(f"{db}\t{percentage:.1f}\t{matched_count}\t{total_count}\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute MSA match statistics from metadata and original hit counts."
    )
    parser.add_argument(
        "--metadata", required=True, help="Path to the metadata CSV file"
    )
    parser.add_argument(
        "--original_counts", required=True, help="Path to the original counts file"
    )
    parser.add_argument(
        "--msa_root",
        required=True,
        help="Root directory containing pfam, panther, hamap, ncbifam subfolders",
    )
    parser.add_argument(
        "--output", required=True, help="Output file path to write results"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    msa_paths = {
        "pfam": os.path.join(args.msa_root, "pfam"),
        "panther": os.path.join(args.msa_root, "panther"),
        "ncbifam": os.path.join(args.msa_root, "ncbifam"),
        "hamap": os.path.join(args.msa_root, "hamap"),
    }

    print("Loading metadata...")
    db_to_ids = load_metadata(args.metadata)

    print("Loading original hits...")
    found_proteins = load_original_hits(args.original_counts)

    print("Computing match statistics...")
    compute_match_stats(db_to_ids, msa_paths, found_proteins, args.output)
    print(f"Results written to: {args.output}")


if __name__ == "__main__":
    main()
