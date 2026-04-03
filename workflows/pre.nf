include { REMOVE_DUPLICATE_BRANCHES           } from '../modules/local/remove_duplicate_branches/main'
include { EXTRACT_VALID_INTERPRO_IDS          } from '../modules/local/extract_valid_interpro_ids/main'
include { EXTRACT_CANDIDATE_INTERPRO_FAMILIES } from '../modules/local/extract_candidate_interpro_families/main'
include { EXTRACT_HAMAP_METADATA              } from '../modules/local/extract_hamap_metadata/main'
include { EXTRACT_NCBIFAM_METADATA            } from '../modules/local/extract_ncbifam_metadata/main'
include { EXTRACT_PANTHER_METADATA            } from '../modules/local/extract_panther_metadata/main'
include { EXTRACT_PFAM_METADATA               } from '../modules/local/extract_pfam_metadata/main'
include { FILTER_VALID_CANDIDATE_FAMILIES     } from '../modules/local/filter_valid_candidate_families/main'
include { SAMPLE_INTERPRO                     } from '../modules/local/sample_interpro/main'
include { CONVERT_SAMPLED_TO_FASTA            } from '../modules/local/convert_sampled_to_fasta/main'
include { COMBINE_DB_FASTA                    } from '../modules/local/combine_db_fasta/main'
include { DIAMOND_MAKEDB                      } from '../modules/nf-core/diamond/makedb/main'
include { DIAMOND_BLASTP                      } from '../modules/nf-core/diamond/blastp/main'
include { IDENTIFY_UNIPROT_DECOYS             } from '../modules/local/identify_uniprot_decoys/main'
include { COMBINE_DECOY_FASTA                 } from '../modules/local/combine_decoy_fasta/main'

workflow PRE {
    take:
    interpo_hierarchy_file
    id_mapping_file
    path_to_hamap
    path_to_ncbifam
    path_to_panther
    path_to_pfam
    path_to_swissprot
    min_membership
    num_per_db
    num_decoys

    main:
    ch_hierarchy = Channel.fromPath(interpo_hierarchy_file, checkIfExists: true)
    REMOVE_DUPLICATE_BRANCHES( ch_hierarchy )
    
    EXTRACT_VALID_INTERPRO_IDS( REMOVE_DUPLICATE_BRANCHES.out.hierarchy )

    ch_mapping = Channel.fromPath(id_mapping_file, checkIfExists: true)
    EXTRACT_CANDIDATE_INTERPRO_FAMILIES( EXTRACT_VALID_INTERPRO_IDS.out.output, ch_mapping )

    ch_hamap = Channel.fromPath(path_to_hamap, checkIfExists: true)
    EXTRACT_HAMAP_METADATA( ch_hamap )

    ch_ncbifam = Channel.fromPath(path_to_ncbifam, checkIfExists: true)
    EXTRACT_NCBIFAM_METADATA( ch_ncbifam )

    ch_panther = Channel.fromPath(path_to_panther, checkIfExists: true)
    EXTRACT_PANTHER_METADATA( ch_panther )

    ch_pfam = Channel.fromPath(path_to_pfam, checkIfExists: true)
    EXTRACT_PFAM_METADATA( ch_pfam )

    FILTER_VALID_CANDIDATE_FAMILIES( EXTRACT_CANDIDATE_INTERPRO_FAMILIES.out.metadata, \
        EXTRACT_HAMAP_METADATA.out.metadata, EXTRACT_NCBIFAM_METADATA.out.metadata, \
        EXTRACT_PANTHER_METADATA.out.metadata, EXTRACT_PFAM_METADATA.out.metadata
    )

    SAMPLE_INTERPRO( FILTER_VALID_CANDIDATE_FAMILIES.out.metadata, REMOVE_DUPLICATE_BRANCHES.out.hierarchy, \
        min_membership, num_per_db
    )

    CONVERT_SAMPLED_TO_FASTA( SAMPLE_INTERPRO.out.metadata, \
        ch_hamap, ch_ncbifam, ch_panther, ch_pfam
    )

    COMBINE_DB_FASTA( CONVERT_SAMPLED_TO_FASTA.out.fasta_folder )
    
    ch_fasta = COMBINE_DB_FASTA.out.fasta
        .map { file ->
            [[id: 'combined_db_fasta'], file]
        }

    DIAMOND_MAKEDB( ch_fasta, [], [], [] )
    ch_sp = Channel.of([ [id:'sp_diamond_db'], [ file(path_to_swissprot, checkIfExists: true) ] ])
    DIAMOND_BLASTP( ch_sp, DIAMOND_MAKEDB.out.db, 6, 'qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore' )

    IDENTIFY_UNIPROT_DECOYS( DIAMOND_BLASTP.out.txt, ch_sp, num_decoys )

    COMBINE_DECOY_FASTA( COMBINE_DB_FASTA.out.fasta, IDENTIFY_UNIPROT_DECOYS.out.decoys )
}
