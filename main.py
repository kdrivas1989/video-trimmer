#!/usr/bin/env python3
"""Video Trimmer Web App - Upload videos, select trim times, and download results."""

import os
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from moviepy import VideoFileClip

app = Flask(__name__)

# Use local folders for file storage
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'output'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'mts'}

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

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
    """Convert seconds to HH:MM:SS.mmm format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def timestamp_to_seconds(timestamp):
    """Convert HH:MM:SS.mmm or MM:SS.mmm format to seconds."""
    parts = timestamp.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    else:
        return float(parts[0])


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
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

        # Try to get duration, but don't fail if it takes too long
        try:
            duration = get_video_duration(filepath)
        except Exception:
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


@app.route('/trim', methods=['POST'])
def trim_video():
    data = request.json
    video_id = data.get('id')
    start_time = data.get('start', '00:00:00')
    end_time = data.get('end')

    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404

    video = videos[video_id]

    try:
        start = timestamp_to_seconds(start_time)
        end = timestamp_to_seconds(end_time) if end_time else video['duration']

        if start >= end:
            return jsonify({'error': 'Start time must be before end time'}), 400

        # Generate output path
        original_name = Path(video['filename']).stem
        output_name = f"{original_name}_trimmed.mp4"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{video_id}_{output_name}")

        with VideoFileClip(video['filepath']) as clip:
            trimmed = clip.subclipped(start, end)
            trimmed.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                logger=None
            )

        videos[video_id]['output_path'] = output_path
        videos[video_id]['output_name'] = output_name

        return jsonify({
            'success': True,
            'id': video_id,
            'output_name': output_name
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


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


@app.route('/video/<video_id>')
def serve_video(video_id):
    if video_id not in videos:
        return jsonify({'error': 'Video not found'}), 404

    video = videos[video_id]
    return send_file(video['filepath'])


@app.route('/delete/<video_id>', methods=['DELETE'])
def delete_video(video_id):
    if video_id in videos:
        video = videos[video_id]
        # Clean up files
        if os.path.exists(video['filepath']):
            os.remove(video['filepath'])
        if 'output_path' in video and os.path.exists(video['output_path']):
            os.remove(video['output_path'])
        del videos[video_id]

    return jsonify({'success': True})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'

    print("\n=== Video Trimmer Web App ===")
    print(f"Open http://localhost:{port} in your browser\n")
    app.run(debug=debug, host='0.0.0.0', port=port)
