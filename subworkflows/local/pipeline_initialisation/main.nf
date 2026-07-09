include { validateParameters } from 'plugin/nf-schema'

workflow PIPELINE_INITIALISATION {

    main:
    validateParameters()

    if (!(params.workflow_mode in ['pre', 'post'])) {
        error "Invalid --workflow_mode '${params.workflow_mode}'. Allowed values: pre, post."
    }

    if (!params.outdir) {
        error "Missing required parameter --outdir."
    }

    [
        min_membership       : params.min_membership,
        num_per_db           : params.num_per_db,
        num_decoys           : params.num_decoys,
        min_intersection_size: params.min_intersection_size
    ].each { name, value ->
        if (value == null) {
            error "Invalid --${name}: expected a positive number, got null."
        }
        def numeric
        try {
            numeric = value as BigDecimal
        } catch (Exception _ignored) {
            error "Invalid --${name}: expected a positive number, got '${value}'."
        }
        if (numeric <= 0) {
            error "Invalid --${name}: expected a positive number, got '${value}'."
        }
    }

    log.info """
    ------------------------------------------------------
    Pipeline : ${workflow.manifest.name}
    Version  : ${workflow.manifest.version}
    Mode     : ${params.workflow_mode}
    Outdir   : ${params.outdir}

    PRE parameters:
      interpro_hierarchy_file : ${params.interpro_hierarchy_file}
      id_mapping_file         : ${params.id_mapping_file}
      path_to_hamap           : ${params.path_to_hamap}
      path_to_ncbifam         : ${params.path_to_ncbifam}
      path_to_panther         : ${params.path_to_panther}
      path_to_pfam            : ${params.path_to_pfam}
      path_to_swissprot       : ${params.path_to_swissprot}
      min_membership          : ${params.min_membership}
      num_per_db              : ${params.num_per_db}
      num_decoys              : ${params.num_decoys}
      seed                    : ${params.seed}

    POST parameters:
      post_samplesheet        : ${params.post_samplesheet}
      pre_id_registry         : ${params.pre_id_registry}
      pre_universe_fasta      : ${params.pre_universe_fasta}
      pre_universe_sha256     : ${params.pre_universe_sha256}
      pre_sampled_metadata    : ${params.pre_sampled_metadata}
      pre_sampled_fasta_dir   : ${params.pre_sampled_fasta_dir}
      match_threshold         : ${params.match_threshold}
      association_threshold   : ${params.association_threshold}
      max_unmapped_fraction   : ${params.max_unmapped_fraction}
      max_ambiguous_fraction  : ${params.max_ambiguous_fraction}
      min_intersection_size   : ${params.min_intersection_size}
      min_universe_coverage   : ${params.min_universe_coverage}
      scorecard_weights       : ${params.scorecard_weights}
      skip_multiqc            : ${params.skip_multiqc}
    ------------------------------------------------------
    """.stripIndent()
}
