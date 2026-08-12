process DOWNLOAD_SWISSPROT {
    tag "swissprot:${params.swissprot_version}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.

    output:
    path "uniprot_sprot.fasta", emit: fasta

    tuple val("${task.process}"), val('curl'), eval("curl --version | head -n1 | sed 's/^curl //; s/ .*//'"), emit: versions_curl, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o uniprot_sprot.fasta.gz ${params.swissprot_latest_link}
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
