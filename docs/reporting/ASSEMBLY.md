# Geological report assembly

A saved report combines Markdown narrative with an optional fixed-schema geological appendix. It is a bounded evidence component, not yet a general section/block editor or framework template engine.

## Capture and revisions

The editor can keep the saved appendix, capture current project/prospect records or remove it. Save/review applies the choice with the current title/narrative. Ordinary narrative edits inherit the old snapshot; live source edits/deletions do not silently rewrite it. Explicit capture/removal creates a revision, even when narrative is unchanged.

The snapshot records schema version, scope, capture time, selected tables/figure, row identities/values and SHA-256. Historical reports default to an empty appendix. The existing series lock, author policy, stale-parent rejection and audit transaction apply.

## Schemas and scope

| Table | Fields |
|---|---|
| Collars | Key, name, WGS84 longitude/latitude, total depth (m), dip and true-north bearing |
| Assays | Drillhole, from/to depths (m), sample ID, Au ppm and Cu ppm |
| Lithology | Drillhole, from/to depths, lithology and mineralisation |

Only drillholes belonging to the report project and organisation are eligible. A linked prospect further restricts the scope. Child intervals belong to those holes. Mismatched project/prospect relationships fail.

Limits are 20 drillholes and 100 rows per interval table, with stable ordering. Larger scopes fail with advice to narrow the prospect or omit a table; no rows are silently truncated. Empty scopes and missing values (`—`) are explicit. Negative assays retain raw below-detection notation, without inferring a verified threshold. Invalid/nonfinite displayed measurements, coordinates and intervals fail before save.

These are recorded downhole intervals, not true widths, composites or resource estimates. Other assay elements, full lithological descriptions, methods, surveys and QA/QC are outside the fixed schemas.

## Collar figure

The optional plan is a north-up local schematic of the saved WGS84 collar points, with longitude adjusted at mean latitude. Numbered keys identify collars; missing coordinates are counted and coincident collars share a marker with combined keys. Date-line-crossing scopes require using the coordinate table instead. There is no basemap, survey-accuracy or distance-scale claim.

Browser SVG, PDF vectors and DOCX PNG use the same coordinate layout. No external map tiles or remote images are needed. Tables scroll within accessible regions on narrow screens.

## Review and exports

Submission locks the narrative and appendix in the reviewed revision. Exports for reports with appendices validate posted narrative/title against that saved version, then render saved values with revision/status/clearance and capture scope/time/digest. Native newline differences are normalized.

PDF has real repeating-header tables and a vector figure whose caption/note stays with it. DOCX has native table objects and an embedded figure with a description. Record text passed to ReportLab is escaped as text.

Capture is a bounded read set during a save transaction, not a serializable whole-database backup. Original drafting provenance remains separate. The legacy document Sources footer still reads access-checked linked-document metadata at export; full catalogue freezing, archived/signed artifacts, wider fonts and complex Markdown remain work.

[Verification](../VERIFICATION.md) includes actual PDF/DOCX parsing, a maximum-size multipage table, native saving and unchanged saved/exported values after live assays change.
