# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nextflow DSL2 pipeline that benchmarks [nf-core/proteinfamilies](https://github.com/nf-core/proteinfamilies) by sampling manually curated protein families from InterPro (HAMAP, NCBIFAM, PANTHER, PFAM) and measuring how well they can be reconstructed.

## Running the Pipeline

Requires Nextflow >= 24.04.2. A container/conda profile is required alongside any executor profile.

```bash
# PRE workflow: sample InterPro families and prepare benchmark dataset
nextflow run benchmark-proteinfamilies -c slurm_benchmark.config -profile singularity,slurm --workflow_mode pre -resume

# POST workflow: analyze reconstruction results
nextflow run benchmark-proteinfamilies -c slurm_benchmark.config -profile singularity,slurm --workflow_mode post -resume
```

PRE mode requires a config file with paths to InterPro hierarchy, XML mapping, and database directories (HAMAP, NCBIFAM, PANTHER, PFAM, SwissProt). POST mode requires paths to PRE outputs plus nf-core/proteinfamilies results. See `nextflow.config` for all parameters.

## Architecture

### Two-Mode Design

The pipeline is controlled by `--workflow_mode` (`pre` or `post`), routed in `main.nf`:

- **`workflows/pre.nf`** - Parses InterPro hierarchy, extracts metadata from 4 protein family databases in parallel, samples families respecting tree structure, converts to FASTA, generates decoy sequences via DIAMOND BLASTP against SwissProt. Output: `combined_decoy.fasta` fed into nf-core/proteinfamilies.
- **`workflows/post.nf`** - Compares generated families to originals using Jaccard similarity, calculates sequence/family coverage, analyzes decoy recruitment (false positives), produces visualizations.

### Module Structure

All custom modules live in `modules/local/` (21 modules). Each has `main.nf` and `environment.yml`. nf-core DIAMOND modules are in `modules/nf-core/diamond/`.

### Python Scripts

`bin/` contains 21 Python scripts that implement the core logic, called by Nextflow processes. Key dependencies: BioPython (sequence parsing), pandas (tabular data), matplotlib (plotting). Scripts handle multiple alignment formats (.msa, .aln, .fas, .fasta, with .gz support).

### Configuration

- `nextflow.config` - Global parameters and container/executor profiles
- `conf/base.config` - Process resource labels (process_single through process_high_memory)
- `conf/modules.config` - Per-module output publishing paths and arguments

### Key Parameters

- `min_membership` (default: 25) - minimum proteins per family to be eligible for sampling
- `num_per_db` (default: 50) - number of families sampled per database
- `num_decoys` (default: 10000) - number of decoy sequences from SwissProt
- `jaccard_similarity_threshold` (default: 0.5) - cutoff for matching generated to original families

## NCBIFAM Note

NCBIFAM has two family ID formats: `TIGRxxxxx` and `NFxxxxxx`, with different alignment file structures. Code handling NCBIFAM must account for both.
