#!/usr/bin/env python3
"""Video Trimmer Desktop App - Standalone offline application."""

import threading
import webview
from main import app

def start_server():
    """Start Flask server in background."""
    app.run(host='127.0.0.1', port=5050, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Start Flask server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Create native window
    webview.create_window(
        'Video Trimmer',
        'http://127.0.0.1:5050',
        width=1200,
        height=800,
        resizable=True,
        min_size=(800, 600)
    )
    webview.start()
