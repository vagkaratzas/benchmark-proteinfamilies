#!/usr/bin/env python3

import argparse
import os
import gzip
import csv
from collections import defaultdict
from Bio import SeqIO


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract metadata from clustering and sequence data"
    )
    parser.add_argument(
        "--db_folder",
        required=True,
        help="Path to database folder with 4 subfolders of .fasta files",
    )
    parser.add_argument(
        "--cluster_file", required=True, help="Path to clustering 2-column TSV file"
    )
    parser.add_argument(
        "--metadata", required=True, help="CSV mapping file with interpro metadata"
    )
    parser.add_argument(
        "--generated_fasta", required=True, help="Path to folder with .fasta.gz files"
    )
    parser.add_argument(
        "--output", default="metadata_summary.csv", help="Output metadata CSV"
    )
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
    return parser.parse_args()


def load_cluster_file(cluster_file):
    member_to_cluster = {}
    cluster_sizes = defaultdict(list)

    with open(cluster_file) as f:
        for line in f:
            rep, member = line.strip().split()
            member_to_cluster[member] = rep

    for member, rep in member_to_cluster.items():
        cluster_sizes[rep].append(member)

    return member_to_cluster, cluster_sizes


def load_interpro_csv(path):
    interpro_map = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            interpro_map[row["dbkey"]] = row
    return interpro_map


def load_use_case_data(folder):
    use_case_sets = {}
    for filename in os.listdir(folder):
        if not filename.endswith(".fasta.gz"):
            continue
        path = os.path.join(folder, filename)
        seq_ids = set()
        lengths = []
        with gzip.open(path, "rt") as handle:
            for record in SeqIO.parse(handle, "fasta"):
                seq_id = record.id.split("/")[0]
                seq_ids.add(seq_id)
                lengths.append(len(record.seq))
        avg_len = sum(lengths) / len(lengths) if lengths else 0
        use_case_sets[filename] = (seq_ids, avg_len)
    return use_case_sets


def analyze_fasta_file(
    fasta_path, member_to_cluster, cluster_sizes, use_case_sets, cluster_log, match_log
):
    family_name = os.path.basename(fasta_path).replace(".fasta", "")
    with open(fasta_path) as handle:
        records = list(SeqIO.parse(handle, "fasta"))

    avg_length = sum(len(rec.seq) for rec in records) / len(records) if records else 0

    seq_ids = [rec.id for rec in records]
    split_seq_ids = [rec.id.split("/")[0] for rec in records]
    split_seq_set = set(split_seq_ids)

    # Cluster analysis
    fam_clusters = defaultdict(list)
    for seq_id in seq_ids:
        if seq_id in member_to_cluster:
            cluster = member_to_cluster[seq_id]
            fam_clusters[cluster].append(seq_id)

    cluster_count = len(fam_clusters)

    with open(cluster_log, "a") as f:
        f.write(f"{family_name}:\n")

        # Group clusters by their size
        size_to_members = defaultdict(list)
        for members in fam_clusters.values():
            size = len(members)
            size_to_members[size].extend(members)

        for size in sorted(size_to_members):
            members = size_to_members[size]
            count = len(members) // size  # number of clusters of this size
            f.write(f"{count} clusters with {size} members [{', '.join(members)}]\n")

        f.write("\n")

    # Use-case match analysis
    common_count_by_file = {}
    for uc_file, (uc_set, avg_len) in use_case_sets.items():
        common = split_seq_set & uc_set
        if common:
            common_count_by_file[uc_file] = (len(common), avg_len)

    total_matched = sum(x[0] for x in common_count_by_file.values())
    matched_seqs = set()
    for uc_file, (uc_set, _) in use_case_sets.items():
        matched_seqs.update(split_seq_set & uc_set)
    unmatched_seqs = split_seq_set - matched_seqs
    unmatched = len(unmatched_seqs)

    with open(match_log, "a") as f:
        f.write(f"{family_name}:\n")
        for uc_file, (count, avg_len) in sorted(common_count_by_file.items()):
            f.write(
                f"  {count} common sequences with {uc_file} (average length: {int(avg_len)})\n"
            )
        f.write(f"  {unmatched} unmatched sequences [{', '.join(unmatched_seqs)}]\n\n")

    # Match tag
    tag = "vanished"
    if total_matched == 0:
        tag = "vanished"
    else:
        top_match = max(common_count_by_file.values(), key=lambda x: x[0])[0]
        if top_match >= 0.5 * len(split_seq_set):
            tag = "matched"
        elif len(common_count_by_file) > 1:
            tag = "split"
        else:
            tag = "partial"

    return family_name, cluster_count, avg_length, tag, split_seq_set


def main():
    args = parse_args()
    member_to_cluster, cluster_sizes = load_cluster_file(args.cluster_file)
    interpro_map = load_interpro_csv(args.metadata)
    use_case_sets = load_use_case_data(args.generated_fasta)

    cluster_log = args.cluster_log
    match_log = args.match_log

    # Clear log files if they exist
    open(cluster_log, "w").close()
    open(match_log, "w").close()

    results = []
    for root, _, files in os.walk(args.db_folder):
        for filename in files:
            if not filename.endswith(".fasta"):
                continue
            fasta_path = os.path.join(root, filename)
            print(f"Processing {fasta_path}...")
            family_name, cluster_count, avg_length, tag, seq_set = analyze_fasta_file(
                fasta_path,
                member_to_cluster,
                cluster_sizes,
                use_case_sets,
                cluster_log,
                match_log,
            )
            interpro = interpro_map.get(family_name, {})
            row = {
                "family": family_name,
                "interpro_id": interpro.get("interpro_id", ""),
                "db": interpro.get("db", ""),
                "total_sequences": len(seq_set),
                "cluster_count": cluster_count,
                "avg_length": round(avg_length, 2),
                "tag": tag,
            }
            results.append(row)

    # Write final metadata CSV
    fieldnames = [
        "family",
        "interpro_id",
        "db",
        "total_sequences",
        "cluster_count",
        "avg_length",
        "tag",
    ]
    with open(args.output, "w", newline="") as out_csv:
        writer = csv.DictWriter(out_csv, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nMetadata written to {args.output}")
    print(f"Cluster log written to {cluster_log}")
    print(f"Match log written to {match_log}")


if __name__ == "__main__":
    main()
