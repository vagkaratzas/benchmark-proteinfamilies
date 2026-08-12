# benchmark-proteinfamilies: Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v2.0.0dev - unreleased

A near-total rewrite of POST and a substantial rework of PRE. The headline reason for the major
version is that **v1.0.0 scored real tool output as zero without saying so**: every metric was a set
intersection on raw ID strings, and protein-family tools do not round-trip sequence IDs. Measured
against real mgnifams output, `record.id.split("/")[0]` resolved 95 of 486 IDs — 80.45% silently
dropped — leaving Jaccard at 0.0 against every curated family and reporting that as a legitimate
score. Identity is now recorded by PRE at construction time and resolved by POST through a registry,
and the failure mode is loud.

Every parameter of the v1.0.0 interface was renamed or replaced; see _Breaking changes_ below.

### Breaking changes

PRE database parameters now follow a uniform `*_db` / `*_latest_link` / `*_version` shape:

| v1.0.0                                                            | v2.0.0                                               |
| ----------------------------------------------------------------- | ---------------------------------------------------- |
| `interpo_hierarchy_file` (sic — the released name carried a typo) | `interpro_hierarchy_db`                              |
| `id_mapping_file`                                                 | `interpro_mapping_db`                                |
| `path_to_hamap` / `_ncbifam` / `_panther` / `_pfam`               | `hamap_db` / `ncbifam_db` / `panther_db` / `pfam_db` |
| `path_to_swissprot`                                               | `swissprot_db`                                       |

POST no longer takes one run's paths as parameters; it takes a samplesheet of many runs, plus the
PRE artefacts to score them against:

| v1.0.0                                                     | v2.0.0                                                            |
| ---------------------------------------------------------- | ----------------------------------------------------------------- |
| `path_to_alignments`                                       | `msa_dir` column in `--post_samplesheet`                          |
| `path_to_db_fasta`, `path_to_decoys`                       | `pre_universe_fasta` (+ `pre_id_registry`, `pre_universe_sha256`) |
| `path_to_sampled_metadata`, `path_to_sampled_fasta_folder` | `pre_sampled_metadata`, `pre_sampled_fasta_dir`                   |
| `jaccard_similarity_threshold`                             | `match_threshold`                                                 |

Also breaking:

- POST additionally requires `pre_id_registry` and `pre_universe_sha256`, which v1.0.0 did not
  produce. **A v1.0.0 universe cannot be scored by v2.0.0** — rerun PRE.
- Unset path parameters used to default to the _string_ `'null'`; they are now real `null`.
- `--outdir` is now required and rejected when empty.
- PRE output layout changed: results are published under `pre/`, POST under `post/<sample>/`.

### Added

- **`id_registry.tsv` and `universe.sha256`** emitted by PRE. The registry records
  `universe_id, parent_id, source_type, db_layer, family, coords, ungapped_len, seq_sha1` for every
  sequence in the universe; `universe_id` is the comparison key for every metric.
- **`bin/benchmark_ids.py`** — resolves an observed ID through a forward alias index built from
  registry rows plus an unordered coordinate lattice, disambiguating on the observed sequence
  (`seq_sha1`, then substring containment) when several candidates survive. Ambiguity is a
  first-class status, never resolved arbitrarily.
- **Samplesheet-driven POST** (`sample,tool,msa_dir,clustering_tsv`), scoring many tool runs in one
  invocation and ranking them against each other. `clustering_tsv` is optional and, when present,
  cross-checks MSA completeness to detect a seed-MSA misconfiguration.
- **New metrics**, because Jaccard alone cannot tell a tool that splits one curated family into five
  from one that merges five into one: per-family precision/recall/F1 (`family_metrics.tsv`),
  directional within-`db_layer` split/merge topology with an original-overlap baseline
  (`split_merge_summary.tsv`, `original_overlap_baseline.tsv`), an EXPLORATORY composite scorecard,
  and a ranked cross-run comparison (`benchmark_comparison.csv`).
- **Loud failure on ID drift**: `unmapped_fraction` / `ambiguous_fraction` gates
  (`max_unmapped_fraction`, `max_ambiguous_fraction`), full `unmapped.tsv` / `ambiguous.tsv` per run,
  and a `universe.sha256` check recorded in every result table so a samplesheet cannot be scored
  against a universe it was not built from.
