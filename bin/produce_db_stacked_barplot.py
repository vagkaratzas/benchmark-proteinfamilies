#!/usr/bin/env python3
"""Stacked barplot of matched vs unmatched curated families per database layer."""

import argparse

import matplotlib.pyplot as plt
import pandas as pd


def main(input_file, output_file):
    df = pd.read_csv(input_file, sep="\t")
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

    if df.empty:
        fig, ax = plt.subplots()
        ax.set_xlabel("Jaccard similarity score threshold")
        ax.set_ylabel("Number of produced families that match original families")
        ax.set_title("Entries by similarity threshold and database")
        ax.text(0.5, 0.5, "No matches", ha="center", va="center")
        ax.set_xticks([])
        ax.set_yticks([])
        plt.tight_layout()
        plt.savefig(output_file, dpi=300)
        return
    else:
        layers = sorted(df["db_layer"].dropna().unique())

    counts = {
        thr: df[df["similarity_score"] >= thr]["db_layer"].value_counts()
        for thr in thresholds
    }
    plot_df = pd.DataFrame(counts).fillna(0).astype(int).reindex(layers, fill_value=0)

    cmap = plt.get_cmap("tab10")
    colors = [cmap(index % cmap.N) for index, _layer in enumerate(layers)]

    ax = plot_df.T.plot(kind="bar", stacked=True, color=colors)
    ax.set_xlabel("Jaccard similarity score threshold")
    ax.set_ylabel("Number of produced families that match original families")
    ax.set_title("Entries by similarity threshold and database")
    ax.set_xticklabels([str(thr) for thr in thresholds], rotation=0)
    ax.legend(title="DB")
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)


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
