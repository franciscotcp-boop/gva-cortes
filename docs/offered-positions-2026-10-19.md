# Ordinary offers published on 2026-10-19

- Source: https://ceice.gva.es/documents/162909733/415637604/261020_pue_prov.pdf
- Attached PDF matches the official download byte for byte.
- SHA-256: `7b17dc1f98a30fb5689669f28b613d67eacee5fe17e156a96c14450007977af2`.
- Printed publication: 19 October; adjudication round: 20 October 2026.
- 61 pages; all 334 printed slot identifiers independently checked with pypdf.
- 172 Maestros and 162 other-body offers across 63 specialties.
- 33 vacancies, 241 indefinite substitutions and 60 fixed-term substitutions.
- 31 English requirements, 13 itinerant posts, 63 observations and 6 compositions.
- No missing center codes or truncated `fins al` observations.
- Replaces the previous ordinary snapshot and removes 91 expired difficult-coverage offers.
- No changes to cuts, personal profiles, accreditations or other published data.

## Automation blocker

GitHub run 1816 (`39179970845`, job `117830440466`) failed before reaching
the source-download steps: `test_verify_public_backups` could not import
`requests`. The backup verifier introduced that dependency without declaring
it in `requirements.txt`. Add the explicit dependency and a regression check
that it is installed before validation. Declare Windows timezone data too,
so the same tests run in a clean Windows environment.

Verification: all 185 tests pass in a fresh virtual environment installed
only from the repository requirements; `pip check` reports no broken requirements.
This fixes the dependency failure, not any independent remote-network restriction.

## Live verification

- Commit: `9e15bbbce6bfcc09c22337d2948c5aa0bcf4d490`.
- GitHub run 1817 (`39252596440`) completed successfully on 19 October.
  It passed all 185 tests, fetched the official source and returned `unchanged`
  for `261020_pue_prov.pdf`, ordinary snapshot 20 October, 334 items.
  No duplicate publication or extra notification fingerprint was generated.
- Primary public JSON matched the complete staged payload, with CORS `*`.
- The existing embedded CodePen on the published WordPress page loaded the new
  offer date and returned Infantil posts ordered from Elx/Elche, including
  hours, English requirements, itinerancy, compositions and observations.
- The unchanged Android 1.8.4 importer displayed all 334 items on both 19 and
  20 October. Its actual Java event detector produced a new `continuous_offers`
  event on 19 October; all other notification events stayed unchanged.
  This is not a claim of physical notification delivery to every device.