- **On-demand reference databases.** Six `DOWNLOAD_*` modules fetch any database left null from its
  `*_latest_link`, and publish it under `<outdir>/pre/databases` for reuse via `*_db`.
- **Skippable member databases** — `--skip_hamap`, `--skip_ncbifam`, `--skip_panther`, `--skip_pfam`.
  At least one must remain enabled; InterPro and SwissProt are never skippable.
- **MultiQC report** and a `--skip_multiqc` toggle.
- **`--seed`** (default `null`) to reproduce a specific PRE run on demand. Sampling stays
  nondeterministic by design; cross-run comparability comes from `universe.sha256`, not from seeding.
- `--min_universe_coverage` (opt-in hard coverage gate), `--min_intersection_size`,
  `--association_threshold`, `--scorecard_weights`.
- **nf-core conformance**: `nextflow_schema.json` with nf-schema `validateParameters()`,
  `pipeline_initialisation` / `pipeline_completion` subworkflows, a `tag` and a `stub:` block on
  every local module, `meta.yml` per module, pinned containers, `tower.yml`, and a `seqera` profile.
- **Tests**, none of which existed in v1.0.0: 51 nf-tests (real + stub per module, plus workflow
  stubs), 10 Python tests, and a `benchmark_ids.py` self-check. Three offline profiles run the whole
  thing over committed synthetic fixtures: `test` (POST), `test_pre`, `test_pre_download`.
- **Versions** collected on the global `versions` topic into `pipeline_info/software_versions.yml`.
- `pre-commit` configuration including `nextflow lint`.

### Changed

- **POST is now tool-agnostic**: database layers are derived from the data rather than a hardcoded
  `["pfam","panther","ncbifam","hamap"]` list, and alignment format is detected by sniffing the first
  non-blank line rather than trusting the file extension.
- **Jaccard is pruned with an inverted index** and parallelised, replacing an O(U×O) scan that
  re-parsed every original FASTA inside its inner loop.
- The four `EXTRACT_*_METADATA` modules merged into one parameterised `EXTRACT_DB_METADATA`.
- Workflows split into `DOWNLOAD_DBS`, `GENERATE_DECOYS`, `SCORE_SAMPLES` and `REPORT_BENCHMARK`
  subworkflows.
- Decoy headers are cleaned consistently with family headers, so the universe is uniformly pipe-free.
- Documentation consolidated into `README.md` (users) and `AGENTS.md` (developers).

### Fixed

Bugs that were present in the released v1.0.0:

- **The 80.45% ID-resolution failure described above** — the reason for this release.
  `calculate_jaccard_similarity.py` reduced every observed ID with `record.id.split("/")[0]`, which
  handles a trailing `/start-end` but not `_start_end`, and mangles nested forms such as
  `2632373804_177_299/1-122`.
- `investigate_matched_originals.py` loaded zero generated FASTAs — it hard-filtered on `.fasta.gz`
  while the reference tools emit `.faa` / `.fas.gz` — so every original family was tagged `vanished`.
- `combine_decoy_fasta.py` dropped legitimate curated family members that share a sequence across
  databases, removing them from the universe while `sampled_fasta/` still listed them. The offending
  membership test (`seq in unique_sequences.values()`) was also a linear scan inside a per-record
  loop, i.e. O(n²) over ~10⁵ sequences; it is now a dict lookup.
- The dedupe in `convert_sampled_to_fasta.py` keyed on the raw record ID while writing the cleaned
  one, so `A.B` and `A|B` both emitted `A_B` and produced duplicate universe IDs.
- DIAMOND `makedb` was pinned to 2.1.8 while `blastp` was on 2.1.11.

### Removed

- `db_cache_dir` and the `storeDir` reference-database cache, introduced during development and
  never released. Downloaded databases are published like any other output instead; point the
  matching `*_db` at the published directory to reuse them.
- `PLAN.md`, `PLAN-REVIEW-LOG.md` and `REPORT.md`. Their durable conclusions were folded into
  `README.md` and `AGENTS.md`; the rest was process narrative that git history already records.

## v1.0.0 - 2026-04-03

Initial release, accompanying the paper.

<https://github.com/vagkaratzas/benchmark-proteinfamilies/releases/tag/v1.0.0>
