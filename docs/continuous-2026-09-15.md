# Continuous adjudication, 15 September 2026

Imported both user-supplied PDFs after confirming their date and official links
on the Conselleria resolution page. The scheduled updater run 1654 failed on
connection timeouts loading that page before downloading either PDF. Its tests
passed and it did not publish partial data. No workflow or client code is changed.
The importer now handles the explicitly reviewed program-code exception below.

## Checks

- Maestros: 8,270 status records matched; 309 strict specialty awards, 292 cuts.
- Other bodies: 15,293 status records matched; 297 strict specialty awards plus
  11 program awards linked to their originating headers, yielding 302 cuts.
- All 617 awards match exactly one personal award detail, including center,
  type, workload, English requirement, itinerancy and source observations.
- Independent extraction counted 315 printed Adjudicat blocks in Maestros and
  442 in other bodies, exactly matching the parser's awarded status records.
- Every new Maestro cut has a positive specialty position; start-of-year cuts
  and initial individual positions are unchanged.
- 617 distinct covered posts removed from 681 offers, leaving 64 unfilled.
- Notification detector reports a new continuous-results event, without a new
  start-results or offered-post event. Publication is a single data commit.
- All 132 repository tests pass, including ordinary cross-specialty rejection,
  program origin, bilingual notes, ambiguous-origin rejection and offer matching.

## Reviewed Program Assignments

The user clarified that posts with these program codes belong to the originating
specialty header. The PDF has exactly one awarded header for each of these
eleven people. Preserve that specialty and its printed rank and append the
program code and bilingual name to observations. The current released clients
display observation strings literally, so both languages appear together
without a CodePen edit or Android update. These are not difficult coverage.

The exception is restricted to reviewed codes 275, 276, 277, 293 and 297;
ordinary cross-specialty cases still require matching codes. Reject ambiguous
originating headers rather than selecting a rank arbitrarily. Preserve the
actual offered specialty code for offer matching and removal.

| Post | Program | Origin | Rank | PDF page | Official name |
| --- | --- | --- | --- | --- | --- |
| 767192 | 293 | 201 | 74 | 279 | VILA SERRANO, ALBA |
| 831056 | 293 | 201 | 133 | 285 | MIRALLES MALFEITO, ESTHER |
| 213439 | 275 | 202 | 15 | 297 | SAN MAXIMO RANGEL, NOELIA |
| 200384 | 275 | 203 | 25 | 301 | LOPEZ PASTOR, AITANA |
| 215868 | 275 | 203 | 53 | 304 | JIMENEZ AGUILAR, ZAHIRA |
| 767189 | 293 | 205 | 228 | 391 | MARTINEZ PEIRO, IVAN |
| 899336 | 277 | 205 | 253 | 394 | REDONDO FERNANDEZ, MARINA |
| 906274 | 277 | 205 | 284 | 397 | GARCIA LLORENS, JOSE MIGUEL |
| 600180 | 276 | 207 | 286 | 616 | PEREZ DOMINGO SIMARRO, CRISTINA |
| 871091 | 276 | 219 | 257 | 1095 | MARTI NAVARRO, ANA MARIA |
| 787373 | 297 | 256 | 7 | 1395 | BELDA GANDIA, ELVIRA |

The provisional difficult-coverage participant list remains excluded.
