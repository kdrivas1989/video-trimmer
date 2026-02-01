#!/usr/bin/env python3
"""Video Trimmer Web App - Upload videos, select trim times, and download results."""

import os
import uuid
import subprocess
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from moviepy import VideoFileClip

app = Flask(__name__)

# Use appropriate directory for file storage based on environment
def get_app_data_dir():
    """Get appropriate directory for app data storage."""
    # Check if running on Render (native Python, not Docker)
    if os.environ.get('RENDER'):
        # Use /tmp for Render's native runtime (writable)
        return Path('/tmp/video-trimmer')
    elif os.path.exists('/.dockerenv'):
        # Use /app for Docker
        return Path('/app')
    else:
        # Use user's home directory for desktop app
        home = Path.home()
        return home / 'VideoTrimmer'

APP_DATA_DIR = get_app_data_dir()
app.config['UPLOAD_FOLDER'] = str(APP_DATA_DIR / 'uploads')
app.config['OUTPUT_FOLDER'] = str(APP_DATA_DIR / 'output')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB max
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'mts'}

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
PREVIEW_FOLDER = str(APP_DATA_DIR / 'previews')
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

# Store video info in memory (for demo purposes)
videos = {}

# Browser-playable codecs
BROWSER_PLAYABLE_CODECS = {'h264', 'avc1', 'vp8', 'vp9', 'av1'}


