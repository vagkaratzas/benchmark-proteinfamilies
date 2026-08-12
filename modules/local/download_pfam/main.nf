process DOWNLOAD_PFAM {
    tag "pfam:${params.pfam_version}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.

    output:
    path "pfam", emit: alignments

    tuple val("${task.process}"), val('curl'), eval("curl --version | head -n1 | sed 's/^curl //; s/ .*//'"), emit: versions_curl, topic: versions
    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o Pfam-A.seed.gz ${params.pfam_latest_link}
    split_pfam_seed.py --input Pfam-A.seed.gz --output-dir pfam
    rm -f Pfam-A.seed.gz
    find pfam -type f -name '*.sto' -print -quit | grep -q .
    """

    stub:
    """
    mkdir -p pfam
    cat > pfam/PF00001.sto <<'EOF'
    # STOCKHOLM 1.0
    stub_pfam_seq MAAA
    //
    EOF
    """
}
