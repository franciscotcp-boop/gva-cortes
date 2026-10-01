# Continuous results, 1 October 2026

Both owner-supplied PDFs were independently downloaded from the official page
and confirmed byte-identical before publication:

- Maestros: https://ceice.gva.es/documents/162909733/415637604/261001_lis_mae.pdf
  SHA-256: `98c2ef0d4210d66b54986eb25bc355f72b13c027695341bd06bbe58da3801ef7`.
- Secundaria: https://ceice.gva.es/documents/162909733/415637604/261001_lis_sec.pdf
  SHA-256: `9c37583538315ed02524236e269ae69bdfa4649b5263b453d2ca63db13f80ee7`.

The 800-page Maestros PDF contains 265 printed awarded records. The 1,518-page
Secundaria PDF contains 282; cross-specialty and cross-body repetitions do not
create duplicate awards or cuts. Independent text extraction matches every
printed awarded status, and all 473 distinct posts are represented.

Published 255 Maestros and 218 Secundaria awards. Updated continuous cuts,
current statuses, specialty positions, profile assignment details, observations,
province counts and cumulative vacancy totals. Removed the 473 covered offers
from the current 632-post snapshot; retained precisely the 159 unfilled posts.
Start-of-course cuts and initial ranks remain unchanged. All 284 reviewed
difficult-coverage awards remain intact.

## Owner-reviewed program assignments

- Guillermo Vicedo Dura, 841479: originating pool 256, position 230;
  retain 297 FPA Comunicacion (Valenciano) in observations.
- Laura Pellicer Carboneras, 200253: originating pool 203, position 30;
  retain 275 Cultura Clasica in observations.
- Jorge Roca Coscolla, 207211: originating pool 219, position 152;
  retain 276 Ambito Cientifico in observations and the itinerant flag.

These selections are scoped to the exact source SHA, name, center and post.
The owner-confirmed distinct Vicent/Vicente identities remain separate; the
unmatched non-awarded Vicent row is never applied to the Vicente profile.

## Verification

All 161 Python regression tests passed. The full staged/runtime audit found
zero omitted posts and zero unmatched awards. Runtime validation reports:
3,860 centers, 7,076 initial cuts, 11,183 continuous cuts, 45,660 people,
23,172 assignment-context records, 159 offers and 17,164 accreditations.
The actual Android publication detector produced only a new continuous-results
event; no initial-results or offered-post event was introduced.

No client source, CodePen, APK or AAB was changed.
