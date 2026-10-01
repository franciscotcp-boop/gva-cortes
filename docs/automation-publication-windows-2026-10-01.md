# Publication windows and recovery

All times below are Europe/Madrid. GitHub owns the automation; this change
does not add a Codeberg or Codex scheduler and does not change the clients.

## Checks

| Source | Days and season | Publication window | Other checks |
| --- | --- | --- | --- |
| Ordinary offered posts | Monday/Wednesday, September through July 1 | Every 30 minutes from 13:07 to 15:37 | 09:07, 11:07, 17:07, 19:07, 20:07 |
| Continuous adjudications | Tuesday/Thursday, September through June | Every 30 minutes from 09:17 to 14:47 | 15:17, 18:17, 21:17 |
| Difficult-coverage offers | Friday, September through June | Every 30 minutes from 13:20 to 15:50 | 09:20, 11:20, 17:20, 19:20, 21:20, 23:20 |

Annual participants, English accreditations and start-of-course checks retain
their existing seasons and hours. Difficult-coverage cleanup runs Saturday
at 00:20. Delayed Friday events must not import difficult offers on Saturday.

The workflow selects the source from the triggering cron, not its actual
start hour. Seasons and allowed dates are checked even for delayed events.

## Recovery

- The watchdog runs every 15 minutes at :11, :26, :41 and :56 during
  09:00-23:59 and 00:00-00:59. It also handles completed primary runs.
- A scheduled check is overdue after 15 minutes. The watchdog verifies
  the receipt for the relevant source, run, attempt and commit, not merely
  a recent JSON timestamp or a green run that checked another source.
- An active processing run is not cancelled before 40 minutes; the primary
  job has a 35-minute timeout. Concurrent updates remain serialized.
- A failed recovery leaves its alert open, but does not disable future
  recovery forever. Another attempt is allowed after 60 minutes.
- The last actual attempt timestamp is stored in the issue body. Unrelated
  comments and cancellation notices do not restart that waiting period.
- A recovery is confirmed only after its required sources succeeded and
  the publication/validation receipt was verified.

## Program adjudications

The project owner's existing decisions may be reused only for the same
normalized teacher name, post ID, center, program and school year. Accents
are ignored for matching, never for display. The confirmed originating pool
must still be uniquely present among awarded records in the current PDF;
the current PDF supplies its current position. Conflicting historical
decisions are not reused. An exact review for the current PDF takes priority.

There is no universal rule mapping scientific areas to Physics and Chemistry
or Technology. A new ambiguity stays pending. A structured report lists
the teacher, post, center, program and pool options in the watchdog alert.
Reports are scoped to the current run and attempt, so old pending cases
cannot leak into later notifications.

If either body's PDF cannot be processed, no partial results, profiles or
offer removal are published. Existing valid public data remain in place.
Normal validation and notification triggers remain unchanged.

## Limits and verification

GitHub can delay or omit scheduled events; Conselleria can time out or return
incomplete documents. These controls reduce missed checks and recover them
when GitHub runs the watchdog; they cannot guarantee either external service.
The PDF review and publication checks still precede any data publication.

Verification: 170 Python tests, 30 watchdog tests, and runtime JSON validation.
No CodePen, Android source or public data changes are included in this update.
