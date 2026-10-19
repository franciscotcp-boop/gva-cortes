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
