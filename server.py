"""Read-only HPL availability frontend. No third-party runtime dependencies."""
import json
import os
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('HPL_DATA_DIR', str(ROOT / 'data')))
PASSES = [
    {'id': 'hca', 'name': 'Hamilton Conservation Authority', 'shortName': 'HCA', 'description': 'Conservation area pass', 'catalogueUrl': 'https://hpl.bibliocommons.com/item/show/S125C722592'},
    {'id': 'rom', 'name': 'Royal Ontario Museum', 'shortName': 'ROM', 'description': 'Museum pass', 'catalogueUrl': 'https://hpl.bibliocommons.com/item/show/S125C878844'},
]

def status():
    try:
        saved = json.loads((DATA / 'availability.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        saved = {'passes': {}}
    now = datetime.now(timezone.utc)
    result = []
    for definition in PASSES:
        item = saved.get('passes', {}).get(definition['id'], {})
        stamp = item.get('checkedAt')
        age = None
        if stamp:
            parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError('Snapshot timestamps must include a timezone')
            age = max(0, (now - parsed).total_seconds())
        state = 'pending' if age is None else 'stale' if age > 660 else 'fresh'
        result.append({**definition, 'checkedAt': stamp, 'freshness': state,
                       'error': item.get('error'), 'branches': item.get('branches', [])})
    return {'generatedAt': now.isoformat(), 'intervalMinutes': 5, 'copyType': 'Rec Pass Express', 'passes': result}

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/api/status', '/api/health'):
            try:
                payload = status()
                if path == '/api/health':
                    payload = {'ok': True, 'watcherFresh': all(p['freshness'] == 'fresh' and not p['error'] for p in payload['passes'])}
                body = json.dumps(payload).encode()
                code = 200
            except (ValueError, TypeError, KeyError, OSError):
                body = b'{"error":"Availability data could not be read. Check watcher output."}'
                code = 503
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path not in ('/', '/index.html', '/app.js', '/style.css', '/favicon.svg'):
            self.send_error(404)
            return
        super().do_GET()

if __name__ == '__main__':
    host = os.environ.get('HPL_HOST', '127.0.0.1')
    port = int(os.environ.get('HPL_PORT', '31008'))
    print(f'HPL Watcher frontend: http://{host}:{port}', flush=True)
    ThreadingHTTPServer((host, port), partial(Handler, directory=str(ROOT / 'public'))).serve_forever()