def get_video_codec(filepath):
    """Get video codec using ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath
        ], capture_output=True, text=True, timeout=30)
        return result.stdout.strip().lower()
    except Exception:
        return None


def is_browser_playable(filepath):
    """Check if video codec is playable in browsers."""
    codec = get_video_codec(filepath)
    if codec:
        return codec in BROWSER_PLAYABLE_CODECS
    # Assume playable if we can't detect
    return True


def transcode_for_browser(video_id, source_path):
    """Transcode video to H.264 for browser playback (runs in background)."""
    preview_path = os.path.join(PREVIEW_FOLDER, f"{video_id}_preview.mp4")
    temp_path = preview_path + ".tmp"

    if os.path.exists(preview_path):
        return  # Already transcoded

    try:
        # Use ffmpeg directly for more reliable transcoding
        cmd = [
            'ffmpeg', '-y', '-i', source_path,
            '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0',
            '-pix_fmt', 'yuv420p', '-preset', 'fast',
            '-vf', 'scale=-2:720',  # Scale to 720p max
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart',
            temp_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(temp_path):
            os.rename(temp_path, preview_path)
            # Update video entry if it exists
            if video_id in videos:
                videos[video_id]['preview_path'] = preview_path
                videos[video_id]['preview_ready'] = True
        else:
            print(f"Transcode failed for {video_id}: {result.stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except Exception as e:
        print(f"Transcode failed for {video_id}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_video_duration(filepath):
    """Get video duration in seconds."""
    try:
        with VideoFileClip(filepath) as clip:
            return clip.duration
    except Exception:
        return 0


def seconds_to_timestamp(seconds):
    """Convert seconds to SS.mmm format."""
    total_secs = int(seconds)
    ms = int((seconds % 1) * 1000)
    return f"{total_secs}.{ms:03d}s"


def timestamp_to_seconds(timestamp):
    """Convert SS.mmm format to seconds."""
    # Remove 's' suffix if present
    clean = timestamp.strip().rstrip('s')
    return float(clean)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if file and allowed_file(file.filename):
            video_id = str(uuid.uuid4())
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{video_id}_{filename}")
            file.save(filepath)

            # Skip duration reading on upload - it's slow for large files
            # Duration will be read when previewing
            duration = 0

            # Check if browser can play this codec
            playable = is_browser_playable(filepath)

            # Get duration on upload
            duration = get_video_duration(filepath)

            videos[video_id] = {
                'id': video_id,
                'filename': filename,
                'filepath': filepath,
                'duration': duration,
                'duration_str': seconds_to_timestamp(duration),
                'browser_playable': playable,
                'preview_ready': False
            }

            # Auto-transcode in background if not browser-playable
            if not playable:
                thread = threading.Thread(
                    target=transcode_for_browser,
                    args=(video_id, filepath)
                )
                thread.daemon = True
                thread.start()

            return jsonify({
                'id': video_id,
                'filename': filename,
                'duration': duration,
                'duration_str': seconds_to_timestamp(duration),
                'start_time': '0.000s',
                'end_time': seconds_to_timestamp(duration),
                'browser_playable': playable
            })

        return jsonify({'error': 'Invalid file type'}), 400

    except OSError as e:
        if e.errno == 28:
            return jsonify({'error': 'No space left on device. Please free up disk space.'}), 500
        elif e.errno == 13:
            return jsonify({'error': f'Permission denied. Cannot write to: {app.config["UPLOAD_FOLDER"]}'}), 500
        return jsonify({'error': f'OS Error [{e.errno}]: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {str(e)}'}), 500


@app.route('/trim', methods=['POST'])
def trim_video():
    try:
        data = request.json
        video_id = data.get('id')
        start_time = data.get('start', '0s')
        end_time = data.get('end')

        if video_id not in videos:
            return jsonify({'error': 'Video not found'}), 404

        video = videos[video_id]

        # Check if source file exists
        if not os.path.exists(video['filepath']):
            return jsonify({'error': f"Source file not found: {video['filepath']}"}), 400

        start = timestamp_to_seconds(start_time)
        end = timestamp_to_seconds(end_time) if end_time else video['duration']

        if start >= end:
            return jsonify({'error': 'Start time must be before end time'}), 400

        # Generate output path with custom name if provided
        custom_name = data.get('output_name', '').strip()
        if custom_name:
            output_name = f"{custom_name}.mp4"
        else:
            original_name = Path(video['filename']).stem
            output_name = f"{original_name}_trimmed.mp4"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{video_id}_{output_name}")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with VideoFileClip(video['filepath']) as clip:
            # Add 2 second buffer before and after (within video bounds)
            buffer_seconds = 2
            actual_start = max(0, start - buffer_seconds)
            actual_end = min(clip.duration, end + buffer_seconds)

            trimmed = clip.subclipped(actual_start, actual_end)
            trimmed.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                preset="ultrafast",
                logger=None
            )

        videos[video_id]['output_path'] = output_path
        videos[video_id]['output_name'] = output_name

        return jsonify({
            'success': True,
            'id': video_id,
            'output_name': output_name
        })

    except BrokenPipeError as e:
        error_msg = f"Broken pipe error (errno 32): Video encoding was interrupted. This can happen if: (1) disk is full, (2) output folder is inaccessible, or (3) ffmpeg crashed. Source: {video.get('filepath', 'unknown')}"
        return jsonify({'error': error_msg}), 500
    except OSError as e:
        if e.errno == 32:
            error_msg = f"Broken pipe error (errno 32): Video encoding was interrupted. Source: {video.get('filepath', 'unknown')}. Check disk space and permissions."
        elif e.errno == 28:
            error_msg = "No space left on device. Please free up disk space and try again."
        elif e.errno == 13:
            error_msg = f"Permission denied. Cannot write to output folder: {app.config['OUTPUT_FOLDER']}"
        else:
            error_msg = f"OS Error [{e.errno}]: {str(e)}. File: {video.get('filepath', 'unknown')}"
        return jsonify({'error': error_msg}), 500
    except Exception as e:
        import traceback
        error_details = f"{type(e).__name__}: {str(e)}"
        # Include file path for debugging
        if 'video' in locals():
            error_details += f" | Source: {video.get('filepath', 'unknown')}"
        return jsonify({'error': error_details}), 500


@app.route('/download/<video_id>')
def download_video(video_id):
    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404

    video = videos[video_id]
    if 'output_path' not in video:
        return jsonify({'error': 'Video not yet trimmed'}), 400

    return send_file(
        video['output_path'],
        as_attachment=True,
        download_name=video['output_name']
    )


@app.route('/duration/<video_id>')
def get_duration(video_id):
    """Get video duration (reads from file if not cached)."""
    # Check dictionary first for cached duration
    if video_id in videos:
        video = videos[video_id]
        if video.get('duration', 0) == 0:
            duration = get_video_duration(video['filepath'])
            video['duration'] = duration
            video['duration_str'] = seconds_to_timestamp(duration)
        return jsonify({
            'duration': video['duration'],
            'duration_str': video['duration_str']
        })

    # Otherwise find file on disk
    filepath = find_video_file(video_id)
    if not filepath:
        return jsonify({'error': 'Video not found'}), 404

    duration = get_video_duration(filepath)
    return jsonify({
        'duration': duration,
        'duration_str': seconds_to_timestamp(duration)
    })


@app.route('/video/<video_id>')
def serve_video(video_id):
    # Find video file (handles server restarts)
    filepath = find_video_file(video_id)
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'Video not found'}), 404

    # Get file extension for mimetype
    ext = os.path.splitext(filepath)[1].lower()
    mimetypes = {
        '.mp4': 'video/mp4',
        '.mkv': 'video/x-matroska',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.webm': 'video/webm',
        '.mts': 'video/mp2t',
    }
    mimetype = mimetypes.get(ext, 'video/mp4')

    return send_file(filepath, mimetype=mimetype, conditional=True)


def find_video_file(video_id):
    """Find video file by ID, even if not in videos dictionary."""
    # First check if in dictionary
    if video_id in videos:
        return videos[video_id]['filepath']

    # Otherwise scan uploads folder for matching file
    upload_folder = app.config['UPLOAD_FOLDER']
    if os.path.exists(upload_folder):
        for filename in os.listdir(upload_folder):
            if filename.startswith(video_id + '_'):
                return os.path.join(upload_folder, filename)
    return None


@app.route('/preview/<video_id>')
def get_preview(video_id):
    """Generate and serve an H.264 preview for H.265/HEVC videos."""
    preview_path = os.path.join(PREVIEW_FOLDER, f"{video_id}_preview.mp4")

    # Check if preview already exists
    if os.path.exists(preview_path):
        return send_file(
            preview_path,
            mimetype='video/mp4',
            as_attachment=False,
            conditional=True,
            max_age=0
        )

    # Find the source video file
    source_path = find_video_file(video_id)
    if not source_path or not os.path.exists(source_path):
        return jsonify({'error': 'Video not found'}), 404

    # Generate preview by transcoding to H.264
    try:
        with VideoFileClip(source_path) as clip:
            # Use a reasonable resolution for preview (max 720p)
            if clip.h > 720:
                resized = clip.resized(height=720)
            else:
                resized = clip

            resized.write_videofile(
                preview_path,
                codec="libx264",
                audio_codec="aac",
                preset="fast",
                ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-profile:v", "baseline", "-level", "3.0"],
                logger=None
            )

        return send_file(preview_path, mimetype='video/mp4', conditional=True)

    except Exception as e:
        return jsonify({'error': f'Failed to generate preview: {str(e)}'}), 500


@app.route('/open-video/<video_id>')
def open_video_player(video_id):
    """Open video in system's default video player."""
    import subprocess
    preview_path = os.path.join(PREVIEW_FOLDER, f"{video_id}_preview.mp4")

    if os.path.exists(preview_path):
        subprocess.Popen(['open', preview_path])
        return jsonify({'success': True, 'path': preview_path})

    # Try original video
    source_path = find_video_file(video_id)
    if source_path and os.path.exists(source_path):
        subprocess.Popen(['open', source_path])
        return jsonify({'success': True, 'path': source_path})

    return jsonify({'error': 'Video not found'}), 404


