# October 1 automation audit

At 13:43 UTC, the repository Actions API listed no update runs for October 1
and no daytime watchdog runs. Last update #1697 completed successfully the
previous evening. Last watchdog #999 ran at 01:30 UTC, outside the source
calendar; both workflows were active. There was no failed PDF processing run
to diagnose at that point: the expected daytime events had not created runs.

Local official-page requests succeeded and both October 1 PDFs were confirmed
byte-identical to the owner-supplied files. No evidence of a Conselleria traffic
block was found in this maintenance check.

GitHub reported an infrastructure incident around 02:00 UTC and a separate
latency incident around 13:37 UTC. Neither report proves that this repository's
missing scheduled events were caused by those incidents:
https://www.githubstatus.com/incidents/dqn46wtvbdzv
https://www.githubstatus.com/incidents/c8466lzvnmsv

## Recovery hardening

The watchdog now scans all pending source turns from the same Madrid day,
instead of only the previous three hours. Its initial monitoring guard uses
the same configured lookback/grace as the subsequent audit. Thus, when a
delayed watchdog eventually starts, an earlier missed turn cannot disappear
from its recovery window. Tests cover a noon restart with an unconfirmed
morning turn, configured guard limits, and the midnight boundary.

Existing per-source success checks, run-scoped receipts, bounded retries,
validation gates, same-day difficult-offer expiry, and last-valid data are
preserved. The watchdog does not create external automation or change client
code. It cannot run while GitHub itself fails to start both workflows; that
external failure remains a limitation, not a guarantee solved by this change.

## Live recovery verification

All 24 watchdog regression tests passed. After publication, watchdog #1000
(run 36872722772) detected the unconfirmed continuous-results turn and
automatically dispatched updater #1698 (run 36872768341). Both completed
successfully. The updater read the official page, recognized the two already
processed PDF hashes, validated the datasets and saved its run-scoped receipt.
Recovery issue #13 was created and closed after confirmation.

The resulting acf2705 commit updates monitoring metadata only. Structured
comparison confirmed unchanged cuts, vacancy totals, profiles and remaining
offers, so the recovery did not create another publication notification.
The existing embedded CodePen showed the October 1 assignment details,
both Maestros cut positions and the eight remaining Primaria offers.
