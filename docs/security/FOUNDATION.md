# Access and security policy

`core/access.py` centralises organisation, role and clearance decisions. Requests without a valid tenant/profile fail closed. Record access also checks relevant project, tenement and source relationships, preventing a permitted parent ID from exposing foreign related data.

## Administration and writes

Application author roles may create reports and permitted domain records. Editing a report requires its author or an application administrator in the same organisation, subject to clearance. Ordinary application administrators do not gain access to Django's unscoped platform admin; that interface is reserved for platform superusers.

Report revision/review rules apply in addition to role checks: an author cannot edit a locked or stale revision by posting its ID directly. Review authority is separately checked for the selected pathway.

## Derived information and files

Document and report lists, detail routes, links, analysis, exports and reviewed cache paths enforce organisation/clearance. Reports preserve the requesting context's conservative classification. The report editor also checks source-document access; a report link does not bypass a reclassified source.

Uploaded files are private. Downloads use authenticated application routes and current access checks; model file URLs are not an authorization mechanism. Stored geospatial/user-controlled strings are serialized safely before use in browser scripts.

Audit records retain organisation/clearance context. Data-changing services that require an audit write keep it in their database transaction, so an audit failure does not leave a falsely recorded successful mutation.

## Limits

These controls cover the reviewed application routes and services. They do not establish universal integrity for every direct ORM/platform-admin writer, a complete penetration test or compliance certification. Existing development infrastructure and dependency issues must be addressed before public deployment.

[Verification](../VERIFICATION.md) · [Architecture](../ARCHITECTURE.md)
