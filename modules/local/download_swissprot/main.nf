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
    path "versions.yml"      , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o uniprot_sprot.fasta.gz https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz
    gzip -dc uniprot_sprot.fasta.gz > uniprot_sprot.fasta
    rm -f uniprot_sprot.fasta.gz
    test -s uniprot_sprot.fasta

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        curl: \$(curl --version | head -n 1 | sed 's/curl //; s/ .*//')
        gzip: \$(gzip --version | head -n 1 | sed 's/.* //')
    END_VERSIONS
    """

    stub:
    """
    cat > uniprot_sprot.fasta <<'EOF'
    >stub_swissprot_seq
    MAAA
    EOF

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        curl: stub
        gzip: stub
    END_VERSIONS
    """
}
