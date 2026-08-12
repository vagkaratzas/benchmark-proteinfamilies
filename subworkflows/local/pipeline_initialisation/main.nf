include { validateParameters } from 'plugin/nf-schema'

//
// Validate params and print the run header.
//
// nf-schema's validateParameters() checks types against nextflow_schema.json; the assertions
// below cover what the schema deliberately cannot. Everything here fails fast, before a single
// task is submitted -- a bad param that surfaces mid-run wastes an entire benchmark.
//
workflow PIPELINE_INITIALISATION {

    main:
    validateParameters()

    if (!(params.workflow_mode in ['pre', 'post'])) {
        error "Invalid --workflow_mode '${params.workflow_mode}'. Allowed values: pre, post."
    }

    // Nextflow publishes into a directory literally named `true` when --outdir is passed with no
    // value, so an empty outdir is rejected rather than silently honoured.
    if (!params.outdir) {
        error "Missing required parameter --outdir."
    }

    // A PRE run whose four member databases are all skipped would build a universe with no
    // curated families in it -- a benchmark with nothing to score. Caught here rather than
    // downstream, where it surfaces as an empty-channel deadlock instead of a message.
    if (params.workflow_mode == 'pre') {
        def enabled_dbs = ['hamap', 'ncbifam', 'panther', 'pfam'].findAll { db ->
            params["skip_${db}"].toString().toLowerCase() != 'true'
        }
        if (!enabled_dbs) {
            error "All four member databases are skipped. PRE needs at least one of --skip_hamap, --skip_ncbifam, --skip_panther, --skip_pfam left false."
        }
    }

    //
    // Coerce and bound-check the numeric params.
    //
    // On Nextflow 26 a value from the CLI arrives as a String while the same param defaulted in
    // config stays an Integer. nextflow_schema.json therefore accepts ["integer","string"] with a
    // numeric pattern, and the real "> 0" contract is enforced here, on the coerced value. Do not
    // "tighten" the schema back to integer-only: that rejects every CLI override.
    //
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
      interpro_hierarchy_db   : ${params.interpro_hierarchy_db ?: "download <- ${params.interpro_hierarchy_latest_link}"}
      interpro_mapping_db     : ${params.interpro_mapping_db ?: "download <- ${params.interpro_mapping_latest_link}"}
      hamap_db                : ${params.skip_hamap ? 'skipped' : params.hamap_db ?: "download <- ${params.hamap_latest_link}"}
      ncbifam_db              : ${params.skip_ncbifam ? 'skipped' : params.ncbifam_db ?: "download <- ${params.ncbifam_latest_link}"}
      panther_db              : ${params.skip_panther ? 'skipped' : params.panther_db ?: "download <- ${params.panther_latest_link}"}
      pfam_db                 : ${params.skip_pfam ? 'skipped' : params.pfam_db ?: "download <- ${params.pfam_latest_link}"}
      swissprot_db            : ${params.swissprot_db ?: "download <- ${params.swissprot_latest_link}"}
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
