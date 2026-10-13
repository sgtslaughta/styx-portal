"""Docker API guard for the e2e stack (stdlib only).

The backend hardcodes the Traefik container name `styx-traefik`, which on a dev
host is the LIVE stack's Traefik. This shim sits between the e2e backend and
the host docker socket so the suite can never touch anything outside its own
compose project:

- reads (GET/HEAD) pass through, except `styx-traefik` lookups (404) and the
  container list, which is narrowed to containers labelled discoverable;
- the only writes allowed are network create/connect/disconnect on the e2e
  services network, for containers of the e2e project; `styx-traefik` in a
  connect/disconnect body is rewritten to the e2e Traefik container.
"""
import json
import os
import re
import socket
import socketserver
import sys
import urllib.parse

SOCK = "/var/run/docker.sock"
PROJECT = os.environ["E2E_PROJECT"]
NETWORK = os.environ["E2E_SERVICES_NETWORK"]
LABEL = "styx-e2e.discoverable=true"
VER = re.compile(r"^/v\d+\.\d+")


def docker(method: str, path: str) -> tuple[int, bytes]:
    s = socket.socket(socket.AF_UNIX)
    s.connect(SOCK)
    s.sendall(f"{method} {path} HTTP/1.0\r\nHost: docker\r\n\r\n".encode())
    data = b""
    while chunk := s.recv(65536):
        data += chunk
    s.close()
    head, _, body = data.partition(b"\r\n\r\n")
    return int(head.split()[1]), body


def inspect(name: str) -> dict | None:
    code, body = docker("GET", f"/containers/{urllib.parse.quote(name)}/json")
    return json.loads(body) if code == 200 else None


def traefik_id() -> str:
    flt = urllib.parse.quote(json.dumps({"label": [
        f"com.docker.compose.project={PROJECT}", "com.docker.compose.service=traefik"]}))
    _, body = docker("GET", f"/containers/json?filters={flt}")
    return json.loads(body)[0]["Id"]


def network_name(ref: str) -> str | None:
    code, body = docker("GET", f"/networks/{urllib.parse.quote(ref)}")
    return json.loads(body)["Name"] if code == 200 else None


class Handler(socketserver.StreamRequestHandler):
    def reply(self, code: int, msg: str) -> None:
        body = json.dumps({"message": msg}).encode()
        self.wfile.write(f"HTTP/1.1 {code} X\r\nContent-Type: application/json\r\n"
                         f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)

    def handle(self) -> None:
        line = self.rfile.readline().decode()
        if not line:
            return
        method, target, _ = line.split(" ", 2)
        headers = []
        length = 0
        while (h := self.rfile.readline().decode()) not in ("\r\n", "\n", ""):
            k, _, v = h.partition(":")
            if k.lower() == "content-length":
                length = int(v.strip())
            if k.lower() in ("connection", "content-length", "transfer-encoding"):
                continue
            headers.append(h.rstrip("\r\n"))
        body = self.rfile.read(length) if length else b""
        url = urllib.parse.urlsplit(target)
        path = VER.sub("", url.path)
        verdict = self.check(method, path, url, body)
        if isinstance(verdict[0], int):  # (status, message) = refused
            self.reply(*verdict)
            return
        target, body = verdict
        up = socket.socket(socket.AF_UNIX)
        up.connect(SOCK)
        req = [f"{method} {target} HTTP/1.1", *headers, "Connection: close"]
        if body or method == "POST":
            req.append(f"Content-Length: {len(body)}")
        up.sendall(("\r\n".join(req) + "\r\n\r\n").encode() + body)
        while chunk := up.recv(65536):
            self.wfile.write(chunk)
            self.wfile.flush()
        up.close()

    def check(self, method, path, url, body):
        target = url.path + (f"?{url.query}" if url.query else "")
        if "/containers/styx-traefik/" in path + "/":
            return 404, "No such container: styx-traefik (e2e shim)"
        if method in ("GET", "HEAD"):
            if path == "/containers/json":
                q = urllib.parse.parse_qs(url.query)
                flt = json.loads(q.get("filters", ["{}"])[0] or "{}")
                labels = flt.get("label", [])
                flt["label"] = [*labels, LABEL]
                q["filters"] = [json.dumps(flt)]
                target = url.path + "?" + urllib.parse.urlencode(q, doseq=True)
            return target, body
        if method != "POST":
            return 403, f"e2e shim: {method} not allowed"
        if path == "/networks/create":
            if json.loads(body or b"{}").get("Name") != NETWORK:
                return 403, "e2e shim: only the e2e services network may be created"
            return target, body
        m = re.fullmatch(r"/networks/([^/]+)/(connect|disconnect)", path)
        if not m:
            return 403, f"e2e shim: POST {path} not allowed"
        if network_name(urllib.parse.unquote(m.group(1))) != NETWORK:
            return 403, "e2e shim: foreign network"
        data = json.loads(body or b"{}")
        if data.get("Container") == "styx-traefik":
            data["Container"] = traefik_id()
        info = inspect(data.get("Container", ""))
        if not info or info["Config"]["Labels"].get("com.docker.compose.project") != PROJECT:
            return 403, "e2e shim: container outside the e2e project"
        return target, json.dumps(data).encode()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print(f"docker shim: project={PROJECT} network={NETWORK}", file=sys.stderr, flush=True)
    Server(("0.0.0.0", 2375), Handler).serve_forever()
