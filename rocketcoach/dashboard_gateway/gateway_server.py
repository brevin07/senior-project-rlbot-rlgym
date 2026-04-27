from __future__ import annotations

import argparse
import http.client
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class GatewayHandler(BaseHTTPRequestHandler):
    live_base: str = "http://127.0.0.1:8765"
    replay_base: str = "http://127.0.0.1:8775"
    dist_dir: Path = Path("frontend/dashboard/dist")
    legacy_live: Optional[Path] = None
    legacy_replay: Optional[Path] = None

    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")

    def _send_text(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, *, cache_control: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type, _ = mimetypes.guess_type(str(path))
        if not content_type:
            content_type = "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self, target_base: str, target_path: str) -> None:
        parsed = urlparse(target_base)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length"}}
        headers["Accept-Encoding"] = "identity"
        forwarded_host = str(self.headers.get("X-Forwarded-Host", "") or self.headers.get("Host", "") or "").strip()
        if forwarded_host:
            headers["X-Forwarded-Host"] = forwarded_host
            headers["X-Forwarded-Proto"] = str(
                self.headers.get("X-Forwarded-Proto", "")
                or ("https" if forwarded_host.endswith(".app") else "http")
            ).strip().lower()

        body = None
        if self.command in {"POST", "PUT", "PATCH"}:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length > 0 else b""

        is_replay = parsed.hostname == "replay"
        attempts = 4 if is_replay else 1
        last_exc: Exception | None = None

        for idx in range(attempts):
            try:
                # Replay analysis can take a while; use a longer upstream timeout.
                conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=120)
                conn.request(self.command, target_path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()

                self.send_response(resp.status)
                for key, value in resp.getheaders():
                    if key.lower() in {"transfer-encoding", "content-encoding", "connection"}:
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as exc:
                last_exc = exc
                if idx >= attempts - 1:
                    break
                time.sleep(0.45 * (idx + 1))

        self._send_text(HTTPStatus.BAD_GATEWAY, f"Upstream error: {last_exc}")

    def _handle_api(self, prefix: str, base: str) -> bool:
        if not self.path.startswith(prefix):
            return False
        rest = self.path[len(prefix):]
        if not rest:
            rest = "/health"
        target = "/api" + rest
        self._proxy(base, target)
        return True

    def _handle_legacy(self, prefix: str, root: Optional[Path]) -> bool:
        if not self.path.startswith(prefix):
            return False
        if root is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Legacy assets not configured")
            return True
        rel = self.path[len(prefix):].lstrip("/")
        if not rel:
            rel = "index.html"
        file_path = (root / rel).resolve()
        if root not in file_path.parents and file_path != root:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid path")
            return True
        self._send_file(file_path)
        return True

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_text(HTTPStatus.OK, "ok")
            return
        if self.path.startswith("/collision_meshes/"):
            self._proxy(self.replay_base, self.path)
            return
        if self._handle_api("/api/live", self.live_base):
            return
        if self._handle_api("/api/replay", self.replay_base):
            return
        if self._handle_legacy("/legacy/live", self.legacy_live):
            return
        if self._handle_legacy("/legacy/replay", self.legacy_replay):
            return

        if not self.dist_dir.exists():
            self._send_text(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "React build not found. Run `npm install` and `npm run build` in frontend/dashboard.`\n",
            )
            return

        if self.path.startswith("/assets/"):
            self._send_file(self.dist_dir / self.path.lstrip("/"), cache_control="public, max-age=31536000, immutable")
            return

        index = self.dist_dir / "index.html"
        self._send_file(index, cache_control="no-store")

    def do_POST(self) -> None:
        if self._handle_api("/api/live", self.live_base):
            return
        if self._handle_api("/api/replay", self.replay_base):
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="RLGym dashboard gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--live", default="http://127.0.0.1:8765")
    parser.add_argument("--replay", default="http://127.0.0.1:8775")
    parser.add_argument("--dist", default="frontend/dashboard/dist")
    parser.add_argument("--legacy-live", default="rocketcoach/live_analysis/web")
    parser.add_argument("--legacy-replay", default="rocketcoach/replay_dashboard/web")
    args = parser.parse_args()

    handler = GatewayHandler
    handler.live_base = args.live
    handler.replay_base = args.replay
    handler.dist_dir = Path(args.dist).resolve()
    handler.legacy_live = Path(args.legacy_live).resolve() if args.legacy_live else None
    handler.legacy_replay = Path(args.legacy_replay).resolve() if args.legacy_replay else None

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"[gateway] running at http://{args.host}:{args.port}")
    print(f"[gateway] live -> {handler.live_base} | replay -> {handler.replay_base}")
    print(f"[gateway] dist -> {handler.dist_dir}")
    server.serve_forever()


if __name__ == "__main__":
    main()
