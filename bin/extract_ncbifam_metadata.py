#!/usr/bin/env python3

import argparse
import os
from Bio import AlignIO, SeqIO


def count_sequences(path):
    with open(path) as f:
        first_line = f.readline()
        f.seek(0)
        if first_line.startswith("# STOCKHOLM"):
            alignment = AlignIO.read(f, "stockholm")
            return len(alignment)
        elif first_line.startswith(">"):
            records = list(SeqIO.parse(f, "fasta"))
            return len(records)
        else:
            raise ValueError(f"Unrecognized format in file: {path}")


def write_metadata(folder, output):
    with open(output, "w") as out:
        out.write("id\tnum_proteins\n")
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(".SEED"):
                continue
            file_path = os.path.join(folder, fname)
            try:
                fam_id = fname.split(".")[0]
                num = count_sequences(file_path)
                out.write(f"{fam_id}\t{num}\n")
            except Exception as e:
                print(f"Skipping {fname}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract metadata from SEED alignment files"
    )
    parser.add_argument("folder", help="Folder containing SEED files")
    parser.add_argument("output", help="Path to output TSV file")
    args = parser.parse_args()

    write_metadata(args.folder, args.output)
