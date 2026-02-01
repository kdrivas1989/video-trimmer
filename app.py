#!/usr/bin/env python3
"""Video Trimmer Desktop App - Standalone offline application."""

import threading
import webbrowser
import sys
from main import app

USE_BROWSER = '--browser' in sys.argv or True  # Default to browser for better video support

def start_server():
    """Start Flask server."""
    app.run(host='127.0.0.1', port=5050, debug=False, use_reloader=False, threaded=True)

if __name__ == '__main__':
    if USE_BROWSER:
        # Open in default browser (better video support)
        import time
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()
        time.sleep(1)  # Wait for server to start
        webbrowser.open('http://127.0.0.1:5050')
        print("Video Trimmer running at http://127.0.0.1:5050")
        print("Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
    else:
        # Use pywebview (native window)
        import webview
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        window = webview.create_window(
            'Video Trimmer',
            'http://127.0.0.1:5050',
            width=1200,
            height=800,
            resizable=True,
            min_size=(800, 600)
        )
        webview.start(private_mode=False)
