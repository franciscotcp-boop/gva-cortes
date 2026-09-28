# Ordinary offered posts published on 2026-09-28

Source: https://ceice.gva.es/documents/162909733/414354213/260929_pue_prov.pdf

The official download matches the user-supplied PDF byte for byte.
SHA-256: `252cc161a6d16792430190a067a295ec583463d5b01f53ddcab0f6c2902b8d15`.
The 67-page PDF is dated 28 September and concerns the 29 September round.
The existing `publication_date` / `snapshot_date` contract stores the round
date, `2026-09-29`; the offers are available immediately, not delayed until then.

## Replacement and checks

- Replace the three remaining ordinary offers with all 345 current offers.
- 158 Maestros, 187 other bodies; 70 specialties.
- 50 vacancies, 234 indefinite substitutions, 61 determined substitutions.
- 23 English requirements, 18 itinerant posts, 69 nonempty observations.
- Preserve all 13 shared-center compositions, including their center codes,
  hours and specialties. PDF drawing order avoids overlapping names/hours;
  extraction checks the center codes against the page layout and excludes
  following rows, headings and page footers.
- An independent PDF slot inventory matches all 345 unique slot identifiers.
- No unknown centers or truncated `fins al` observations.
- Keep cuts, personal profiles, ranks, accreditations and all 284 difficult
  coverage awards unchanged. No reconciliation against a future result PDF.
- Existing web and Android clients already display the composition field;
  no CodePen edit, APK or AAB is necessary.

## Validation

154 regression tests passed. Runtime validation passed with 3,861 centers,
7,076 initial cuts, 10,991 continuous cuts, 45,657 people, 22,445 assignment
context entries, 345 offers and 17,164 accreditations.

The actual Android publication event detector was exercised with the previous
and new snapshots at 2026-09-28: only `continuous_offers` changes. Initial and
continuous result events and difficult coverage events do not change. This
checks event generation, not delivery to every device.
