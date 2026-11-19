# Ingestion and document versions

## Workbook contract

The importer validates the four named collar/survey/lithology/assay sheets and essential headers before writing. Errors identify the sheet and Excel row. An invalid workbook writes no rows. The CLI reports a `CommandError`; dry runs use the same parsing, tenant and range checks without committing data.

Without **Update existing**, repeat imports skip a matching hole and its children. With replacement enabled, collar metadata and child categories are replaced atomically. An empty child sheet clears that category for the workbook's matching holes. Unrelated holes and existing prospect links are retained. Ambiguous existing duplicate identifiers reject the workbook instead of selecting an arbitrary record.

The service locks the process to serialize its concurrent imports. Data and import audit commit together. Direct ORM writers do not automatically take this service lock.

## Measurements and coordinates

Validation rejects nonfinite/malformed numbers, incomplete coordinate pairs, unsupported grids, invalid projected coordinate ranges, transformation errors and invalid WGS84 output. Optional missing coordinate pairs remain allowed. Source CRS/easting/northing are retained.

Depths must be nonnegative; dip and bearing have explicit ranges. Intervals require `0 <= from < to` and cannot exceed a known total depth. Dates, field lengths and choices are checked. Negative assay values are retained because the existing source convention uses them for below-detection notation. Overlap/check-assay policies require domain-specific treatment rather than a blanket prohibition.

## Document versions

Version creation locks and re-reads the parent, rejecting stale uploads. Replacement metadata, extracted chunks and parent retirement are transactional. Every version uses a unique UUID-based storage path, so an upload with the same filename cannot overwrite historical bytes.

Extraction occurs before storage consumes the stream. If database work fails after a newly stored key is acknowledged, the service attempts cleanup while leaving the old version current. Database/object storage are not a distributed transaction: abrupt termination, failed cleanup or a later enclosing rollback can still leave orphaned files. A reconciliation service and live storage-fault tests remain necessary.

[Verification](../VERIFICATION.md) includes real workbook, storage-failure, rollback and concurrency checks.
