#!/usr/bin/env python3

import argparse
from pathlib import Path
from Bio import SeqIO


def parse_args():
    parser = argparse.ArgumentParser(
        description="Combine and deduplicate FASTA files by name and sequence."
    )
    parser.add_argument(
        "--input_folder", help="Folder with 4 subfolders containing .fasta files"
    )
    parser.add_argument("--output_file", help="Output FASTA file name")
    return parser.parse_args()


def collect_fasta_files(folder):
    return list(Path(folder).rglob("*.fasta"))


def main():
    args = parse_args()
    fasta_files = collect_fasta_files(args.input_folder)

    log_path = Path("log.txt")

    total_count = 0
    name_dups = 0
    seq_dups = 0

    seen_ids = dict()
    seen_seqs = dict()  # maps sequence string to (record.id, filename)
    final_records = []

    with open(log_path, "w") as log:
        log.write("📊 Deduplication Report\n")
        log.write("=======================\n")
        log.write(f"Total FASTA files found: {len(fasta_files)}\n")

        for fasta_file in fasta_files:
            for record in SeqIO.parse(fasta_file, "fasta"):
                total_count += 1
                seq_str = str(record.seq)

                if record.id in seen_ids:
                    name_dups += 1
                    original_file = seen_ids[record.id]
                    log.write(
                        f"⚠️  Duplicate name: {record.id} in {fasta_file.name} (same as name in {original_file})\n"
                    )
                    continue
                seen_ids[record.id] = fasta_file.name

                if seq_str in seen_seqs:
                    seq_dups += 1
                    original_id, original_file = seen_seqs[seq_str]
                    log.write(
                        f"⚠️  Duplicate sequence: {record.id} in {fasta_file.name} (same as {original_id} from {original_file})\n"
                    )
                else:
                    seen_seqs[seq_str] = (record.id, fasta_file.name)

                final_records.append(record)

        log.write("\nSummary:\n")
        log.write(f"Total sequences found: {total_count}\n")
        log.write(f"Duplicates by name (removed): {name_dups}\n")
        log.write(f"Duplicates by sequence (logged only): {seq_dups}\n")
        log.write(f"Unique sequences written: {len(final_records)}\n")
        log.write(f"\n✅ Final deduplicated FASTA written to: {args.output_file}\n")

    SeqIO.write(final_records, args.output_file, "fasta")


if __name__ == "__main__":
    main()
