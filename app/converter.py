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
    Convert HEIC/HEIF to AVIF (full-size only) - Direct conversion
    Returns AVIF data as bytes
    """
    memory_start = get_memory_usage()
    print(f"[CONVERTER] Starting direct HEIC->AVIF conversion of {original_filename} - Memory: {memory_start}MB")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set input file extension based on original filename
        if original_filename.lower().endswith('.heif'):
            input_path = Path(tmpdir) / "input.heif"
        else:
            input_path = Path(tmpdir) / "input.heic"
        
        # Use original filename for output, just change extension to .avif
        base_name = Path(original_filename).stem  # Gets filename without extension
        output_path = Path(tmpdir) / f"{base_name}.avif"
        
        # Write input HEIC/HEIF
        input_path.write_bytes(heic_data)
        memory_after_write = get_memory_usage()
        print(f"[CONVERTER] HEIC written to temp file - Memory: {memory_after_write}MB (+{memory_after_write - memory_start}MB)")

        try:
            # Direct conversion from HEIC/HEIF to AVIF using avifenc
            print(f"[CONVERTER] Converting HEIC/HEIF directly to AVIF...")
            result = subprocess.run([
                "avifenc", 
                "--min", "0", "--max", "15",  # High quality (0=best, 18≈90% JPEG quality)
                "--speed", "10",  # Maximum speed (0=slowest/best, 10=fastest)
                "--jobs", "4",  # Use 4 threads for faster encoding
                str(input_path), 
                str(output_path)
            ], capture_output=True, text=True)

            memory_after_conversion = get_memory_usage()
            print(f"[CONVERTER] Direct HEIC->AVIF conversion complete - Memory: {memory_after_conversion}MB (+{memory_after_conversion - memory_start}MB from start)")

            if result.returncode != 0:
                print(f"[CONVERTER] avifenc failed with error: {result.stderr}")
                print(f"[CONVERTER] Trying fallback method...")
                # Try fallback conversion using Pillow + avifenc
                return convert_heic_to_avif_pillow_fallback(heic_data, original_filename, tmpdir)

            # Read the converted AVIF file
            avif_data = output_path.read_bytes()
            
            # Memory cleanup
            gc.collect()
            memory_after_read = get_memory_usage()
            print(f"[CONVERTER] AVIF file read and cleanup complete - Memory: {memory_after_read}MB")
            
            original_size_mb = round(len(heic_data) / 1024 / 1024, 2)
            avif_size_mb = round(len(avif_data) / 1024 / 1024, 2)
            compression_ratio = round((1 - len(avif_data) / len(heic_data)) * 100, 1)
            
            print(f"[CONVERTER] ✅ Direct conversion successful: {original_filename}")
            print(f"[CONVERTER] Original HEIC: {original_size_mb}MB -> AVIF: {avif_size_mb}MB ({compression_ratio}% reduction)")
            
            return avif_data
            
        except Exception as e:
            print(f"[CONVERTER] ❌ Error during direct conversion: {str(e)}")
            # Try alternative conversion method using Pillow + avifenc
            return convert_heic_to_avif_pillow_fallback(heic_data, original_filename, tmpdir)

def convert_heic_to_avif_pillow_fallback(heic_data: bytes, original_filename: str, tmpdir: str) -> bytes:
    """
    Fallback conversion method using Pillow to convert HEIC->JPEG, then avifenc for JPEG->AVIF
    """
    print(f"[CONVERTER] Trying fallback conversion with Pillow + avifenc...")
    
    input_path = Path(tmpdir) / "input.heic"
    intermediate_path = Path(tmpdir) / "intermediate.jpg"
    base_name = Path(original_filename).stem
    output_path = Path(tmpdir) / f"{base_name}.avif"
    
    # Write input file
    input_path.write_bytes(heic_data)
    
    try:
        # First, convert HEIC to JPEG using Pillow with HEIF support
        print(f"[CONVERTER] Converting HEIC to intermediate JPEG...")
        
        # Open HEIC file with Pillow
        with Image.open(input_path) as heic_image:
            # Convert to RGB if necessary (HEIC might be in different color space)
            if heic_image.mode != 'RGB':
                heic_image = heic_image.convert('RGB')
            
            # Save as high-quality JPEG
            heic_image.save(intermediate_path, 'JPEG', quality=95, optimize=True)
        
        print(f"[CONVERTER] HEIC -> JPEG conversion complete")
        
        # Now convert JPEG to AVIF using avifenc
        print(f"[CONVERTER] Converting JPEG to AVIF...")
        result = subprocess.run([
            "avifenc", 
            "--min", "0", "--max", "15",  # High quality
            "--speed", "10",  # Maximum speed
            "--jobs", "4",  # Use 4 threads
            str(intermediate_path), 
            str(output_path)
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[CONVERTER] avifenc failed in fallback: {result.stderr}")
            # Try final fallback with ImageMagick
            return convert_heic_to_avif_imagemagick(heic_data, original_filename, tmpdir)
        
        # Read the converted AVIF file
        avif_data = output_path.read_bytes()
        
        original_size_mb = round(len(heic_data) / 1024 / 1024, 2)
        avif_size_mb = round(len(avif_data) / 1024 / 1024, 2)
        compression_ratio = round((1 - len(avif_data) / len(heic_data)) * 100, 1)
        
        print(f"[CONVERTER] ✅ Pillow fallback conversion successful: {original_filename}")
        print(f"[CONVERTER] Original HEIC: {original_size_mb}MB -> AVIF: {avif_size_mb}MB ({compression_ratio}% reduction)")
        
        return avif_data
        
    except Exception as e:
        print(f"[CONVERTER] ❌ Pillow fallback conversion failed: {str(e)}")
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
