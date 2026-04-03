#!/usr/bin/env python3

import os
import argparse
from Bio import AlignIO


def count_sequences_in_stockholm(file_path):
    alignment = AlignIO.read(file_path, "stockholm")
    return len(alignment)


def generate_metadata(folder_path, output_tsv):
    with open(output_tsv, "w") as out:
        out.write("id\tnum_proteins\n")
        for filename in sorted(os.listdir(folder_path)):
            if filename.endswith(".sto"):
                pfam_id = os.path.splitext(filename)[0]
                file_path = os.path.join(folder_path, filename)
                try:
                    num_proteins = count_sequences_in_stockholm(file_path)
                    out.write(f"{pfam_id}\t{num_proteins}\n")
                except Exception as e:
                    print(f"Error parsing {filename}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate metadata TSV from Stockholm files."
    )
    parser.add_argument("input_folder", help="Path to folder containing .sto files")
    parser.add_argument("output_file", help="Path to output metadata TSV file")

    args = parser.parse_args()

    generate_metadata(args.input_folder, args.output_file)


if __name__ == "__main__":
    main()
