include { VALIDATE_POST_SAMPLESHEET       } from '../subworkflows/local/validate_post_samplesheet/main'
include { CALCULATE_SEQUENCE_STATS       } from '../modules/local/calculate_sequence_stats/main'
include { CALCULATE_DB_SEQUENCE_COVERAGE } from '../modules/local/calculate_db_sequence_coverage/main'
include { ANALYZE_RECRUITED_DECOYS       } from '../modules/local/analyze_recruited_decoys/main'
include { CALCULATE_JACCARD_SIMILARITY   } from '../modules/local/calculate_jaccard_similarity/main'
include { PRODUCE_DB_STACKED_BARPLOT     } from '../modules/local/produce_db_stacked_barplot/main'
include { CALCULATE_DB_FAMILY_COVERAGE   } from '../modules/local/calculate_db_family_coverage/main'
include { GET_SIZE_DISTRIBUTIONS         } from '../modules/local/get_size_distributions/main'
include { INVESTIGATE_MATCHED_ORIGINALS  } from '../modules/local/investigate_matched_originals/main'

workflow POST {
    take:
    post_samplesheet
    pre_id_registry
    pre_universe_fasta
    pre_universe_sha256
    pre_sampled_metadata
    pre_sampled_fasta_dir
    match_threshold
    max_unmapped_fraction
    max_ambiguous_fraction
    min_universe_coverage

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
    min_universe_coverage_cli = min_universe_coverage == null ? '' : min_universe_coverage

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
}
