include { REMOVE_DUPLICATE_BRANCHES           } from '../modules/local/remove_duplicate_branches/main'
include { EXTRACT_VALID_INTERPRO_IDS          } from '../modules/local/extract_valid_interpro_ids/main'
include { EXTRACT_CANDIDATE_INTERPRO_FAMILIES } from '../modules/local/extract_candidate_interpro_families/main'
include { EXTRACT_DB_METADATA                 } from '../modules/local/extract_db_metadata/main'
include { FILTER_VALID_CANDIDATE_FAMILIES     } from '../modules/local/filter_valid_candidate_families/main'
include { SAMPLE_INTERPRO                     } from '../modules/local/sample_interpro/main'
include { PREPARE_BENCHMARK_FASTA             } from '../modules/local/prepare_benchmark_fasta/main'
include { DIAMOND_MAKEDB                      } from '../modules/nf-core/diamond/makedb/main'
include { DIAMOND_BLASTP                      } from '../modules/nf-core/diamond/blastp/main'
include { IDENTIFY_UNIPROT_DECOYS             } from '../modules/local/identify_uniprot_decoys/main'
include { COMBINE_DECOY_FASTA                 } from '../modules/local/combine_decoy_fasta/main'

workflow PRE {
    take:
    interpro_hierarchy_file
    id_mapping_file
    path_to_hamap
    path_to_ncbifam
    path_to_panther
    path_to_pfam
    path_to_swissprot
    min_membership
    num_per_db
    num_decoys
    seed

    main:
    ch_hierarchy = Channel.fromPath(interpro_hierarchy_file, checkIfExists: true)
    REMOVE_DUPLICATE_BRANCHES( ch_hierarchy )

    EXTRACT_VALID_INTERPRO_IDS( REMOVE_DUPLICATE_BRANCHES.out.hierarchy )

    ch_mapping = Channel.fromPath(id_mapping_file, checkIfExists: true)
    EXTRACT_CANDIDATE_INTERPRO_FAMILIES( EXTRACT_VALID_INTERPRO_IDS.out.output, ch_mapping )

    ch_hamap = Channel.fromPath(path_to_hamap, checkIfExists: true)
    ch_ncbifam = Channel.fromPath(path_to_ncbifam, checkIfExists: true)
    ch_panther = Channel.fromPath(path_to_panther, checkIfExists: true)
    ch_pfam = Channel.fromPath(path_to_pfam, checkIfExists: true)

    ch_db_metadata_inputs = channel.of(
        [[id: 'hamap', db_type: 'hamap'], file(path_to_hamap, checkIfExists: true)],
        [[id: 'ncbifam', db_type: 'ncbifam'], file(path_to_ncbifam, checkIfExists: true)],
        [[id: 'panther', db_type: 'panther'], file(path_to_panther, checkIfExists: true)],
        [[id: 'pfam', db_type: 'pfam'], file(path_to_pfam, checkIfExists: true)]
    )
    EXTRACT_DB_METADATA( ch_db_metadata_inputs )

    FILTER_VALID_CANDIDATE_FAMILIES(
        EXTRACT_CANDIDATE_INTERPRO_FAMILIES.out.metadata,
        EXTRACT_DB_METADATA.out.metadata.map { _meta, metadata -> metadata }.collect()
    )

    SAMPLE_INTERPRO( FILTER_VALID_CANDIDATE_FAMILIES.out.metadata, REMOVE_DUPLICATE_BRANCHES.out.hierarchy, \
        min_membership, num_per_db, seed
    )

    PREPARE_BENCHMARK_FASTA( SAMPLE_INTERPRO.out.metadata, \
        ch_hamap, ch_ncbifam, ch_panther, ch_pfam, seed
    )

    ch_fasta = PREPARE_BENCHMARK_FASTA.out.fasta
        .map { file ->
            [[id: 'combined_db_fasta'], file]
        }

    DIAMOND_MAKEDB( ch_fasta, [], [], [] )
    ch_sp = Channel.of([ [id:'sp_diamond_db'], [ file(path_to_swissprot, checkIfExists: true) ] ])
    DIAMOND_BLASTP( ch_sp, DIAMOND_MAKEDB.out.db, 6, 'qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore' )

    IDENTIFY_UNIPROT_DECOYS( DIAMOND_BLASTP.out.txt, ch_sp, num_decoys, seed )

    COMBINE_DECOY_FASTA( PREPARE_BENCHMARK_FASTA.out.fasta, IDENTIFY_UNIPROT_DECOYS.out.decoys, \
        PREPARE_BENCHMARK_FASTA.out.registry
    )
}
