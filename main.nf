include { PRE  } from './workflows/pre'
include { POST } from './workflows/post'

workflow BENCHMARK_PROTEINFAMILIES {

    take:
    workflow_mode // channel: samplesheet read in from --input

    main:
    //
    // WORKFLOW: Run pre pipeline
    //
    if (workflow_mode == "pre") {
        PRE( params.interpo_hierarchy_file, params.id_mapping_file, \
            params.path_to_hamap, params.path_to_ncbifam, params.path_to_panther, params.path_to_pfam, \
            params.path_to_swissprot, params.min_membership, params.num_per_db, params.num_decoys
        )
    }
    //
    // WORKFLOW: Run post pipeline
    //
    else if (workflow_mode == "post") {
        POST( params.path_to_alignments, params.path_to_db_fasta, params.path_to_decoys, \
            params.path_to_sampled_metadata, params.path_to_sampled_fasta_folder, params.jaccard_similarity_threshold, \
            params.path_to_mmseqs_tsv, params.path_to_generated_fasta
        )
    }
}

workflow {

    main:
    //
    // WORKFLOW: Run main workflow
    //
    BENCHMARK_PROTEINFAMILIES (
        params.workflow_mode
    )

}
