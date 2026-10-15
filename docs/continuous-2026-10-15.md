# October 15 Publication Audit

The automation published the supplied PDFs before this manual review. Run 1778
completed successfully and created commit `f182ad7` at 12:39:57 UTC (14:39 Madrid).
No duplicate data publication or notification event was introduced by the audit.

## Sources and Results

- `261015_lis_mae.pdf`: 758 pages, SHA-256
  `96e7007294d9cdeef85006bad7693fdb10beea4d3d41f62672fc28361dd7f85b`.
- `261015_lis_sec.pdf`: 1,433 pages, SHA-256
  `a85ddbf546264559d7dbad6c8657d5e09dde4303fe18d3c85e74d26682225f38`.
- `261016_pue_prov.pdf`: 12 pages, SHA-256
  `50a27a3e4ef0238c1209bf264ffd3c4824671589db48fe33e473492714cf260c`.
  The printed publication date is October 15, despite October 16 in the filename.

All three hashes match the automated publication. The full reparse verifies 222
Maestros awards and 156 other-body awards, with exactly one matching personal
profile per award, including center, hours, placement type, English requirement,
itinerancy and observations. All covered slot keys are accounted for. Five
program placements have a unique originating pool and retain their program codes
and bilingual notes. No program-pool choice needs owner resolution.

Independent PDF text counts find 227 awarded rows in Maestros and 212 in other
bodies, matching the parser's status rows. These are not counts of unique awards:
the published profiles and cutoffs deduplicate repeated participants/placements.

The offer reconciliation removes 378 covered posts from the previous 467,
leaving 89 unfilled. Difficult coverage supersedes 88 overlapping ordinary posts.
The result is 91 difficult-coverage offers plus one ordinary retained offer
(207630, Mathematics, IES Joan Llopis Mari in Cullera), without duplicate slots.
The 91 difficult offers expire on October 16 at 00:00 Europe/Madrid. Both shipped
clients hide them with cached data after that boundary, preserving the ordinary
offer. All center codes exist and no split `fins al` observation is incomplete.

Initial cutoffs and initial ranks remain unchanged. The primary public URLs match
the validated files and provide the required cross-origin access. The shipped
Android and CodePen importers pass all 378 award checks and offer-expiry checks.
The actual Android event detector changes only `continuous_results` and
`difficult_offers`; repeated reads preserve event identifiers.

## Identity Review

The previously owner-confirmed separate identities DEL ARCO VICENT and DEL ARCO
VICENTE remain separate. A new non-awarded participant, TENA MARTINEZ, AIDA
(general position 3275, participated), is not automatically merged with the
initial Infantil profile MARTINEZ TENA, AIDA (initial position 4857). On October 15
the owner explicitly confirmed that these identities must remain separate.
Do not transfer general position 3275 to the initial Infantil profile or infer
a specialty for TENA MARTINEZ, AIDA from the other person's record. No awarded
profile is missing.
The owner subsequently confirmed that TENA MARTINEZ, AIDA cannot be located in
her initial pool and explicitly requested leaving her without a personal profile
for now. Preserve the existing MARTINEZ TENA, AIDA profile unchanged; do not add
a placeholder or merge the identities based on their neighboring list entries.

## Failed Queued Run

Run 1779 was queued at 12:38:37 UTC while run 1778 was active. Its checkout at
12:40:15 still selected the event's older commit `29f23f2`, even though `f182ad7`
had already been published. Its non-fast-forward push was correctly rejected at
12:42:45. This was not a Conselleria download failure and did not undo the earlier
successful publication. Runs 1780 and 1781 subsequently completed successfully.

The updater checkout now explicitly selects the current default branch when the
queued job starts. Existing concurrency serialization, validation and ordinary
non-force push protections remain intact. A regression test covers the checkout
configuration; all 176 tests pass. Manual changes during a running job still
cannot be overwritten by a force push.
