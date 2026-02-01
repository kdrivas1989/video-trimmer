#!/usr/bin/env python3
"""Video Trimmer Web App - Upload videos, select trim times, and download results."""

import os
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from moviepy import VideoFileClip

app = Flask(__name__)

# Use appropriate directory for file storage based on environment
def get_app_data_dir():
    """Get appropriate directory for app data storage."""
    # Check if running in Docker/server environment
    if os.environ.get('RENDER') or os.path.exists('/.dockerenv'):
        # Use local directory for server/Docker
        return Path('/app')
    else:
        # Use user's home directory for desktop app
        home = Path.home()
        return home / 'VideoTrimmer'

APP_DATA_DIR = get_app_data_dir()
app.config['UPLOAD_FOLDER'] = str(APP_DATA_DIR / 'uploads')
app.config['OUTPUT_FOLDER'] = str(APP_DATA_DIR / 'output')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'mts'}

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
PREVIEW_FOLDER = str(APP_DATA_DIR / 'previews')
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

# Store video info in memory (for demo purposes)
videos = {}


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

            videos[video_id] = {
                'id': video_id,
                'filename': filename,
                'filepath': filepath,
                'duration': duration,
                'duration_str': seconds_to_timestamp(duration)
            }

            return jsonify({
                'id': video_id,
                'filename': filename,
                'duration': duration,
                'duration_str': seconds_to_timestamp(duration)
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
            trimmed = clip.subclipped(start, end)
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
    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404

    video = videos[video_id]

    # Get duration if not already cached or is 0
    if video.get('duration', 0) == 0:
        duration = get_video_duration(video['filepath'])
        video['duration'] = duration
        video['duration_str'] = seconds_to_timestamp(duration)

    return jsonify({
        'duration': video['duration'],
        'duration_str': video['duration_str']
    })


@app.route('/video/<video_id>')
def serve_video(video_id):
    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404

    video = videos[video_id]
    filepath = video['filepath']

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


@app.route('/preview/<video_id>')
def get_preview(video_id):
    """Generate and serve an H.264 preview for H.265/HEVC videos."""
    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404

    video = videos[video_id]
    preview_path = os.path.join(PREVIEW_FOLDER, f"{video_id}_preview.mp4")

    # Check if preview already exists
    if os.path.exists(preview_path):
        return send_file(preview_path, mimetype='video/mp4', conditional=True)

    # Generate preview by transcoding to H.264
    try:
        with VideoFileClip(video['filepath']) as clip:
            # Use a reasonable resolution for preview (max 720p)
            if clip.h > 720:
                resized = clip.resized(height=720)
            else:
                resized = clip

            resized.write_videofile(
                preview_path,
                codec="libx264",
                audio_codec="aac",
                preset="ultrafast",
                bitrate="2000k",
                logger=None
            )

        video['preview_path'] = preview_path
        return send_file(preview_path, mimetype='video/mp4', conditional=True)

    except Exception as e:
        return jsonify({'error': f'Failed to generate preview: {str(e)}'}), 500


@app.route('/preview/status/<video_id>')
def preview_status(video_id):
    """Check if a preview exists or needs to be generated."""
    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404

    preview_path = os.path.join(PREVIEW_FOLDER, f"{video_id}_preview.mp4")
    return jsonify({
        'exists': os.path.exists(preview_path),
        'video_id': video_id
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
