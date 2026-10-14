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

The owner has been asked whether to authorize a local fallback requiring an
awake, connected computer, or investigate a separately hosted always-on
connection with verified access and potential cost. No local service, proxy,
paid infrastructure or additional recurring automation has been installed.
