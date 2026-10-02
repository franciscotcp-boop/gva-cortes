# Difficult-coverage offers: October 2, 2026

Source: https://ceice.gva.es/documents/162909733/415675295/261002_pue_def.pdf

SHA-256: dc3d71e46a310792b8320d325ddcec6e3a9ba78f49d5eddbaa124f0440d9eff4

The attached file matches the official definitive PDF byte-for-byte. Its
printed date is October 2. The owner's explicit exception makes its offers
visible on October 2 and hidden from October 3 at 00:00 Madrid time.

## Publication

- 18 pages; 162 unique printed posts, all extracted and checked by a second
  PDF reader; all centers exist in the current center guide.
- 84 Masters posts and 78 Secondary/other-body posts across 46 specialties.
- 7 vacancies, 36 indefinite replacements, 119 defined replacements.
- 20 English-requirement posts; 13 itinerant posts. Observations and composition
  are retained, including PROA+, singular centers and PFQB.
- 157 overlaps with the 159 remaining ordinary offers. Difficult coverage
  takes priority, with no duplicate post IDs. Today: 162 difficult + 2 ordinary
  = 164 offers. Tomorrow: 2 ordinary offers.
- Cuts, personal profiles and assignment conditions are unchanged. Only
  the offered-post snapshot is updated, so clients do not need a release.

## Calendar change

From now on, difficult coverage is checked Thursdays, September-June, every
30 minutes from 13:20 to 15:50 Madrid time. Other Thursday checks remain at
09:20, 11:20, 17:20, 19:20, 21:20 and 23:20. Friday accreditation checks
are unchanged; there are no scheduled Friday difficult-coverage imports.

A local daily cleanup at 00:20 removes expired offers without accessing
Conselleria. Normal Thursday offers therefore expire Friday; the current
Friday exception expires Saturday. Existing web and Android clients also
hide difficult offers immediately when their snapshot date is no longer
today, including cached data.

The selector and watchdog use the same calendar. Delayed Thursday scheduled
events cannot reopen Thursday offers on Friday. Definitive `_pue_def.pdf`
links are recognized even without descriptive link text. An invalid difficult
PDF now raises a failure instead of silently reporting no current document,
preserving the last valid publication for recovery.

Verification: 173 Python tests, 30 watchdog tests, runtime schema checks,
162-post independent inventory, client cached-data expiry checks, and the
Android event detector (only the new difficult-offer event changes).
