"""Isolated launcher fixture; never opens PostgreSQL or a browser."""
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

mode, port = sys.argv[1], int(sys.argv[2])
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])
print('Fixture startup stderr: normal native diagnostic, not a failure.', file=sys.stderr, flush=True)
time.sleep(float(os.environ.get('FITGATE_LAUNCHER_TEST_DELAY', '0')))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/test/fixture':
            body = json.dumps({'pid': os.getpid(), 'child': child.pid})
        elif mode == 'backend' and self.path == '/api/v1/health/':
            body = json.dumps({'status': 'ready', 'database': 'postgresql'})
        elif mode == 'backend' and self.path == '/openapi.json':
            body = json.dumps({'info': {'title': 'FitGate API'}})
        elif mode == 'frontend':
            body = '<html><title>Spor Salonu Gecis Kontrol</title><script src="/src/main.jsx"></script></html>'
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html' if mode == 'frontend' else 'application/json')
        self.end_headers()
        self.wfile.write(body.encode())


ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
