# jsDelivr Backup Verification

## Observed Incident

On October 15 the exact `@main` URL used by shipped clients for
`data/posiciones_bolsa.json` returned HTTP 200 with
`Content-Type: application/json; charset=utf-8`, but the response was a 199-byte
GitHub error message beginning `429: Too Many Requests`, not JSON. Its ETag was
`W/"c7-EzZLbDgxCg0EorqpG5RbOYGa4Ag"`. Other attempts returned HTTP 404 or timed out.

The original GitHub URL returned all 11,693,762 bytes, valid JSON, CORS `*`, and
SHA-256 `2240c53f6b965712ef4ef8abae75bcbd1438264d9edbabf9d5613c91c2946ccf`.
The repository snapshot is below the documented package limits, and this file
is below the documented 20 MB GitHub-file limit. No records need to be removed.

The owner authorized the CAPTCHA in the official purge tool. The service
reported success, but subsequent complete-content checks still rejected the
positions response. A purge success message is not evidence of valid content.
An exact-commit request and the metadata API also timed out; those diagnostic
URLs were not added to the clients.

The cutoff backup has recovered: the existing jsDelivr URL for
`data/adjudicaciones.json` returns all 3,753,889 bytes and matches GitHub exactly:
`aea7551a5e34a9c6c4a2aeb00c1d5b1a0f9b8b06b374d6634628b228144963af`.
Both primary URLs remain valid. At the final check in this review, the positions
backup was still invalid and must not be reported as repaired.

## Reusable Check

Run `python scripts/verify_public_backups.py` against the current validated
checkout. It reads the same two primary and two backup URLs as the clients and
checks HTTP status, JSON content, equality of the complete dataset, and CORS.
It explicitly rejects the observed GitHub error even when returned as HTTP 200.
Use `--attempts 2 --retry-delay 60` for one spaced retry. Requests are bounded;
the command exits nonzero if any copy is unavailable, outdated or invalid.

This is a read-only operational check, not a new schedule or an automatic purge.
It does not overwrite data, change publication IDs, send user notifications,
modify CodePen or rebuild Android. Do not repeatedly purge a healthy fallback,
and do not change teacher records to work around a CDN failure.
