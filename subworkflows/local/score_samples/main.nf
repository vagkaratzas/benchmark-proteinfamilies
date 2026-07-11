include { CALCULATE_SEQUENCE_STATS       } from '../../../modules/local/calculate_sequence_stats/main'
include { CALCULATE_DB_SEQUENCE_COVERAGE } from '../../../modules/local/calculate_db_sequence_coverage/main'
include { ANALYZE_RECRUITED_DECOYS       } from '../../../modules/local/analyze_recruited_decoys/main'
include { CALCULATE_JACCARD_SIMILARITY   } from '../../../modules/local/calculate_jaccard_similarity/main'
include { CALCULATE_FAMILY_METRICS       } from '../../../modules/local/calculate_family_metrics/main'
include { ANALYZE_SPLITS_MERGES          } from '../../../modules/local/analyze_splits_merges/main'
include { COMPUTE_SCORECARD              } from '../../../modules/local/compute_scorecard/main'
include { INVESTIGATE_MATCHED_ORIGINALS  } from '../../../modules/local/investigate_matched_originals/main'

//
// Score one tool run against the curated originals. Everything here is per-sample and fans out
// over the samplesheet; nothing compares runs to each other (that is REPORT_BENCHMARK's job).
//
// Every metric is a set intersection on `universe_id` strings resolved through the PRE registry,
// which is why the registry, universe FASTA and checksum are threaded into each module rather
// than each module re-deriving identity from the ID text.
//
workflow SCORE_SAMPLES {

    take:
    samples          // [ meta, msa_dir, clustering_tsv ] per samplesheet row
    registry         // PRE id_registry.tsv
    universe         // PRE combined_decoy.faa
    universe_sha256  // PRE universe.sha256
    metadata         // PRE sampled_metadata.csv
    sampled_fasta    // PRE sampled_fasta/
    benchmark_ids    // bin/benchmark_ids.py, staged as a library
    post_common      // bin/post_common.py, staged as a library
    match_threshold
    association_threshold
    max_unmapped_fraction
    max_ambiguous_fraction
    min_intersection_size
    min_universe_coverage
    scorecard_weights

    main:
    // Split the tool's sequences into curated originals / decoys / unknowns. The original
    // counts feed the coverage denominator, so this runs before coverage.
    CALCULATE_SEQUENCE_STATS(
        samples,
        registry,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common
    )

    CALCULATE_DB_SEQUENCE_COVERAGE(
        CALCULATE_SEQUENCE_STATS.out.original_count,
        metadata,
        sampled_fasta,
        registry,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common
    )

    // Decoys have no curated family, so anything a tool recruited from them is a false positive.
    ANALYZE_RECRUITED_DECOYS(
        samples,
        registry,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common
    )

    // Jaccard is symmetric and one-to-one: it says how well families pair up, but it cannot
    // tell a tool that split one family into five from one that merged five into one.
    CALCULATE_JACCARD_SIMILARITY(
        samples,
        sampled_fasta,
        metadata,
        registry,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common,
        match_threshold,
        max_unmapped_fraction,
        max_ambiguous_fraction,
        min_universe_coverage
    )

    // ...so P/R/F1 per matched pair and the split/merge topology are computed separately, and
    // both are needed before a run can be scored.
    CALCULATE_FAMILY_METRICS(
        samples,
        sampled_fasta,
        metadata,
        registry,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common
    )

    ANALYZE_SPLITS_MERGES(
        samples,
        sampled_fasta,
        metadata,
        registry,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common,
        association_threshold,
        min_intersection_size
    )

    // The scorecard consumes the two above, so join them back onto the sample they came from
    // rather than relying on channel order.
    ch_scorecard_inputs = samples
        .join(CALCULATE_FAMILY_METRICS.out.metrics)
        .join(ANALYZE_SPLITS_MERGES.out.summary)

    COMPUTE_SCORECARD(
        ch_scorecard_inputs,
        sampled_fasta,
        metadata,
        registry,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common,
        scorecard_weights
    )

    // Gated on the row supplying a clustering TSV, declaratively via `ext.when` in
    // conf/modules.config -- not by an `if` here.
    INVESTIGATE_MATCHED_ORIGINALS(
        samples,
        sampled_fasta,
        metadata,
        registry,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common
    )

    ch_mqc = CALCULATE_FAMILY_METRICS.out.mqc
        .mix(
            ANALYZE_SPLITS_MERGES.out.mqc,
            COMPUTE_SCORECARD.out.mqc
        )

    emit:
    edgelist  = CALCULATE_JACCARD_SIMILARITY.out.edgelist
    qc        = CALCULATE_JACCARD_SIMILARITY.out.qc
    metrics   = CALCULATE_FAMILY_METRICS.out.metrics
    summary   = ANALYZE_SPLITS_MERGES.out.summary
    coverage  = CALCULATE_DB_SEQUENCE_COVERAGE.out.coverage
    scorecard = COMPUTE_SCORECARD.out.scorecard
    decoys    = ANALYZE_RECRUITED_DECOYS.out.stats
    mqc       = ch_mqc
}
