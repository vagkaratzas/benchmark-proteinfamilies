#!/usr/bin/env python3
"""Count family membership in one curated database, emitting `id<TAB>num_proteins`.

One script serves all four databases; `--db_type` selects the rules. The counts drive the
`min_membership` filter, so a miscount silently changes which families are eligible for sampling.
"""

import argparse
import os
from pathlib import Path

from Bio import AlignIO


# Each database names its family after the file, but not by the same rule.
#
# NCBIFAM is the exception that will bite you: its files are `TIGR00001.SEED` *and*
# `NF000001.1.SEED`, so `splitext` on the latter yields `NF000001.1` -- a family id that matches
# nothing. Splitting on the first `.` gives `NF000001`, which is correct for both forms. The other
# three databases have no dots in their accessions, so `splitext` is right for them.
# tests/test_extract_db_metadata.py pins this.
DB_RULES = {
    "hamap": {
        "extension": ".msa",
        "id_from_name": lambda filename: os.path.splitext(filename)[0],
    },
    "ncbifam": {
        "extension": ".SEED",
        "id_from_name": lambda filename: filename.split(".")[0],
    },
    "panther": {
        "extension": ".fasta",
        "id_from_name": lambda filename: os.path.splitext(filename)[0],
    },
    "pfam": {
        "extension": ".sto",
        "id_from_name": lambda filename: os.path.splitext(filename)[0],
    },
}


def sniff_alignment_format(path):
    with Path(path).open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith("# STOCKHOLM"):
                return "stockholm"
            if line.startswith(">"):
                return "fasta"
            break
    raise ValueError(f"Unrecognized format in file: {path}")


def count_fasta_records(path):
    count = 0
    with Path(path).open() as handle:
        for line in handle:
            if line.startswith(">"):
                count += 1
    return count


def count_stockholm_records(path):
    alignment = AlignIO.read(path, "stockholm")
    return len(alignment)


def count_sequences(path):
    alignment_format = sniff_alignment_format(path)
    if alignment_format == "stockholm":
        return count_stockholm_records(path)
    return count_fasta_records(path)


def write_metadata(input_folder, output_file, db_type):
    rule = DB_RULES[db_type]
    extension = rule["extension"]
    id_from_name = rule["id_from_name"]

    with Path(output_file).open("w") as out:
        out.write("id\tnum_proteins\n")
        for filename in sorted(os.listdir(input_folder)):
            if not filename.endswith(extension):
                continue
            file_path = Path(input_folder) / filename
            try:
                family_id = id_from_name(filename)
                out.write(f"{family_id}\t{count_sequences(file_path)}\n")
            except Exception as exc:
                print(f"Skipping {filename}: {exc}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate metadata TSV from supported protein family database files."
    )
    parser.add_argument(
        "--db_type",
        required=True,
        choices=sorted(DB_RULES),
        help="Database type that controls file extension and family ID parsing.",
    )
    parser.add_argument("input_folder", help="Path to the database alignment folder")
    parser.add_argument("output_file", help="Path to the output metadata TSV")
    return parser.parse_args()


def main():
    args = parse_args()
    write_metadata(args.input_folder, args.output_file, args.db_type)


if __name__ == "__main__":
    main()
