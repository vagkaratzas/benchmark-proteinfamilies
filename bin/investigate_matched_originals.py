#!/usr/bin/env python3

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from benchmark_ids import load_registry, resolve
from post_common import (
    discover_alignment_files,
    family_files_from_metadata,
    resolve_records,
    strip_known_extension,
    verify_universe_checksum,
)


CLUSTER_MISSING_WARNING_FRACTION = 0.25


def parse_args():
    parser = argparse.ArgumentParser(
        description="Summarise sampled original families against generated MSA membership."
    )
    parser.add_argument(
        "--db_folder",
        required=True,
        help="Path to sampled FASTA folder with DB subfolders.",
    )
    parser.add_argument(
        "--msa_dir", required=True, help="Generated full-family MSA folder."
    )
    parser.add_argument(
        "--cluster_file",
        default=None,
        help="Optional 2-column rep-to-member clustering TSV file.",
    )
    parser.add_argument(
        "--metadata", required=True, help="CSV mapping file with sampled metadata."
    )
    parser.add_argument("--id_registry", required=True)
    parser.add_argument("--pre_universe_fasta", required=True)
    parser.add_argument("--pre_universe_sha256", required=True)
    parser.add_argument("--output", default="metadata.csv", help="Output metadata TSV")
    parser.add_argument(
        "--cluster_log",
        default="all_clusters.txt",
        help="Output clusters description TXT",
    )
    parser.add_argument(
        "--match_log",
        default="all_matches.txt",
        help="Output matched families description TXT",
    )
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    return parser.parse_args()


def load_interpro_csv(path):
    interpro_map = {}
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            interpro_map[row["dbkey"]] = row
    return interpro_map


def load_use_case_data(folder, registry):
    use_case_sets = {}
    use_case_index = defaultdict(set)
    all_members = set()
    unresolved = []
    for path in discover_alignment_files(folder):
        members, _frags, unmapped, ambiguous, _n_raw = resolve_records(
            path,
            registry,
            f"use_case:{strip_known_extension(path.name)}",
        )
        use_case_name = strip_known_extension(path.name)
        use_case_sets[use_case_name] = members
        for universe_id in members:
            use_case_index[universe_id].add(use_case_name)
        all_members.update(members)
        unresolved.extend(unmapped)
        unresolved.extend(ambiguous)
    return use_case_sets, use_case_index, all_members, unresolved


def resolve_cluster_id(raw_id, registry):
    resolution = resolve(raw_id, registry)
    if resolution.status == "resolved" and resolution.universe_id is not None:
        return resolution.universe_id, None
    return None, {
        "raw_id": raw_id,
        "candidates": ",".join(sorted(resolution.candidates)),
        "reason": f"cluster:{resolution.status}",
    }


def load_cluster_file(cluster_file, registry):
    member_to_cluster = {}
    cluster_sizes = defaultdict(list)
    unresolved = []

    if not cluster_file:
        return member_to_cluster, cluster_sizes, unresolved
    path = Path(cluster_file)
    if not path.exists() or path.stat().st_size == 0:
        return member_to_cluster, cluster_sizes, unresolved

    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            rep_raw, member_raw = line.rstrip("\n").split()[:2]
            rep, rep_error = resolve_cluster_id(rep_raw, registry)
            member, member_error = resolve_cluster_id(member_raw, registry)
            if rep_error:
                unresolved.append(rep_error)
            if member_error:
                unresolved.append(member_error)
            if rep is None or member is None:
                continue
            member_to_cluster[member] = rep
            cluster_sizes[rep].append(member)

    return member_to_cluster, cluster_sizes, unresolved


def average_registry_length(seq_set, registry):
    lengths = [
        int(registry.rows[universe_id].get("ungapped_len", "0") or 0)
        for universe_id in seq_set
    ]
    return sum(lengths) / len(lengths) if lengths else 0


