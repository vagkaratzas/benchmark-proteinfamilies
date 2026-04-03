#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
import argparse


def main(input_file, output_file):
    # Load the data
    df = pd.read_csv(input_file, sep="\t")

    # Define similarity thresholds
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    db_layers = ["hamap", "ncbifam", "panther", "pfam"]

    # Count entries ≥ each threshold, grouped by db_layer
    counts = {
        thr: df[df["similarity_score"] >= thr]["db_layer"].value_counts()
        for thr in thresholds
    }

    # Create a DataFrame for plotting
    plot_df = pd.DataFrame(counts).fillna(0).astype(int)
    plot_df = plot_df.reindex(db_layers)  # Ensure consistent db_layer order

    # Plotting
    colors = {
        "hamap": "#1f77b4",
        "ncbifam": "#ff7f0e",
        "panther": "#2ca02c",
        "pfam": "#d62728",
    }

    plot_df.T.plot(kind="bar", stacked=True, color=[colors[db] for db in plot_df.index])

    plt.xlabel("Jaccard similarity score threshold")
    plt.ylabel("Number of produced families that match original families")
    plt.title("Entries by similarity threshold and database")
    plt.xticks(rotation=0)
    plt.legend(title="DB")
    plt.tight_layout()

    # Save to PNG
    plt.savefig(output_file, dpi=300)
    print(f"Plot saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate similarity score barplot by db_layer."
    )
    parser.add_argument(
        "--input_file", required=True, help="Path to the input TSV file."
    )
    parser.add_argument(
        "--output_file", required=True, help="Path to save the output PNG file."
    )
    args = parser.parse_args()
    main(args.input_file, args.output_file)
