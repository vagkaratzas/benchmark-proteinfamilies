#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path
from Bio import SeqIO, AlignIO
from Bio.SeqRecord import SeqRecord


def parse_args():
    parser = argparse.ArgumentParser(
        description="Process sampled metadata and resolve MSA file paths."
    )
    parser.add_argument(
        "--metadata_file", required=True, help="Path to the sampled_metadata.tsv file"
    )
    parser.add_argument("--hamap", required=True, help="Path to HAMAP alignment folder")
    parser.add_argument(
        "--ncbifam", required=True, help="Path to NCBIfam alignment folder"
    )
    parser.add_argument(
        "--panther", required=True, help="Path to Panther alignment folder"
    )
    parser.add_argument("--pfam", required=True, help="Path to Pfam alignment folder")
    parser.add_argument(
        "--output_folder", required=True, help="Path to store converted FASTA files"
    )
    parser.add_argument(
        "--updated_metadata_file",
        required=True,
        help="Path to output updated metadata file",
    )
    return parser.parse_args()


def get_db_path(db, paths):
    return paths.get(db.lower())


def find_matching_file(folder: Path, dbkey: str):
    for file in folder.iterdir():
        if file.is_file() and file.name.split(".")[0] == dbkey:
            return file
    return None


def detect_format(file_path: Path) -> str:
    with open(file_path, "r") as f:
        first_line = f.readline().strip()
        if first_line.startswith(">"):
            return "fasta"
        elif first_line.startswith("# STOCKHOLM"):
            return "stockholm"
        else:
            return "unknown"


def clean_sequence(seq: str) -> str:
    return "".join([aa for aa in seq if aa.isupper()])


def clean_id(seq_id: str) -> str:
    return seq_id.translate(
        str.maketrans(".|=", "___")
    )  # Replaces .|= with underscores


def convert_to_fasta(input_file: Path, fmt: str, output_file: Path):
    seen_ids = set()
    seen_seqs = set()
    records = []

    if fmt == "fasta":
        parsed = SeqIO.parse(input_file, "fasta")
    elif fmt == "stockholm":
        parsed = AlignIO.read(input_file, "stockholm")
    else:
        return 0

    for record in parsed:
        clean_seq = clean_sequence(str(record.seq))

        if record.id in seen_ids:
            continue  # Skip duplicate ID
        if clean_seq in seen_seqs:
            continue  # Skip duplicate sequence

        # Clean the sequence ID by replacing special characters with underscores
        cleaned_id = clean_id(record.id)

        seen_ids.add(record.id)
        seen_seqs.add(clean_seq)
        records.append(SeqRecord(seq=clean_seq, id=cleaned_id, description=""))

    if records:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as out_f:
            SeqIO.write(records, out_f, "fasta")

    return len(records)  # Return number of unique sequences


def main():
    args = parse_args()

    db_paths = {
        "hamap": Path(args.hamap),
        "ncbifam": Path(args.ncbifam),
        "panther": Path(args.panther),
        "pfam": Path(args.pfam),
    }

    output_base = Path(args.output_folder)
    updated_metadata = []

    with open(args.metadata_file, newline="") as tsvfile:
        reader = csv.DictReader(tsvfile, delimiter=",")
        for row in reader:
            db = row["db"].lower()
            dbkey = row["dbkey"]
            ipr_id = row["interpro_id"]
            base_path = get_db_path(db, db_paths)

            if base_path is None:
                print(f"[SKIPPED] Unknown DB type '{db}' for IPR {ipr_id}")
                continue

            matching_file = find_matching_file(base_path, dbkey)
            if not matching_file:
                print(f"[NOT FOUND] {dbkey} in {base_path}")
                continue

            fmt = detect_format(matching_file)
            if fmt == "unknown":
                print(f"[SKIPPED] Unknown format for file {matching_file}")
                continue

            output_file = output_base / db / f"{dbkey}.fasta"
            try:
                count = convert_to_fasta(matching_file, fmt, output_file)
                print(
                    f"[OK] Converted {dbkey} from {fmt.upper()} to {output_file} ({count} unique)"
                )
                row["protein_count"] = count  # Update the count
                updated_metadata.append(row)
            except Exception as e:
                print(f"[ERROR] Failed to convert {matching_file}: {e}")

    # Write updated metadata
    updated_path = Path(args.updated_metadata_file)
    with open(updated_path, "w", newline="") as out_meta:
        writer = csv.DictWriter(out_meta, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in updated_metadata:
            writer.writerow(row)
    print(f"[DONE] Updated metadata saved to {updated_path}")


if __name__ == "__main__":
    main()
