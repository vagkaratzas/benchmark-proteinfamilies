include { PRE  } from './workflows/pre'
include { POST } from './workflows/post'
include { PIPELINE_INITIALISATION } from './subworkflows/local/pipeline_initialisation'
include { PIPELINE_COMPLETION     } from './subworkflows/local/pipeline_completion'

//
// Benchmark any protein-family generation tool against manually curated InterPro families.
//
// The two modes are separate runs, not two halves of one DAG, because the step between them
// happens outside this pipeline: PRE emits a universe FASTA, the user runs their tool on it
// however they like, and POST scores whatever came back. Wiring them into a single workflow
// would mean owning the tool invocation, which is exactly what a tool-agnostic benchmark cannot do.
//
workflow BENCHMARK_PROTEINFAMILIES {

    take:
    workflow_mode

    main:
    //
    // WORKFLOW: Build the benchmark universe (runs once, feeds the external tool).
    //
    if (workflow_mode == "pre") {
        PRE(
            params.interpro_hierarchy_file,
            params.id_mapping_file,
            params.path_to_hamap,
            params.path_to_ncbifam,
            params.path_to_panther,
            params.path_to_pfam,
            params.path_to_swissprot,
            params.min_membership,
            params.num_per_db,
            params.num_decoys,
            params.seed
        )
    }
    //
    // WORKFLOW: Score the tool runs listed in the samplesheet against that universe.
    //
    else if (workflow_mode == "post") {
        POST(
            params.post_samplesheet,
            params.pre_id_registry,
            params.pre_universe_fasta,
            params.pre_universe_sha256,
            params.pre_sampled_metadata,
            params.pre_sampled_fasta_dir,
            params.match_threshold,
            params.association_threshold,
            params.max_unmapped_fraction,
            params.max_ambiguous_fraction,
            params.min_intersection_size,
            params.min_universe_coverage,
            params.scorecard_weights,
            // On the CLI `--skip_multiqc false` arrives as the String "false", and every
            // non-empty String is truthy in Groovy -- so a bare `!params.skip_multiqc`
            // would silently skip MultiQC exactly when the user asked for it.
            params.skip_multiqc.toString().toLowerCase() == 'true'
        )
    }
}

workflow {

    main:
    PIPELINE_INITIALISATION()

    BENCHMARK_PROTEINFAMILIES(
        params.workflow_mode
    )

    // Also drains the global `versions` topic into pipeline_info/software_versions.yml, so it
    // must run in both modes -- not only on the POST reporting path.
    PIPELINE_COMPLETION()

}
