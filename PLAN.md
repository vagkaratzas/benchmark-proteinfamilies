# Plan: Benchmark-Proteinfamilies Pipeline Overhaul

## Context

The benchmark-proteinfamilies pipeline currently has a `pre` mode (sample InterPro families + add decoys into a FASTA) and a `post` mode (analyze reconstruction quality). The post mode is tightly coupled to nf-core/proteinfamilies outputs (hardcoded mmseqs TSV, `.fasta.gz` generated families, `.fas.gz` alignments, 4 hardcoded DB layers). The goal is to make it a **generic benchmark framework** where any protein family building tool (e.g., nf-core/proteinfamilies, mgnifams, or others) can be evaluated via a standardized samplesheet input. The POST mode should support **multi-run comparative analysis** — a single POST invocation can benchmark multiple tool runs and produce cross-tool comparison stats/plots. Additionally, all Python scripts should be optimized for speed and parallelized where possible.

### Design decisions

- **Multi-run comparative POST**: Samplesheet supports multiple rows (one per tool/run). Each row is processed independently, then a final comparative step aggregates results across runs.
- **`.faa` extension**: PRE outputs switch from `.fasta` to `.faa` to signal amino acid content.
- **Merge CONVERT_SAMPLED_TO_FASTA + COMBINE_DB_FASTA**: Single module outputs both `sampled_fasta/` folder and combined `.faa` in one step.

---

## Phase 0: Reference Database Acquisition

Currently the pipeline requires users to manually download and organize 7 separate databases before running PRE mode. This phase automates that acquisition so a user only needs to point to a cache directory (or let the pipeline download everything fresh).

### Design

- All 7 path params become optional (`null` by default). If a param is `null`, the corresponding download module runs and its output path is used downstream.
- If a local path is supplied, it is used directly (HPC clusters with no internet access still work).
- Downloaded files are stored under `params.db_cache_dir` in version-stamped subdirectories so re-runs skip re-downloading.
- Version params (`interpro_release`, `pfam_version`, `panther_version`) pin which release to fetch.

### 0.1 Update `nextflow.config` params

- [ ] Make all 7 existing DB path params optional: default to `null`
  - `interpro_hierarchy_file`, `id_mapping_file`, `path_to_hamap`, `path_to_ncbifam`, `path_to_panther`, `path_to_pfam`, `path_to_swissprot`
- [ ] Add `db_cache_dir = "${projectDir}/data/reference"` — root directory for all downloaded databases
- [ ] Add version params:
  - `interpro_release = "current"` — resolves to latest InterPro release on EBI FTP
  - `pfam_version = "37.2"`
  - `panther_version = "19.0"`

### 0.2 Create per-database download modules

Each module: checks if the target already exists in `db_cache_dir` before downloading (idempotent).

- [ ] `modules/local/download_interpro/main.nf` + `environment.yml`
  - Downloads `ParentChildTreeFile.txt` and `interpro.xml.gz` from `https://ftp.ebi.ac.uk/pub/databases/interpro/{release}/`
  - Outputs: `interpro_hierarchy_file`, `id_mapping_file`
- [ ] `modules/local/download_hamap/main.nf` + `environment.yml`
  - Downloads HAMAP alignment archive from ExPASy FTP and extracts to `hamap_alignments/`
  - Output: `path_to_hamap` directory
- [ ] `modules/local/download_ncbifam/main.nf` + `environment.yml`
  - Downloads NCBI PGAP HMM library from `https://ftp.ncbi.nlm.nih.gov/hmm/current/`
  - Output: `path_to_ncbifam` directory
- [ ] `modules/local/download_panther/main.nf` + `environment.yml`
  - Downloads PANTHER MSA archive for `panther_version` from PANTHER FTP
  - **Large dataset** (tens of GB): emit a size warning in the log
  - Output: `path_to_panther` directory
- [ ] `modules/local/download_pfam/main.nf` + `environment.yml`
  - Downloads PFAM seed alignments for `pfam_version` from EBI FTP
  - Output: `path_to_pfam` directory
- [ ] `modules/local/download_swissprot/main.nf` + `environment.yml`
  - Downloads `uniprot_sprot.fasta.gz` from UniProt FTP and decompresses
  - Output: `path_to_swissprot` FASTA file

### 0.3 Wire conditional downloads in `workflows/pre.nf`

- [ ] For each database param: `if (params.X == null) { DOWNLOAD_X(...) | set { X_path } } else { X_path = Channel.value(file(params.X)) }`
- [ ] Pass resolved paths (downloaded or user-supplied) into all downstream modules unchanged — no other module changes needed
- [ ] Add a preflight check: validate that each resolved path exists and is non-empty; fail early with a descriptive error if a download failed or a user-supplied path is wrong

### 0.4 Update `conf/modules.config`

- [ ] Add `publishDir` entries for all 6 download modules pointing to `${params.db_cache_dir}/{db_name}/{version}/`

---

## Phase 1: POST Samplesheet Infrastructure

### 1.1 Define POST samplesheet format

