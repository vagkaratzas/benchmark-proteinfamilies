process DOWNLOAD_PANTHER {
    tag "panther:${params.panther_version}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.
    storeDir "${params.db_cache_dir}/panther/${params.panther_version}"

    output:
    path "PANTHER${params.panther_version}_fasta", emit: alignments
    path "versions.yml"                      , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def releaseDir = params.panther_version == 'current' ? 'current_release' : params.panther_version
    def archiveVersion = params.panther_version == 'current' ? '19.0' : params.panther_version
    def archive = "PANTHER${archiveVersion}_fasta.tgz"
    def outputDir = "PANTHER${params.panther_version}_fasta"
    """
    echo "[WARN] PANTHER FASTA/MSA archive is large; ensure ${params.db_cache_dir}/panther/${params.panther_version} has sufficient persistent storage." >&2
    curl -fL --retry 3 -o ${archive} https://data.pantherdb.org/ftp/panther_library/${releaseDir}/${archive}
    mkdir -p extract ${outputDir}
    tar -xzf ${archive} -C extract
    find extract -type f -name '*.fasta' -exec mv {} ${outputDir}/ \\;
    rm -rf extract ${archive}
    find ${outputDir} -type f -name '*.fasta' -print -quit | grep -q .

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        curl: \$(curl --version | head -n 1 | sed 's/curl //; s/ .*//')
        tar: \$(tar --version | head -n 1 | sed 's/.* //')
    END_VERSIONS
    """

    stub:
    """
    mkdir -p PANTHER${params.panther_version}_fasta
    cat > PANTHER${params.panther_version}_fasta/PTHR00001.fasta <<'EOF'
    >stub_panther_seq
    MAAA
    EOF

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        curl: stub
        tar: stub
    END_VERSIONS
    """
}
