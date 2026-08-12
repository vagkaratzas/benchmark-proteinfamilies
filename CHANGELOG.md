# benchmark-proteinfamilies: Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v2.0.0dev - unreleased

POST rewritten, PRE reworked. Major because every v1.0.0 parameter was renamed or replaced, and POST
now requires PRE artefacts v1.0.0 never produced.

Reason for the rewrite: v1.0.0 scored real tool output as zero without saying so. Metrics were set
intersections on raw ID strings, but tools do not round-trip IDs — on real mgnifams output
`record.id.split("/")[0]` resolved 95 of 486 IDs (80.45% dropped), giving Jaccard 0.0 against every
curated family and reporting it as a legitimate score.

### Breaking

PRE databases now use a uniform `*_db` / `*_latest_link` / `*_version` shape:

| v1.0.0                                              | v2.0.0                                               |
| --------------------------------------------------- | ---------------------------------------------------- |
| `interpo_hierarchy_file` (released name had a typo) | `interpro_hierarchy_db`                              |
| `id_mapping_file`                                   | `interpro_mapping_db`                                |
| `path_to_hamap` / `_ncbifam` / `_panther` / `_pfam` | `hamap_db` / `ncbifam_db` / `panther_db` / `pfam_db` |
| `path_to_swissprot`                                 | `swissprot_db`                                       |

POST takes a samplesheet of many runs instead of one run's paths:

| v1.0.0                                                     | v2.0.0                                          |
| ---------------------------------------------------------- | ----------------------------------------------- |
| `path_to_alignments`                                       | `msa_dir` column in `--post_samplesheet`        |
| `path_to_db_fasta`, `path_to_decoys`                       | `pre_universe_fasta`                            |
| `path_to_sampled_metadata`, `path_to_sampled_fasta_folder` | `pre_sampled_metadata`, `pre_sampled_fasta_dir` |
| `jaccard_similarity_threshold`                             | `match_threshold`                               |

- POST also requires `pre_id_registry` and `pre_universe_sha256`. **A v1.0.0 universe cannot be
  scored by v2.0.0** — rerun PRE.
- Unset path params defaulted to the _string_ `'null'`; now real `null`.
- `--outdir` is required and rejected when empty.
- Output layout: `pre/` and `post/<sample>/`.

### Added

- `id_registry.tsv` and `universe.sha256` from PRE. Registry columns: `universe_id, parent_id,
source_type, db_layer, family, coords, ungapped_len, seq_sha1`. `universe_id` is the comparison
  key for every metric.
- `bin/benchmark_ids.py` — resolves observed IDs via a forward alias index plus an unordered
  coordinate lattice, disambiguating on the observed sequence when candidates tie. Ambiguity is a
  first-class status.
- Samplesheet POST (`sample,tool,msa_dir,clustering_tsv`): many runs per invocation, ranked against
  each other. `clustering_tsv` optional; when present it cross-checks MSA completeness.
- Metrics beyond Jaccard: per-family P/R/F1 (`family_metrics.tsv`), directional within-`db_layer`
  split/merge with an overlap baseline (`split_merge_summary.tsv`, `original_overlap_baseline.tsv`),
  an EXPLORATORY scorecard, and a ranked `benchmark_comparison.csv`.
- Loud ID-drift failure: `max_unmapped_fraction` / `max_ambiguous_fraction` gates, full
  `unmapped.tsv` / `ambiguous.tsv`, and a `universe.sha256` check in every result table.
- On-demand reference databases: six `DOWNLOAD_*` modules fetch any `*_db` left null from its
  `*_latest_link` and publish it under `<outdir>/pre/databases` for reuse.
- `--skip_hamap`, `--skip_ncbifam`, `--skip_panther`, `--skip_pfam`. At least one member database
  must stay enabled; InterPro and SwissProt are never skippable.
- MultiQC report, `--skip_multiqc`.
- `--seed` (default `null`) to reproduce a specific PRE run. Sampling stays nondeterministic by
  design; comparability comes from `universe.sha256`.
- `--min_universe_coverage`, `--min_intersection_size`, `--association_threshold`,
  `--scorecard_weights`.
- nf-core conformance: `nextflow_schema.json` + nf-schema validation, `pipeline_initialisation` /
  `pipeline_completion`, `tag` and `stub:` on every local module, `meta.yml` per module, pinned
  containers, `tower.yml`, `seqera` profile.
- Tests, none in v1.0.0: 51 nf-tests, 10 Python tests, a `benchmark_ids.py` self-check, and three
  offline fixture profiles (`test`, `test_pre`, `test_pre_download`).
- Versions collected on the `versions` topic into `pipeline_info/software_versions.yml`.
- `nextflow lint` as a `pre-commit` hook.

### Changed

- POST is tool-agnostic: `db_layer`s derived from the data instead of a hardcoded
  `["pfam","panther","ncbifam","hamap"]`, and alignment format sniffed from the first non-blank line
  instead of the extension.
- Jaccard pruned with an inverted index and parallelised, replacing an O(U×O) scan that re-parsed
  every original FASTA in its inner loop.
- Four `EXTRACT_*_METADATA` modules merged into one parameterised `EXTRACT_DB_METADATA`.
- Workflows split into `DOWNLOAD_DBS`, `GENERATE_DECOYS`, `SCORE_SAMPLES`, `REPORT_BENCHMARK`.
- Decoy headers cleaned like family headers, so the universe is uniformly pipe-free.

### Fixed

- `calculate_jaccard_similarity.py` reduced IDs with `record.id.split("/")[0]` — handles `/start-end`
  but not `_start_end`, and mangles nested forms like `2632373804_177_299/1-122`. This is the 80.45%
  loss above.
- `investigate_matched_originals.py` filtered on `.fasta.gz` while the tools emit `.faa` / `.fas.gz`,
  so it loaded zero files and tagged every original family `vanished`.
- `combine_decoy_fasta.py` dropped curated members sharing a sequence across databases while
  `sampled_fasta/` still listed them. Its `seq in unique_sequences.values()` test was also O(n²) over
  ~10⁵ sequences; now a dict lookup.
- `convert_sampled_to_fasta.py` deduped on the raw record ID while writing the cleaned one, so `A.B`
  and `A|B` both emitted `A_B` — duplicate universe IDs.
- DIAMOND `makedb` was pinned to 2.1.8 while `blastp` was on 2.1.11.

## v1.0.0 - 2026-04-03

Initial release, accompanying the paper.

<https://github.com/vagkaratzas/benchmark-proteinfamilies/releases/tag/v1.0.0>