- [ ] Create `assets/schema_post_samplesheet.json` — nf-core-style JSON schema
- Samplesheet CSV columns:

  ```
  sample,tool,msa_dir,hmm_dir,clustering_tsv,generated_fasta_dir
  ```

  - `sample`: unique identifier for this benchmark run (e.g., `proteinfamilies_default`, `mgnifams_run1`)
  - `tool`: name of the external tool (e.g., `proteinfamilies`, `mgnifams`) — used for labeling in comparative plots
  - `msa_dir`: path to directory of MSA files (any format: `.fas.gz`, `.fasta`, `.aln`, `.sto`, etc.)
  - `hmm_dir`: path to directory of HMM files (for future HMM-based metrics)
  - `clustering_tsv`: **optional** — path to clustering TSV (e.g., mmseqs output). Empty string if N/A
  - `generated_fasta_dir`: **optional** — path to generated family FASTA files. Empty string if N/A

- PRE outputs (`db_fasta`, `decoy_fasta`, `sampled_metadata`, `sampled_fasta_dir`) are shared across all rows → provided as **pipeline params** not per-row samplesheet columns

### 1.2 Create samplesheet validation subworkflow

- [ ] Create `subworkflows/local/validate_post_samplesheet/main.nf`
  - Parse CSV via `Channel.fromPath(...).splitCsv(header: true)`
  - Validate required paths exist
  - Emit structured channel: `tuple(val(meta), path(msa_dir), path(hmm_dir), val(clustering_tsv), val(generated_fasta_dir))` per row
  - `meta` map contains `id` (sample name) and `tool` (tool name)

### 1.3 Update `nextflow.config` params

- [ ] Remove individual POST path params: `path_to_alignments`, `path_to_mmseqs_tsv`, `path_to_generated_fasta`
- [ ] Keep shared PRE-output params (these are the same for all benchmark rows):
  - `path_to_db_fasta` → rename to `pre_db_fasta`
  - `path_to_decoys` → rename to `pre_decoy_fasta`
  - `path_to_sampled_metadata` → rename to `pre_sampled_metadata`
  - `path_to_sampled_fasta_folder` → rename to `pre_sampled_fasta_dir`
- [ ] Add `post_samplesheet = null` parameter
- [ ] Keep `jaccard_similarity_threshold = 0.5`

### 1.4 Rewire `main.nf` and `workflows/post.nf`

- [ ] `main.nf`: Change POST call to pass `params.post_samplesheet`, shared PRE-output params, and `params.jaccard_similarity_threshold`
- [ ] `workflows/post.nf`:
  - Replace 8 `take:` params with: `samplesheet`, `pre_db_fasta`, `pre_decoy_fasta`, `pre_sampled_metadata`, `pre_sampled_fasta_dir`, `jaccard_similarity_threshold`
  - Parse samplesheet → channel of `(meta, msa_dir, hmm_dir, clustering_tsv, generated_fasta_dir)` tuples
  - Run all per-sample modules via `.map` / channel operations so each sample row is processed independently
  - After per-sample modules complete, add a **comparative aggregation step** (Phase 1.5)

### 1.5 Add comparative aggregation module

- [ ] Create `modules/local/compare_benchmark_runs/main.nf` + `bin/compare_benchmark_runs.py`
  - Collects per-sample Jaccard results, coverage stats, decoy stats
  - Produces:
    - **Cross-tool comparison table** (CSV): side-by-side metrics per tool
    - **Comparative bar/violin plots**: Jaccard distributions per tool, family coverage per tool
    - **Comparative stacked barplot**: Same as current but with tool-grouped bars
  - Only runs if >1 sample in samplesheet; otherwise skips
- [ ] Update `conf/modules.config` with publishing path: `${params.outdir}/post/comparison/`

---

## Phase 2: Dynamic DB Layer Detection

All scripts currently hardcode `db_layers = ["pfam", "panther", "ncbifam", "hamap"]`. Replace with dynamic discovery from `sampled_fasta_dir` subdirectories.

- [ ] `bin/calculate_jaccard_similarity.py` (line 50): Discover `db_layers` via `os.listdir(original_base_dir)` filtering for directories
- [ ] `bin/calculate_db_family_coverage.py` (line 28): Same dynamic discovery
- [ ] `bin/calculate_db_sequence_coverage.py` (lines 9, 73-78): Build `db_to_ids` and `msa_paths` dynamically from metadata CSV `db` column + subdirectories
- [ ] `bin/produce_db_stacked_barplot.py` (lines 13, 24-29): Derive `db_layers` from input TSV `db_layer` column; generate colors dynamically via `matplotlib.cm.tab10`

---

## Phase 3: Make INVESTIGATE_MATCHED_ORIGINALS Optional

This module depends on mmseqs clustering TSV and generated FASTA — both proteinfamilies-specific.

### 3.1 Script changes

- [ ] `bin/investigate_matched_originals.py`: Make `--cluster_file` and `--generated_fasta` optional (`required=False, default=None`)
  - When `cluster_file` is None: skip cluster analysis, set `cluster_count=0`
  - When `generated_fasta` is None: skip use-case match analysis, set `tag="unknown"`
  - Generalize file extensions: accept `.fasta.gz`, `.fasta`, `.fas.gz`, `.fas`, `.aln.gz`, `.aln`

### 3.2 Workflow changes

- [ ] `workflows/post.nf`: Conditionally run INVESTIGATE_MATCHED_ORIGINALS only when `clustering_tsv` and `generated_fasta_dir` are non-empty in the samplesheet row
- [ ] `modules/local/investigate_matched_originals/main.nf`: Accept optional inputs; use `val` type for paths that may be empty

---

## Phase 4: Alignment Format Auto-Detection

The POST workflow hardcodes `'fas.gz'` as alignment type. Support auto-detection.

