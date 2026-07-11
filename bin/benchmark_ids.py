#!/usr/bin/env python3

import csv
import hashlib
import io
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union


COORD_PATTERNS = (
    re.compile(r"/\d+-\d+$"),
    re.compile(r"_\d+_\d+$"),
)


@dataclass
class Registry:
    rows: Dict[str, Dict[str, str]]
    alias_index: Dict[str, str]
    ambiguous_aliases: Dict[str, Set[str]]
    parent_index: Dict[str, Set[str]]
    sequences: Dict[str, str] = field(default_factory=dict)


@dataclass
class Resolution:
    universe_id: Optional[str]
    status: str
    candidates: Set[str] = field(default_factory=set)


def ungap(seq: str) -> str:
    return "".join(
        char for char in str(seq) if char not in "-." and not char.islower()
    ).upper()


def sha1_of(seq: str) -> str:
    return hashlib.sha1(ungap(seq).encode()).hexdigest()


def clean_id(seq_id: str) -> str:
    return seq_id.translate(str.maketrans(".|=", "___"))


def _strip_once(seq_id: str) -> Set[str]:
    stripped = set()
    for pattern in COORD_PATTERNS:
        if pattern.search(seq_id):
            stripped.add(pattern.sub("", seq_id))
    return stripped


def coordinate_lattice(seq_id: str) -> Set[str]:
    candidates = {seq_id}
    stack = [seq_id]
    while stack:
        current = stack.pop()
        for stripped in _strip_once(current):
            if stripped not in candidates:
                candidates.add(stripped)
                stack.append(stripped)
    return candidates


def to_parent_id(universe_id: str) -> str:
    current = universe_id
    while True:
        stripped = _strip_once(current)
        if not stripped:
            return current
        current = sorted(stripped, key=len)[0]


def _add_alias(registry: Registry, alias: str, universe_id: str) -> None:
    if not alias:
        return

    existing = registry.alias_index.get(alias)
    if existing == universe_id:
        return
    if existing is not None:
        registry.ambiguous_aliases[alias] = {existing, universe_id}
        del registry.alias_index[alias]
        return

    ambiguous = registry.ambiguous_aliases.get(alias)
    if ambiguous is not None:
        ambiguous.add(universe_id)
        return

    registry.alias_index[alias] = universe_id


def _pipe_aliases(cleaned_id: str) -> Set[str]:
    aliases = set()
    for prefix in ("sp", "tr"):
        marker = f"{prefix}_"
        if cleaned_id.startswith(marker):
            remainder = cleaned_id[len(marker) :]
            if "_" in remainder:
                accession, name = remainder.split("_", 1)
                aliases.add(accession)
                aliases.add(f"{prefix}|{accession}|{name}")
    return aliases


def _aliases_for_row(row: Dict[str, str]) -> Set[str]:
    universe_id = row["universe_id"]
    parent_id = row.get("parent_id", "")
    coords = row.get("coords", "")

    aliases = {universe_id, clean_id(universe_id)}
    aliases.update(coordinate_lattice(universe_id))
    aliases.update(coordinate_lattice(clean_id(universe_id)))

    if parent_id and parent_id != "-":
        aliases.add(parent_id)
        aliases.add(clean_id(parent_id))

    if coords and coords != "-" and parent_id and parent_id != "-":
        aliases.add(f"{parent_id}/{coords}")
        aliases.add(clean_id(f"{parent_id}/{coords}"))
        match = re.fullmatch(r"(\d+)-(\d+)", coords)
        if match:
            aliases.add(f"{parent_id}_{match.group(1)}_{match.group(2)}")
            aliases.add(clean_id(f"{parent_id}_{match.group(1)}_{match.group(2)}"))

    aliases.update(_pipe_aliases(universe_id))
    aliases.update(_pipe_aliases(clean_id(universe_id)))
    return aliases


