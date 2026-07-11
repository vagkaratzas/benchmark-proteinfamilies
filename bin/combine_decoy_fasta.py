#!/usr/bin/env python3
"""Concatenate curated family sequences with the decoys to form the benchmark universe.

Emits the universe FASTA, the registry extended with decoy rows, and the sha256 that pins every
downstream result to this exact universe.

Deduplicates by name and by sequence: a decoy identical to a curated sequence would be scored as a
false positive when a tool correctly recruits it. Removals are logged rather than silently dropped.
"""

import argparse
import csv
import hashlib
import io
import re
from pathlib import Path

from Bio import SeqIO


REGISTRY_COLUMNS = [
    "universe_id",
    "parent_id",
    "source_type",
    "db_layer",
    "family",
    "coords",
    "ungapped_len",
    "seq_sha1",
]

COORD_PATTERNS = (
    re.compile(r"/(\d+)-(\d+)$"),
    re.compile(r"_(\d+)_(\d+)$"),
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Combine family and decoy FASTA files, removing duplicates."
    )
    parser.add_argument(
        "--families_fasta",
        type=str,
        required=True,
        help="Path to the families FASTA file.",
    )
    parser.add_argument(
        "--decoys_fasta", type=str, required=True, help="Path to the decoys FASTA file."
    )
    parser.add_argument(
        "--combined_fasta",
        type=str,
        required=True,
        help="Path to the output combined FASTA file.",
    )
    parser.add_argument(
        "--id_registry",
        type=str,
        required=True,
        help="Path to the family id_registry.tsv.",
    )
    parser.add_argument(
        "--output_registry",
        type=str,
        required=True,
        help="Path to the updated id_registry.tsv.",
    )
    parser.add_argument(
        "--universe_sha256", type=str, required=True, help="Path to universe.sha256."
    )
    parser.add_argument(
        "--log_file",
        type=str,
        default="combined_decoy_log.txt",
        help="Path to the log file.",
    )
    return parser.parse_args()


def clean_id(seq_id: str) -> str:
    return seq_id.translate(str.maketrans(".|=", "___"))


def ungap(seq: str) -> str:
    return "".join(
        char for char in str(seq) if char not in "-." and not char.islower()
    ).upper()


