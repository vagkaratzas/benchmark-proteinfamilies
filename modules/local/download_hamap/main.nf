process DOWNLOAD_HAMAP {
    tag "hamap:${params.hamap_version}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.

    output:
    path "hamap_alignments", emit: alignments

    tuple val("${task.process}"), val('curl'), eval("curl --version | head -n1 | sed 's/^curl //; s/ .*//'"), emit: versions_curl, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o hamap_alignments.tar.gz ${params.hamap_latest_link}
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
