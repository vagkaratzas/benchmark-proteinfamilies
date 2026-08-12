process DOWNLOAD_PANTHER {
    tag "panther:${params.panther_version}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.

    output:
    // Named for the database, not the release: the version lives in the `tag` and in
    // --panther_version, so bumping a release does not rename an output channel.
    path "panther", emit: alignments

    tuple val("${task.process}"), val('curl'), eval("curl --version | head -n1 | sed 's/^curl //; s/ .*//'"), emit: versions_curl, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    echo "[WARN] The PANTHER FASTA/MSA archive is large; ensure the work directory and --outdir have sufficient storage." >&2
    curl -fL --retry 3 -o panther.tgz ${params.panther_latest_link}
    mkdir -p extract panther
    tar -xzf panther.tgz -C extract
    find extract -type f -name '*.fasta' -exec mv {} panther/ \\;
    rm -rf extract panther.tgz
    find panther -type f -name '*.fasta' -print -quit | grep -q .
    """

    stub:
    """
    mkdir -p panther
    cat > panther/PTHR00001.fasta <<'EOF'
    >stub_panther_seq
    MAAA
    EOF
    """
}
