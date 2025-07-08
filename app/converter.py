import subprocess
import tempfile
from pathlib import Path
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
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use intermediate JPEG method (most reliable)
            result = convert_heic_to_avif_with_intermediate(heic_data, original_filename, tmpdir)
            
            # Force garbage collection before returning
            gc.collect()
            
            memory_end = get_memory_usage()
            print(f"[CONVERTER] Conversion completed - Memory: {memory_end}MB (delta: {memory_end - memory_start:+.2f}MB)")
            
            return result
    except Exception as e:
        # Force garbage collection on error
        gc.collect()
        memory_error = get_memory_usage()
        print(f"[CONVERTER] Conversion failed - Memory after cleanup: {memory_error}MB")
        raise e

def convert_heic_to_avif_with_intermediate(heic_data: bytes, original_filename: str, tmpdir: str) -> bytes:
    """
    Convert HEIC to AVIF using Pillow (HEIC->JPEG) + avifenc (JPEG->AVIF)
    """
    print(f"[CONVERTER] Converting HEIC->AVIF using Pillow + avifenc...")
    
    input_path = Path(tmpdir) / "input.heic"
    intermediate_path = Path(tmpdir) / "intermediate.jpg"
    base_name = Path(original_filename).stem
    output_path = Path(tmpdir) / f"{base_name}.avif"
    
    # Write input file
    input_path.write_bytes(heic_data)
    
    try:
        # Step 1: Convert HEIC to JPEG using Pillow with HEIF support
        print(f"[CONVERTER] Step 1: Converting HEIC to intermediate JPEG...")
        
        with Image.open(input_path) as heic_image:
            # Convert to RGB if necessary (HEIC might be in different color space)
            if heic_image.mode != 'RGB':
                heic_image = heic_image.convert('RGB')
            
            # Save as high-quality JPEG
            heic_image.save(intermediate_path, 'JPEG', quality=95, optimize=True)
        
        # Force garbage collection after first conversion
        gc.collect()
        
        print(f"[CONVERTER] Step 2: Converting JPEG to AVIF using avifenc...")
        
        # Step 2: Convert JPEG to AVIF using avifenc
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
            raise RuntimeError(f"avifenc conversion failed: {result.stderr}")
        
        # Check if output file was created and has content
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("avifenc output file is empty or missing")
        
        # Read the converted AVIF file
        avif_data = output_path.read_bytes()
        
        original_size_mb = round(len(heic_data) / 1024 / 1024, 2)
        avif_size_mb = round(len(avif_data) / 1024 / 1024, 2)
        compression_ratio = round((1 - len(avif_data) / len(heic_data)) * 100, 1)
        
        print(f"[CONVERTER] ✅ HEIC->AVIF conversion successful: {original_filename}")
        print(f"[CONVERTER] Original HEIC: {original_size_mb}MB -> AVIF: {avif_size_mb}MB ({compression_ratio}% reduction)")
        
        return avif_data
        
    except Exception as e:
        print(f"[CONVERTER] ❌ Conversion failed: {str(e)}")
        raise RuntimeError(f"HEIC to AVIF conversion failed: {str(e)}")
