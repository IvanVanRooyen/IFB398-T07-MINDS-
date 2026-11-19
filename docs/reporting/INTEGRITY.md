# Report revisions and review

Reports have a stable `series_id`, distinct from a particular revision ID or title. Title changes remain part of the same series. A revision retains its parent and inherits source-document relations, original drafting provenance and the geological appendix unless an explicit capture/removal changes that appendix.

## Save contract

Writers lock the series anchor and parent revision. Only the latest editable draft can be saved. An outdated parent returns a conflict with the latest accessible version link; a locked revision cannot become a draft through an update request.

Title, narrative, clearance and appendix changes participate in revision detection. Keeping identical content and the saved appendix is a no-op. Data and the required audit write commit together. The editor follows the returned revision/save/review URLs rather than continuing to post to the old revision.

## Review contract

The editor submits its current title/narrative and appendix choice. The server saves that exact combination when needed, then links the workflow to that revision and locks it for review. A partial or stale editor payload is rejected. Native form submission includes the same externally associated fields without requiring JavaScript.

The enhanced editor retains local changes after a failed save. Navigation/review/export waits for necessary saves, and edits made during an in-flight request remain marked unsaved rather than being silently discarded.

Review, approval, rejection and publication check the relevant authority and state. JORC/VALMIN names describe review pathways, not certification. Full framework requirements and qualified domain review remain separate work.

## Export boundary

Reports with geological appendices export saved narrative and data together. Unsaved mismatched title/text is rejected; native CRLF differences are normalized. The editor saves dirty changes before requesting a download. Legacy process/cache exports retain separate behavior; fully archived/signed artifacts and a complete frozen source catalogue remain open.

[Geological assembly](ASSEMBLY.md) · [Verification](../VERIFICATION.md)
