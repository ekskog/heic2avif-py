FROM python:3.11-slim

# System dependencies for HEIC/HEIF and AVIF processing (minimal set)
RUN apt-get update && apt-get install -y \
    libheif-dev \
    libavif-bin \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy source files
COPY app /app/app
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Clean up
RUN apt-get autoremove -y && apt-get clean

# Expose port
EXPOSE 3000

# Launch FastAPI with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