- [ ] `bin/calculate_sequence_stats.py`: Add `--alignment_type auto` option; detect format per-file by extension (`.sto` → Stockholm, `.fas.gz`/`.fasta`/`.aln` → FASTA); refactor `parse_alignment_folder` to handle mixed formats
- [ ] `modules/local/calculate_sequence_stats/main.nf`: Pass `'auto'` instead of hardcoded `'fas.gz'`
- [ ] Update output file prefix to generic `alignment_` when using auto-detect

No changes needed for `calculate_jaccard_similarity.py` and `analyze_recruited_decoys.py` (already handle multiple extensions).

---

## Phase 5: Performance Optimizations

### 5.1 `calculate_jaccard_similarity.py` — CRITICAL bottleneck

Currently O(U × O) full-scan, re-parsing original files for every use-case file.

- [ ] **Pre-parse all originals once** into `{(db_layer, basename): set(protein_ids)}`
- [ ] **Build inverted index**: `protein_id → set of (db_layer, family_basename)}`
- [ ] For each use-case file: look up protein IDs in index → find candidate originals → compute Jaccard only for candidates
- [ ] **Add `multiprocessing.Pool`** for parallel use-case file processing
- [ ] Add `--num_workers` arg (default: `os.cpu_count()`)
- [ ] Update module label from `process_single` to `process_medium` in `modules/local/calculate_jaccard_similarity/main.nf`

### 5.2 `investigate_matched_originals.py` — Triple-nested loop

- [ ] **Pre-build inverted index** from use-case data: `protein_id → list(uc_filenames)`
- [ ] For each original family: index-lookup to find candidate use-case files, compute intersection only for candidates
- [ ] Reduces from O(F × UC × avg_size) to O(F × avg_size × index_lookup)

### 5.3 `calculate_sequence_stats.py` — Sequential file I/O

- [ ] Add `concurrent.futures.ProcessPoolExecutor` for parallel alignment file parsing
- [ ] Each file processed independently; aggregate `original_count` + `decoy_count` dicts after
- [ ] Update module label from `process_single` to `process_low`

### 5.4 `sample_interpro.py` — Tree traversal

- [ ] Pre-compute ancestry/descendant/sibling caches during tree construction instead of on-the-fly traversal per sample

### 5.5 Update `conf/base.config`

- [ ] Update resource labels for parallelized modules (jaccard → `process_medium`, seq_stats → `process_low`)

---

## Phase 6: PRE Workflow Cleanup

### 6.1 Merge 4 EXTRACT\_\*\_METADATA modules into 1 parameterized module

- [ ] Create `modules/local/extract_db_metadata/main.nf` + `environment.yml`
- [ ] Create `bin/extract_db_metadata.py` — accepts `--db_type` arg (hamap/ncbifam/panther/pfam); auto-detects input format
- [ ] Update `workflows/pre.nf`: Replace 4 include+call pairs with single include + 4 channel-driven calls
- [ ] Update `bin/filter_valid_candidate_families.py`: Accept variable number of metadata files (collect channel) instead of 4 hardcoded inputs
- [ ] Update `modules/local/filter_valid_candidate_families/main.nf` input signature
- [ ] Update `conf/modules.config`: Replace 4 `withName: 'EXTRACT_*_METADATA'` blocks with 1 `withName: 'EXTRACT_DB_METADATA'`
- [ ] Delete old modules and scripts:
  - `modules/local/extract_hamap_metadata/`
  - `modules/local/extract_ncbifam_metadata/`
  - `modules/local/extract_panther_metadata/`
  - `modules/local/extract_pfam_metadata/`
  - `bin/extract_hamap_metadata.py`, `bin/extract_ncbifam_metadata.py`, `bin/extract_panther_metadata.py`, `bin/extract_pfam_metadata.py`

### 6.2 Merge CONVERT_SAMPLED_TO_FASTA + COMBINE_DB_FASTA into single module

- [ ] Create `modules/local/prepare_benchmark_fasta/main.nf` + `environment.yml`
- [ ] Create `bin/prepare_benchmark_fasta.py` — merges logic from `convert_sampled_to_fasta.py` + `combine_db_fasta.py`
  - Outputs both `sampled_fasta/` directory (per-DB subfolders) AND `combined_db.faa`
  - Single pass: extract per-DB FASTAs → write to subfolders → simultaneously build combined deduplicated FASTA
  - Also produces `updated_sampled_metadata.csv`
- [ ] Update `workflows/pre.nf`: Replace 2 module calls with 1
- [ ] Update `conf/modules.config`: Replace 2 `withName:` blocks with 1 `withName: 'PREPARE_BENCHMARK_FASTA'`
- [ ] Delete old modules and scripts:
  - `modules/local/convert_sampled_to_fasta/`
  - `modules/local/combine_db_fasta/`
  - `bin/convert_sampled_to_fasta.py`
  - `bin/combine_db_fasta.py`

### 6.3 Output `.faa` instead of `.fasta`

- [ ] `bin/combine_decoy_fasta.py`: Change output extension to `.faa` (`combined_decoy.faa`)
- [ ] `modules/local/combine_decoy_fasta/main.nf`: Update output filename to `.faa`
- [ ] New `bin/prepare_benchmark_fasta.py`: Use `.faa` extension for combined output
- [ ] `workflows/pre.nf`: Update any channel references to new filenames
- [ ] `bin/identify_uniprot_decoys.py`: If it references output extensions, update to `.faa`

