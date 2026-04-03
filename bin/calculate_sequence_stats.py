#!/usr/bin/env python3

import os
import gzip
import argparse
from collections import defaultdict
from Bio import SeqIO
from Bio import AlignIO


def load_fasta_names(fasta_path):
    names = set()
    with (
        gzip.open(fasta_path, "rt") if fasta_path.endswith(".gz") else open(fasta_path)
    ) as handle:
        for record in SeqIO.parse(handle, "fasta"):
            names.add(record.id.split("/", 1)[0])
    return names


def parse_alignment_folder(folder_path, original_set, decoy_set, file_type):
    original_count = defaultdict(int)
    decoy_count = defaultdict(int)
    unknown_proteins = set()

    for name in original_set:
        original_count[name] = 0
    for name in decoy_set:
        decoy_count[name] = 0

    for file in os.listdir(folder_path):
        if not file.endswith(f".{file_type}"):
            continue

        filepath = os.path.join(folder_path, file)

        if file_type == "sto":
            try:
                alignment = AlignIO.read(filepath, "stockholm")
                for record in alignment:
                    cleaned_name = record.id.split("/", 1)[0]
                    if cleaned_name in original_count:
                        original_count[cleaned_name] += 1
                    elif cleaned_name in decoy_count:
                        decoy_count[cleaned_name] += 1
                    else:
                        unknown_proteins.add(cleaned_name)
            except Exception as e:
                print(f"Warning: Failed to parse {filepath} as Stockholm. Error: {e}")

        elif file_type in ("aln", "fas.gz"):
            open_func = gzip.open if file_type == "fas.gz" else open
            mode = "rt" if file_type == "fas.gz" else "r"
            try:
                with open_func(filepath, mode) as handle:
                    for record in SeqIO.parse(handle, "fasta"):
                        cleaned_name = record.id.split("/", 1)[0]
                        if cleaned_name in original_count:
                            original_count[cleaned_name] += 1
                        elif cleaned_name in decoy_count:
                            decoy_count[cleaned_name] += 1
                        else:
                            unknown_proteins.add(cleaned_name)
            except Exception as e:
                print(f"Warning: Failed to parse {filepath}. Error: {e}")

    return original_count, decoy_count, unknown_proteins


def write_counts_file(counts_dict, output_path, label):
    sorted_counts = sorted(counts_dict.items(), key=lambda x: -x[1])
    with open(output_path, "w") as f:
        f.write(f"{label} Proteins (sorted by count):\n")
        for name, count in sorted_counts:
            f.write(f"{name}\t{count}\n")


def write_summary(original_count, decoy_count, unknown_proteins, summary_file):
    unique_original_found = sum(1 for count in original_count.values() if count > 0)
    unique_decoy_found = sum(1 for count in decoy_count.values() if count > 0)
    total_original_matches = sum(original_count.values())
    total_decoy_matches = sum(decoy_count.values())
    total_unknowns = len(unknown_proteins)

    summary = (
        f"Total original matches in alignment files: {total_original_matches}\n"
        f"Total decoy matches in alignment files: {total_decoy_matches}\n"
        f"Total unknown sequences in alignment files: {total_unknowns}\n\n"
        f"Unique original proteins found: {unique_original_found} / {len(original_count)}\n"
        f"Unique decoy proteins found: {unique_decoy_found} / {len(decoy_count)}\n"
    )

    print(summary)
    with open(summary_file, "w") as f:
        f.write(summary)


def main():
    parser = argparse.ArgumentParser(
        description="Parse alignment files and count matches for original and decoy proteins."
    )
    parser.add_argument("--original_fasta", help="Path to the original FASTA file")
    parser.add_argument("--decoy_fasta", help="Path to the decoy FASTA file")
    parser.add_argument("--alignment_folder", help="Folder containing alignment files")
    parser.add_argument(
        "--alignment_type",
        choices=["sto", "aln", "fas.gz"],
        help="Type of alignment files: 'sto', 'aln', or 'fas.gz'",
    )

    args = parser.parse_args()

    prefix = f"{args.alignment_type}_"

    print("Loading original FASTA...")
    original_set = load_fasta_names(args.original_fasta)
    print(f"Loaded {len(original_set)} unique original proteins.")

    print("Loading decoy FASTA...")
    decoy_set = load_fasta_names(args.decoy_fasta)
    print(f"Loaded {len(decoy_set)} unique decoy proteins.")

    print(f"Parsing .{args.alignment_type} files...")
    original_count, decoy_count, unknown_proteins = parse_alignment_folder(
        args.alignment_folder, original_set, decoy_set, args.alignment_type
    )

    print("Writing output files...")
    write_counts_file(original_count, f"{prefix}original_counts.txt", "Original")
    write_counts_file(decoy_count, f"{prefix}decoy_counts.txt", "Decoy")
    write_summary(original_count, decoy_count, unknown_proteins, f"{prefix}summary.txt")

    unknown_file = f"{prefix}unknown_sequences.txt"
    with open(unknown_file, "w") as f:
        for name in sorted(unknown_proteins):
            f.write(f"{name}\n")

    print(f"Found {len(unknown_proteins)} unknown sequences. Written to {unknown_file}")
    print("Done.")


if __name__ == "__main__":
    main()
