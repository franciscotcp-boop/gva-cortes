# Difficult-Coverage Assignments

Status: provisional arrows are not publishable. The owner has now requested
individual cross-checks against the official GVA staff directory because no
definitive result PDF will be published for this round.

The 11 September participant PDF is provisional. Its arrows do not confirm that
candidates attended or met the qualification requirements. No awards from that
document may be published merely because they are arrow-marked.

## Manually Reviewed Directory Evidence

`make_directory_review_ledger` accepts a separate, reviewed evidence record for
each assignment. It requires a single exact normalized-name result, a verified
school code, official directory URLs, and the check timestamp. Conflicting
ordinary assignments, homonyms, and multiple possible posts at the same school
must remain pending for manual resolution. No result is not proof that a person
was not awarded; it must not clear an existing assignment.

By default, official award PDFs take priority over directory-based inferences. The
review importer rejects people with an existing official award. Subsequent
automatic rebuilds suppress a directory inference if an official award appears,
including a correction to an older PDF; they never change that PDF's assignment.
Merging a directory review also rejects replacing a previously imported official
difficult-coverage round or attributing another inferred post to its awardee.
Also review later offer snapshots and filled-post reconciliation by post ID: a
post reoffered or officially assigned after the reviewed round cannot be dated
to that earlier round from current workplace evidence alone.

The owner has manually resolved exceptions for the 11 September round. These
are not blanket permission to ignore PDFs or infer future awards. Record each
choice in the award's `verification.manual_confirmation`. A later reoffer alone
does not invalidate an owner-confirmed placement from this round. Where several
posts at the confirmed school have identical visible conditions, `slot_id` is
null and `possible_slot_ids` retains the alternatives; do not invent a post ID.

`pool_identity` selects a specific existing homonym without changing her ranks.
For a confirmed separate person outside the pool, set
`profile_resolution.separate_homonym`, retain the PDF name in
`source_official_name`, and use that same full name in given-name-first order
in the client-facing `official_name`. Do not set `pool_identity` or add an empty
pool row: legacy clients discard empty rows before attaching the ledger. This
distinct, non-fabricated name ordering lets the client create one unranked
searchable homonym without reusing the existing person's award or pool ranks.

An explicit confirmation that an ordinary substitution has ended may use
`profile_resolution.superseded_ordinary_assignments`. Each item stores the exact
specialty and full original detail; only that exact active detail becomes N/null
in the personal profile. Keep its historical assignment and all cutoffs intact.
A different or newer ordinary award is not cleared. Both continuous updates and
pool rebuilds reapply the reviewed resolutions before publishing. The current
exception is Hector Cosa Selva's ended 266 substitution; Lidia Marton Bedia keeps
her ordinary IES Pou Clar award.

The provisional PDF supplies the ordered candidates and post header; the saved
offer snapshot supplies hours, notes and other working conditions. The staff
directory confirms current workplace, not the exact award date, specialty or
post identifier. This method is therefore an explicitly requested cross-reference,
not an official definitive adjudication resolution. Record that distinction in
`verification_basis`, `source.document_type`, `source.is_definitive_resolution`
and the per-award `verification` object.

The existing clients require the compatibility value `status: definitive` for
a released ledger. That value must not be used to describe the provisional source
PDF as definitive. The normal PDF importer still rejects provisional documents.

## Data Boundary

Released awards use the optional `difficult_assignments` extension in the pool
JSON, backed by a separate ledger. They never become cuts or lottery-based pool
ranks. Ranks and regular notification timestamps are unchanged. Existing profile
statuses only change for explicitly confirmed, narrowly scoped resolutions above.
Optional specialty labels can complete missing catalog names in both languages;
they do not add a person to a pool or create a rank.

The importer requires an explicitly reviewed definitive document and rejects
provisional headings. Recheck the extraction layout when that document arrives;
the final PDF may differ from the participant-table format used for preparation.
Match names without accent differences. Never resolve homonyms by lottery order.

## Display

- The awarded specialty comes first, with the awarded and difficult-coverage badges.
- If the person already belongs to that specialty pool, retain all its numbers.
- For master special-education posts 151/152, reuse the existing 126/127 pool
  only when that person is already registered there. Preserve the original post
  specialty in `offered_specialty_code`; never invent a pool entry or number.
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

Provisional arrows have not been imported as awards. No automatic watcher for
definitive difficult-coverage results has been added. The future definitive layout
may require an extractor adjustment, but the published client contract is ready.
