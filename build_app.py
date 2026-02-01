#!/usr/bin/env python3
"""Build script to create standalone Video Trimmer app."""

import subprocess
import sys
import os

def build():
    """Build the standalone app using PyInstaller."""

    # Determine path separator for --add-data (: on macOS/Linux, ; on Windows)
    sep = ';' if sys.platform == 'win32' else ':'

    # PyInstaller command
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=VideoTrimmer',
        '--windowed',  # No console window
        '--onedir',    # Create a directory with all files
        f'--add-data=templates{sep}templates',  # Include templates folder
        '--hidden-import=moviepy',
        '--hidden-import=imageio',
        '--hidden-import=imageio_ffmpeg',
        '--hidden-import=webview',
        '--hidden-import=flask',
        '--collect-all=moviepy',
        '--collect-all=imageio',
        '--collect-all=imageio_ffmpeg',
        '--copy-metadata=imageio',
        '--copy-metadata=imageio_ffmpeg',
        'app.py'
    ]

    # Add Windows-specific icon if it exists
    if sys.platform == 'win32' and os.path.exists('icon.ico'):
        cmd.insert(-1, '--icon=icon.ico')

    print("Building Video Trimmer app...")
    print("This may take several minutes...")

    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        print("\n✓ Build complete!")
        print("App location: dist/VideoTrimmer/")
        if sys.platform == 'darwin':
            print("On macOS, run: open dist/VideoTrimmer/VideoTrimmer.app")
        elif sys.platform == 'win32':
            print("On Windows, run: dist\\VideoTrimmer\\VideoTrimmer.exe")
        else:
            print("Run: dist/VideoTrimmer/VideoTrimmer")
    else:
        print("\n✗ Build failed")
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(build())
