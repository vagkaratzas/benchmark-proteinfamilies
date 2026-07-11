process DOWNLOAD_INTERPRO {
    tag "interpro:${params.interpro_release}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.
    storeDir "${params.db_cache_dir}/interpro/${params.interpro_release}"

    output:
    path "ParentChildTreeFile.txt", emit: hierarchy
    path "interpro.xml.gz"       , emit: mapping

    // No version emit here, deliberately: a topic-channel emit is a `tuple` output, and
    // Nextflow allows only `val`/`path` outputs on a process with `storeDir`. The persistent
    // database cache is worth more than a curl/tar version string, so the cache wins.

    when:
    task.ext.when == null || task.ext.when

    script:
    def releaseDir = params.interpro_release == 'current' ? 'current_release' : params.interpro_release
    def baseUrl = "https://ftp.ebi.ac.uk/pub/databases/interpro/${releaseDir}"
    """
    curl -fL --retry 3 -o ParentChildTreeFile.txt ${baseUrl}/ParentChildTreeFile.txt
    curl -fL --retry 3 -o interpro.xml.gz ${baseUrl}/interpro.xml.gz
    test -s ParentChildTreeFile.txt
    test -s interpro.xml.gz
    """

    stub:
    """
    cat > ParentChildTreeFile.txt <<'EOF'
    IPR000001::Stub root
    --IPR000002::Stub family
    EOF
    cat > interpro.xml <<'EOF'
    <?xml version="1.0" encoding="UTF-8"?>
    <interprodb>
      <interpro id="IPR000002" type="Family" short_name="StubFam" protein_count="1">
        <member_list>
          <db_xref db="PFAM" dbkey="PF00001" name="Stub PFAM family"/>
        </member_list>
      </interpro>
    </interprodb>
    EOF
    gzip -c interpro.xml > interpro.xml.gz
    """
}
