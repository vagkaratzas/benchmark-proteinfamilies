include { DIAMOND_MAKEDB          } from '../../../modules/nf-core/diamond/makedb/main'
include { DIAMOND_BLASTP          } from '../../../modules/nf-core/diamond/blastp/main'
include { IDENTIFY_UNIPROT_DECOYS } from '../../../modules/local/identify_uniprot_decoys/main'
include { COMBINE_DECOY_FASTA     } from '../../../modules/local/combine_decoy_fasta/main'

//
// Add negative controls to the benchmark universe: SwissProt proteins that align to none of
// the curated families, so a tool that over-recruits can be caught doing it.
//
// The decoys must be proteins the curated families do not already contain, which is why this
// runs DIAMOND rather than sampling SwissProt blindly: every SwissProt protein is searched
// against the curated set, and only the ones with no hit are eligible.
//
workflow GENERATE_DECOYS {

    take:
    curated_fasta    // combined_db.faa: every sampled curated sequence
    curated_registry // id_registry.tsv for the curated (non-decoy) sequences
    swissprot        // SwissProt FASTA, the decoy source
    num_decoys
    seed

    main:
    ch_db = curated_fasta.map { fasta -> [[id: 'combined_db_fasta'], fasta] }
    DIAMOND_MAKEDB( ch_db, [], [], [] )

    // DIAMOND_BLASTP takes the query as a tuple of (meta, [files]); SwissProt is the query
    // and the curated families are the database, so a "no hit" means "not a curated protein".
    ch_sp = swissprot.map { sp -> [[id: 'sp_diamond_db'], [sp]] }
    DIAMOND_BLASTP(
        ch_sp,
        DIAMOND_MAKEDB.out.db,
        6,
        'qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore'
    )

    IDENTIFY_UNIPROT_DECOYS( DIAMOND_BLASTP.out.txt, ch_sp, num_decoys, seed )

    // The registry is extended with the decoy rows here, so `source_type` is recorded by PRE
    // rather than being guessed from an ID shape downstream.
    COMBINE_DECOY_FASTA( curated_fasta, IDENTIFY_UNIPROT_DECOYS.out.decoys, curated_registry )

    emit:
    fasta           = COMBINE_DECOY_FASTA.out.fasta
    registry        = COMBINE_DECOY_FASTA.out.registry
    universe_sha256 = COMBINE_DECOY_FASTA.out.universe_sha256
    // Not `log`: that name is taken by Nextflow's own logger and shadowing it fails at parse time.
    dedup_log       = COMBINE_DECOY_FASTA.out.log
}
