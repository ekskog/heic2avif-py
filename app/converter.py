import subprocess
import tempfile
from pathlib import Path
from typing import Tuple
import psutil
import os
import gc
from PIL import Image
import pillow_heif

# Register HEIF opener with Pillow
pillow_heif.register_heif_opener()

def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process(os.getpid())
    return round(process.memory_info().rss / 1024 / 1024, 2)

def convert_heic_to_avif_variants(heic_data: bytes, original_filename: str = "image.heic") -> bytes:
    """
    Convert HEIC/HEIF to AVIF using Pillow + avifenc approach
    Returns AVIF data as bytes
    """
    memory_start = get_memory_usage()
    print(f"[CONVERTER] Starting HEIC->AVIF conversion of {original_filename} - Memory: {memory_start}MB")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use Pillow + avifenc method (most reliable for HEIC)
        return convert_heic_to_avif_pillow_method(heic_data, original_filename, tmpdir)

def convert_heic_to_avif_pillow_method(heic_data: bytes, original_filename: str, tmpdir: str) -> bytes:
    """
    Convert HEIC to AVIF using Pillow + pillow-avif (primary method)
    Avoids intermediate JPEG to reduce memory usage
    """
    print(f"[CONVERTER] Converting HEIC->AVIF using Pillow (direct conversion)...")
    
    input_path = Path(tmpdir) / "input.heic"
    base_name = Path(original_filename).stem
    output_path = Path(tmpdir) / f"{base_name}.avif"
    
    # Write input file
    input_path.write_bytes(heic_data)
    
    try:
        # Direct conversion using Pillow with AVIF support (no intermediate)
        print(f"[CONVERTER] Direct HEIC->AVIF conversion (no intermediate)...")
        
        # Open HEIC file with Pillow
        with Image.open(input_path) as heic_image:
            # Convert to RGB if necessary
            if heic_image.mode != 'RGB':
                heic_image = heic_image.convert('RGB')
            
            # Save directly as AVIF (requires pillow-avif-plugin)
            heic_image.save(output_path, 'AVIF', quality=85, speed=6)
        
        # Check if file was created successfully
        if not output_path.exists():
            print(f"[CONVERTER] Direct AVIF save failed, trying avifenc method...")
            return convert_heic_to_avif_with_intermediate(heic_data, original_filename, tmpdir)
        
        # Read the converted AVIF file
        avif_data = output_path.read_bytes()
        
        original_size_mb = round(len(heic_data) / 1024 / 1024, 2)
        avif_size_mb = round(len(avif_data) / 1024 / 1024, 2)
        compression_ratio = round((1 - len(avif_data) / len(heic_data)) * 100, 1)
        
        print(f"[CONVERTER] ✅ Direct HEIC->AVIF conversion successful: {original_filename}")
        print(f"[CONVERTER] Original HEIC: {original_size_mb}MB -> AVIF: {avif_size_mb}MB ({compression_ratio}% reduction)")
        
        return avif_data
        
    except Exception as e:
        print(f"[CONVERTER] ❌ Direct Pillow conversion failed: {str(e)}")
        print(f"[CONVERTER] Falling back to intermediate JPEG method...")
        # Try intermediate conversion method
        return convert_heic_to_avif_with_intermediate(heic_data, original_filename, tmpdir)