---

## Phase 7: Configuration & Documentation

- [ ] `conf/modules.config`: Update module names, add entries for new modules (`EXTRACT_DB_METADATA`, `PREPARE_BENCHMARK_FASTA`, `COMPARE_BENCHMARK_RUNS`), remove entries for deleted modules
- [ ] `conf/modules.config`: Add per-sample output paths: `${params.outdir}/post/${meta.id}/` for each POST module so multi-run outputs don't collide
- [ ] `nextflow.config` manifest: Update description to "Benchmark protein family reconstruction tools against curated InterPro families"
- [ ] `CLAUDE.md`: Update architecture description for 3-step framework, document samplesheet format, multi-run comparative analysis
- [ ] `README.md`: Add samplesheet format documentation, usage examples for proteinfamilies and mgnifams outputs, multi-run example
- [ ] Create `assets/test_samplesheet_proteinfamilies.csv` — example with proteinfamilies outputs
- [ ] Create `assets/test_samplesheet_mgnifams.csv` — example with mgnifams outputs
- [ ] Create `assets/test_samplesheet_comparative.csv` — example with both tools for comparative analysis

---

## Phase 8: Verification

- [ ] Run PRE workflow end-to-end → confirm `.faa` outputs, unified metadata extraction, merged FASTA module works
- [ ] Create a single-row POST samplesheet with proteinfamilies outputs → run POST → confirm all per-sample metrics/visualizations generated under `post/{sample_id}/`
- [ ] Create a single-row POST samplesheet with mgnifams outputs (empty `clustering_tsv` + `generated_fasta_dir`) → run POST → confirm pipeline completes, `INVESTIGATE_MATCHED_ORIGINALS` skipped gracefully
- [ ] Create a multi-row POST samplesheet (both tools) → run POST → confirm comparative plots and table generated under `post/comparison/`
- [ ] Benchmark `calculate_jaccard_similarity.py` old vs new on real data — expect 10-100x speedup
- [ ] Verify all output files match expected formats

---

## Dependency Graph

```
Phase 0 (DB Downloads) ── independent, can be done in parallel with Phases 1-6

Phase 1 (Samplesheet + Comparative) ──┐
                                        ├── Phase 3 (Optional Investigate) ──┐
Phase 2 (Dynamic DBs) ─────────────────┘                                     ├── Phase 7 (Docs)
                                                                              │
Phase 4 (Format Detection) ──┐                                                ├── Phase 8 (Verification)
                              ├────────────────────────────────────────────────┘
Phase 5 (Performance) ───────┘

Phase 6 (PRE Cleanup) ── independent, can be done in parallel with Phases 0-5
```

---

## Files Summary

### New Files

| File                                                    | Purpose                                               |
| ------------------------------------------------------- | ----------------------------------------------------- |
| `modules/local/download_interpro/main.nf`               | Download InterPro hierarchy + XML mapping             |
| `modules/local/download_interpro/environment.yml`       | Environment for InterPro download                     |
| `modules/local/download_hamap/main.nf`                  | Download HAMAP alignments                             |
| `modules/local/download_hamap/environment.yml`          | Environment for HAMAP download                        |
| `modules/local/download_ncbifam/main.nf`                | Download NCBI PGAP HMM library                        |
| `modules/local/download_ncbifam/environment.yml`        | Environment for NCBIFAM download                      |
| `modules/local/download_panther/main.nf`                | Download PANTHER MSA files                            |
| `modules/local/download_panther/environment.yml`        | Environment for PANTHER download                      |
| `modules/local/download_pfam/main.nf`                   | Download PFAM seed alignments                         |
| `modules/local/download_pfam/environment.yml`           | Environment for PFAM download                         |
| `modules/local/download_swissprot/main.nf`              | Download UniProt/SwissProt FASTA                      |
| `modules/local/download_swissprot/environment.yml`      | Environment for SwissProt download                    |
| `assets/schema_post_samplesheet.json`                   | POST samplesheet JSON schema                          |
| `subworkflows/local/validate_post_samplesheet/main.nf`  | Samplesheet parsing subworkflow                       |
| `modules/local/extract_db_metadata/main.nf`             | Unified metadata extraction module                    |
| `modules/local/extract_db_metadata/environment.yml`     | Environment for unified module                        |
| `bin/extract_db_metadata.py`                            | Unified metadata extraction script                    |
| `modules/local/prepare_benchmark_fasta/main.nf`         | Merged FASTA conversion + combination module          |
| `modules/local/prepare_benchmark_fasta/environment.yml` | Environment for merged module                         |
| `bin/prepare_benchmark_fasta.py`                        | Merged FASTA script (convert + combine + deduplicate) |
| `modules/local/compare_benchmark_runs/main.nf`          | Cross-tool comparative analysis module                |
| `modules/local/compare_benchmark_runs/environment.yml`  | Environment for comparison module                     |
| `bin/compare_benchmark_runs.py`                         | Comparative stats + plots script                      |
| `assets/test_samplesheet_proteinfamilies.csv`           | Example samplesheet                                   |
| `assets/test_samplesheet_mgnifams.csv`                  | Example samplesheet                                   |
| `assets/test_samplesheet_comparative.csv`               | Multi-tool example samplesheet                        |

### Key Files to Modify

