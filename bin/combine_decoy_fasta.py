#!/usr/bin/env python3

import argparse
from Bio import SeqIO


def parse_args():
    parser = argparse.ArgumentParser(
        description="Combine two FASTA files, removing duplicates."
    )
    parser.add_argument(
        "--families_fasta", type=str, help="Path to the families FASTA file."
    )
    parser.add_argument(
        "--decoys_fasta", type=str, help="Path to the decoys FASTA file."
    )
    parser.add_argument(
        "--combined_fasta", type=str, help="Path to the output combined FASTA file."
    )
    parser.add_argument(
        "--log_file",
        type=str,
        default="decoy_log.txt",
        help="Path to the log file (default: log.txt).",
    )
    return parser.parse_args()


def combine_fastas(families_fasta, decoys_fasta, combined_fasta, log_file):
    # Initialize a set to track unique sequences and a dictionary for sequence names
    unique_sequences = {}
    duplicate_names = set()
    duplicate_sequences = set()

    # Function to process a FASTA file and add unique sequences
    def process_fasta(file_path):
        for record in SeqIO.parse(file_path, "fasta"):
            seq = str(record.seq)
            name = record.id

            # Check for duplicate by name
            if name in unique_sequences:
                duplicate_names.add(name)
            # Check for duplicates by sequence, since some 100% identical sequences might not be identified by diamond/blastp (because results are capped at 25 entries per query sequence)
            elif seq in unique_sequences.values():
                duplicate_sequences.add(seq)
            else:
                unique_sequences[name] = seq

    # Process both FASTA files
    process_fasta(families_fasta)
    process_fasta(decoys_fasta)

    # Write the combined unique sequences to the output file
    with open(combined_fasta, "w") as out_fasta:
        for name, seq in unique_sequences.items():
            out_fasta.write(f">{name}\n{seq}\n")

    # Log the duplicates to the log file
    with open(log_file, "w") as log:
        if duplicate_names:
            log.write("Duplicate names found:\n")
            for name in duplicate_names:
                log.write(f"{name}\n")

        if duplicate_sequences:
            log.write("Duplicate sequences found:\n")
            for seq in duplicate_sequences:
                log.write(f"{seq}\n")


if __name__ == "__main__":
    args = parse_args()
    combine_fastas(
        args.families_fasta, args.decoys_fasta, args.combined_fasta, args.log_file
    )
    print(f"Combined FASTA written to: {args.combined_fasta}")
    print(f"Log written to: {args.log_file}")
