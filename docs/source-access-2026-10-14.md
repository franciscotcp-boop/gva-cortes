# Conselleria connectivity investigation, 14 October 2026

## Production failure

Updater #1768 (scheduled) and recovery #1769 selected `puestos`, but all three
connection attempts to the official offers page timed out. Neither execution
reached PDF parsing or publication. The ordinary offers were subsequently
published manually as commit aa17d7f, with 467 validated posts.

- https://github.com/franciscotcp-boop/gva-cortes/actions/runs/38566757942
- https://github.com/franciscotcp-boop/gva-cortes/actions/runs/38567954591

## Read-only experiments

Two manually dispatched diagnostic runs compared fresh Ubuntu and macOS
GitHub-hosted runners. They used the production User-Agent and verified HTTPS,
testing the offers page, the continuous-results page and the current PDF.
Each normal request was limited to 20 seconds. A second client, curl over IPv4,
was tested after a failed normal request, with a 10-second connection limit.

The first run obtained different DNS results: Linux resolved 195.77.19.36;
macOS resolved 195.77.20.69. Both failed all requests. The second run also tested
the other observed official address with curl `--resolve`, retaining the
original hostname, TLS SNI and certificate verification. Both alternatives
failed before TCP connection establishment (HTTP 000, connect/TLS time zero).

- https://github.com/franciscotcp-boop/gva-cortes/actions/runs/38572590146
- https://github.com/franciscotcp-boop/gva-cortes/actions/runs/38573091062

At the same time, the maintenance computer received HTTP 200 for both pages
and the PDF through the identical Python client. The PDF hash was
65ea0418e3dc77c4f7a0873e756f054261ae9a91b6fb32f1b06554588da6d52b,
matching the owner-supplied October 15 document. A separate local curl request
to 195.77.19.36 also succeeded in 0.42 seconds with certificate verification.

### Additional GitHub-only investigation

The owner rejected a local-computer fallback and a separately hosted server.
No such fallback has been installed or contracted.

A third read-only run tested Windows x64 (Azure westus3) and Ubuntu ARM64
(Azure eastus). Both failed all three HTTPS requests with connection timeouts.
Their curl probes also failed before TCP/TLS establishment, including the
other official IP address. Neither runner provided a working alternative.

- https://github.com/franciscotcp-boop/gva-cortes/actions/runs/38574272269

This is not evidence of a permanent ban: updater #1765 on October 13 at
19:51 UTC successfully read the continuous-results page from an Ubuntu
runner in Azure centralus, finding five PDF links. Its production source
check completed without a retry warning. This establishes intermittent
reachability, but does not identify the network operator or cause of today's
failed connections.

- https://github.com/franciscotcp-boop/gva-cortes/actions/runs/38458189652

A fourth run used the separate `ubuntu-slim` container infrastructure
(Azure westus3). It failed the same three HTTPS requests, both official
addresses with curl, and a TCP-only port-80 check. Read-only control requests
to `https://sede.gva.es/va/cercador-persones` and `https://www.gva.es/` also
timed out. GitHub checkout, Python setup and artifact upload worked in that
job. The incident therefore extends beyond the specific offers page on this
tested route. The diagnostic summary now explicitly warns that successful
report collection does not mean the source is accessible.

- https://github.com/franciscotcp-boop/gva-cortes/actions/runs/38574743254

There is no successful alternative among the five tested runner types:
Ubuntu x64, macOS ARM64, Windows x64, Ubuntu ARM64, and Ubuntu single-CPU.
No unencrypted source content was fetched or used for publication. The
next root-cause investigation needs routing/filtering/congestion evidence
from the network operators; these client-side timeouts cannot identify
which operator or network condition is responsible.

## Conclusion and boundaries

The failure is specific to the tested network paths from hosted runners, not
the PDF extractor, Python alone, IPv6 preference, or one DNS address. These
tests do not establish whether the underlying cause is filtering, routing,
geographic policy or congestion; there was no HTTP access-denial response.
Switching the production job to macOS or pinning an IP has no demonstrated
benefit, so neither change was made. Longer retries were already failing.

The diagnostic workflow has no schedule, write permissions or publication
steps. Its green job result means diagnostic collection completed, not that
Conselleria was reachable; the report records each connection failure.
No production calendar, parser, client, dataset, certificate policy or
notification setting was changed by this investigation.

The production updater and watchdog remain active with their existing
schedules and bounded recovery attempts. All 175 unit tests still pass.
The 467 manually published offers were rechecked on both raw.githubusercontent
and jsDelivr: both exactly match the validated data and return CORS `*`.
There is no verified access fix yet. No local service, proxy, paid
infrastructure or additional recurring automation has been installed.
