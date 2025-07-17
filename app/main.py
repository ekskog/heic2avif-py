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
    bucketName: Optional[str] = Form(None),
    folderPath: Optional[str] = Form(None),
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
        if not filename.lower().endswith(('.heic', '.heif')):
            raise HTTPException(status_code=400, detail="Only HEIC/HEIF images are supported.")
    
    heic_data = await image.read()
    heic_size_mb = round(len(heic_data) / 1024 / 1024, 2)
    
    # Check if file is too large (safety limit)
    max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "100"))  # Default 100MB limit
    if heic_size_mb > max_file_size_mb:
        raise HTTPException(
            status_code=413, 
            detail=f"File too large: {heic_size_mb}MB exceeds limit of {max_file_size_mb}MB"
        )
    
    filename = originalFilename or image.filename or "image.heic"
    print(f"[CONVERT] Processing {filename}: HEIC input size = {heic_size_mb}MB")
    
    try:
        # Check memory after reading file
        memory_after_read = get_memory_info()
        print(f"[CONVERT] File read into memory - Memory after: RSS={memory_after_read['rss_mb']}MB (+{memory_after_read['rss_mb'] - memory_before['rss_mb']}MB)")
        
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
        
        # Check memory after conversion
        memory_after_conversion = get_memory_info()
        print(f"[CONVERT] Conversion complete - Memory after: RSS={memory_after_conversion['rss_mb']}MB")
        
        # Send callback to PhotoVault API
        callback_success = await send_conversion_callback(
            bucketName=bucketName,
            folderPath=folderPath,
            originalFilename=filename,
            convertedFilename=filename.replace('.heic', '.avif').replace('.heif', '.avif'),
            success=True,
            fileSize=converted_size,
            originalSize=original_size,
            compressionRatio=compression_ratio,
            processingTime=None  # Could add timing if needed
        )
        
        if not callback_success:
            print(f"[CONVERT] Warning: Failed to send callback for {filename}")
        
        # Return the converted AVIF data
        return {
            "success": True,
            "message": "HEIC successfully converted to AVIF",
            "original_size": original_size,
            "converted_size": converted_size,
            "compression_ratio": compression_ratio,
            "avif_data": base64.b64encode(avif_data).decode('utf-8')
        }
        
    except Exception as e:
        print(f"[CONVERT] Conversion failed for {filename}: {str(e)}")
        
        # Send failure callback
        await send_conversion_callback(
            bucketName=bucketName,
            folderPath=folderPath,
            originalFilename=filename,
            convertedFilename=None,
            success=False,
            error=str(e)
        )
        
        # Clean up memory
        if 'heic_data' in locals():
            del heic_data
        gc.collect()
        
        memory_after_error = get_memory_info()
        print(f"[CONVERT] Error cleanup complete - Memory: RSS={memory_after_error['rss_mb']}MB")
        
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")

async def send_conversion_callback(
    bucketName: Optional[str] = None,
    folderPath: Optional[str] = None,
    originalFilename: Optional[str] = None,
    convertedFilename: Optional[str] = None,
    success: bool = False,
    fileSize: Optional[int] = None,
    originalSize: Optional[int] = None,
    compressionRatio: Optional[float] = None,
    processingTime: Optional[int] = None,
    error: Optional[str] = None
):
    """Send conversion completion callback to PhotoVault API"""
    
    # Get API URL from environment
    api_url = os.getenv("PHOTOVAULT_API_URL", "http://photovault-api:3001")
    callback_url = f"{api_url}/conversion-complete"
    
    # Prepare callback payload
    callback_data = {
        "originalFilename": originalFilename,
        "convertedFilename": convertedFilename,
        "success": success,
        "bucketName": bucketName,
        "folderPath": folderPath
    }
    
    # Add optional fields if provided
    if fileSize is not None:
        callback_data["fileSize"] = fileSize
    if originalSize is not None:
        callback_data["originalSize"] = originalSize
    if compressionRatio is not None:
        callback_data["compressionRatio"] = compressionRatio
    if processingTime is not None:
        callback_data["processingTime"] = processingTime
    if error is not None:
        callback_data["error"] = error
    
    try:
        timeout = int(os.getenv("CALLBACK_TIMEOUT", "30"))
        
        print(f"[CALLBACK] Sending callback to {callback_url}")
        print(f"[CALLBACK] Payload: {callback_data}")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(callback_url, json=callback_data)
            
            if response.status_code == 200:
                print(f"[CALLBACK] ✅ Callback sent successfully for {originalFilename}")
                return True
            else:
                print(f"[CALLBACK] ❌ Callback failed with status {response.status_code}: {response.text}")
                return False
                
    except httpx.TimeoutException:
        print(f"[CALLBACK] ❌ Callback timeout for {originalFilename}")
        return False
    except Exception as e:
        print(f"[CALLBACK] ❌ Callback error for {originalFilename}: {str(e)}")
        return False

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
