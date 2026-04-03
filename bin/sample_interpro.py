#!/usr/bin/env python3

import argparse
import pandas as pd
import re
from pathlib import Path


class Node:
    def __init__(self, ipr_id, label=None):
        self.ipr_id = ipr_id
        self.label = label
        self.parent = None
        self.children = []
        self.depth = 0

    def add_child(self, child_node):
        self.children.append(child_node)
        child_node.parent = self
        child_node.depth = self.depth + 1

    def get_descendants(self):
        descendants = set()
        stack = self.children[:]
        while stack:
            node = stack.pop()
            descendants.add(node.ipr_id)
            stack.extend(node.children)
        return descendants

    def get_siblings(self):
        if not self.parent:
            return set()
        return {sibling.ipr_id for sibling in self.parent.children if sibling != self}

    def get_direct_parent(self):
        return self.parent.ipr_id if self.parent else None

    def get_ancestors(self):
        ancestors = set()
        current = self.parent
        while current:
            ancestors.add(current.ipr_id)
            current = current.parent
        return ancestors


def build_tree_from_text(tree_text):
    root = None
    stack = []
    nodes = {}
    for line in tree_text.strip().splitlines():
        depth = len(re.match(r"^-*", line).group(0)) // 2
        line = re.sub(r"^[-]+", "", line).strip()
        if not line:
            continue
        parts = line.split("::")
        ipr_id = parts[0]
        label = parts[1] if len(parts) > 1 else ""
        node = Node(ipr_id, label)
        nodes[ipr_id] = node

        if depth == 0:
            root = node
        else:
            parent = stack[depth - 1]
            parent.add_child(node)
        if len(stack) <= depth:
            stack.append(node)
        else:
            stack[depth] = node
    return root, nodes


def filter_by_minimum_membership(df, min_membership):
    return df[df["protein_count"] >= min_membership].copy()


def log_selection(logfile, picked, removed):
    with open(logfile, "a") as f:
        f.write(f"PICKED: {picked}\n")
        for kind, entries in removed.items():
            f.write(f"REMOVED {kind.upper()}: {sorted(entries)}\n")
        f.write("\n")


def sample_entries(df, tree_nodes, num_per_db, logfile):
    selected = set()
    excluded = set()

    db_groups = df.groupby("db")
    samples_per_db = {db: [] for db in db_groups.groups}

    # Work through rounds, one pick per db in each round
    for round_i in range(num_per_db):
        for db, group in db_groups:
            available = group[~group["interpro_id"].isin(excluded)]
            if available.empty:
                continue

            picked_row = available.sample(n=1).iloc[0]
            ipr = picked_row["interpro_id"]
            samples_per_db[db].append(picked_row)
            selected.add(ipr)

            node = tree_nodes.get(ipr)
            if node:
                descendants = node.get_descendants()
                ancestors = node.get_ancestors()
                siblings = node.get_siblings()

                to_remove = descendants | ancestors | siblings | {ipr}
                excluded |= to_remove

                log_selection(
                    logfile,
                    ipr,
                    {
                        "descendants": descendants,
                        "ancestors": ancestors,
                        "siblings": siblings,
                        "self": {ipr},
                    },
                )

    sampled_df = pd.concat([pd.DataFrame(rows) for rows in samples_per_db.values()])
    return sampled_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interpro_file", required=True)
    parser.add_argument("--tree_file", required=True)
    parser.add_argument("--min_membership", type=int, default=25)
    parser.add_argument("--num_per_db", type=int, default=50)
    parser.add_argument("--logfile", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.interpro_file, sep="\t")
    df = filter_by_minimum_membership(df, args.min_membership)

    tree_text = Path(args.tree_file).read_text()
    _, nodes = build_tree_from_text(tree_text)

    Path(args.logfile).write_text("")  # Clear logfile
    sampled = sample_entries(df, nodes, args.num_per_db, args.logfile)
    sampled.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