| File                                     | Change                                                                                                                                           |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `nextflow.config`                        | Make DB path params optional, add `db_cache_dir` + version params, remove old POST params, add `post_samplesheet`, rename PRE-output params      |
| `workflows/pre.nf`                       | Conditional download wiring for all 7 DB inputs (Phase 0) + unified EXTRACT_DB_METADATA, merged PREPARE_BENCHMARK_FASTA, `.faa` output (Phase 6) |
| `main.nf`                                | Update POST call signature                                                                                                                       |
| `workflows/post.nf`                      | Samplesheet-driven input, per-sample channel ops, conditional modules, comparative aggregation                                                   |
| `bin/calculate_jaccard_similarity.py`    | Dynamic DBs, inverted index, multiprocessing                                                                                                     |
| `bin/calculate_sequence_stats.py`        | Auto-detect format, parallel parsing                                                                                                             |
| `bin/investigate_matched_originals.py`   | Optional inputs, multi-format, index optimization                                                                                                |
| `bin/calculate_db_sequence_coverage.py`  | Dynamic DB layers                                                                                                                                |
| `bin/calculate_db_family_coverage.py`    | Dynamic DB layers                                                                                                                                |
| `bin/produce_db_stacked_barplot.py`      | Dynamic DBs + colors                                                                                                                             |
| `bin/combine_decoy_fasta.py`             | `.faa` extension                                                                                                                                 |
| `bin/filter_valid_candidate_families.py` | Accept variable metadata files                                                                                                                   |
| `bin/sample_interpro.py`                 | Pre-computed tree caches                                                                                                                         |
| `conf/modules.config`                    | Module name updates, per-sample output paths, new module entries                                                                                 |
| `conf/base.config`                       | Resource label updates for parallelized modules                                                                                                  |

### Files to Delete

| File/Directory                            | Replaced By                              |
| ----------------------------------------- | ---------------------------------------- |
| `modules/local/extract_hamap_metadata/`   | `modules/local/extract_db_metadata/`     |
| `modules/local/extract_ncbifam_metadata/` | `modules/local/extract_db_metadata/`     |
| `modules/local/extract_panther_metadata/` | `modules/local/extract_db_metadata/`     |
| `modules/local/extract_pfam_metadata/`    | `modules/local/extract_db_metadata/`     |
| `bin/extract_hamap_metadata.py`           | `bin/extract_db_metadata.py`             |
| `bin/extract_ncbifam_metadata.py`         | `bin/extract_db_metadata.py`             |
| `bin/extract_panther_metadata.py`         | `bin/extract_db_metadata.py`             |
| `bin/extract_pfam_metadata.py`            | `bin/extract_db_metadata.py`             |
| `modules/local/convert_sampled_to_fasta/` | `modules/local/prepare_benchmark_fasta/` |
| `modules/local/combine_db_fasta/`         | `modules/local/prepare_benchmark_fasta/` |
| `bin/convert_sampled_to_fasta.py`         | `bin/prepare_benchmark_fasta.py`         |
| `bin/combine_db_fasta.py`                 | `bin/prepare_benchmark_fasta.py`         |

---

## Phase 9: Nextflow Best-Practice Improvements

These items are infrastructure and code-quality improvements that should be implemented in parallel with the functional phases above. Each item notes the earliest phase it should land alongside.

### 9.1 Parameter validation with `nf-schema` (alongside Phase 0 + Phase 1)

- [ ] Add `nextflow_schema.json` at the repository root — describes every `params.*` entry with type, description, required flag, and allowed values. Required for `nf-schema` plugin validation at pipeline start.
- [ ] Add the `nf-schema` plugin declaration to `nextflow.config`:
  ```
  plugins { id 'nf-schema@2.x' }
  ```
  and call `validateParameters()` inside the `workflow {}` block in `main.nf`.
- [ ] Replace the ad-hoc `'null'` string defaults (e.g. `path_to_alignments = 'null'`) with true `null` defaults throughout `nextflow.config`; `nf-schema` coerces and validates types correctly when defaults are the right type. **(Phase 1.3 param rename is the natural moment to do this.)**
- [ ] Add `assets/schema_pre_samplesheet.json` alongside the existing `schema_post_samplesheet.json` plan — even though PRE currently uses positional params rather than a samplesheet, having the schema file documents the expected param shapes and makes future samplesheet adoption easier.

### 9.2 `stub` blocks in every local module (alongside Phase 0 + Phase 6)

The nf-core DIAMOND modules already have `stub` blocks. None of the 21 local modules do. Stub blocks enable `nextflow run … -stub` for rapid offline DAG validation without executing any tools.