def sha1_of(seq: str) -> str:
    return hashlib.sha1(ungap(seq).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_parent_coords(universe_id: str):
    current = universe_id
    coords = []
    while True:
        for pattern in COORD_PATTERNS:
            match = pattern.search(current)
            if match:
                coords.append(f"{match.group(1)}-{match.group(2)}")
                current = pattern.sub("", current)
                break
        else:
            break
    return current, ",".join(reversed(coords)) if coords else "-"


def decoy_parent_id(cleaned_id: str) -> str:
    for prefix in ("sp", "tr"):
        marker = f"{prefix}_"
        if cleaned_id.startswith(marker):
            remainder = cleaned_id[len(marker) :]
            if "_" in remainder:
                return remainder.split("_", 1)[0]
    parent_id, _ = split_parent_coords(cleaned_id)
    return parent_id


def read_registry(path: Path):
    comments = []
    data_lines = []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            comments.append(line)
        elif line.strip():
            data_lines.append(line)

    rows = []
    if data_lines:
        rows = list(csv.DictReader(io.StringIO("\n".join(data_lines)), delimiter="\t"))
    return comments, rows


def write_registry(path: Path, comments, rows):
    with open(path, "w", newline="") as handle:
        for comment in comments:
            handle.write(f"{comment}\n")
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def decoy_registry_row(universe_id: str, seq: str):
    return {
        "universe_id": universe_id,
        "parent_id": decoy_parent_id(universe_id),
        "source_type": "decoy",
        "db_layer": "-",
        "family": "-",
        "coords": "-",
        "ungapped_len": str(len(ungap(seq))),
        "seq_sha1": sha1_of(seq),
    }


def combine_fastas(
    families_fasta,
    decoys_fasta,
    combined_fasta,
    id_registry,
    output_registry,
    universe_sha256,
    log_file,
):
    comments, registry_rows = read_registry(Path(id_registry))
    registry_by_id = {row["universe_id"]: row for row in registry_rows}

    unique_sequences = {}
    seq_to_name = {}
    seq_to_source = {}
    duplicate_family_names = []
    duplicate_decoy_names = []
    decoy_sequence_leaks = []
    duplicate_decoy_sequences = []
    decoy_rows = []
    decoy_parent_candidates = set()

    def add_family_record(name, seq):
        if name in unique_sequences:
            duplicate_family_names.append(name)
            return False

        unique_sequences[name] = seq
        seq_to_name.setdefault(seq, name)
        seq_to_source.setdefault(seq, "family")
        return True

    def add_decoy_record(name, seq):
        if name in unique_sequences:
            duplicate_decoy_names.append(name)
            return False
        if seq in seq_to_name:
            duplicate = (name, seq_to_name[seq])
            if seq_to_source[seq] == "family":
                decoy_sequence_leaks.append(duplicate)
            else:
                duplicate_decoy_sequences.append(duplicate)
            return False

        unique_sequences[name] = seq
        seq_to_name[seq] = name
        seq_to_source[seq] = "decoy"
        decoy_rows.append(decoy_registry_row(name, seq))
        return True

    for record in SeqIO.parse(families_fasta, "fasta"):
        add_family_record(record.id, ungap(str(record.seq)))

    missing_registry_ids = set(unique_sequences) - set(registry_by_id)
    if missing_registry_ids:
        missing = ", ".join(sorted(missing_registry_ids)[:20])
        raise ValueError(
            "Family FASTA contains universe_id values missing from id_registry.tsv: "
            f"{missing}"
        )

    kept_family_rows = [
        registry_by_id[universe_id]
        for universe_id in unique_sequences
        if universe_id in registry_by_id
        and registry_by_id[universe_id].get("source_type") == "family"
    ]
    family_parent_ids = {
        row["parent_id"]
        for row in kept_family_rows
        if row.get("parent_id") not in (None, "-", "")
    }

    for record in SeqIO.parse(decoys_fasta, "fasta"):
        name = clean_id(record.id)
        seq = ungap(str(record.seq))
        decoy_parent_candidates.add(decoy_parent_id(name))
        add_decoy_record(name, seq)

    parent_overlap = family_parent_ids & decoy_parent_candidates
    if parent_overlap:
        overlap = ", ".join(sorted(parent_overlap)[:20])
        raise ValueError(
            "Decoy parent_id overlaps family parent_id; refusing to build leaked universe. "
            f"Overlapping parent_id values: {overlap}"
        )

    combined_fasta = Path(combined_fasta)
    with open(combined_fasta, "w") as out_fasta:
        for name, seq in unique_sequences.items():
            out_fasta.write(f">{name}\n{seq}\n")

    write_registry(Path(output_registry), comments, kept_family_rows + decoy_rows)
    Path(universe_sha256).write_text(f"{sha256_file(combined_fasta)}\n")

    with open(log_file, "w") as log:
        if duplicate_family_names:
            log.write("Duplicate family names removed:\n")
            for name in duplicate_family_names:
                log.write(f"{name}\n")

        if duplicate_decoy_names:
            log.write("Duplicate decoy names removed:\n")
            for name in duplicate_decoy_names:
                log.write(f"{name}\n")

        if decoy_sequence_leaks:
            log.write(
                "Dropped decoy sequence identical to a family sequence (leakage):\n"
            )
            for name, original_name in decoy_sequence_leaks:
                log.write(f"{name}\tduplicate_of\t{original_name}\n")

        if duplicate_decoy_sequences:
            log.write("Duplicate decoy sequences removed:\n")
            for name, original_name in duplicate_decoy_sequences:
                log.write(f"{name}\tduplicate_of\t{original_name}\n")


if __name__ == "__main__":
    args = parse_args()
    combine_fastas(
        args.families_fasta,
        args.decoys_fasta,
        args.combined_fasta,
        args.id_registry,
        args.output_registry,
        args.universe_sha256,
        args.log_file,
    )
    print(f"Combined FASTA written to: {args.combined_fasta}")
    print(f"Registry written to: {args.output_registry}")
    print(f"Checksum written to: {args.universe_sha256}")
    print(f"Log written to: {args.log_file}")
