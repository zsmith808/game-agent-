#!/usr/bin/env python3
"""
Simple HTTP Server for Avalon Viewer.
Serves the HTML viewer and serves game state JSON.
"""

import http.server
import socketserver
import json
import os
from pathlib import Path

PORT = 8080
WEB_DIR = Path(__file__).parent
GAME_STATE_FILE = WEB_DIR / "current_game.json"
NEXT_ACTION_FLAG = WEB_DIR / ".next_action_triggered"
WAITING_FLAG = WEB_DIR / ".waiting_for_next"

class AvalonHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler that serves game state JSON."""

    def do_GET(self):
        # Parse path and query
        full_path = self.path.split('?')[0]
        query = self.path.split('?')[1] if '?' in self.path else ''

        # Handle next action trigger
        if full_path == "/next_action":
            NEXT_ACTION_FLAG.write_text("triggered")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            return

        # Handle new game - clear all state files (supports GET and POST)
        if full_path == "/new_game":
            # Remove game state and trigger files
            for f in [GAME_STATE_FILE, NEXT_ACTION_FLAG, WAITING_FLAG]:
                if f.exists():
                    f.unlink()
            # Signal the game engine to start a new game
            (WEB_DIR / ".new_game_requested").write_text("1")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "message": "Game reset"}).encode("utf-8"))
            return

        # Handle waiting status check
        if full_path == "/waiting_status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"waiting": WAITING_FLAG.exists()}).encode("utf-8"))
            return

        # Serve game state JSON
        if full_path == "/game_state.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()

            # Check for demo parameter
            if 'demo=1' in query and (WEB_DIR / "sample_game.json").exists():
                with open(WEB_DIR / "sample_game.json", "r") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            elif GAME_STATE_FILE.exists():
                with open(GAME_STATE_FILE, "r") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(json.dumps({"status": "waiting"}).encode("utf-8"))
            return

        # Serve the HTML viewer
        if full_path == "/" or full_path == "/index.html":
            viewer_path = WEB_DIR / "avalon_viewer.html"
            if viewer_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                with open(viewer_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Viewer HTML not found")
            return

        # Default: serve files from current directory
        super().do_GET()

    def log_message(self, format, *args):
        """Suppress default logging, just print minimal info."""
        if self.path == "/game_state.json":
            print(f"[HTTP] GET game_state.json")
        else:
            print(f"[HTTP] {self.address_string()} - {format % args}")


class AvalonServer(socketserver.TCPServer):
    allow_reuse_address = True


def run_server():
    """Start the HTTP server."""
    # Change to web directory
    os.chdir(WEB_DIR)

    with AvalonServer(("", PORT), AvalonHTTPRequestHandler) as httpd:
        print("=" * 60)
        print(f"AVALON VIEWER SERVER")
        print("=" * 60)
        print(f"Open in browser: http://localhost:{PORT}")
        print(f"Game state file: {GAME_STATE_FILE}")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


if __name__ == "__main__":
    run_server()
