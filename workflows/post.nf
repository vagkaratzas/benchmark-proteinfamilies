include { VALIDATE_POST_SAMPLESHEET       } from '../subworkflows/local/validate_post_samplesheet/main'
include { CALCULATE_SEQUENCE_STATS       } from '../modules/local/calculate_sequence_stats/main'
include { CALCULATE_DB_SEQUENCE_COVERAGE } from '../modules/local/calculate_db_sequence_coverage/main'
include { ANALYZE_RECRUITED_DECOYS       } from '../modules/local/analyze_recruited_decoys/main'
include { CALCULATE_JACCARD_SIMILARITY   } from '../modules/local/calculate_jaccard_similarity/main'
include { PRODUCE_DB_STACKED_BARPLOT     } from '../modules/local/produce_db_stacked_barplot/main'
include { CALCULATE_DB_FAMILY_COVERAGE   } from '../modules/local/calculate_db_family_coverage/main'
include { GET_SIZE_DISTRIBUTIONS         } from '../modules/local/get_size_distributions/main'
include { INVESTIGATE_MATCHED_ORIGINALS  } from '../modules/local/investigate_matched_originals/main'
include { CALCULATE_FAMILY_METRICS       } from '../modules/local/calculate_family_metrics/main'
include { ANALYZE_SPLITS_MERGES          } from '../modules/local/analyze_splits_merges/main'
include { COMPUTE_SCORECARD              } from '../modules/local/compute_scorecard/main'
include { COMPARE_BENCHMARK_RUNS         } from '../modules/local/compare_benchmark_runs/main'
include { MULTIQC                        } from '../modules/nf-core/multiqc/main'

workflow POST {
    take:
    post_samplesheet
    pre_id_registry
    pre_universe_fasta
    pre_universe_sha256
    pre_sampled_metadata
    pre_sampled_fasta_dir
    match_threshold
    association_threshold
    max_unmapped_fraction
    max_ambiguous_fraction
    min_intersection_size
    min_universe_coverage
    scorecard_weights
    skip_multiqc

    main:
    VALIDATE_POST_SAMPLESHEET( post_samplesheet )
    ch_samples = VALIDATE_POST_SAMPLESHEET.out.samples

    ch_registry      = channel.value(file(pre_id_registry, checkIfExists: true))
    ch_universe      = channel.value(file(pre_universe_fasta, checkIfExists: true))
    ch_universe_sha  = channel.value(file(pre_universe_sha256, checkIfExists: true))
    ch_metadata      = channel.value(file(pre_sampled_metadata, checkIfExists: true))
    ch_sampled_fasta = channel.value(file(pre_sampled_fasta_dir, checkIfExists: true))
    ch_benchmark_ids = channel.value(file("${projectDir}/bin/benchmark_ids.py", checkIfExists: true))
    ch_post_common   = channel.value(file("${projectDir}/bin/post_common.py", checkIfExists: true))
    ch_multiqc_config = channel.value(file("${projectDir}/assets/multiqc_config.yml", checkIfExists: true))
    ch_comparison_meta = channel.value([id: 'comparison', tool: 'comparison'])
    min_universe_coverage_cli = min_universe_coverage == null ? '' : min_universe_coverage
    scorecard_weights_cli = scorecard_weights == null ? '' : scorecard_weights.toString()

    CALCULATE_SEQUENCE_STATS(
        ch_samples,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common
    )

    CALCULATE_DB_SEQUENCE_COVERAGE(
        CALCULATE_SEQUENCE_STATS.out.original_count,
        ch_metadata,
        ch_sampled_fasta,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common
    )

    ANALYZE_RECRUITED_DECOYS(
        ch_samples,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common
    )

    CALCULATE_JACCARD_SIMILARITY(
        ch_samples,
        ch_sampled_fasta,
        ch_metadata,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common,
        match_threshold,
        max_unmapped_fraction,
        max_ambiguous_fraction,
        min_universe_coverage_cli
    )

    CALCULATE_FAMILY_METRICS(
        ch_samples,
        ch_sampled_fasta,
        ch_metadata,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common
    )

    ANALYZE_SPLITS_MERGES(
        ch_samples,
        ch_sampled_fasta,
        ch_metadata,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common,
        association_threshold,
        min_intersection_size
    )

    PRODUCE_DB_STACKED_BARPLOT( CALCULATE_JACCARD_SIMILARITY.out.edgelist )

    CALCULATE_DB_FAMILY_COVERAGE(
        CALCULATE_JACCARD_SIMILARITY.out.edgelist,
        ch_sampled_fasta,
        ch_metadata,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common
    )

    GET_SIZE_DISTRIBUTIONS(
        CALCULATE_JACCARD_SIMILARITY.out.edgelist,
        ch_metadata,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common
    )

    ch_scorecard_inputs = ch_samples
        .join(CALCULATE_FAMILY_METRICS.out.metrics)
        .join(ANALYZE_SPLITS_MERGES.out.summary)

    COMPUTE_SCORECARD(
        ch_scorecard_inputs,
        ch_sampled_fasta,
        ch_metadata,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common,
        scorecard_weights_cli
    )

    INVESTIGATE_MATCHED_ORIGINALS(
        ch_samples,
        ch_sampled_fasta,
        ch_metadata,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common
    )

    COMPARE_BENCHMARK_RUNS(
        ch_comparison_meta,
        COMPUTE_SCORECARD.out.scorecard.map { _meta, scorecard -> scorecard }.collect(),
        CALCULATE_FAMILY_METRICS.out.metrics.map { _meta, metrics -> metrics }.collect(),
        ANALYZE_SPLITS_MERGES.out.summary.map { _meta, summary -> summary }.collect(),
        CALCULATE_DB_SEQUENCE_COVERAGE.out.coverage.map { _meta, coverage -> coverage }.collect(),
        ch_benchmark_ids,
        ch_post_common
    )


    if (!skip_multiqc) {
        ch_mqc_files = CALCULATE_FAMILY_METRICS.out.mqc
            .mix(
                ANALYZE_SPLITS_MERGES.out.mqc,
                COMPUTE_SCORECARD.out.mqc,
                COMPARE_BENCHMARK_RUNS.out.mqc_csv,
                COMPARE_BENCHMARK_RUNS.out.mqc_f1_plot,
                COMPARE_BENCHMARK_RUNS.out.mqc_db_plot
            )
            .map { _meta, mqc_file -> mqc_file }
            .collect()

        MULTIQC(
            ch_comparison_meta,
            ch_mqc_files,
            ch_multiqc_config
        )
    }
}
