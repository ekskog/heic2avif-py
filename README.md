# HEIC2AVIF-PY

A FastAPI microservice that converts HEIC/HEIF images to AVIF format.

## Features

- **HEIC/HEIF to AVIF conversion**: Converts Apple's HEIC/HEIF format to efficient AVIF format
- **Quality optimization**: Maintains high quality while reducing file size
- **Memory efficient**: Optimized for handling large image files
- **Callback support**: Notifies the main API when conversion is complete
- **Health monitoring**: Built-in health check endpoint

## API Endpoints

- `GET /health` - Health check with memory usage info
- `POST /convert` - Convert HEIC/HEIF image to AVIF

## Requirements

- Python 3.11+
- libheif-dev (for HEIC/HEIF support)
- libavif-bin (for AVIF encoding)
- ImageMagick (for image processing)

## Installation

### Using Docker

```bash
docker build -t heic2avif-py .
docker run -p 3001:3001 heic2avif-py
```

### Local Development

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y libheif-dev libavif-bin imagemagick

# Install Python dependencies
pip install -r requirements.txt

# Run the service
uvicorn app.main:app --host 0.0.0.0 --port 3001
```

## Usage

```bash
# Convert a HEIC image
curl -X POST "http://localhost:3001/convert" \
  -F "image=@photo.heic"
```

## Environment Variables

- `PHOTOVAULT_API_URL`: URL of the PhotoVault API for callbacks (default: http://photovault-api:3001)
- `CALLBACK_TIMEOUT`: Timeout for callback requests in seconds (default: 30)

## Docker Image

The service is packaged as a Docker container with all necessary dependencies pre-installed.

## Integration

This service integrates with the PhotoVault API by:
1. Receiving HEIC/HEIF images via the `/convert` endpoint
2. Converting them to AVIF format
3. Sending completion callbacks to the PhotoVault API