- [ ] Add `stub:` blocks to all existing local modules — each block should `touch` every declared output file and emit a minimal `versions.yml`. Priority order:
  - [ ] `REMOVE_DUPLICATE_BRANCHES` — stub: `touch parsed_hierarchy.txt`
  - [ ] `EXTRACT_VALID_INTERPRO_IDS` — stub: touch output file(s)
  - [ ] `EXTRACT_CANDIDATE_INTERPRO_FAMILIES` — stub: touch output file(s)
  - [ ] `EXTRACT_HAMAP_METADATA`, `EXTRACT_NCBIFAM_METADATA`, `EXTRACT_PANTHER_METADATA`, `EXTRACT_PFAM_METADATA` — stub each; these are deleted in Phase 6 so stub them now and the replacement `EXTRACT_DB_METADATA` inherits the pattern automatically.
  - [ ] `FILTER_VALID_CANDIDATE_FAMILIES` — stub: touch output file(s)
  - [ ] `SAMPLE_INTERPRO` — stub: touch `log.txt sampled_metadata.csv`
  - [ ] `CONVERT_SAMPLED_TO_FASTA`, `COMBINE_DB_FASTA` — stub each before Phase 6 merges them; the replacement `PREPARE_BENCHMARK_FASTA` must also have a stub from the outset.
  - [ ] `IDENTIFY_UNIPROT_DECOYS` — stub: `touch decoys.fasta`
  - [ ] `COMBINE_DECOY_FASTA` — stub: touch output file
  - [ ] `CALCULATE_SEQUENCE_STATS` — stub: touch the four `${type}_*.txt` outputs
  - [ ] `CALCULATE_DB_SEQUENCE_COVERAGE`, `ANALYZE_RECRUITED_DECOYS`, `CALCULATE_JACCARD_SIMILARITY`, `PRODUCE_DB_STACKED_BARPLOT`, `CALCULATE_DB_FAMILY_COVERAGE`, `GET_SIZE_DISTRIBUTIONS`, `INVESTIGATE_MATCHED_ORIGINALS` — stub each
- [ ] Add stubs to all 6 new Phase 0 download modules (`DOWNLOAD_INTERPRO` etc.) from the moment they are created — download modules are the most disruptive to test without stubs.
- [ ] Add stubs to all Phase 1 + Phase 6 new modules (`COMPARE_BENCHMARK_RUNS`, `EXTRACT_DB_METADATA`, `PREPARE_BENCHMARK_FASTA`) from the moment they are created.

### 9.3 `tag` directives on all local processes (alongside Phase 0 + Phase 6)

`tag` makes the Nextflow execution log and Tower/Seqera Platform task list human-readable. The nf-core DIAMOND modules use `tag "$meta.id"`. All local modules lack a `tag` directive.

- [ ] Add `tag` to every existing local module. For modules that already receive a `meta` map (e.g. `IDENTIFY_UNIPROT_DECOYS` takes `tuple val(meta), path(hits)`) use `tag "$meta.id"`. For single-path input modules use a descriptive literal or a derivable value such as the input filename:
  - `REMOVE_DUPLICATE_BRANCHES` — `tag "interpro_hierarchy"`
  - `EXTRACT_VALID_INTERPRO_IDS` — `tag "interpro"`
  - `EXTRACT_CANDIDATE_INTERPRO_FAMILIES` — `tag "interpro"`
  - `EXTRACT_HAMAP_METADATA` etc. — `tag "hamap"` / `"ncbifam"` / `"panther"` / `"pfam"`
  - `FILTER_VALID_CANDIDATE_FAMILIES` — `tag "interpro"`
  - `SAMPLE_INTERPRO` — `tag "interpro"`
  - `CONVERT_SAMPLED_TO_FASTA`, `COMBINE_DB_FASTA`, `COMBINE_DECOY_FASTA` — `tag "pre"`
  - `IDENTIFY_UNIPROT_DECOYS` — `tag "$meta.id"` (already receives meta)
  - All POST modules — `tag "$meta.id"` once Phase 1 introduces the `meta` map per samplesheet row; use `tag "post"` in the interim.
- [ ] All Phase 0 download modules created in Phase 0 must include a `tag` from the outset (e.g. `tag "interpro_${params.interpro_release}"`).
- [ ] Phase 1 samplesheet refactor is the natural point to wire `meta.id` tags into POST modules.

### 9.4 `meta` map convention and `tuple val(meta), ...` channel pattern (alongside Phase 1)

Currently most local modules take bare `path` inputs. The nf-core DIAMOND modules and `IDENTIFY_UNIPROT_DECOYS` already use `tuple val(meta), path(...)`. Consistent use of the meta map is essential for multi-sample POST support introduced in Phase 1.

- [ ] Phase 1 samplesheet subworkflow (`validate_post_samplesheet`) must emit `tuple val(meta), ...` channels — `meta` map must contain at minimum `id` (sample name) and `tool` (tool label). Document the full meta-map keys in `CLAUDE.md`.
- [ ] All POST modules refactored in Phases 1–4 must be updated to accept `tuple val(meta), path(...)` inputs and propagate `meta` through outputs so downstream `publishDir` paths can use `${meta.id}`.
- [ ] In `conf/modules.config`, update every POST `publishDir` path to include `${meta.id}` once Phase 1 lands (this is already called out in Phase 7 but should be treated as a meta-map concern, not just a config concern).
- [ ] In `workflows/pre.nf`, the inline `meta` map created for `DIAMOND_MAKEDB` (line 68–70: `[[id: 'combined_db_fasta'], file]`) is correct; ensure any new PRE modules follow the same pattern.

### 9.5 `storeDir` for reference database download modules (alongside Phase 0)

`storeDir` is the correct Nextflow directive for content-addressed caching of files that should persist beyond a single run and never be re-computed if the cached file already exists — exactly the semantics needed for the Phase 0 database downloads.

- [ ] Use `storeDir "${params.db_cache_dir}/<db_name>/<version>"` in each download module instead of `publishDir`. This means Nextflow itself manages the cache-hit check; the pipeline does not need manual `if (file.exists())` logic in the workflow script.
- [ ] Set `errorStrategy 'retry'` and `maxRetries 3` on all download modules — network failures are transient and retrying is always safe for idempotent downloads.
- [ ] Add label `error_retry` (already defined in `conf/base.config`) to all download modules so the retry policy is inherited automatically.
- [ ] Document in `CLAUDE.md` that `--db_cache_dir` is a persistent store and must not be placed inside `work/` or `outdir/`.

