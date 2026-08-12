process DOWNLOAD_INTERPRO {
    tag "interpro:${params.interpro_release}"
    label 'process_download'

    conda "${moduleDir}/environment.yml"
    // TODO: pin a SHA-digested container that provides curl + tar + gzip (+ python for pfam).
    // Left unset deliberately: no digest could be resolved or verified offline, and shipping an
    // unverified image would fail at runtime under -profile docker/singularity. Use -profile conda,
    // or supply the database paths directly, until this is pinned.

    output:
    path "ParentChildTreeFile.txt", emit: hierarchy
    path "interpro.xml.gz"       , emit: mapping

    tuple val("${task.process}"), val('curl'), eval("curl --version | head -n1 | sed 's/^curl //; s/ .*//'"), emit: versions_curl, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    curl -fL --retry 3 -o ParentChildTreeFile.txt ${params.interpro_hierarchy_latest_link}
    curl -fL --retry 3 -o interpro.xml.gz ${params.interpro_mapping_latest_link}
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
