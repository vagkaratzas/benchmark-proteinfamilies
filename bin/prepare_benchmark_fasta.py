#!/usr/bin/env python3
"""Extract the sampled families' sequences from the four databases and record every ID.

Emits one FASTA per family, a combined FASTA, and -- the load-bearing output -- `id_registry.tsv`,
which maps every `universe_id` (the exact header written into the universe) to its `parent_id`,
`source_type`, `db_layer`, family, coordinates and sequence hash.

The registry is the single source of identity for the whole benchmark. POST never infers what a
sequence is from the text of an ID; it looks it up here. Anything not recorded at this step cannot
be recovered later.
"""

import argparse
import csv
import hashlib
import re
from pathlib import Path

from Bio import AlignIO, SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord


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

SLASH_COORD_PATTERN = re.compile(r"/(\d+)-(\d+)$")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Prepare sampled family FASTAs, a combined FASTA, and an ID registry."
    )
    parser.add_argument(
        "--metadata_file", required=True, help="Path to the sampled_metadata.csv file"
    )
    parser.add_argument(
        "--db",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help=(
            "Member database alignment folder as NAME=PATH, e.g. pfam=/path/to/pfam. "
            "Repeat once per database; databases skipped by the pipeline are simply absent."
        ),
    )
    parser.add_argument(
        "--output_folder", required=True, help="Output sampled FASTA dir"
    )
    parser.add_argument(
        "--updated_metadata_file",
        required=True,
        help="Path to output updated metadata file",
    )
    parser.add_argument(
        "--combined_fasta", required=True, help="Path to output combined FASTA"
    )
    parser.add_argument(
        "--id_registry", required=True, help="Path to output id_registry.tsv"
    )
    parser.add_argument(
        "--combined_db_sha256", required=True, help="Path to output combined_db.sha256"
    )
    parser.add_argument(
        "--log_file", default="log.txt", help="Path to the deduplication log"
    )
    parser.add_argument(
        "--seed",
        default=None,
        help="Optional PRE sampling seed to record in the registry header",
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
    with open(file_path, "r") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                return "fasta"
            if line.startswith("# STOCKHOLM"):
                return "stockholm"
            return "unknown"
    return "unknown"


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


def clean_id(seq_id: str) -> str:
    return seq_id.translate(str.maketrans(".|=", "___"))


# PRE strips only a trailing `/start-end`: curated alignments use no other coordinate form, and
# this is the *authoritative* record of what each sequence is. POST's resolver deliberately accepts
# more forms (`_start_end` too), because it is reconciling what a tool wrote, not recording truth.
# The asymmetry is intentional -- do not "unify" the two.
def split_parent_coords(universe_id: str):
    match = SLASH_COORD_PATTERN.search(universe_id)
    if not match:
        return universe_id, "-"
    return (
        SLASH_COORD_PATTERN.sub("", universe_id),
        f"{match.group(1)}-{match.group(2)}",
    )


def parse_records(input_file: Path, fmt: str):
    if fmt == "fasta":
        yield from SeqIO.parse(input_file, "fasta")
    elif fmt == "stockholm":
        yield from AlignIO.read(input_file, "stockholm")


def convert_family(input_file: Path, fmt: str, output_file: Path):
    seen_ids = set()
    seen_seqs = set()
    records = []

    for record in parse_records(input_file, fmt):
        clean_seq = ungap(str(record.seq))
        cleaned_id = clean_id(record.id)

        if cleaned_id in seen_ids:
            continue
        if clean_seq in seen_seqs:
            continue

        seen_ids.add(cleaned_id)
        seen_seqs.add(clean_seq)
        records.append(SeqRecord(Seq(clean_seq), id=cleaned_id, description=""))

    if records:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as out_f:
            SeqIO.write(records, out_f, "fasta")

    return records


def registry_row(record: SeqRecord, db_layer: str, family: str):
    universe_id = record.id
    seq = str(record.seq)
    parent_id, coords = split_parent_coords(universe_id)
    return {
        "universe_id": universe_id,
        "parent_id": parent_id,
        "source_type": "family",
        "db_layer": db_layer,
        "family": family,
        "coords": coords,
        "ungapped_len": str(len(ungap(seq))),
        "seq_sha1": sha1_of(seq),
    }


def write_registry(path: Path, rows, seed=None):
    with open(path, "w", newline="") as handle:
        if seed is not None:
            handle.write(f"# seed={seed}\n")
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def parse_db_args(items):
    """Turn the repeated NAME=PATH arguments into the {db: folder} map the walk below expects."""
    db_paths = {}
    for item in items:
        name, sep, path = item.partition("=")
        if not sep or not name or not path:
            raise ValueError(f"--db expects NAME=PATH, got {item!r}")
        db_paths[name.lower()] = Path(path)
    return db_paths


def main():
    args = parse_args()

    db_paths = parse_db_args(args.db)

    output_base = Path(args.output_folder)
    updated_metadata = []
    final_records = []
    registry_rows = []
    seen_ids = {}
    seen_seqs = {}
    total_count = 0
    name_dups = 0
    seq_dups = 0

    with (
        open(args.metadata_file, newline="") as metadata_handle,
        open(args.log_file, "w") as log,
    ):
        reader = csv.DictReader(metadata_handle, delimiter=",")
        fieldnames = list(reader.fieldnames or [])
        if "protein_count" not in fieldnames:
            fieldnames.append("protein_count")

        log.write("Deduplication Report\n")
        log.write("====================\n")

        for row in reader:
            db = row["db"].lower()
            dbkey = row["dbkey"]
            ipr_id = row["interpro_id"]
            base_path = get_db_path(db, db_paths)

            if base_path is None:
                log.write(f"[SKIPPED] Unknown DB type '{db}' for IPR {ipr_id}\n")
                continue

            matching_file = find_matching_file(base_path, dbkey)
            if not matching_file:
                # The database name, not base_path: the caller stages these directories under
                # generated names, so logging the path would make the report depend on staging.
                log.write(f"[NOT FOUND] {dbkey} in {db}\n")
                continue

            fmt = detect_format(matching_file)
            if fmt == "unknown":
                log.write(f"[SKIPPED] Unknown format for file {matching_file}\n")
                continue

            output_file = output_base / db / f"{dbkey}.faa"
            records = convert_family(matching_file, fmt, output_file)
            row["protein_count"] = len(records)
            updated_metadata.append(row)
            log.write(
                f"[OK] Converted {dbkey} from {fmt.upper()} to {output_file} ({len(records)} unique)\n"
            )

            for record in records:
                total_count += 1
                seq = str(record.seq)

                if record.id in seen_ids:
                    name_dups += 1
                    log.write(
                        f"Duplicate name removed from combined FASTA: {record.id} in {output_file.name} "
                        f"(first seen in {seen_ids[record.id]})\n"
                    )
                    continue
                seen_ids[record.id] = output_file.name

                if seq in seen_seqs:
                    seq_dups += 1
                    original_id, original_file = seen_seqs[seq]
                    log.write(
                        f"Duplicate sequence retained with distinct name: {record.id} in {output_file.name} "
                        f"(same as {original_id} from {original_file})\n"
                    )
                else:
                    seen_seqs[seq] = (record.id, output_file.name)

                final_records.append(record)
                registry_rows.append(registry_row(record, db, dbkey))

        with open(args.updated_metadata_file, "w", newline="") as out_meta:
            writer = csv.DictWriter(out_meta, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_metadata)

        combined_fasta = Path(args.combined_fasta)
        with open(combined_fasta, "w") as out_fasta:
            SeqIO.write(final_records, out_fasta, "fasta")

        write_registry(Path(args.id_registry), registry_rows, args.seed)
        Path(args.combined_db_sha256).write_text(f"{sha256_file(combined_fasta)}\n")

        log.write("\nSummary:\n")
        log.write(f"Total sequences found: {total_count}\n")
        log.write(f"Duplicates by cleaned name (removed): {name_dups}\n")
        log.write(f"Duplicates by sequence (logged only): {seq_dups}\n")
        log.write(f"Unique sequences written: {len(final_records)}\n")
        log.write(f"Final deduplicated FASTA written to: {combined_fasta}\n")

    print(f"[DONE] Sampled FASTA written to {output_base}")
    print(f"[DONE] Combined FASTA written to {args.combined_fasta}")
    print(f"[DONE] Registry written to {args.id_registry}")


if __name__ == "__main__":
    main()