def convert_heic_to_avif_with_intermediate(heic_data: bytes, original_filename: str, tmpdir: str) -> bytes:
    """
    Convert HEIC to AVIF using intermediate JPEG (fallback method)
    """
    print(f"[CONVERTER] Converting HEIC->AVIF using intermediate JPEG...")
    
    input_path = Path(tmpdir) / "input.heic"
    intermediate_path = Path(tmpdir) / "intermediate.jpg"
    base_name = Path(original_filename).stem
    output_path = Path(tmpdir) / f"{base_name}.avif"
    
    # Write input file
    input_path.write_bytes(heic_data)
    
    try:
        # First, convert HEIC to JPEG using Pillow with HEIF support
        print(f"[CONVERTER] Step 1: Converting HEIC to intermediate JPEG...")
        
        # Open HEIC file with Pillow
        with Image.open(input_path) as heic_image:
            # Convert to RGB if necessary (HEIC might be in different color space)
            if heic_image.mode != 'RGB':
                heic_image = heic_image.convert('RGB')
            
            # Save as high-quality JPEG
            heic_image.save(intermediate_path, 'JPEG', quality=95, optimize=True)
        
        print(f"[CONVERTER] Step 2: Converting JPEG to AVIF...")
        
        # Now convert JPEG to AVIF using avifenc
        result = subprocess.run([
            "avifenc", 
            "--min", "0", "--max", "15",  # High quality
            "--speed", "10",  # Maximum speed
            "--jobs", "4",  # Use 4 threads
            str(intermediate_path), 
            str(output_path)
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[CONVERTER] avifenc failed: {result.stderr}")
            # Try final fallback with ImageMagick
            return convert_heic_to_avif_imagemagick(heic_data, original_filename, tmpdir)
        
        # Read the converted AVIF file
        avif_data = output_path.read_bytes()
        
        original_size_mb = round(len(heic_data) / 1024 / 1024, 2)
        avif_size_mb = round(len(avif_data) / 1024 / 1024, 2)
        compression_ratio = round((1 - len(avif_data) / len(heic_data)) * 100, 1)
        
        print(f"[CONVERTER] ✅ Intermediate HEIC->AVIF conversion successful: {original_filename}")
        print(f"[CONVERTER] Original HEIC: {original_size_mb}MB -> AVIF: {avif_size_mb}MB ({compression_ratio}% reduction)")
        
        return avif_data
        
    except Exception as e:
        print(f"[CONVERTER] ❌ Intermediate conversion failed: {str(e)}")
        # Try final fallback with ImageMagick
        return convert_heic_to_avif_imagemagick(heic_data, original_filename, tmpdir)

def convert_heic_to_avif_imagemagick(heic_data: bytes, original_filename: str, tmpdir: str) -> bytes:
    """
    Final fallback conversion method using ImageMagick for direct HEIC->AVIF conversion
    """
    print(f"[CONVERTER] Trying final fallback conversion with ImageMagick...")
    
    # Set input file extension based on original filename
    if original_filename.lower().endswith('.heif'):
        input_path = Path(tmpdir) / "input.heif"
    else:
        input_path = Path(tmpdir) / "input.heic"
    
    base_name = Path(original_filename).stem
    output_path = Path(tmpdir) / f"{base_name}.avif"
    
    # Write input file
    input_path.write_bytes(heic_data)
    
    try:
        # Use ImageMagick to convert HEIC directly to AVIF
        result = subprocess.run([
            "magick",
            str(input_path),
            "-quality", "85",  # High quality
            str(output_path)
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[CONVERTER] ImageMagick conversion failed: {result.stderr}")
            raise RuntimeError(f"ImageMagick conversion failed: {result.stderr}")
        
        # Read the converted AVIF file
        avif_data = output_path.read_bytes()
        
        original_size_mb = round(len(heic_data) / 1024 / 1024, 2)
        avif_size_mb = round(len(avif_data) / 1024 / 1024, 2)
        compression_ratio = round((1 - len(avif_data) / len(heic_data)) * 100, 1)
        
        print(f"[CONVERTER] ✅ ImageMagick conversion successful: {original_filename}")
        print(f"[CONVERTER] Original HEIC: {original_size_mb}MB -> AVIF: {avif_size_mb}MB ({compression_ratio}% reduction)")
        
        return avif_data
        
    except Exception as e:
        print(f"[CONVERTER] ❌ ImageMagick conversion also failed: {str(e)}")
        raise RuntimeError(f"All conversion methods failed. Last error: {str(e)}")
