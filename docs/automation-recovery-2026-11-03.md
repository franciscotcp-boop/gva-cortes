# Scheduled checks: delayed events and midnight recovery

## Evidence

On 2026-11-03 both workflows were active on `main`, Actions was enabled, and
the repository and cron actor were active. This was not inactivity disabling
the workflow, a missing schedule, or a Conselleria request failure.

- [Updater #1910](https://github.com/franciscotcp-boop/gva-cortes/actions/runs/41530537021)
  was created on Monday 2026-11-02 at 21:40:47 UTC (22:40 Madrid). Its event
  was `7,37 13-15 * 1-7,9-12 1,3`, whose latest Monday slot was 15:37 Madrid:
  at least seven hours late.
- [Updater #1912](https://github.com/franciscotcp-boop/gva-cortes/actions/runs/41560288102)
  was created on Tuesday 2026-11-03 at 01:31:32 UTC (02:31 Madrid), with the
  Monday/Wednesday offers expression. The old selector returned
  `sin_comprobacion` because it checked the current weekday only.
- [Watchdog #1244](https://github.com/franciscotcp-boop/gva-cortes/actions/runs/41557274793)
  at 01:04:24 UTC only considered Tuesday's cleanup. Its previous-date filter
  excluded Monday's checks.

The sampled runs started when created; the long delay preceded run creation.
GitHub's API does not expose the internal reason for a missing cron delivery.
GitHub documents that scheduled events may be delayed or dropped under load:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
This evidence does not establish a specific GitHub service incident or a
timezone bug. The `timezone` property is supported.

## Changes

- The updater resolves its source against real Madrid slots in the preceding
  24 hours, rather than rejecting a late event solely because the day changed.
- The watchdog checks that same rolling window, with a 15-minute grace period,
  and retains source-specific completion evidence. It recovers only missing
  sources, not all sources every quarter hour.
- Closed seasons remain closed. Difficult-coverage offers are never recovered
  after their Madrid publication day; recovery of a failed run across midnight
  requests cleanup instead of republishing those offers.
- The watchdog has a simple quarter-hour UTC pulse, including overnight hours,
  and still evaluates the publication calendar in Europe/Madrid. This changes
  the trigger registration without attributing the fault to timezone support.
- Changes to automation code trigger a watchdog check on `main`; normal data
  commits do not. Queued watchdog runs check out the latest default branch.
- Logs record the actual start instant, event expression and each missed slot.

## Verification and limits

Regression tests cover the actual November event, midnight, summer/winter,
season boundaries, 24-hour limits, source completion deduplication and expired
difficult coverage. No frontend, Android, extractor or published JSON change
is included in this patch.

Both scheduled workflows still depend on GitHub's scheduler. A passing manual
or push run is not proof of a timely `schedule` delivery. Inspect the actual
event type and timestamps before claiming that scheduling has recovered.
No external scheduler, local service, paid service or self-dispatch loop was
introduced.
