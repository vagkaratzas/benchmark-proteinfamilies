process DOWNLOAD_HAMAP {
    tag "hamap:current"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.
    storeDir "${params.db_cache_dir}/hamap/current"

    output:
    path "hamap_alignments", emit: alignments

    // No version emit here, deliberately: a topic-channel emit is a `tuple` output, and
    // Nextflow allows only `val`/`path` outputs on a process with `storeDir`. The persistent
    // database cache is worth more than a curl/tar version string, so the cache wins.

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o hamap_alignments.tar.gz https://ftp.expasy.org/databases/hamap/old/hamap_alignments.tar.gz
    mkdir -p extract hamap_alignments
    tar -xzf hamap_alignments.tar.gz -C extract
    find extract -type f -name '*.msa' -exec mv {} hamap_alignments/ \\;
    rm -rf extract hamap_alignments.tar.gz
    find hamap_alignments -type f -name '*.msa' -print -quit | grep -q .
    """

    stub:
    """
    mkdir -p hamap_alignments
    cat > hamap_alignments/MF_00001.msa <<'EOF'
    >stub_hamap_seq
    MAAA
    EOF
    """
}
