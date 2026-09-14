# Definitive Difficult-Coverage Assignments

Status: waiting for the definitive result PDF. Do not publish provisional winners.

The 11 September participant PDF is provisional. Its arrows do not confirm that
candidates attended or met the qualification requirements. No awards from that
document are present in the public runtime data.

## Data Boundary

Definitive awards use the optional `difficult_assignments` extension in the pool
JSON, backed by a separate ledger. They never become cuts or lottery-based pool
ranks. Existing people, ranks and regular notification timestamps are unchanged.

The importer requires an explicitly reviewed definitive document and rejects
provisional headings. Recheck the extraction layout when that document arrives;
the final PDF may differ from the participant-table format used for preparation.
Match names without accent differences. Never resolve homonyms by lottery order.

## Display

- The awarded specialty comes first, with the awarded and difficult-coverage badges.
- If the person already belongs to that specialty pool, retain all its numbers.
- Otherwise show an independent award card, without inventing membership or ranks.
- Include the existing center details, contacts, location controls and award date.
- Keep other specialty cards and ranks below, with a not-awarded display status.
- A later ordinary assignment supersedes an earlier difficult-coverage award.
- Provisional, ambiguous and other-academic-year awards do not activate cards.

Both languages and both clients share this behavior. The existing CodePen
`Francisco-LD/wBgYewP`, embedded in the user's website, now supports the extension.
Android 1.8.4 (versionCode 31) includes the same support. The APK and AAB use the
existing upload signing certificate. Users need this client update before a new
specialty outside their registered pools can be displayed correctly.

## Importing the Future Definitive PDF

1. Verify the document is definitive and review its layout and selected winners.
2. Recover the matching difficult-coverage offer snapshot, including hours and notes.
3. Run `scripts/difficult_assignments.py` with the PDF, `--offers`, `--date`, and
   `--confirmed-final`. The date must be the definitive adjudication date.
4. Resolve ambiguous identities manually before making their awards visible.
   `pool_identity`, when needed, is the exact list of specialty/initial-rank pairs
   of the reviewed pool record; names remain accent-insensitive.
5. Validate the ledger, personal cards, unchanged cuts, and unchanged notification
   publication stamps before publishing the JSON and independent ledger together.

The provisional participant PDF has not been imported. No automatic watcher for
definitive difficult-coverage results has been added. The future definitive layout
may require an extractor adjustment, but the published client contract is ready.
