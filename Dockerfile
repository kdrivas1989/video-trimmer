FROM python:3.11-slim

# Install ffmpeg for video processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies (excluding desktop-only packages)
RUN pip install --no-cache-dir \
    moviepy>=1.0.3 \
    flask>=3.0.0 \
    gunicorn>=21.0.0 \
    imageio>=2.31.0 \
    imageio-ffmpeg>=0.4.9

# Copy application code
COPY main.py .
COPY templates/ templates/

# Create directories for uploads and outputs
RUN mkdir -p uploads output previews

# Expose port
EXPOSE 10000

# Run with gunicorn
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:10000", "--timeout", "300", "--workers", "2"]
