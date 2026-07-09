include { REMOVE_DUPLICATE_BRANCHES           } from '../modules/local/remove_duplicate_branches/main'
include { EXTRACT_VALID_INTERPRO_IDS          } from '../modules/local/extract_valid_interpro_ids/main'
include { EXTRACT_CANDIDATE_INTERPRO_FAMILIES } from '../modules/local/extract_candidate_interpro_families/main'
include { EXTRACT_DB_METADATA                 } from '../modules/local/extract_db_metadata/main'
include { FILTER_VALID_CANDIDATE_FAMILIES     } from '../modules/local/filter_valid_candidate_families/main'
include { SAMPLE_INTERPRO                     } from '../modules/local/sample_interpro/main'
include { PREPARE_BENCHMARK_FASTA             } from '../modules/local/prepare_benchmark_fasta/main'
include { DOWNLOAD_INTERPRO                   } from '../modules/local/download_interpro/main'
include { DOWNLOAD_HAMAP                      } from '../modules/local/download_hamap/main'
include { DOWNLOAD_NCBIFAM                    } from '../modules/local/download_ncbifam/main'
include { DOWNLOAD_PANTHER                    } from '../modules/local/download_panther/main'
include { DOWNLOAD_PFAM                       } from '../modules/local/download_pfam/main'
include { DOWNLOAD_SWISSPROT                  } from '../modules/local/download_swissprot/main'
include { DIAMOND_MAKEDB                      } from '../modules/nf-core/diamond/makedb/main'
include { DIAMOND_BLASTP                      } from '../modules/nf-core/diamond/blastp/main'
include { IDENTIFY_UNIPROT_DECOYS             } from '../modules/local/identify_uniprot_decoys/main'
include { COMBINE_DECOY_FASTA                 } from '../modules/local/combine_decoy_fasta/main'
include { DUMP_SOFTWARE_VERSIONS              } from '../modules/local/dump_software_versions/main'

def isNullPath(value) {
    value == null || value.toString().trim().equalsIgnoreCase('null')
}

def pathHasContent(resolved) {
    if (java.nio.file.Files.isDirectory(resolved)) {
        def entries = java.nio.file.Files.list(resolved)
        def hasEntry = entries.findAny().isPresent()
        entries.close()
        return hasEntry
    }
    return java.nio.file.Files.size(resolved) > 0
}

