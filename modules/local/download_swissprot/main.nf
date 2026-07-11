process DOWNLOAD_SWISSPROT {
    tag "swissprot:current"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.
    storeDir "${params.db_cache_dir}/swissprot/current"

    output:
    path "uniprot_sprot.fasta", emit: fasta

    // No version emit here, deliberately: a topic-channel emit is a `tuple` output, and
    // Nextflow allows only `val`/`path` outputs on a process with `storeDir`. The persistent
    // database cache is worth more than a curl/tar version string, so the cache wins.

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o uniprot_sprot.fasta.gz https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz
    gzip -dc uniprot_sprot.fasta.gz > uniprot_sprot.fasta
    rm -f uniprot_sprot.fasta.gz
    test -s uniprot_sprot.fasta
    """

    stub:
    """
    cat > uniprot_sprot.fasta <<'EOF'
    >stub_swissprot_seq
    MAAA
    EOF
    """
}
