#!/usr/bin/env python3

import pandas as pd
import argparse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze matched and unmatched family size distributions based on similarity results."
    )
    parser.add_argument(
        "--metadata_file",
        required=True,
        help="Path to metadata TSV file (with protein_count, dbkey, etc.).",
    )
    parser.add_argument(
        "--similarity_file", required=True, help="Path to similarity results TSV file."
    )
    parser.add_argument(
        "--output_file", required=True, help="Path to output report file (text format)."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Load input files
    metadata_df = pd.read_csv(args.metadata_file)
    similarity_df = pd.read_csv(args.similarity_file, sep="\t")

    # Get unique matched IDs
    matched_ids = set(similarity_df["original_basename"].unique())

    # Split metadata into matched and unmatched
    matched_df = metadata_df[metadata_df["dbkey"].isin(matched_ids)].copy()
    unmatched_df = metadata_df[~metadata_df["dbkey"].isin(matched_ids)].copy()

    # Open output file
    with open(args.output_file, "w") as out_f:
        # Original distribution
        out_f.write("Original size distribution (protein_count column):\n")
        out_f.write(str(metadata_df["protein_count"].describe()) + "\n\n")

        # Matched distribution
        out_f.write("Matched size distribution (protein_count column):\n")
        out_f.write(str(matched_df["protein_count"].describe()) + "\n\n")

        # Unmatched distribution
        out_f.write("Unmatched size distribution (protein_count column):\n")
        out_f.write(str(unmatched_df["protein_count"].describe()) + "\n\n")

    # Optionally save splits too if you want
    matched_df.to_csv("matched_metadata.tsv", sep="\t", index=False)
    unmatched_df.to_csv("unmatched_metadata.tsv", sep="\t", index=False)


if __name__ == "__main__":
    main()
