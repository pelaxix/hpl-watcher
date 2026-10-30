"""Independent on-demand HPL availability frontend."""
import json
import os
from availability import Availability
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PASSES = []  # Discovered from HPL's pass catalogue at check time.

CHECKER = Availability(PASSES)

def status():
    return CHECKER.status()

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_POST(self):
        if urlsplit(self.path).path != '/api/check':
            self.send_error(404)
            return
        # Same-origin requests only; a normal browser fetch supplies Origin.
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            self.send_error(403)
            return
        body = json.dumps(CHECKER.start()).encode()
        self.send_response(202)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/api/status', '/api/health'):
            try:
                payload = status()
                if path == '/api/health':
                    payload = {'ok': True, 'checking': payload['checking']}
                body = json.dumps(payload).encode()
                code = 200
            except (ValueError, TypeError, KeyError, OSError):
                body = b'{"error":"Availability could not be read. Try again."}'
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