def validatePreInputPath(value, paramName) {
    if (value == null || value.toString().trim() == '') {
        error "Invalid --${paramName}: resolved path is empty."
    }
    def resolved = file(value)
    if (!java.nio.file.Files.exists(resolved)) {
        error "Invalid --${paramName}: resolved path '${value}' does not exist."
    }
    if (!pathHasContent(resolved)) {
        error "Invalid --${paramName}: resolved path '${value}' exists but is empty."
    }
    return resolved
}

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
    ch_download_versions = channel.empty()

    if (isNullPath(interpro_hierarchy_file) || isNullPath(id_mapping_file)) {
        DOWNLOAD_INTERPRO()
        ch_download_versions = ch_download_versions.mix(DOWNLOAD_INTERPRO.out.versions)
    }
    ch_hierarchy = isNullPath(interpro_hierarchy_file) ?
        DOWNLOAD_INTERPRO.out.hierarchy :
        channel.value(validatePreInputPath(interpro_hierarchy_file, 'interpro_hierarchy_file'))
    REMOVE_DUPLICATE_BRANCHES( ch_hierarchy )

    EXTRACT_VALID_INTERPRO_IDS( REMOVE_DUPLICATE_BRANCHES.out.hierarchy )

    ch_mapping = isNullPath(id_mapping_file) ?
        DOWNLOAD_INTERPRO.out.mapping :
        channel.value(validatePreInputPath(id_mapping_file, 'id_mapping_file'))
    EXTRACT_CANDIDATE_INTERPRO_FAMILIES( EXTRACT_VALID_INTERPRO_IDS.out.output, ch_mapping )

    if (isNullPath(path_to_hamap)) {
        DOWNLOAD_HAMAP()
        ch_hamap = DOWNLOAD_HAMAP.out.alignments
        ch_download_versions = ch_download_versions.mix(DOWNLOAD_HAMAP.out.versions)
    } else {
        ch_hamap = channel.value(validatePreInputPath(path_to_hamap, 'path_to_hamap'))
    }

    if (isNullPath(path_to_ncbifam)) {
        DOWNLOAD_NCBIFAM()
        ch_ncbifam = DOWNLOAD_NCBIFAM.out.alignments
        ch_download_versions = ch_download_versions.mix(DOWNLOAD_NCBIFAM.out.versions)
    } else {
        ch_ncbifam = channel.value(validatePreInputPath(path_to_ncbifam, 'path_to_ncbifam'))
    }

    if (isNullPath(path_to_panther)) {
        DOWNLOAD_PANTHER()
        ch_panther = DOWNLOAD_PANTHER.out.alignments
        ch_download_versions = ch_download_versions.mix(DOWNLOAD_PANTHER.out.versions)
    } else {
        ch_panther = channel.value(validatePreInputPath(path_to_panther, 'path_to_panther'))
    }

    if (isNullPath(path_to_pfam)) {
        DOWNLOAD_PFAM()
        ch_pfam = DOWNLOAD_PFAM.out.alignments
        ch_download_versions = ch_download_versions.mix(DOWNLOAD_PFAM.out.versions)
    } else {
        ch_pfam = channel.value(validatePreInputPath(path_to_pfam, 'path_to_pfam'))
    }

    if (isNullPath(path_to_swissprot)) {
        DOWNLOAD_SWISSPROT()
        ch_swissprot = DOWNLOAD_SWISSPROT.out.fasta
        ch_download_versions = ch_download_versions.mix(DOWNLOAD_SWISSPROT.out.versions)
    } else {
        ch_swissprot = channel.value(validatePreInputPath(path_to_swissprot, 'path_to_swissprot'))
    }

    ch_db_metadata_inputs = ch_hamap.map { hamap -> [[id: 'hamap', db_type: 'hamap'], hamap] }
        .mix(
            ch_ncbifam.map { ncbifam -> [[id: 'ncbifam', db_type: 'ncbifam'], ncbifam] },
            ch_panther.map { panther -> [[id: 'panther', db_type: 'panther'], panther] },
            ch_pfam.map { pfam -> [[id: 'pfam', db_type: 'pfam'], pfam] }
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
    ch_sp = ch_swissprot.map { sp -> [ [id:'sp_diamond_db'], [ sp ] ] }
    DIAMOND_BLASTP( ch_sp, DIAMOND_MAKEDB.out.db, 6, 'qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore' )

    IDENTIFY_UNIPROT_DECOYS( DIAMOND_BLASTP.out.txt, ch_sp, num_decoys, seed )

    COMBINE_DECOY_FASTA( PREPARE_BENCHMARK_FASTA.out.fasta, IDENTIFY_UNIPROT_DECOYS.out.decoys, \
        PREPARE_BENCHMARK_FASTA.out.registry
    )

    ch_versions = ch_download_versions
        .mix(
            REMOVE_DUPLICATE_BRANCHES.out.versions,
            EXTRACT_VALID_INTERPRO_IDS.out.versions,
            EXTRACT_CANDIDATE_INTERPRO_FAMILIES.out.versions,
            EXTRACT_DB_METADATA.out.versions.map { _meta, versions -> versions },
            FILTER_VALID_CANDIDATE_FAMILIES.out.versions,
            SAMPLE_INTERPRO.out.versions,
            PREPARE_BENCHMARK_FASTA.out.versions,
            DIAMOND_MAKEDB.out.versions,
            DIAMOND_BLASTP.out.versions,
            IDENTIFY_UNIPROT_DECOYS.out.versions,
            COMBINE_DECOY_FASTA.out.versions
        )

    DUMP_SOFTWARE_VERSIONS( ch_versions.collect() )
}
