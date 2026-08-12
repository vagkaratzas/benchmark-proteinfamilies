include { DOWNLOAD_INTERPRO  } from '../../../modules/local/download_interpro/main'
include { DOWNLOAD_HAMAP     } from '../../../modules/local/download_hamap/main'
include { DOWNLOAD_NCBIFAM   } from '../../../modules/local/download_ncbifam/main'
include { DOWNLOAD_PANTHER   } from '../../../modules/local/download_panther/main'
include { DOWNLOAD_PFAM      } from '../../../modules/local/download_pfam/main'
include { DOWNLOAD_SWISSPROT } from '../../../modules/local/download_swissprot/main'

// A path param that is `null` means "fetch it from the matching *_latest_link". Nextflow hands a
// CLI `--x null` through as the *String* "null", which is truthy, so the string form is checked too.
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

// A user-supplied path is checked for existence *and* content: an empty directory would
// otherwise sail through and only surface later as a family with no sequences.
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

//
// Resolve every reference database PRE needs, downloading only the ones the user did not supply.
//
// The four member databases are emitted as one keyed channel rather than four named outputs. That
// is what makes them individually skippable: a skipped database simply contributes no element, and
// every consumer downstream is already written against "however many databases arrived".
//
workflow DOWNLOAD_DBS {

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

    main:
    // One DOWNLOAD_INTERPRO run yields both the hierarchy and the mapping, so it fires if
    // either is missing -- and each output is then taken from the download or from the user.
    if (isNullPath(interpro_hierarchy_db) || isNullPath(interpro_mapping_db)) {
        DOWNLOAD_INTERPRO()
    }

    ch_hierarchy = isNullPath(interpro_hierarchy_db)
        ? DOWNLOAD_INTERPRO.out.hierarchy
        : channel.value(validatePreInputPath(interpro_hierarchy_db, 'interpro_hierarchy_db'))

    ch_mapping = isNullPath(interpro_mapping_db)
        ? DOWNLOAD_INTERPRO.out.mapping
        : channel.value(validatePreInputPath(interpro_mapping_db, 'interpro_mapping_db'))

    ch_member_dbs = channel.empty()

    if (!skip_hamap) {
        if (isNullPath(hamap_db)) {
            DOWNLOAD_HAMAP()
            ch_hamap = DOWNLOAD_HAMAP.out.alignments
        } else {
            ch_hamap = channel.value(validatePreInputPath(hamap_db, 'hamap_db'))
        }
        ch_member_dbs = ch_member_dbs.mix(ch_hamap.map { db -> [[id: 'hamap', db_type: 'hamap'], db] })
    }

    if (!skip_ncbifam) {
        if (isNullPath(ncbifam_db)) {
            DOWNLOAD_NCBIFAM()
            ch_ncbifam = DOWNLOAD_NCBIFAM.out.alignments
        } else {
            ch_ncbifam = channel.value(validatePreInputPath(ncbifam_db, 'ncbifam_db'))
        }
        ch_member_dbs = ch_member_dbs.mix(ch_ncbifam.map { db -> [[id: 'ncbifam', db_type: 'ncbifam'], db] })
    }

    if (!skip_panther) {
        if (isNullPath(panther_db)) {
            DOWNLOAD_PANTHER()
            ch_panther = DOWNLOAD_PANTHER.out.alignments
        } else {
            ch_panther = channel.value(validatePreInputPath(panther_db, 'panther_db'))
        }
        ch_member_dbs = ch_member_dbs.mix(ch_panther.map { db -> [[id: 'panther', db_type: 'panther'], db] })
    }

    if (!skip_pfam) {
        if (isNullPath(pfam_db)) {
            DOWNLOAD_PFAM()
            ch_pfam = DOWNLOAD_PFAM.out.alignments
        } else {
            ch_pfam = channel.value(validatePreInputPath(pfam_db, 'pfam_db'))
        }
        ch_member_dbs = ch_member_dbs.mix(ch_pfam.map { db -> [[id: 'pfam', db_type: 'pfam'], db] })
    }

    // SwissProt is the decoy source and is never skippable: decoys are part of the universe
    // contract that POST validates against.
    if (isNullPath(swissprot_db)) {
        DOWNLOAD_SWISSPROT()
        ch_swissprot = DOWNLOAD_SWISSPROT.out.fasta
    } else {
        ch_swissprot = channel.value(validatePreInputPath(swissprot_db, 'swissprot_db'))
    }

    emit:
    hierarchy  = ch_hierarchy
    mapping    = ch_mapping
    member_dbs = ch_member_dbs
    swissprot  = ch_swissprot
}
