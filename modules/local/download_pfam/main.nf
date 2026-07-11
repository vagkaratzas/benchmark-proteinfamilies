process DOWNLOAD_PFAM {
    tag "pfam:${params.pfam_version}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.
    storeDir "${params.db_cache_dir}/pfam/${params.pfam_version}"

    output:
    path "pfam"        , emit: alignments

    // No version emit here, deliberately: a topic-channel emit is a `tuple` output, and
    // Nextflow allows only `val`/`path` outputs on a process with `storeDir`. The persistent
    // database cache is worth more than a curl/tar version string, so the cache wins.

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o Pfam-A.seed.gz https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam${params.pfam_version}/Pfam-A.seed.gz
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
