#!/usr/bin/env python3
"""Shared helpers for the POST modules: alignment discovery, universe verification, ID resolution.

This is a library, not a CLI. Nextflow puts bin/ on PATH but not on PYTHONPATH, so the modules
that use it stage this file as a `path` input and prepend $PWD to PYTHONPATH in their script block.

Biopython is imported lazily inside `iter_alignment_records` rather than at module scope: several
callers only need the checksum and metadata helpers, and their containers deliberately do not ship
biopython. A module-scope import would break them on import alone.
"""

import csv
import gzip
import hashlib
import sys
from pathlib import Path

from benchmark_ids import resolve


# POST is tool-agnostic, so it cannot assume an output extension. This list is the union of what
# the reference tools emit; anything outside it is not treated as an alignment. An earlier version
# filtered on `.fasta.gz` alone, which matched nothing from either reference tool (they write
# `.faa` / `.fas.gz`) and silently tagged every curated family "vanished".
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
    """Family name from a filename, matching the longest known extension first.

    `Path.stem` is wrong here: it would turn `PF00001.fasta.gz` into `PF00001.fasta`. The
    extension list is ordered longest-first so the double extensions are tried before `.gz`.
    """
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
    """Detect Stockholm vs FASTA by content, falling back to the extension.

    Content wins over the filename because NCBIFAM ships both formats under the same `.SEED`
    extension -- trusting the extension there misparses half the database.
    """
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
    # Biopython is imported here, not at module scope, so that importing this library does not
    # itself require biopython. Callers that only use the checksum/metadata helpers
    # (CALCULATE_DB_FAMILY_COVERAGE, GET_SIZE_DISTRIBUTIONS) run in containers without it.
    from Bio import AlignIO
    from Bio import SeqIO

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
    """Abort unless the universe FASTA is the one these results claim to be scored against.

    Raises SystemExit on mismatch. Every result table records this checksum, which is what stops a
    samplesheet from being scored against a *different* PRE universe than the tool actually ran on
    -- a mistake that produces plausible-looking numbers rather than an error.
    """
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
    """Index sampled family FASTAs as {db: {family: path}}.

    Raises ValueError on two files with the same family basename in one database: the metadata maps
    (db, dbkey) to exactly one file, and a duplicate makes that mapping ambiguous. Failing here is
    deliberate -- picking one arbitrarily would score a tool against the wrong curated family.
    """
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
    """Pair each metadata row with its sampled FASTA, as (db, family, path, row).

    Families in the metadata with no matching FASTA are warned about, not fatal: a database release
    can list a family whose alignment it does not ship. Deduplicates on (db, dbkey) because one
    curated family can be reached through several InterPro entries.
    """
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
