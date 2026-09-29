# Continuous adjudications: 29 September 2026

## Sources

Both attached files match the official downloads byte for byte:

- https://ceice.gva.es/documents/162909733/414354213/260929_lis_mae.pdf
  SHA-256 `093989fca72b3f16749f18c7eb6dc17e2d13ec3c36089ae772154e7366c095e3`
- https://ceice.gva.es/documents/162909733/414354213/260929_lis_sec.pdf
  SHA-256 `9e8bacd93c1d02f8918f872dddd673db23dada3db9f3f5e66b8ec79e868de741`

814 Maestros pages and 1,485 secondary/other-body pages. An independent reader
counts 144 and 210 printed `Adjudicat` entries, respectively; these exactly
match the parsed statuses. Cross-body and cross-specialty repetitions do not
create duplicate awards or incorrect cuts.

## Results

- 298 unique awards: 140 Maestros and 158 secondary/other bodies.
- Today's center/specialty cut rows: 138 Maestros and 153 other bodies.
- 11,062 accumulated continuous cut rows; all 7,076 initial cuts unchanged.
- Current statuses, ranks, province information and personal assignment details
  updated. Initial ranks retained, including people not awarded today.
- Remove 298 filled post/center/specialty identities from the 345 offered
  posts; retain exactly 47 unfilled posts with the original offer source.
- 58 assignments retain observations; no fabricated observation text.
- All 284 reviewed difficult-coverage awards remain unchanged.
- No CodePen edit or Android build required.

## Identity and originating-pool decisions

The owner confirmed Carlos Bagan Sevillano, post 875872, IES La Plana,
as Physics/Chemistry 207, rank 67. The 276 scientific-area program remains in
the bilingual observations. The decision is scoped to this PDF's hash, name,
center, slot and actual post specialty.

Ricardo Simo Vedreno, post 767329 at the public FPA center in Mislata,
appears awarded only in Biology/Geology 208, rank 58. Handle FPA program 292
with the existing originating-pool exception and preserve the bilingual
program note. Ambiguous origins still require review; ordinary mismatching
specialties still do not create cuts.

The owner explicitly confirmed that `DEL ARCO VICENT, MARIA DESAMPARADOS`
(current Maestros rank 7160, not awarded) and
`DEL ARCO VICENTE, MARIA DESAMPARADOS` (initial general rank 17161) are
different people. Do not alias them or transfer specialties. The former has
no confirmed initial specialties, so her status remains unmatched rather
than inventing a profile or modifying the latter's identity/rank. All 298
awards have exactly one verified personal-profile match.

## Validation

156 regression tests pass. Independent slot/profile/cut audit and runtime
validation pass: 3,861 centers, 45,659 people, 22,721 assignment-context rows,
47 offers and 17,164 accreditations.

The Android publication detector generates only the new `continuous_results`
event. Removing filled offers does not generate another offered-post event,
and no initial-result or difficult-coverage event changes. This checks event
generation, not notification delivery on each user's device.
