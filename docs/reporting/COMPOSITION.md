# Evidence-scoped report composition

`ReportCompositionForm` validates project, report type, tone, instructions, source mode, explicit document IDs and section/reference options. The six report types select different outlines. Invalid values, inaccessible/wrong-project/old document IDs and oversized selections fail before drafting.

## Evidence modes

- **Selected files:** one to ten accessible latest documents from the project; no unrelated context is added.
- **Latest project files:** at most ten latest accessible project documents, with the selected subset recorded.
- **Prospect:** directly linked accessible files and the target's project/prospect context; an empty linked set never falls back to unrelated project documents.

The queue fixes source IDs/fingerprints and the project/prospect context. Drafting uses those frozen inputs after access revalidation. A ranked passage is selected within each chosen document; this does not remove file/subset limits. Prospect context includes hypothesis as an unverified proposition, objective, location and a bounded linked-collar summary, not the complete geological database.

## Draft methods

AI-assisted drafting passes report type, tone, additional instructions and enabled sections to the configured provider. These are model instructions, not guarantees of adherence. Sources are treated as untrusted evidence, and the prompt explicitly distinguishes observations, inference and missing information.

Manual mode prepares the selected outline without instantiating/calling a provider. The source/context excerpts remain available for author reference. Its manifest records backend `manual`, with no model or submitted prompt. Both modes use the durable worker.

## Bounds and provenance

AI prompts have a 6,000 UTF-8 byte cap, with bounded per-document passages. Oversized instructions/metadata fail rather than silently dropping selected evidence. This byte limit is not a measurement against every model's tokenizer.

The saved manifest records options, scope, source identities/versions/checksums/fingerprints, passage details and serialized context. For AI drafts it also records the exact prompt/hash, model/backend and generation-time citation check. Manual edits retain the original drafting record. Historical reports are not assigned invented provenance.

Source/context access is checked before generation and before publication. Report/source/audit persistence is transactional. The normal composer and prospect actions bypass legacy process-level generation caches.

[Jobs](JOBS.md) · [Evaluation](../ai/QUALITY.md) · [Geological assembly](ASSEMBLY.md)