### 9.6 Software version tracking with `CUSTOM_DUMPSOFTWAREVERSIONS` (alongside Phase 7)

All local modules already emit `versions.yml` but nothing aggregates them into a pipeline-level version report. The nf-core pattern uses the `CUSTOM_DUMPSOFTWAREVERSIONS` module (from `nf-core/modules`) to collate and publish a single `software_versions.yml` at the end of the run.

- [ ] Add `modules/nf-core/custom/dumpsoftwareversions/` (pull via `nf-core modules install custom/dumpsoftwareversions`).
- [ ] In both `workflows/pre.nf` and `workflows/post.nf`, collect all `*.out.versions` channels with `.mix()` and pass to `CUSTOM_DUMPSOFTWAREVERSIONS`.
- [ ] Add `withName: 'CUSTOM_DUMPSOFTWAREVERSIONS'` block in `conf/modules.config` with `publishDir` pointing to `${params.outdir}/pipeline_info/`.
- [ ] This is a Phase 7 (Configuration & Documentation) item but should be done before Phase 8 verification so version provenance is captured in the test runs.

### 9.7 `nf-test` for module and workflow testing (alongside Phase 8)

There are no tests of any kind in the repository. nf-test is the standard testing framework for Nextflow DSL2 and is required for nf-core module submission.

- [ ] Initialize nf-test: `nf-test init` at the repository root (creates `nf-test.config`).
- [ ] Write module-level tests for the highest-value modules first:
  - [ ] `tests/modules/local/sample_interpro/main.nf.test` — validates correct CSV output structure and log generation.
  - [ ] `tests/modules/local/calculate_jaccard_similarity/main.nf.test` — validates that similarity scores fall in [0, 1] and output CSV has expected columns.
  - [ ] `tests/modules/local/extract_db_metadata/main.nf.test` — once Phase 6 creates it; test all four `--db_type` variants.
  - [ ] `tests/modules/local/prepare_benchmark_fasta/main.nf.test` — once Phase 6 creates it; verify both output paths are produced.
- [ ] Write workflow-level stub tests:
  - [ ] `tests/workflows/pre/main.nf.test` — use `-stub` profile with minimal fixture files; validates DAG connectivity and output directory structure without any real computation.
  - [ ] `tests/workflows/post/main.nf.test` — same approach with a single-row test samplesheet fixture.
- [ ] Create `tests/` directory with `nextflow.config` that enables the `test` profile pointing to small fixture files in `tests/fixtures/`.
- [ ] Add `test` profile to `nextflow.config` (minimal resources: 1 CPU, 2 GB RAM, no time limit) so CI can run without HPC.
- [ ] Add small fixture files under `tests/fixtures/` (tiny hierarchy file, small FASTA, minimal alignment folder) so tests run in seconds.

### 9.8 `PIPELINE_INITIALISATION` and `PIPELINE_COMPLETION` subworkflows (alongside Phase 7)

nf-core pipelines wrap startup validation and completion notification in dedicated subworkflows. Adding these makes future nf-core compatibility straightforward.

- [ ] Create `subworkflows/local/pipeline_initialisation/main.nf`:
  - Calls `validateParameters()` (from `nf-schema`).
  - Validates `params.workflow_mode` is one of `['pre', 'post']`; fails with a descriptive error otherwise.
  - Validates `params.outdir` is set.
  - Logs pipeline name, version, and parameter summary via `log.info`.
- [ ] Create `subworkflows/local/pipeline_completion/main.nf`:
  - Logs completion message with duration and output directory.
  - Optionally sends a completion email if `params.email` is set (nf-core pattern).
- [ ] Wire both subworkflows into the top-level `workflow {}` block in `main.nf` — initialisation before the mode branch, completion in an `onComplete` or terminal channel.
- [ ] Add `params.email = null` and `params.hook_url = null` to `nextflow.config` (no-op by default, enables Tower notification hooks).

### 9.9 `manifest` block completeness and Seqera Platform integration (alongside Phase 7)

- [ ] `nextflow.config` manifest block additions:
  - [ ] Add `doi` field once the pipeline has a publication or Zenodo DOI.
  - [ ] Update `description` to match the new generic benchmark framing from Phase 7 (currently says "nf-core/proteinfamilies" specifically).
  - [ ] Confirm `nextflowVersion = '!>=24.04.2'` is still the minimum required; bump if any Phase 0–8 feature requires a newer version.
- [ ] Add `tower.yml` at the repository root for Seqera Platform workspace configuration:
  ```yaml
  reports:
    - display: "Jaccard similarity report"
      file: "post/**/jaccard_similarities.csv"
    - display: "Decoy stats"
      file: "post/**/decoy_stats.csv"
    - display: "Software versions"
      file: "pipeline_info/software_versions.yml"
  ```
- [ ] Add a `seqera` profile to `nextflow.config` that sets `tower.enabled = true` and any workspace-level resource overrides, so users running on Seqera Platform can activate it with `-profile seqera`.

### 9.10 Container pinning with SHA digests (ongoing, enforce in Phase 6 + Phase 0)

