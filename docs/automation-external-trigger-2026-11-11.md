# Independent trigger for the existing GitHub watchdog

## Purpose

GitHub Support ticket 4946765 identified the reported missing runs as matching
the known best-effort limitations of Actions schedules and recommended an
external `workflow_dispatch` trigger. Both existing workflows were active;
manual runs succeeded while daytime schedule events were absent.

The owner approved cron-job.org and a new repository-scoped credential.
GitHub remains responsible for source access, parsing, validation, publication,
and incident reporting. The external service never queries Conselleria or
receives application datasets. No frontend, Android, or published data changes
are required for this connection.

## Saved configuration

- Service: cron-job.org, job `8842310`.
- Title: `AdjudicApp - respaldo del vigilante de GitHub`.
- Schedule: `8,23,38,53 * * * *`, timezone `Europe/Madrid`.
- Method: `POST`.
- URL: `https://api.github.com/repos/franciscotcp-boop/gva-cortes/actions/workflows/watchdog-adjudicaciones.yml/dispatches`.
- Body: `{"ref":"main","inputs":{"dry_run":false,"test_alert":false}}`.
- Headers: `Accept: application/vnd.github+json`,
  `Content-Type: application/json`, `X-GitHub-Api-Version: 2022-11-28`,
  and the separately stored `Authorization: Bearer ...` credential.
- Request timeout: 30 seconds. Redirects are not treated as successful.
- Response-body history is disabled.
- Email alerts: first failed request, recovery after failure, automatic disabling.

The quarter-hour pulse starts the watchdog, not a source download. The existing
watchdog selects only overdue sources from the Madrid publication calendar,
checks completion evidence, respects concurrency and retry cooldowns, and never
republishes expired difficult-coverage offers. GitHub's own schedules remain as
an additional path. Do not replace this payload with a forced `all` update.

## Credential maintenance

- GitHub token label: `AdjudicApp cron-job dispatcher`.
- Resource owner: `franciscotcp-boop`.
- Selected repository: `gva-cortes` only.
- Permissions: Actions read/write and the required Metadata read-only.
- No account permissions, Contents write, Workflows write, or Secrets access.
- Expiration selected: **2027-11-10**; GitHub reports the cutoff as
  **2027-11-09 23:00 UTC**. Renew before that instant, preferably by November 1.
- The credential is stored only in the job's authorization header. Never put
  it in a URL, repository file, issue, log, screenshot, or maintenance report.

Renewal requires the owner's approval: create a replacement with the same scope,
update the job header, verify a real scheduled dispatch and its GitHub result,
then revoke the old credential. Do not request broad `repo` access.

## Verification

The 35 watchdog regression tests passed. The cron-job.org connection test on
2026-11-11 at 14:34:35 UTC returned HTTP 204 and created watchdog run
[#1311](https://github.com/franciscotcp-boop/gva-cortes/actions/runs/43039792765),
which completed successfully. A connection test is not evidence of a scheduled
execution.

The first actual scheduled request was due at 15:38:00 Madrid and ran at
15:38:04 (4.76 seconds late), returning HTTP 204. GitHub created watchdog
[#1312](https://github.com/franciscotcp-boop/gva-cortes/actions/runs/43040361372)
at 14:38:06 UTC. It completed successfully with `DRY_RUN: false` and no overdue
sources, as expected after the earlier verified publication. This was an
external scheduled request, not another click on the test button.

The next scheduled request created watchdog
[#1313](https://github.com/franciscotcp-boop/gva-cortes/actions/runs/43042794348)
at 14:53:04 UTC. It detected the pending offers slot from 14:37 UTC and
automatically dispatched updater
[#1962](https://github.com/franciscotcp-boop/gva-cortes/actions/runs/43042873731)
at 14:53:33 UTC. Both completed successfully. The updater passed 196 tests,
fetched the official `261112_pue_prov.pdf`, verified all 293 offers and all
runtime datasets, and reported `unchanged`; no data commit was needed.
The watchdog recorded the successful recovery in issue 85. No manual GitHub
dispatch was used for either of these scheduled verification requests.

## Operational limits

This removes exclusive dependence on GitHub's schedule-event delivery; it does
not guarantee uninterrupted operation of GitHub, cron-job.org, or Conselleria.
HTTP 204 confirms dispatch acceptance, not PDF processing or publication.
The existing watchdog and updater outcomes remain the authoritative checks for
source processing. A green watchdog with no overdue sources is an intentional
no-op, not a newly published update.
