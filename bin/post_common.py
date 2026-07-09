#!/usr/bin/env python3

import csv
import gzip
import hashlib
import sys
from pathlib import Path

from Bio import AlignIO
from Bio import SeqIO

from benchmark_ids import resolve


KNOWN_ALIGNMENT_EXTENSIONS = (
    ".fasta.gz",
    ".fas.gz",
    ".sto.gz",
    ".clipkit",
    ".fasta",
    ".faa",
    ".afa",
    ".aln",
    ".sto",
)


def open_text(path):
    path = Path(path)
    return gzip.open(path, "rt") if path.name.endswith(".gz") else path.open()


def strip_known_extension(filename):
    for ext in KNOWN_ALIGNMENT_EXTENSIONS:
        if filename.endswith(ext):
            return filename[: -len(ext)]
    return Path(filename).stem


def discover_alignment_files(folder):
    folder = Path(folder)
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file()
        and any(path.name.endswith(ext) for ext in KNOWN_ALIGNMENT_EXTENSIONS)
    )


def sniff_alignment_format(path):
    path = Path(path)
    with open_text(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith("# STOCKHOLM"):
                return "stockholm"
            if line.startswith(">"):
                return "fasta"
            break
    return "stockholm" if path.name.endswith((".sto", ".sto.gz")) else "fasta"


def iter_alignment_records(path):
    fmt = sniff_alignment_format(path)
    with open_text(path) as handle:
        if fmt == "stockholm":
            for alignment in AlignIO.parse(handle, "stockholm"):
                yield from alignment
        else:
            yield from SeqIO.parse(handle, "fasta")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_universe_checksum(universe_fasta, checksum_file):
    expected = Path(checksum_file).read_text().strip().split()[0]
    observed = sha256_file(universe_fasta)
    if observed != expected:
        raise SystemExit(
            "Universe checksum mismatch: "
            f"{universe_fasta} sha256 is {observed}, "
            f"but {checksum_file} contains {expected}"
        )
    return observed


def read_metadata_rows(metadata_file):
    with Path(metadata_file).open(newline="") as handle:
        return list(csv.DictReader(handle))


def scan_family_files(sampled_fasta_dir):
    by_db = {}
    root = Path(sampled_fasta_dir)
    for db_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        db = db_dir.name.lower()
        by_db[db] = {}
        for path in discover_alignment_files(db_dir):
            family = strip_known_extension(path.name)
            if family in by_db[db]:
                raise ValueError(
                    f"Duplicate sampled family basename {family!r} in {db_dir}; "
                    "exact metadata mapping would be ambiguous"
                )
            by_db[db][family] = path
    return by_db


def family_files_from_metadata(sampled_fasta_dir, metadata_file):
    scanned = scan_family_files(sampled_fasta_dir)
    rows = read_metadata_rows(metadata_file)
    family_files = []
    missing = []
    seen = set()

    for row in rows:
        db = row.get("db", "").strip().lower()
        family = row.get("dbkey", "").strip()
        if not db or not family:
            continue
        key = (db, family)
        if key in seen:
            continue
        seen.add(key)
        path = scanned.get(db, {}).get(family)
        if path is None:
            missing.append(f"{db}/{family}")
            continue
        family_files.append((db, family, path, row))

    if missing:
        print(
            "Warning: metadata families without exact sampled FASTA matches: "
            + ", ".join(missing),
            file=sys.stderr,
        )

    return family_files


def family_files_from_directory(sampled_fasta_dir):
    family_files = []
    for db, files in scan_family_files(sampled_fasta_dir).items():
        for family, path in sorted(files.items()):
            family_files.append((db, family, path, {}))
    return family_files


def resolve_records(path, registry, reason_prefix, fail_on_unresolved=False):
    members = set()
    raw_by_universe = {}
    unmapped = []
    ambiguous = []
    n_raw = 0

    for record in iter_alignment_records(path):
        n_raw += 1
        resolution = resolve(record.id, registry, str(record.seq))
        if resolution.status == "resolved" and resolution.universe_id is not None:
            members.add(resolution.universe_id)
            raw_by_universe.setdefault(resolution.universe_id, set()).add(record.id)
        else:
            row = {
                "raw_id": record.id,
                "candidates": ",".join(sorted(resolution.candidates)),
                "reason": f"{reason_prefix}:{resolution.status}",
            }
            if resolution.status == "ambiguous":
                ambiguous.append(row)
            else:
                unmapped.append(row)

    if fail_on_unresolved and (unmapped or ambiguous):
        examples = unmapped[:3] + ambiguous[:3]
        details = "; ".join(
            f"{row['raw_id']} ({row['reason']}: {row['candidates']})"
            for row in examples
        )
        raise ValueError(f"Could not resolve IDs in {path}: {details}")

    fragments = {
        universe_id: len(raw_ids) for universe_id, raw_ids in raw_by_universe.items()
    }
    return members, fragments, unmapped, ambiguous, n_raw


def write_rejected(path, rows):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["raw_id", "candidates", "reason"], delimiter="\t"
        )
        writer.writeheader()
        writer.writerows(rows)
