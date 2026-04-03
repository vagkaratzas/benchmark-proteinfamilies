# Plan: Benchmark-Proteinfamilies Pipeline Overhaul

## Context

The benchmark-proteinfamilies pipeline currently has a `pre` mode (sample InterPro families + add decoys into a FASTA) and a `post` mode (analyze reconstruction quality). The post mode is tightly coupled to nf-core/proteinfamilies outputs (hardcoded mmseqs TSV, `.fasta.gz` generated families, `.fas.gz` alignments, 4 hardcoded DB layers). The goal is to make it a **generic benchmark framework** where any protein family building tool (e.g., nf-core/proteinfamilies, mgnifams, or others) can be evaluated via a standardized samplesheet input. The POST mode should support **multi-run comparative analysis** — a single POST invocation can benchmark multiple tool runs and produce cross-tool comparison stats/plots. Additionally, all Python scripts should be optimized for speed and parallelized where possible.

### Design decisions
- **Multi-run comparative POST**: Samplesheet supports multiple rows (one per tool/run). Each row is processed independently, then a final comparative step aggregates results across runs.
- **`.faa` extension**: PRE outputs switch from `.fasta` to `.faa` to signal amino acid content.
- **Merge CONVERT_SAMPLED_TO_FASTA + COMBINE_DB_FASTA**: Single module outputs both `sampled_fasta/` folder and combined `.faa` in one step.

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

### 6.1 Merge 4 EXTRACT_*_METADATA modules into 1 parameterized module
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
Phase 1 (Samplesheet + Comparative) ──┐
                                        ├── Phase 3 (Optional Investigate) ──┐
Phase 2 (Dynamic DBs) ─────────────────┘                                     ├── Phase 7 (Docs)
                                                                              │
Phase 4 (Format Detection) ──┐                                                ├── Phase 8 (Verification)
                              ├────────────────────────────────────────────────┘
Phase 5 (Performance) ───────┘

Phase 6 (PRE Cleanup) ── independent, can be done in parallel with Phases 1-5
```

---

## Files Summary

### New Files
| File | Purpose |
|------|---------|
| `assets/schema_post_samplesheet.json` | POST samplesheet JSON schema |
| `subworkflows/local/validate_post_samplesheet/main.nf` | Samplesheet parsing subworkflow |
| `modules/local/extract_db_metadata/main.nf` | Unified metadata extraction module |
| `modules/local/extract_db_metadata/environment.yml` | Environment for unified module |
| `bin/extract_db_metadata.py` | Unified metadata extraction script |
| `modules/local/prepare_benchmark_fasta/main.nf` | Merged FASTA conversion + combination module |
| `modules/local/prepare_benchmark_fasta/environment.yml` | Environment for merged module |
| `bin/prepare_benchmark_fasta.py` | Merged FASTA script (convert + combine + deduplicate) |
| `modules/local/compare_benchmark_runs/main.nf` | Cross-tool comparative analysis module |
| `modules/local/compare_benchmark_runs/environment.yml` | Environment for comparison module |
| `bin/compare_benchmark_runs.py` | Comparative stats + plots script |
| `assets/test_samplesheet_proteinfamilies.csv` | Example samplesheet |
| `assets/test_samplesheet_mgnifams.csv` | Example samplesheet |
| `assets/test_samplesheet_comparative.csv` | Multi-tool example samplesheet |

### Key Files to Modify
| File | Change |
|------|--------|
| `nextflow.config` | Remove old POST params, add `post_samplesheet`, rename PRE-output params, update description |
| `main.nf` | Update POST call signature |
| `workflows/post.nf` | Samplesheet-driven input, per-sample channel ops, conditional modules, comparative aggregation |
| `workflows/pre.nf` | Unified EXTRACT_DB_METADATA, merged PREPARE_BENCHMARK_FASTA, `.faa` output |
| `bin/calculate_jaccard_similarity.py` | Dynamic DBs, inverted index, multiprocessing |
| `bin/calculate_sequence_stats.py` | Auto-detect format, parallel parsing |
| `bin/investigate_matched_originals.py` | Optional inputs, multi-format, index optimization |
| `bin/calculate_db_sequence_coverage.py` | Dynamic DB layers |
| `bin/calculate_db_family_coverage.py` | Dynamic DB layers |
| `bin/produce_db_stacked_barplot.py` | Dynamic DBs + colors |
| `bin/combine_decoy_fasta.py` | `.faa` extension |
| `bin/filter_valid_candidate_families.py` | Accept variable metadata files |
| `bin/sample_interpro.py` | Pre-computed tree caches |
| `conf/modules.config` | Module name updates, per-sample output paths, new module entries |
| `conf/base.config` | Resource label updates for parallelized modules |

### Files to Delete
| File/Directory | Replaced By |
|----------------|-------------|
| `modules/local/extract_hamap_metadata/` | `modules/local/extract_db_metadata/` |
| `modules/local/extract_ncbifam_metadata/` | `modules/local/extract_db_metadata/` |
| `modules/local/extract_panther_metadata/` | `modules/local/extract_db_metadata/` |
| `modules/local/extract_pfam_metadata/` | `modules/local/extract_db_metadata/` |
| `bin/extract_hamap_metadata.py` | `bin/extract_db_metadata.py` |
| `bin/extract_ncbifam_metadata.py` | `bin/extract_db_metadata.py` |
| `bin/extract_panther_metadata.py` | `bin/extract_db_metadata.py` |
| `bin/extract_pfam_metadata.py` | `bin/extract_db_metadata.py` |
| `modules/local/convert_sampled_to_fasta/` | `modules/local/prepare_benchmark_fasta/` |
| `modules/local/combine_db_fasta/` | `modules/local/prepare_benchmark_fasta/` |
| `bin/convert_sampled_to_fasta.py` | `bin/prepare_benchmark_fasta.py` |
| `bin/combine_db_fasta.py` | `bin/prepare_benchmark_fasta.py` |
