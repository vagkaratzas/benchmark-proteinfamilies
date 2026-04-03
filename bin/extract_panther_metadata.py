#!/usr/bin/env python3

import os
import argparse


def count_proteins_in_msa(file_path):
    count = 0
    with open(file_path) as f:
        for line in f:
            if line.startswith(">"):
                count += 1
    return count


def generate_metadata(folder_path, output_tsv):
    with open(output_tsv, "w") as out:
        out.write("id\tnum_proteins\n")
        for filename in sorted(os.listdir(folder_path)):
            if filename.endswith(".fasta"):
                file_id = os.path.splitext(filename)[0]
                file_path = os.path.join(folder_path, filename)
                try:
                    num_proteins = count_proteins_in_msa(file_path)
                    out.write(f"{file_id}\t{num_proteins}\n")
                except Exception as e:
                    print(f"Error processing {filename}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate metadata TSV from PANTHER .fasta files."
    )
    parser.add_argument("input_folder", help="Path to folder containing .fasta files")
    parser.add_argument("output_file", help="Path to output metadata TSV file")
    args = parser.parse_args()

    generate_metadata(args.input_folder, args.output_file)


if __name__ == "__main__":
    main()
