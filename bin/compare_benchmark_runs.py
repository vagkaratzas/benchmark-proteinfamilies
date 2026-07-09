#!/usr/bin/env python3
"""Compare scorecards and metric distributions across POST samplesheet rows.

The ranking is EXPLORATORY. Rank 1 is the highest composite_exploratory value;
sorting is descending by composite_exploratory, then ascending by sample/tool to
make ties deterministic.
"""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect per-run scorecards and plots across benchmark rows."
    )
    parser.add_argument("--scorecards", nargs="+", required=True)
    parser.add_argument("--family_metrics", nargs="+", required=True)
    parser.add_argument("--split_merge_summaries", nargs="+", required=True)
    parser.add_argument("--db_coverage_files", nargs="*", default=[])
    parser.add_argument("--output_csv", required=True)
    parser.add_argument("--mqc_csv", default="benchmark_comparison_mqc.csv")
    parser.add_argument(
        "--f1_jaccard_plot",
        default="f1_jaccard_distribution_mqc.png",
    )
    parser.add_argument(
        "--db_coverage_plot",
        default="db_layer_coverage_mqc.png",
    )
    return parser.parse_args()


def read_table(path, delimiter="\t"):
    with Path(path).open(newline="") as handle:
        return list(
            csv.DictReader(
                (line for line in handle if not line.startswith("#")),
                delimiter=delimiter,
            )
        )


def rows_from_files(paths, delimiter="\t"):
    rows = []
    for path in paths:
        rows.extend(read_table(path, delimiter=delimiter))
    return rows


def comparison_frame(scorecards, split_summaries):
    score_df = pd.DataFrame(scorecards)
    split_df = pd.DataFrame(split_summaries)
    if score_df.empty:
        return pd.DataFrame()

    for column in [
        "composite_exploratory",
        "mean_f1",
        "family_coverage",
        "sequence_coverage",
        "no_decoy_recruitment",
        "decoy_recruitment_rate",
        "no_split_merge",
        "split_merge_rate",
        "parent_id_coverage_aux",
    ]:
        if column in score_df:
            score_df[column] = pd.to_numeric(score_df[column])

    if not split_df.empty:
        keep = [
            "sample",
            "tool",
            "n_splits",
            "n_merges",
            "n_one_to_one",
            "n_vanished",
            "n_spurious",
            "n_cross_db_matches",
            "n_merges_excl_overlapping_originals",
        ]
        split_df = split_df[[column for column in keep if column in split_df]]
        merged = score_df.merge(split_df, on=["sample", "tool"], how="left")
    else:
        merged = score_df

    merged = merged.sort_values(
        ["composite_exploratory", "sample", "tool"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    merged.insert(0, "rank_exploratory_desc", range(1, len(merged) + 1))
    return merged


def write_comparison(path, frame):
    with Path(path).open("w", newline="") as handle:
        handle.write(
            "# EXPLORATORY ranking: rank 1 is highest composite_exploratory; "
            "sort=descending composite_exploratory\n"
        )
        frame.to_csv(handle, index=False)


def write_mqc_csv(path, frame):
    frame.to_csv(path, index=False)


def blank_plot(path, message):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.text(0.5, 0.5, message, ha="center", va="center")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_f1_jaccard(rows, output_path):
    frame = pd.DataFrame(rows)
    if frame.empty:
        blank_plot(output_path, "No family metric rows")
        return

    frame["f1"] = pd.to_numeric(frame["f1"])
    frame["jaccard"] = pd.to_numeric(frame["jaccard"])
    tools = sorted(frame["tool"].dropna().unique())
    if not tools:
        blank_plot(output_path, "No tools")
        return

    fig, axes = plt.subplots(1, 2, figsize=(max(8, len(tools) * 1.8), 4))
    for ax, metric, title in [
        (axes[0], "f1", "F1 distribution"),
        (axes[1], "jaccard", "Jaccard distribution"),
    ]:
        data = [
            frame.loc[frame["tool"] == tool, metric].dropna().tolist() for tool in tools
        ]
        ax.boxplot(data, labels=tools, showfliers=False)
        ax.set_title(title)
        ax.set_ylabel(metric)
        ax.set_ylim(0, 1.05)
        ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_db_coverage(rows, output_path):
    frame = pd.DataFrame(rows)
    if frame.empty:
        blank_plot(output_path, "No db-layer coverage rows")
        return

    frame["matched"] = pd.to_numeric(frame["matched"])
    grouped = (
        frame.groupby(["tool", "db"], as_index=False)["matched"]
        .sum()
        .pivot(index="tool", columns="db", values="matched")
        .fillna(0)
        .sort_index()
    )
    if grouped.empty:
        blank_plot(output_path, "No matched db-layer coverage")
        return

    ax = grouped.plot(kind="bar", stacked=True, figsize=(max(7, len(grouped) * 1.6), 4))
    ax.set_xlabel("tool")
    ax.set_ylabel("matched universe_id count")
    ax.set_title("DB-layer sequence coverage")
    ax.tick_params(axis="x", rotation=30)
    ax.legend(title="db_layer", bbox_to_anchor=(1.02, 1), loc="upper left")
    ax.figure.tight_layout()
    ax.figure.savefig(output_path, dpi=150)
    plt.close(ax.figure)


def main():
    args = parse_args()
    scorecards = rows_from_files(args.scorecards)
    family_metrics = rows_from_files(args.family_metrics)
    split_summaries = rows_from_files(args.split_merge_summaries)
    db_coverage = rows_from_files(args.db_coverage_files)

    comparison = comparison_frame(scorecards, split_summaries)
    write_comparison(args.output_csv, comparison)
    write_mqc_csv(args.mqc_csv, comparison)
    plot_f1_jaccard(family_metrics, args.f1_jaccard_plot)
    plot_db_coverage(db_coverage, args.db_coverage_plot)


if __name__ == "__main__":
    main()