- [ ] Audit all local module container declarations. Several modules (e.g. `SAMPLE_INTERPRO`) use bare `biocontainers/pandas:1.4.3` Docker tags without SHA digests — these are mutable and can silently change. The Wave/community registry URLs used in other modules (e.g. `CALCULATE_JACCARD_SIMILARITY`, `REMOVE_DUPLICATE_BRANCHES`) already use SHA blob references, which is correct.
  - [ ] `SAMPLE_INTERPRO`: replace `biocontainers/pandas:1.4.3` with a SHA-pinned community.wave.seqera.io URL equivalent (or lock the digest with `@sha256:...`).
  - [ ] `modules/nf-core/diamond/makedb` uses `depot.galaxyproject.org/singularity/diamond:2.1.8` while `blastp` uses `2.1.11` — align both to the same DIAMOND version.
- [ ] All Phase 0 download modules must use SHA-pinned containers from the moment they are created — download tools like `wget`/`curl` exist in many base images; pin to a specific community.wave.seqera.io SHA blob.
- [ ] Add a note to `CLAUDE.md` explaining the container pinning convention used in this repository (community.wave.seqera.io SHA blobs for local modules, depot.galaxyproject.org for nf-core modules).

### 9.11 `label` consistency and a `process_download` label (alongside Phase 0)

The existing labels (`process_single`, `process_low`, `process_medium`, `process_high`, `process_long`, `process_high_memory`, `error_ignore`, `error_retry`) cover compute-bound work well, but download-heavy processes have different resource profiles: minimal CPU, minimal memory, long wall time, and multiple retries.

- [ ] Add a `process_download` label to `conf/base.config`:
  ```groovy
  withLabel:process_download {
      cpus   = { 1 }
      memory = { 1.GB }
      time   = { 12.h * task.attempt }
      errorStrategy = 'retry'
      maxRetries    = 3
  }
  ```
- [ ] Apply `label 'process_download'` to all 6 Phase 0 download modules.
- [ ] Audit that every local module has exactly one `label` directive; the following modules currently lack an `environment.yml` peer (and may lack a label review): `COMBINE_DECOY_FASTA`, `FILTER_VALID_CANDIDATE_FAMILIES`, `EXTRACT_NCBIFAM_METADATA`, `INVESTIGATE_MATCHED_ORIGINALS`. Verify labels are set and are the correct tier.

### 9.12 `when:` clause standardisation (ongoing)

All local modules already include the nf-core standard `when: task.ext.when == null || task.ext.when` guard. This is correct. The Phase 3 conditional logic for `INVESTIGATE_MATCHED_ORIGINALS` should extend this rather than adding Groovy `if` blocks in the workflow:

- [ ] In Phase 3, set `ext.when` for `INVESTIGATE_MATCHED_ORIGINALS` via `conf/modules.config` based on a channel-level condition rather than an `if/else` block in `workflows/post.nf`. Use the pattern:
  ```groovy
  // in modules.config
  withName: 'INVESTIGATE_MATCHED_ORIGINALS' {
      ext.when = { meta.clustering_tsv != null && meta.generated_fasta_dir != null }
  }
  ```
  so the skip condition is declared in config, not scattered across the workflow script.

### 9.13 Workflow input validation preflight (alongside Phase 0 + Phase 1)

- [ ] In `workflows/pre.nf`, add a preflight `assert` or `error()` block (or a dedicated `subworkflows/local/validate_pre_inputs/main.nf`) that checks: (a) if a DB param is non-null, the resolved `file()` exists and is non-empty; (b) `params.num_per_db > 0`; (c) `params.min_membership > 0`; (d) `params.num_decoys > 0`. This is listed in Phase 0.3 but should be implemented as a reusable validation subworkflow rather than inline guards.
- [x] Fix the typo `params.interpo_hierarchy_file` (line 14 of `main.nf`) — should be `params.interpro_hierarchy_file`. This is a silent bug present today: the PRE workflow receives `null` for the hierarchy file if the correct param name is used on the CLI.

### Summary Table

| Sub-phase | Key deliverable                                                    | Implement alongside |
| --------- | ------------------------------------------------------------------ | ------------------- |
| 9.1       | `nextflow_schema.json` + `nf-schema` plugin + true `null` defaults | Phase 0 / Phase 1   |
| 9.2       | `stub:` blocks in all 21 local modules + all new modules           | Phase 0 / Phase 6   |
| 9.3       | `tag` directive on all local processes                             | Phase 0 / Phase 6   |
| 9.4       | `meta` map + `tuple val(meta), ...` pattern in POST modules        | Phase 1             |
| 9.5       | `storeDir` + `error_retry` label on download modules               | Phase 0             |
| 9.6       | `CUSTOM_DUMPSOFTWAREVERSIONS` aggregation                          | Phase 7             |
| 9.7       | `nf-test` initialisation + module + workflow tests                 | Phase 8             |
| 9.8       | `PIPELINE_INITIALISATION` + `PIPELINE_COMPLETION` subworkflows     | Phase 7             |
| 9.9       | `manifest` doi/description + `tower.yml` + `seqera` profile        | Phase 7             |
| 9.10      | SHA-pinned containers; align DIAMOND versions                      | Phase 0 / Phase 6   |
| 9.11      | `process_download` label + label audit across all modules          | Phase 0             |
| 9.12      | `ext.when` in config for conditional modules (Phase 3)             | Phase 3             |
| 9.13      | PRE input validation subworkflow + fix `interpo_` typo             | Phase 0 / Phase 1   |
