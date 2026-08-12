process DOWNLOAD_NCBIFAM {
    tag "ncbifam:${params.ncbifam_version}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.

    output:
    path "ncbifam", emit: alignments

    tuple val("${task.process}"), val('curl'), eval("curl --version | head -n1 | sed 's/^curl //; s/ .*//'"), emit: versions_curl, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o hmm_PGAP.SEED.tgz ${params.ncbifam_latest_link}
    mkdir -p extract ncbifam
    tar -xzf hmm_PGAP.SEED.tgz -C extract
    find extract -type f -name '*.SEED' -exec mv {} ncbifam/ \\;
    rm -rf extract hmm_PGAP.SEED.tgz
    find ncbifam -type f -name '*.SEED' -print -quit | grep -q .
    """

    stub:
    """
    mkdir -p ncbifam
    cat > ncbifam/NF000001.1.SEED <<'EOF'
    >stub_ncbifam_seq
    MAAA
    EOF
    """
}
