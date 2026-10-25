#!/usr/bin/env python3
"""Local preview that mimics GitHub Pages: /climbing serves climbing.html.

Run from the site root:  python3 scripts/serve.py   ->  http://localhost:4599
"""
import http.server
import os
import socketserver


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        local = path.lstrip("/")
        if local and "." not in os.path.basename(local) and os.path.isfile(local + ".html"):
            self.path = "/" + local + ".html"
        return super().send_head()


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", 4599), PagesHandler) as httpd:
    print("Serving http://localhost:4599")
    httpd.serve_forever()
