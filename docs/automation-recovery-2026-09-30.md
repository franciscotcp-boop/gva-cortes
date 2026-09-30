# Recover missing scheduled checks by source

## Observed failure

At 13:06 UTC on 30 September, the Actions API showed no update run for that
day. The last update was successful run #1692 on 29 September at 20:48 UTC
(continuous results only); the last watchdog was successful run #991 on
30 September at 01:59 UTC, outside its source calendar. These successes did
not mean that the new offers had been checked. The official offers page was
accessible during maintenance and linked the attached, byte-identical PDF.

The watchdog recovered failed/stuck runs, but did not recover a schedule event
that never produced a run. It also monitored only the actual start hour and
could skip its check if GitHub delivered its event late. GitHub documents that
schedule events may be delayed or dropped:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

## Change

- Identify recently due source checks using their actual Madrid cron minute,
  allowing 30 minutes for normal startup delay and looking back three hours.
- Confirm each source from successful source-step timestamps in successful
  Actions runs; a fresh JSON or another source's success is not sufficient.
- Recover only missing sources together with any genuinely failed/stuck source.
- Verify that recovery actually ran its requested source steps, not just that
  the overall run was green.
- Save a small per-run check receipt as a GitHub Actions artifact, including
  selected modes, outcomes, validation/publication outcomes, run ID, attempt,
  commit SHA and completion time. If GitHub returns empty job steps, the
  watchdog uses this verified receipt instead of issuing a false alert. The
  live test of run #1693 exposed this empty-step API response despite complete
  logs and successful processing. Receipts never change runtime app datasets.
- Keep same-day boundaries: Friday difficult offers are never downloaded again
  after midnight; Saturday cleanup can be recovered separately.
- Schedule the watchdog away from the beginning of each hour. Keep the owner's
  primary source calendars, validation gates, bounded retries, incident emails,
  and last valid published data unchanged.

Regression tests cover missing events, late watchdog starts, skipped sources,
unrelated successful runs, old checks, winter Madrid time, next-day expiration,
targeted recovery and false-green recovery rejection.

This remains GitHub-only automation. If GitHub delays both scheduled workflows
or Conselleria is unavailable, immediate publication cannot be guaranteed.
The change fixes missing-turn detection; it cannot control external services.
