process DOWNLOAD_NCBIFAM {
    tag "ncbifam:current"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.
    storeDir "${params.db_cache_dir}/ncbifam/current"

    output:
    path "ncbifam", emit: alignments
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o hmm_PGAP.SEED.tgz https://ftp.ncbi.nlm.nih.gov/hmm/current/hmm_PGAP.SEED.tgz
    mkdir -p extract ncbifam
    tar -xzf hmm_PGAP.SEED.tgz -C extract
    find extract -type f -name '*.SEED' -exec mv {} ncbifam/ \\;
    rm -rf extract hmm_PGAP.SEED.tgz
    find ncbifam -type f -name '*.SEED' -print -quit | grep -q .

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        curl: \$(curl --version | head -n 1 | sed 's/curl //; s/ .*//')
        tar: \$(tar --version | head -n 1 | sed 's/.* //')
    END_VERSIONS
    """

    stub:
    """
    mkdir -p ncbifam
    cat > ncbifam/NF000001.1.SEED <<'EOF'
    >stub_ncbifam_seq
    MAAA
    EOF

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        curl: stub
        tar: stub
    END_VERSIONS
    """
}
