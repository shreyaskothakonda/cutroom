"""Static HTTP server for scene pages, vendor libs and run assets.

ES modules and WebGL need http://, not file://, so every render and
capture goes through this server rooted at the project folder.
"""

from __future__ import annotations

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cutroom import ROOT


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class StaticServer:
    def __init__(self, root: Path = ROOT):
        handler = functools.partial(_Quiet, directory=str(root))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.root = root
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def url_for(self, path: Path | str) -> str:
        rel = Path(path).resolve().relative_to(self.root)
        return f"http://127.0.0.1:{self.port}/{rel.as_posix()}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
