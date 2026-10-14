"""Bounded read-only connectivity checks; never modifies publication data."""
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import tempfile
import time
import urllib.request


URLS = (
    'https://ceice.gva.es/es/web/rrhh-educacion/convocatoria-y-peticion-telematica',
    'https://ceice.gva.es/es/web/rrhh-educacion/resolucion',
    'https://ceice.gva.es/documents/162909733/415637604/261015_pue_prov.pdf',
    'https://sede.gva.es/va/cercador-persones',
    'https://www.gva.es/',
)
HEADERS = {'User-Agent': 'AdjudicApp/1.0 (+https://github.com/franciscotcp-boop/gva-cortes)',
           'Accept': 'text/html,application/pdf,application/octet-stream;q=0.9,*/*;q=0.5'}


def inspect_response(content, content_type):
    return {'bytes': len(content), 'content_type': content_type,
            'sha256': hashlib.sha256(content).hexdigest(),
            'pdf': content.startswith(b'%PDF-'),
            'pdf_link_count': content.lower().count(b'.pdf')}


def main():
    report = {'runner': os.environ.get('RUNNER_OS', platform.system()), 'requests': []}
    try:
        report['dns'] = sorted({item[4][0] for item in socket.getaddrinfo('ceice.gva.es', 443)})
    except OSError as exc:
        report['dns_error'] = str(exc)
    for url in URLS:
        started = time.monotonic()
        record = {'method': 'urllib', 'url': url}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as response:
                content = response.read(10 * 1024 * 1024)
                record.update(status=response.status, final_url=response.url,
                              **inspect_response(content, response.headers.get('Content-Type')))
        except (OSError, ValueError) as exc:
            record.update(error=type(exc).__name__, message=str(exc))
        record['seconds'] = round(time.monotonic() - started, 2)
        report['requests'].append(record)
        print(json.dumps(record), flush=True)
    # Compare a second HTTP client only when the normal client cannot connect.
    if report['requests'][0].get('error'):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'response.html'
            args = ['curl', '-4', '--silent', '--show-error', '--location', '--fail',
                    '--connect-timeout', '10', '--max-time', '30',
                    '--user-agent', HEADERS['User-Agent'], '--output', str(output),
                    '--write-out', '%{http_code} %{remote_ip} %{time_connect} %{time_appconnect} %{time_total}', URLS[0]]
            completed = subprocess.run(args, capture_output=True, text=True, timeout=35)
            record = {'method': 'curl-ipv4', 'url': URLS[0], 'returncode': completed.returncode,
                      'timings': completed.stdout, 'error': completed.stderr}
            if output.exists():
                record.update(inspect_response(output.read_bytes(), None))
            report['requests'].append(record)
            print(json.dumps(record), flush=True)
            # Both addresses were returned by official-host DNS during this incident.
            # Preserve the HTTPS hostname and certificate verification in every probe.
            for address in ('195.77.20.69', '195.77.19.36'):
                if address in report.get('dns', []):
                    continue
                if output.exists():
                    output.unlink()
                resolved = args[:-1] + ['--resolve', f'ceice.gva.es:443:{address}', URLS[0]]
                completed = subprocess.run(resolved, capture_output=True, text=True, timeout=35)
                record = {'method': 'curl-official-address', 'address': address, 'url': URLS[0],
                          'returncode': completed.returncode, 'timings': completed.stdout,
                          'error': completed.stderr}
                if output.exists():
                    record.update(inspect_response(output.read_bytes(), None))
                report['requests'].append(record)
                print(json.dumps(record), flush=True)
        # Compare ports without fetching or publishing any unencrypted content.
        for address in report.get('dns', []):
            started = time.monotonic()
            record = {'method': 'tcp-port-80', 'address': address}
            try:
                with socket.create_connection((address, 80), timeout=10):
                    record['connected'] = True
            except OSError as exc:
                record.update(connected=False, error=str(exc))
            record['seconds'] = round(time.monotonic() - started, 2)
            report['requests'].append(record)
            print(json.dumps(record), flush=True)
    report['official_sources_reachable'] = all(
        record.get('status') == 200 for record in report['requests'][:3])
    Path('source-access-report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    if not report['official_sources_reachable']:
        print('::warning::Diagnostico completado, pero el acceso a Conselleria NO funciona.')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        result = ('Acceso correcto a las tres fuentes probadas.'
                  if report['official_sources_reachable'] else
                  'Acceso fallido a una o mas fuentes. Esta prueba no ha solucionado el acceso.')
        with open(summary, 'a', encoding='utf8') as stream:
            stream.write(f'## Resultado del acceso a Conselleria\n\n{result}\n\n'
                         'No se han publicado ni modificado datos de AdjudicApp.\n')


if __name__ == '__main__':
    main()
