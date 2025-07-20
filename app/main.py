from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from app.converter import convert_heic_to_avif_variants
import base64
import gc
import psutil
import os
import httpx
import subprocess
from typing import Optional

app = FastAPI()

def get_memory_info():
    """Get current memory usage information"""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    return {
        "rss_mb": round(memory_info.rss / 1024 / 1024, 2),  # Resident Set Size
        "vms_mb": round(memory_info.vms / 1024 / 1024, 2),  # Virtual Memory Size
        "percent": round(process.memory_percent(), 2)
    }

@app.get("/health")
async def health_check():
    memory = get_memory_info()
    
    # Check if required libraries are available
    capabilities = {
        "pillow_heif": True,  # We import it at startup
        "avifenc": False
    }
    
    # Check for avifenc
    try:
        result = subprocess.run(["avifenc", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            capabilities["avifenc"] = True
    except:
        pass
    
    # Determine overall health status
    is_healthy = capabilities["pillow_heif"] and capabilities["avifenc"]
    
    # Only log health check if there's an issue
    if memory["percent"] > 80 or not is_healthy:
        print(f"[HEALTH] Service status check - Memory: {memory['percent']}%, Capabilities: {capabilities}")
    
    return {
        "status": "healthy" if is_healthy else "unhealthy", 
        "service": "heic2avif-py",
        "memory": memory,
        "capabilities": capabilities
    }

@app.post("/convert")
async def convert_image(
    image: UploadFile = File(...),
    originalFilename: Optional[str] = Form(None)
):
    # Log initial memory state
    memory_before = get_memory_info()
    heic_size_mb = 0

    print(f"[CONVERT] Starting HEIC conversion - Memory before: RSS={memory_before['rss_mb']}MB, VMS={memory_before['vms_mb']}MB, {memory_before['percent']}%")

    # Check if the file is HEIC/HEIF
    if image.content_type not in ["image/heic", "image/heif"]:
        # Also check filename extension as content-type might not be set correctly
        filename = originalFilename or image.filename or ""
        if not filename.lower().endswith((".heic", ".heif")):
            raise HTTPException(status_code=400, detail="Only HEIC/HEIF images are supported.")

    heic_data = await image.read()
    heic_size_mb = round(len(heic_data) / 1024 / 1024, 2)

    filename = originalFilename or image.filename or "image.heic"
    print(f"[CONVERT] Processing {filename}: HEIC input size = {heic_size_mb}MB")

    try:
        # Convert HEIC to AVIF
        avif_data = convert_heic_to_avif_variants(heic_data, filename)

        # Get file sizes for metrics
        original_size = len(heic_data)
        converted_size = len(avif_data)
        compression_ratio = round((1 - converted_size / original_size) * 100, 1)

        print(f"[CONVERT] Conversion completed: {filename}")
        print(f"[CONVERT] Original size: {heic_size_mb}MB, AVIF size: {round(converted_size / 1024 / 1024, 2)}MB")
        print(f"[CONVERT] Compression: {compression_ratio}% size reduction")

        # Clean up input data from memory early
        del heic_data
        gc.collect()

        # Return the converted AVIF data in the expected format
        return {
            "success": True,
            "fullSize": {
                "data": base64.b64encode(avif_data).decode('utf-8'),
                "size": converted_size
            }
        }

    except Exception as e:
        print(f"[CONVERT] Conversion failed for {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
