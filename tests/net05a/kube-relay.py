#!/usr/bin/env python3
"""Task-only TLS relay of real kube API responses; no successful fake objects.

Rules can disconnect or retain a real request/response. A held outgoing request
continues with the same bytes when released, even after the client times out.
Tokens and Secret bodies are never written to the trace.
"""
import datetime
import http.client
import hashlib
import http.server
import json
import pathlib
import socket
import ssl
import sys
import threading
import time
import urllib.parse
import uuid

private = pathlib.Path(sys.argv[1])
state = json.loads((private / 'run.json').read_text())
control = private / 'proxy'
upstream = urllib.parse.urlparse(state['api_server'])
upstream_tls = ssl.create_default_context(cafile=str(private / 'ca.crt'))
identities = {(private / (name + '.token')).read_text().strip(): name for name in ['network', 'ani', 'runner']}
lock = threading.Lock()
trace = private.parent / 'evidence/kube-relay.jsonl'

def log(data):
    data['at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with lock, trace.open('a') as file:
        file.write(json.dumps(data) + '\n')

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args):
        pass
    def handle_request(self):
        parsed = urllib.parse.urlparse(self.path)
        segments = parsed.path.strip('/').split('/')
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        identity = identities.get(self.headers.get('Authorization', '').removeprefix('Bearer '), 'unknown')
        request_id = uuid.uuid4().hex
        name = segments[-1]
        namespace = segments[segments.index('namespaces') + 1] if 'namespaces' in segments and len(segments) > segments.index('namespaces') + 1 else ''
        if body:
            try:
                obj = json.loads(body)
                name = obj.get('metadata', {}).get('name', name)
            except ValueError:
                obj = {}
        # Never relay a write outside the two task namespaces.
        if self.command != 'GET' and namespace not in state['namespaces']:
            self.close_connection = True
            log({'event': 'scope-denied', 'id': request_id, 'method': self.command, 'path': parsed.path})
            return
        record = {'id': request_id, 'identity': identity, 'method': self.command, 'path': parsed.path, 'name': name, 'dry_run': 'dryRun=' in parsed.query, 'watch': urllib.parse.parse_qs(parsed.query).get('watch') == ['true']}
        rules = []
        for file in sorted(control.glob('*.rule.json')):
            try:
                rule = json.loads(file.read_text())
            except (OSError, ValueError):
                continue
            if rule.get('identity', identity) != identity or rule.get('method', self.command) != self.command:
                continue
            if rule.get('name', name) != name or rule.get('path_contains', '') not in parsed.path or record['dry_run']:
                continue
            rules.append((file, rule))
        log(record | {'event': 'received'})
        for file, rule in rules:
            if rule['action'] in ['disconnect', 'hold_before']:
                self.hit(rule, record, 'before')
                if rule['action'] == 'disconnect':
                    self.close_connection = True
                    return
                self.wait_release(file)
        connection = http.client.HTTPSConnection(upstream.hostname, upstream.port, context=upstream_tls, timeout=600 if record['watch'] else 30)
        headers = {key: value for key, value in self.headers.items() if key.lower() not in ['host', 'connection', 'content-length', 'accept-encoding']}
        headers['Content-Length'] = str(len(body))
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            if record['watch'] and response.status==200:
                self.send_response(response.status)
                self.send_header('Content-Type','application/json')
                self.send_header('Connection','close')
                self.end_headers()
                self.close_connection=True
                log(record|{'event':'watch-open','status':response.status})
                generation=(control/'watch-generation').read_text() if (control/'watch-generation').exists() else ''
                # Read complete streamed JSON lines; content comes only from the
                # real API. A task marker closes just these watch connections.
                stopped=threading.Event()
                def interrupter():
                    while not stopped.wait(.2):
                        current=(control/'watch-generation').read_text() if (control/'watch-generation').exists() else ''
                        if current!=generation:
                            try: connection.sock.shutdown(socket.SHUT_RDWR)
                            except (OSError,AttributeError): pass
                            break
                monitor=threading.Thread(target=interrupter,daemon=True);monitor.start()
                try:
                    while True:
                        line=response.readline()
                        if not line:break
                        self.wfile.write(line);self.wfile.flush()
                        try:
                            item=json.loads(line);obj=item.get('object',{});metadata=obj.get('metadata',{})
                            safe={k:metadata.get(k) for k in ['name','namespace','uid','resourceVersion']}
                            log(record|safe|{'event':'watch-event','type':item.get('type'),'kind':obj.get('kind'),'bytes':len(line),'status_sha256':hashlib.sha256(json.dumps(obj.get('status',{}),sort_keys=True).encode()).hexdigest(),'conditions':[{k:c.get(k) for k in ['type','status']} for c in obj.get('status',{}).get('conditions',[])]})
                        except ValueError: log(record|{'event':'watch-unparsed','bytes':len(line)})
                finally:
                    stopped.set();monitor.join(timeout=1)
                    log(record|{'event':'watch-closed'})
                return
            content = response.read()
            status = response.status
            safe = {}
            # Metadata/Status only; never store object specs or Secret contents.
            try:
                obj = json.loads(content)
                safe = {'kind': obj.get('kind'), 'uid': obj.get('metadata', {}).get('uid'), 'reason': obj.get('reason')}
            except ValueError:
                pass
            log(record | safe | {'event': 'upstream', 'status': status})
            for file, rule in rules:
                if rule['action'] in ['drop_after', 'hold_after']:
                    self.hit(rule, record | safe | {'status': status}, 'after')
                    if rule['action'] == 'drop_after':
                        self.close_connection = True
                        return
                    self.wait_release(file)
            self.send_response(status)
            for key, value in response.getheaders():
                if key.lower() not in ['connection', 'content-length', 'transfer-encoding']:
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            log(record | {'event': 'delivered', 'status': status})
        except (OSError, http.client.HTTPException):
            log(record | {'event': 'transport-disconnected'})
            self.close_connection = True
        finally:
            connection.close()
    def hit(self, rule, record, phase):
        path = control / (rule['id'] + '.hit.json')
        try:
            with path.open('x') as file:
                json.dump(record | {'phase': phase, 'action': rule['action']}, file)
        except FileExistsError:
            pass
    def wait_release(self, path):
        deadline = time.monotonic() + 600
        while path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if path.exists():
            raise TimeoutError('NET-05 relay hold expired')
    do_GET = do_POST = do_DELETE = do_PATCH = do_PUT = handle_request

server = http.server.ThreadingHTTPServer((state['bridge_gateway'], state['proxy_port']), Handler)
tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls.load_cert_chain(str(control / 'tls.crt'), str(control / 'tls.key'))
server.socket = tls.wrap_socket(server.socket, server_side=True)
log({'event': 'listening', 'address': state['bridge_gateway'], 'port': state['proxy_port']})
server.serve_forever()
