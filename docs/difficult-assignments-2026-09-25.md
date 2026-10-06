# Difficult-Coverage Directory Review: 25 September 2026

Reviewed on 6 October 2026 at the owner's request. The supplied `260925_par.pdf`
is a provisional candidate list, not a definitive award resolution. The official
GVA personnel directory verifies current workplace; the archived 24 September
offer snapshot supplies the post's specialty, hours, type and conditions.

## Review

- All 400 pages, 84 posts and 7,300 candidate rows were extracted without errors.
- 442 distinct candidates were queried in their PDF order, stopping at the first
  exact accent-normalized name and verified center match for each post.
- Ten additional accent-free queries found no otherwise missed matches.
- Partial school staff lists were not used as evidence of absence.
- Only verified current-workplace matches are eligible for release. Provisional
  arrows alone do not establish attendance, qualification or an adjudication.
- Seventy new reviewed awards are released, retaining all 284 historical ledger
  entries. There are 353 active awards: Marta Munoz Albero's earlier difficult
  placement remains superseded by her later ordinary assignment.
- Existing pool ranks, cuts, offered posts and publication event identifiers are
  unchanged. No ordinary-results or offered-post notification is generated.

The legacy `status: definitive` value means released for client compatibility.
Evidence explicitly identifies the source as provisional and records the
directory cross-reference, rather than claiming an official definitive result.

## Resolved Cases

- Oscar Soriano Masia: the owner confirmed post 847595, Instalaciones
  Electrotecnicas (2A2), an 18-hour indefinite substitution at IES Marcos Zaragoza.
- Estefania Cabrera Cubero: the owner confirmed her former IES El Pla substitution
  ended. Her current card now shows post 209020, Tecnologia (219), an 18-hour
  indefinite substitution with English requirement at IES Haygon. Only the exact
  former 207 assignment detail is cleared from the active profile; history,
  cutoffs, pool membership and ranks remain unchanged.
- Lara Bernabeu Calero: the uniquely bold, arrow-marked post is 802696 at IES
  Thiar. The next verified candidate, Florina Haralambie, matches post 852101.
- Javier Albors Cano: the uniquely bold, arrow-marked post is 856199 at IES Alvaro
  Falomir. The next verified candidate, Pablo Lopez Honrubia, matches post 917212.
- Vicent Garcia Tello: department 23225 lacks a code-bearing school email. Its
  exact school name, municipality, postcode and Ramon Villanueva 15 address match
  the official guide's 46029240, Extension del CFPA La Serrania in Tuejar. This
  verifies post 917332 without attributing the parent school's code.

## Pending

Diego Ruiz Diez, post 205727 at IES Serra d'Espada, Onda, remains pending explicit
owner review because his existing card holds an ordinary 10 September assignment
at IES Enric Valor, Silla. That existing assignment has not been changed.

No verified directory match was found for posts 891247, 918372, 919090, 896092,
215999, 838230, 904631, 209807, 213853, 911967, 855805, 202109 and 918260.
Absence of a verified match does not clear any existing award or certify that a
post is officially vacant.

## Verification

All 175 regression tests pass. Both shipped client importers attach all 353
active difficult-coverage awards with the expected centers, dates, types, hours,
English requirements, itinerancy and observations. Runtime validation passes,
as does an idempotent `preserve_ledger` rebuild. The actual Android publication
event detector produces identical events before and after this review.
