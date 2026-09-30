# Ordinary offers published on 30 September 2026

The 1 October round replaces the previous ordinary snapshot (47 unfilled
positions) with 632 positions: 339 Maestros and 293 Secondary/other bodies,
covering 84 specialties. It contains 21 vacancies, 221 indefinite replacements
and 390 fixed-term replacements; 56 positions require English and 25 are
itinerant. Observations were preserved for 92 positions and shared-center
compositions for 18. All centers are present in the guide.

Official source:
https://ceice.gva.es/documents/162909733/415637604/261001_pue_prov.pdf

The official 90-page PDF is byte-identical to the owner-supplied attachment.
SHA-256: `16d6510c6fdf47c42c43c700aa8260b8195cfbaf28e845354ab77b843fa9d156`.
Printed publication date: 30/09/2026; adjudication round: 01/10/2026.

Validation:

- Independent PDF slot inventory matches all 632 extracted positions.
- No duplicates, unknown centers, or truncated `fins al` observations.
- All other runtime JSON datasets remain byte-for-byte unchanged, including
  personal profiles, cuts, and the 284 reviewed difficult-coverage awards.
- 156 Python regression tests and runtime validation pass.
- The actual Android publication detector sees only the new
  `continuous_offers` event, available on 30 September, not a repeated result,
  initial-round, or difficult-coverage notification.

No website or Android binary changes are required.
