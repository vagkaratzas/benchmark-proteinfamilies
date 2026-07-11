include { DOWNLOAD_INTERPRO  } from '../../../modules/local/download_interpro/main'
include { DOWNLOAD_HAMAP     } from '../../../modules/local/download_hamap/main'
include { DOWNLOAD_NCBIFAM   } from '../../../modules/local/download_ncbifam/main'
include { DOWNLOAD_PANTHER   } from '../../../modules/local/download_panther/main'
include { DOWNLOAD_PFAM      } from '../../../modules/local/download_pfam/main'
include { DOWNLOAD_SWISSPROT } from '../../../modules/local/download_swissprot/main'

// A path param that is `null` means "fetch it for me". Nextflow hands a CLI `--x null`
// through as the *String* "null", which is truthy, so the string form is checked too.
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
// Resolve every reference database PRE needs, downloading only the ones the user did not
// supply. Each DOWNLOAD_* module writes into a `storeDir` under --db_cache_dir, so a second
// run reuses the cache instead of refetching tens of GB.
//
workflow DOWNLOAD_DBS {

    take:
    interpro_hierarchy_file
    id_mapping_file
    path_to_hamap
    path_to_ncbifam
    path_to_panther
    path_to_pfam
    path_to_swissprot

    main:
    // One DOWNLOAD_INTERPRO run yields both the hierarchy and the mapping, so it fires if
    // either is missing -- and each output is then taken from the download or from the user.
    if (isNullPath(interpro_hierarchy_file) || isNullPath(id_mapping_file)) {
        DOWNLOAD_INTERPRO()
    }

    ch_hierarchy = isNullPath(interpro_hierarchy_file)
        ? DOWNLOAD_INTERPRO.out.hierarchy
        : channel.value(validatePreInputPath(interpro_hierarchy_file, 'interpro_hierarchy_file'))

    ch_mapping = isNullPath(id_mapping_file)
        ? DOWNLOAD_INTERPRO.out.mapping
        : channel.value(validatePreInputPath(id_mapping_file, 'id_mapping_file'))

    if (isNullPath(path_to_hamap)) {
        DOWNLOAD_HAMAP()
        ch_hamap = DOWNLOAD_HAMAP.out.alignments
    } else {
        ch_hamap = channel.value(validatePreInputPath(path_to_hamap, 'path_to_hamap'))
    }

    if (isNullPath(path_to_ncbifam)) {
        DOWNLOAD_NCBIFAM()
        ch_ncbifam = DOWNLOAD_NCBIFAM.out.alignments
    } else {
        ch_ncbifam = channel.value(validatePreInputPath(path_to_ncbifam, 'path_to_ncbifam'))
    }

    if (isNullPath(path_to_panther)) {
        DOWNLOAD_PANTHER()
        ch_panther = DOWNLOAD_PANTHER.out.alignments
    } else {
        ch_panther = channel.value(validatePreInputPath(path_to_panther, 'path_to_panther'))
    }

    if (isNullPath(path_to_pfam)) {
        DOWNLOAD_PFAM()
        ch_pfam = DOWNLOAD_PFAM.out.alignments
    } else {
        ch_pfam = channel.value(validatePreInputPath(path_to_pfam, 'path_to_pfam'))
    }

    if (isNullPath(path_to_swissprot)) {
        DOWNLOAD_SWISSPROT()
        ch_swissprot = DOWNLOAD_SWISSPROT.out.fasta
    } else {
        ch_swissprot = channel.value(validatePreInputPath(path_to_swissprot, 'path_to_swissprot'))
    }

    emit:
    hierarchy = ch_hierarchy
    mapping   = ch_mapping
    hamap     = ch_hamap
    ncbifam   = ch_ncbifam
    panther   = ch_panther
    pfam      = ch_pfam
    swissprot = ch_swissprot
}