@app.route('/preview/status/<video_id>')
def preview_status(video_id):
    """Check if a preview exists or needs to be generated."""
    # Check if video file exists (either in dict or on disk)
    source_path = find_video_file(video_id)
    if not source_path:
        return jsonify({'error': 'Video not found'}), 404

    preview_path = os.path.join(PREVIEW_FOLDER, f"{video_id}_preview.mp4")
    preview_exists = os.path.exists(preview_path)

    # Check if browser can play original
    browser_playable = True
    if video_id in videos:
        browser_playable = videos[video_id].get('browser_playable', True)
    else:
        browser_playable = is_browser_playable(source_path)

    return jsonify({
        'exists': preview_exists,
        'video_id': video_id,
        'browser_playable': browser_playable,
        'use_preview': not browser_playable and preview_exists
    })


@app.route('/delete/<video_id>', methods=['DELETE'])
def delete_video(video_id):
    if video_id in videos:
        video = videos[video_id]
        # Clean up files
        if os.path.exists(video['filepath']):
            os.remove(video['filepath'])
        if 'output_path' in video and os.path.exists(video['output_path']):
            os.remove(video['output_path'])
        # Clean up preview file
        preview_path = os.path.join(PREVIEW_FOLDER, f"{video_id}_preview.mp4")
        if os.path.exists(preview_path):
            os.remove(preview_path)
        del videos[video_id]

    return jsonify({'success': True})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'

    print("\n=== Video Trimmer Web App ===")
    print(f"Open http://localhost:{port} in your browser\n")
    app.run(debug=debug, host='0.0.0.0', port=port)
