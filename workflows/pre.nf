include { DOWNLOAD_DBS                        } from '../subworkflows/local/download_dbs/main'
include { GENERATE_DECOYS                     } from '../subworkflows/local/generate_decoys/main'
include { REMOVE_DUPLICATE_BRANCHES           } from '../modules/local/remove_duplicate_branches/main'
include { EXTRACT_VALID_INTERPRO_IDS          } from '../modules/local/extract_valid_interpro_ids/main'
include { EXTRACT_CANDIDATE_INTERPRO_FAMILIES } from '../modules/local/extract_candidate_interpro_families/main'
include { EXTRACT_DB_METADATA                 } from '../modules/local/extract_db_metadata/main'
include { FILTER_VALID_CANDIDATE_FAMILIES     } from '../modules/local/filter_valid_candidate_families/main'
include { SAMPLE_INTERPRO                     } from '../modules/local/sample_interpro/main'
include { PREPARE_BENCHMARK_FASTA             } from '../modules/local/prepare_benchmark_fasta/main'

//
// PRE builds the benchmark universe, once. It samples curated InterPro families, pulls their
// sequences out of the four member databases, spikes in SwissProt decoys, and -- critically --
// writes the id_registry that records what every sequence in that universe actually is.
//
// The universe FASTA is what the user then hands to whatever tool they are benchmarking.
//
workflow PRE {

    take:
    interpro_hierarchy_db
    interpro_mapping_db
    hamap_db
    ncbifam_db
    panther_db
    pfam_db
    swissprot_db
    skip_hamap
    skip_ncbifam
    skip_panther
    skip_pfam
    min_membership
    num_per_db
    num_decoys
    seed

    main:
    //
    // Resolve the reference databases: any *_db the user left null is downloaded from its
    // *_latest_link, and any skipped member database contributes nothing at all.
    //
    DOWNLOAD_DBS(
        interpro_hierarchy_db,
        interpro_mapping_db,
        hamap_db,
        ncbifam_db,
        panther_db,
        pfam_db,
        swissprot_db,
        skip_hamap,
        skip_ncbifam,
        skip_panther,
        skip_pfam
    )

    //
    // Work out which curated families are candidates for sampling.
    //
    // The hierarchy is deduplicated first: InterPro is a DAG, and a family reachable by two
    // branches would otherwise be sampled twice and score as its own duplicate.
    //
    REMOVE_DUPLICATE_BRANCHES( DOWNLOAD_DBS.out.hierarchy )
    EXTRACT_VALID_INTERPRO_IDS( REMOVE_DUPLICATE_BRANCHES.out.hierarchy )
    EXTRACT_CANDIDATE_INTERPRO_FAMILIES(
        EXTRACT_VALID_INTERPRO_IDS.out.output,
        DOWNLOAD_DBS.out.mapping
    )

    //
    // Count family membership in each database. One parameterised module handles whichever
    // databases arrived, so they fan out in parallel and a new database means a new channel
    // element, not new code.
    //
    EXTRACT_DB_METADATA( DOWNLOAD_DBS.out.member_dbs )

    // A candidate is only usable if it resolves to a family that exists in the downloaded
    // databases -- InterPro lists members that a given database release may not ship.
    FILTER_VALID_CANDIDATE_FAMILIES(
        EXTRACT_CANDIDATE_INTERPRO_FAMILIES.out.metadata,
        EXTRACT_DB_METADATA.out.metadata.map { _meta, metadata -> metadata }.collect()
    )

    //
    // Sample the families and materialise their sequences.
    //
    // Sampling walks the tree rather than the flat list, so the sample is not dominated by
    // whichever branch happens to be largest.
    //
    SAMPLE_INTERPRO(
        FILTER_VALID_CANDIDATE_FAMILIES.out.metadata,
        REMOVE_DUPLICATE_BRANCHES.out.hierarchy,
        min_membership,
        num_per_db,
        seed
    )

    // The module is told which database each staged directory is, because staging renames the
    // directories to break basename collisions between user-supplied paths. Sorting by id keeps
    // the pairing stable, so a rerun stages the same directory under the same name.
    ch_named_member_dbs = DOWNLOAD_DBS.out.member_dbs
        .toSortedList { a, b -> a[0].id <=> b[0].id }
        .map { rows -> [rows.collect { meta, _db -> meta.id }, rows.collect { _meta, db -> db }] }

    PREPARE_BENCHMARK_FASTA(
        SAMPLE_INTERPRO.out.metadata,
        ch_named_member_dbs,
        seed
    )

    //
    // Spike in decoys and emit the universe (FASTA + registry + checksum) the tools are fed.
    //
    GENERATE_DECOYS(
        PREPARE_BENCHMARK_FASTA.out.fasta,
        PREPARE_BENCHMARK_FASTA.out.registry,
        DOWNLOAD_DBS.out.swissprot,
        num_decoys,
        seed
    )

    emit:
    universe        = GENERATE_DECOYS.out.fasta
    registry        = GENERATE_DECOYS.out.registry
    universe_sha256 = GENERATE_DECOYS.out.universe_sha256
    sampled_fasta   = PREPARE_BENCHMARK_FASTA.out.fasta_folder
    sampled_metadata = PREPARE_BENCHMARK_FASTA.out.metadata
}