def analyze_family(
    family_name,
    db,
    fasta_path,
    registry,
    member_to_cluster,
    cluster_sizes,
    use_case_sets,
    use_case_index,
    cluster_log,
    match_log,
):
    seq_set, _frags, _unmapped, _ambiguous, _n_raw = resolve_records(
        fasta_path,
        registry,
        f"original:{db}/{family_name}",
        fail_on_unresolved=True,
    )
    avg_length = average_registry_length(seq_set, registry)

    fam_clusters = defaultdict(list)
    for seq_id in seq_set:
        if seq_id in member_to_cluster:
            cluster = member_to_cluster[seq_id]
            fam_clusters[cluster].append(seq_id)

    cluster_count = len(fam_clusters)

    with Path(cluster_log).open("a") as handle:
        handle.write(f"{family_name}:\n")
        size_to_members = defaultdict(list)
        for members in fam_clusters.values():
            size_to_members[len(members)].extend(members)
        for size in sorted(size_to_members):
            members = size_to_members[size]
            count = len(members) // size
            handle.write(
                f"{count} clusters with {size} members [{', '.join(members)}]\n"
            )
        handle.write("\n")

    candidate_use_cases = set()
    for universe_id in seq_set:
        candidate_use_cases.update(use_case_index.get(universe_id, set()))

    common_count_by_file = {}
    for uc_file in candidate_use_cases:
        uc_set = use_case_sets[uc_file]
        common = seq_set & uc_set
        if common:
            common_count_by_file[uc_file] = len(common)

    total_matched = sum(common_count_by_file.values())
    matched_seqs = set()
    for uc_file in candidate_use_cases:
        uc_set = use_case_sets[uc_file]
        matched_seqs.update(seq_set & uc_set)
    unmatched_seqs = seq_set - matched_seqs

    with Path(match_log).open("a") as handle:
        handle.write(f"{family_name}:\n")
        for uc_file, count in sorted(common_count_by_file.items()):
            handle.write(f"  {count} common sequences with {uc_file}\n")
        handle.write(
            f"  {len(unmatched_seqs)} unmatched sequences "
            f"[{', '.join(sorted(unmatched_seqs))}]\n\n"
        )

    if total_matched == 0:
        tag = "vanished"
    else:
        top_match = max(common_count_by_file.values())
        if top_match >= 0.5 * len(seq_set):
            tag = "matched"
        elif len(common_count_by_file) > 1:
            tag = "split"
        else:
            tag = "partial"

    return family_name, cluster_count, avg_length, tag, seq_set


def cluster_missing_fraction(member_to_cluster, msa_members):
    cluster_members = set(member_to_cluster)
    if not cluster_members:
        return 0.0
    return len(cluster_members - msa_members) / len(cluster_members)


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )
    registry = load_registry(args.id_registry, args.pre_universe_fasta)
    interpro_map = load_interpro_csv(args.metadata)
    use_case_sets, use_case_index, msa_members, msa_unresolved = load_use_case_data(
        args.msa_dir, registry
    )
    member_to_cluster, cluster_sizes, cluster_unresolved = load_cluster_file(
        args.cluster_file, registry
    )
    missing_fraction = cluster_missing_fraction(member_to_cluster, msa_members)

    if missing_fraction > CLUSTER_MISSING_WARNING_FRACTION:
        print(
            f"Warning: {missing_fraction:.3f} of resolved cluster members are absent "
            "from resolved MSA members; confirm msa_dir is a full-family MSA directory",
            file=sys.stderr,
        )

    Path(args.cluster_log).write_text("")
    Path(args.match_log).write_text("")
    if msa_unresolved or cluster_unresolved:
        with Path(args.cluster_log).open("a") as handle:
            handle.write("Unresolved MSA/cluster IDs:\n")
            for row in msa_unresolved + cluster_unresolved:
                handle.write(f"{row['raw_id']}\t{row['candidates']}\t{row['reason']}\n")
            handle.write("\n")

    results = []
    for db, family, path, _row in family_files_from_metadata(
        args.db_folder, args.metadata
    ):
        family_name, cluster_count, avg_length, tag, seq_set = analyze_family(
            family,
            db,
            path,
            registry,
            member_to_cluster,
            cluster_sizes,
            use_case_sets,
            use_case_index,
            args.cluster_log,
            args.match_log,
        )
        interpro = interpro_map.get(family_name, {})
        results.append(
            {
                "sample": args.sample,
                "tool": args.tool,
                "universe_sha256": universe_sha256,
                "membership_source": "MSA",
                "family": family_name,
                "interpro_id": interpro.get("interpro_id", ""),
                "db": interpro.get("db", db),
                "total_sequences": len(seq_set),
                "cluster_count": cluster_count,
                "avg_length": round(avg_length, 2),
                "tag": tag,
                "cluster_missing_fraction": f"{missing_fraction:.6f}",
            }
        )

    fieldnames = [
        "sample",
        "tool",
        "universe_sha256",
        "membership_source",
        "family",
        "interpro_id",
        "db",
        "total_sequences",
        "cluster_count",
        "avg_length",
        "tag",
        "cluster_missing_fraction",
    ]
    with Path(args.output).open("w", newline="") as out_csv:
        writer = csv.DictWriter(out_csv, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    main()