def _read_registry_rows(registry_tsv: Union[str, Path]) -> List[Dict[str, str]]:
    lines = [
        line
        for line in Path(registry_tsv).read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not lines:
        return []
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def load_registry(
    registry_tsv: Union[str, Path], universe_fasta: Optional[Union[str, Path]] = None
) -> Registry:
    registry = Registry(rows={}, alias_index={}, ambiguous_aliases={}, parent_index={})

    for row in _read_registry_rows(registry_tsv):
        universe_id = row["universe_id"]
        if universe_id in registry.rows:
            raise ValueError(f"Duplicate universe_id in registry: {universe_id}")

        registry.rows[universe_id] = row
        parent_id = row.get("parent_id", "")
        if parent_id and parent_id != "-":
            registry.parent_index.setdefault(parent_id, set()).add(universe_id)

        for alias in _aliases_for_row(row):
            _add_alias(registry, alias, universe_id)

    if universe_fasta is not None:
        # Imported here rather than at module scope: only sequence-level disambiguation needs
        # biopython, so modules that merely resolve IDs can run in a biopython-free container.
        from Bio import SeqIO

        for record in SeqIO.parse(str(universe_fasta), "fasta"):
            registry.sequences[record.id] = ungap(str(record.seq))

    return registry


def _lookup_alias(alias: str, registry: Registry) -> Set[str]:
    if alias in registry.alias_index:
        return {registry.alias_index[alias]}
    if alias in registry.ambiguous_aliases:
        return set(registry.ambiguous_aliases[alias])
    return set()


def _sequence_disambiguation(
    candidates: Set[str], registry: Registry, seq: Optional[str]
) -> Optional[str]:
    if seq is None:
        return None

    observed_hash = sha1_of(seq)
    hash_matches = {
        universe_id
        for universe_id in candidates
        if registry.rows[universe_id].get("seq_sha1") == observed_hash
    }
    if len(hash_matches) == 1:
        return next(iter(hash_matches))

    observed = ungap(seq)
    if observed:
        substring_matches = {
            universe_id
            for universe_id in candidates
            if observed in registry.sequences.get(universe_id, "")
        }
        if len(substring_matches) == 1:
            return next(iter(substring_matches))

    return None


def resolve(raw_id: str, registry: Registry, seq: Optional[str] = None) -> Resolution:
    candidates = set()

    candidates.update(_lookup_alias(raw_id, registry))
    for alias in coordinate_lattice(raw_id):
        candidates.update(_lookup_alias(alias, registry))

    if len(candidates) == 1:
        return Resolution(next(iter(candidates)), "resolved", candidates)
    if not candidates:
        return Resolution(None, "unmapped", set())

    universe_id = _sequence_disambiguation(candidates, registry, seq)
    if universe_id is not None:
        return Resolution(universe_id, "resolved", candidates)
    return Resolution(None, "ambiguous", candidates)


RawIdInput = Union[str, Tuple[str, str], Sequence[str]]


def canonicalise(
    raw_ids_or_pairs: Iterable[RawIdInput], registry: Registry
) -> Tuple[Set[str], Dict[str, int], List[str], List[str]]:
    members = set()
    raw_by_universe: Dict[str, Set[str]] = {}
    unmapped = []
    ambiguous = []

    for item in raw_ids_or_pairs:
        if isinstance(item, str):
            raw_id, seq = item, None
        else:
            raw_id = str(item[0])
            seq = str(item[1]) if len(item) > 1 else None

        resolution = resolve(raw_id, registry, seq)
        if resolution.status == "resolved" and resolution.universe_id is not None:
            members.add(resolution.universe_id)
            raw_by_universe.setdefault(resolution.universe_id, set()).add(raw_id)
        elif resolution.status == "ambiguous":
            ambiguous.append(raw_id)
        else:
            unmapped.append(raw_id)

    frags = {
        universe_id: len(raw_ids) for universe_id, raw_ids in raw_by_universe.items()
    }
    return members, frags, unmapped, ambiguous


def _registry_row(
    universe_id: str,
    parent_id: str,
    source_type: str,
    db_layer: str,
    family: str,
    coords: str,
    seq: str,
) -> Dict[str, str]:
    return {
        "universe_id": universe_id,
        "parent_id": parent_id,
        "source_type": source_type,
        "db_layer": db_layer,
        "family": family,
        "coords": coords,
        "ungapped_len": str(len(ungap(seq))),
        "seq_sha1": sha1_of(seq),
    }


def demo() -> None:
    import combine_decoy_fasta
    import prepare_benchmark_fasta

    rows = [
        _registry_row(
            "1814953751", "1814953751", "family", "pfam", "PF00001", "-", "MAAA"
        ),
        _registry_row(
            "711279214", "711279214", "family", "pfam", "PF00002", "-", "MBBB"
        ),
        _registry_row(
            "1446399400", "1446399400", "family", "pfam", "PF00003", "-", "MCCC"
        ),
        _registry_row(
            "2632373804", "2632373804", "family", "pfam", "PF00004", "-", "MDDD"
        ),
        _registry_row(
            "Q9X1J3/1-250", "Q9X1J3", "family", "pfam", "PF00069", "1-250", "MEEE"
        ),
        _registry_row("sp_P12345_NAME", "P12345", "decoy", "-", "-", "-", "MFFF"),
        _registry_row("X", "X", "family", "pfam", "PF00005", "-", "MGGG"),
        _registry_row("X_1_2", "X_1_2", "family", "pfam", "PF00006", "-", "MHHH"),
        _registry_row(
            "LEGIT_12_34", "LEGIT_12_34", "family", "pfam", "PF00007", "-", "MIII"
        ),
        _registry_row(
            "COLLIDE/1-10", "COLLIDE", "family", "pfam", "PF00008", "1-10", "MJJJ"
        ),
        _registry_row(
            "COLLIDE/20-30", "COLLIDE", "family", "pfam", "PF00009", "20-30", "MKKK"
        ),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        registry_tsv = Path(tmpdir) / "id_registry.tsv"
        universe_fasta = Path(tmpdir) / "combined_decoy.faa"

        with open(registry_tsv, "w", newline="") as handle:
            handle.write("# seed=123\n")
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "universe_id",
                    "parent_id",
                    "source_type",
                    "db_layer",
                    "family",
                    "coords",
                    "ungapped_len",
                    "seq_sha1",
                ],
                delimiter="\t",
            )
            writer.writeheader()
            writer.writerows(rows)

        with open(universe_fasta, "w") as handle:
            for row, seq in zip(
                rows,
                [
                    "M-AAA",
                    "MBBB",
                    "MCCC",
                    "MDDD",
                    "MEEE",
                    "MFFF",
                    "MGGG",
                    "MHHH",
                    "MIII",
                    "MJJJ",
                    "MKKK",
                ],
            ):
                handle.write(f">{row['universe_id']}\n{seq}\n")

        registry = load_registry(registry_tsv, universe_fasta)

        checks = [
            ("D1 slash coordinates", "1814953751/178-297", "1814953751", None),
            ("D1 underscore coordinates", "711279214_315_691", "711279214", None),
            ("D1 proteinfamilies coordinates", "1446399400_1_131", "1446399400", None),
            (
                "D1 mixed suffix lattice",
                "2632373804_177_299/1-122",
                "2632373804",
                None,
            ),
            ("D1 PRE original exact", "Q9X1J3/1-250", "Q9X1J3/1-250", None),
            ("D1 decoy forward alias", "sp|P12345|NAME", "sp_P12345_NAME", None),
            ("false attribution sequence evidence", "X_1_2", "X", "MGGG"),
            ("legitimate underscore ID", "LEGIT_12_34", "LEGIT_12_34", None),
        ]

        for name, raw_id, expected, seq in checks:
            resolution = resolve(raw_id, registry, seq)
            assert resolution.status == "resolved", f"{name}: {resolution}"
            assert resolution.universe_id == expected, f"{name}: {resolution}"

        false_without_seq = resolve("X_1_2", registry)
        assert false_without_seq.status == "ambiguous", false_without_seq
        assert false_without_seq.candidates == {"X", "X_1_2"}, false_without_seq

        collision = resolve("COLLIDE", registry)
        assert collision.status == "ambiguous", collision
        assert collision.candidates == {"COLLIDE/1-10", "COLLIDE/20-30"}, collision

        assert ungap("AC-d.eF") == "ACF"
        assert sha1_of("M-G.gG") == sha1_of("MGG")
        assert to_parent_id("2632373804_177_299/1-122") == "2632373804"

        members, frags, unmapped, ambiguous = canonicalise(
            [("X_1_2", "MGGG"), ("X/1-2", "MGGG"), "missing", "COLLIDE"],
            registry,
        )
        assert members == {"X"}
        assert frags == {"X": 2}
        assert unmapped == ["missing"]
        assert ambiguous == ["COLLIDE"]

    assert prepare_benchmark_fasta.split_parent_coords("LEGIT_12_34") == (
        "LEGIT_12_34",
        "-",
    )
    assert prepare_benchmark_fasta.split_parent_coords("A1B2_3_4/10-20") == (
        "A1B2_3_4",
        "10-20",
    )
    assert prepare_benchmark_fasta.split_parent_coords("Q9X1J3/1-250") == (
        "Q9X1J3",
        "1-250",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        families_fasta = tmpdir / "families.faa"
        decoys_fasta = tmpdir / "decoys.faa"
        registry_tsv = tmpdir / "id_registry.tsv"
        combined_fasta = tmpdir / "combined_decoy.faa"
        output_registry = tmpdir / "id_registry.final.tsv"
        universe_sha256 = tmpdir / "universe.sha256"
        log_file = tmpdir / "combined_decoy_log.txt"

        families = [
            ("PF1_A/1-10", "PF1_A", "PF1", "1-10", "MAAAKKLL"),
            ("PTHR2_B/1-10", "PTHR2_B", "PTHR2", "1-10", "MAAAKKLL"),
            ("PF1_C/1-10", "PF1_C", "PF1", "1-10", "MCCCKKLL"),
        ]
        with open(families_fasta, "w") as handle:
            for universe_id, _, _, _, seq in families:
                handle.write(f">{universe_id}\n{seq}\n")
        with open(decoys_fasta, "w") as handle:
            handle.write(">sp|LEAK|DECOY\nMAAAKKLL\n")
            handle.write(">sp|UNIQ|DECOY\nMTTTKKLL\n")
        with open(registry_tsv, "w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "universe_id",
                    "parent_id",
                    "source_type",
                    "db_layer",
                    "family",
                    "coords",
                    "ungapped_len",
                    "seq_sha1",
                ],
                delimiter="\t",
            )
            writer.writeheader()
            for universe_id, parent_id, family, coords, seq in families:
                writer.writerow(
                    _registry_row(
                        universe_id,
                        parent_id,
                        "family",
                        "pfam",
                        family,
                        coords,
                        seq,
                    )
                )

        combine_decoy_fasta.combine_fastas(
            families_fasta,
            decoys_fasta,
            combined_fasta,
            registry_tsv,
            output_registry,
            universe_sha256,
            log_file,
        )

        from Bio import SeqIO

        fasta_ids = {record.id for record in SeqIO.parse(combined_fasta, "fasta")}
        registry = load_registry(output_registry, combined_fasta)
        assert {"PF1_A/1-10", "PTHR2_B/1-10", "PF1_C/1-10"} <= fasta_ids
        assert {"PF1_A/1-10", "PTHR2_B/1-10", "PF1_C/1-10"} <= set(registry.rows)
        assert "sp_LEAK_DECOY" not in fasta_ids
        assert "sp_LEAK_DECOY" not in registry.rows
        assert "sp_UNIQ_DECOY" in fasta_ids
        assert "sp_UNIQ_DECOY" in registry.rows
        assert "decoy sequence identical to a family sequence" in log_file.read_text()

    print("benchmark_ids.py self-check passed")
    print(f"resolved worked examples: {len(checks)}")
    print(
        "pathology checks: false attribution, strip-order, legitimate suffix, alias collision, decoy alias"
    )


if __name__ == "__main__":
    demo()
