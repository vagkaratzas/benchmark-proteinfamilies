//
// Parse and validate the POST samplesheet: sample,tool,msa_dir,clustering_tsv
//
// Emits one [ meta, msa_dir, clustering_tsv ] tuple per row. `clustering_tsv` is optional and
// arrives as `[]` when absent, which is how a Nextflow `path` input models "no file".
//
// Every check here fails the whole run rather than dropping the offending row. A silently skipped
// row would produce a benchmark report that simply omits a tool, which reads as a legitimate
// result -- the failure mode this pipeline exists to avoid.
//
// The channel is built in `emit:` rather than assigned to a variable first: with a single output,
// `nextflow lint` wants the emit unnamed, and an unnamed emit does not count as a use of the
// variable, so the intermediate would then lint as dead.
//
workflow VALIDATE_POST_SAMPLESHEET {

    take:
    samplesheet

    emit:
    channel.fromPath(samplesheet, checkIfExists: true)
        .splitCsv(header: true)
        // `.collect()` gathers every row before validating, so `seen` can span the whole
        // samplesheet: duplicate detection is impossible if rows are checked one at a time.
        .collect()
        .flatMap { rows ->
            def seen = [] as Set
            rows.collect { row ->
                def sample = row.sample?.toString()?.trim()
                def tool = row.tool?.toString()?.trim()
                def msa_dir = row.msa_dir?.toString()?.trim()
                def clustering_tsv = row.clustering_tsv?.toString()?.trim()

                if (!sample) {
                    error "POST samplesheet row is missing required sample"
                }
                // `sample` keys the per-run publishDir and every join downstream, so a duplicate
                // would have two runs silently overwrite each other's outputs.
                if (!seen.add(sample)) {
                    error "POST samplesheet sample must be unique; duplicate: ${sample}"
                }
                if (!tool) {
                    error "POST samplesheet row ${sample} is missing required tool"
                }
                // msa_dir is the sole membership source -- there is nothing to fall back on, so a
                // row without one cannot be scored at all.
                if (!msa_dir) {
                    error "POST samplesheet row ${sample} is missing required msa_dir"
                }

                tuple(
                    // `has_clustering` rides in the meta map so conf/modules.config can gate
                    // INVESTIGATE_MATCHED_ORIGINALS on it with `ext.when`, keeping the branch out
                    // of the workflow body.
                    [id: sample, tool: tool, has_clustering: clustering_tsv ? true : false],
                    file(msa_dir, checkIfExists: true),
                    clustering_tsv ? file(clustering_tsv, checkIfExists: true) : []
                )
            }
        }
}
