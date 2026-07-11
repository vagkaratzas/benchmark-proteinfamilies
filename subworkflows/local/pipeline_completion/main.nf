workflow PIPELINE_COMPLETION {

    main:
    // Every module publishes its tool versions on the global `versions` topic as
    // (process, tool, version) tuples, so the collector does not have to be threaded through
    // each workflow's channels -- it subscribes here once and covers both PRE and POST.
    // `unique()` collapses the repeat emissions of a process that ran once per sample.
    channel.topic('versions')
        .unique()
        .map { process, tool, version -> [process, "${tool}: ${version}"] }
        .groupTuple()
        .map { process, tools -> "\"${process}\":\n" + tools.sort().collect { tool -> "    ${tool}" }.join("\n") }
        .collectFile(
            name: 'software_versions.yml',
            storeDir: "${params.outdir}/pipeline_info",
            sort: true,
            newLine: true
        )

    def run_workflow = workflow
    def run_params = params
    def pipeline_name = run_workflow.manifest.name
    workflow.onComplete {
        log.info """
        ------------------------------------------------------
        Completed : ${pipeline_name}
        Duration  : ${run_workflow.duration}
        Outdir    : ${run_params.outdir}
        Status    : ${run_workflow.success ? 'SUCCESS' : 'FAILED'}
        ------------------------------------------------------
        """.stripIndent()
    }
}
