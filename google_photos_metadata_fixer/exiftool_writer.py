"""
ExifTool-based metadata writing functionality for images and videos.
"""

import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging


class ExifToolMetadataWriter:
    """
    Handles writing metadata to media files using ExifTool.
    Supports both images (EXIF) and videos (QuickTime).
    """
    
    def __init__(
        self,
        output_dir: Path,
        preserve_structure: bool = True,
        exiftool_path: Optional[str] = None,
        error_log_path: Optional[Path] = None,
        max_workers: int = 4
    ):
        self.output_dir = Path(output_dir).resolve()
        self.preserve_structure = preserve_structure
        self.exiftool_path = exiftool_path or "exiftool"
        self.max_workers = max_workers
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup error logging
        self.error_files: List[Tuple[Path, str]] = []
        self.error_log_path = error_log_path or (self.output_dir / "unmatched_files.txt")
        
        # Verify ExifTool is available
        self._verify_exiftool()
    
    def _verify_exiftool(self):
        """Verify ExifTool is installed and accessible."""
        try:
            result = subprocess.run(
                [self.exiftool_path, "-ver"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(f"ExifTool verification failed: {result.stderr}")
            self.exiftool_version = result.stdout.strip()
        except FileNotFoundError:
            raise RuntimeError(
                f"ExifTool not found at '{self.exiftool_path}'. "
                "Please install ExifTool: https://exiftool.org/install.html"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("ExifTool verification timed out")
    
    def _timestamp_to_exif_datetime(self, timestamp: int) -> str:
        """Convert Unix timestamp to EXIF datetime format."""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y:%m:%d %H:%M:%S")
    
    def _get_output_path(self, input_path: Path, relative_path: Path) -> Path:
        """Determine output path for a file."""
        if self.preserve_structure:
            output_path = self.output_dir / relative_path
        else:
            output_path = self.output_dir / input_path.name
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path
    
    def _copy_file(self, src: Path, dst: Path):
        """Copy file preserving metadata."""
        shutil.copy2(src, dst)
    
    def _build_exiftool_args(
        self,
        file_path: Path,
        timestamp: Optional[int],
        gps_data: Optional[Tuple[float, float, float]],
        description: Optional[str],
        is_video: bool
    ) -> List[str]:
        """
        Build ExifTool command arguments for metadata writing.
        """
        args = [self.exiftool_path, "-overwrite_original", "-preserve"]
        
        if timestamp:
            date_str = self._timestamp_to_exif_datetime(timestamp)
            
            if is_video:
                # QuickTime tags for videos
                args.extend([
                    f"-CreateDate={date_str}",
                    f"-ModifyDate={date_str}",
                    f"-TrackCreateDate={date_str}",
                    f"-TrackModifyDate={date_str}",
                    f"-MediaCreateDate={date_str}",
                    f"-MediaModifyDate={date_str}",
                ])
            else:
                # EXIF tags for images
                args.extend([
                    f"-DateTimeOriginal={date_str}",
                    f"-CreateDate={date_str}",
                    f"-ModifyDate={date_str}",
                ])
        
        if gps_data:
            lat, lon, alt = gps_data
            
            if is_video:
                # QuickTime GPS format
                lat_ref = "N" if lat >= 0 else "S"
                lon_ref = "E" if lon >= 0 else "W"
                
                args.extend([
                    f"-GPSLatitude={abs(lat):.6f}",
                    f"-GPSLatitudeRef={lat_ref}",
                    f"-GPSLongitude={abs(lon):.6f}",
                    f"-GPSLongitudeRef={lon_ref}",
                ])
                
                if alt != 0:
                    alt_ref = "Above Sea Level" if alt >= 0 else "Below Sea Level"
                    args.extend([
                        f"-GPSAltitude={abs(alt):.2f}",
                        f"-GPSAltitudeRef={alt_ref}",
                    ])
            else:
                # EXIF GPS format
                lat_ref = "N" if lat >= 0 else "S"
                lon_ref = "E" if lon >= 0 else "W"
                
                args.extend([
                    f"-GPSLatitude={abs(lat):.6f}",
                    f"-GPSLatitudeRef={lat_ref}",
                    f"-GPSLongitude={abs(lon):.6f}",
                    f"-GPSLongitudeRef={lon_ref}",
                ])
                
                if alt != 0:
                    alt_ref = "Above Sea Level" if alt >= 0 else "Below Sea Level"
                    args.extend([
                        f"-GPSAltitude={abs(alt):.2f}",
                        f"-GPSAltitudeRef={alt_ref}",
                    ])
        
        if description:
            # Escape special characters in description
            safe_description = description.replace('"', '\\"')
            
            if is_video:
                args.extend([
                    f"-Description={safe_description}",
                    f"-Comment={safe_description}",
                ])
            else:
                args.extend([
                    f"-ImageDescription={safe_description}",
                    f"-Description={safe_description}",
                ])
        
        args.append(str(file_path))
        return args
    
    def _run_exiftool(self, args: List[str]) -> Tuple[bool, str]:
        """
        Run ExifTool with given arguments.
        Returns (success, message).
        """
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return True, "Metadata written successfully"
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                return False, f"ExifTool error: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "ExifTool timeout (60s)"
        except Exception as e:
            return False, f"Error running ExifTool: {str(e)}"
    
    def _set_file_timestamps(self, file_path: Path, timestamp: int):
        """Set file system creation and modification times."""
        try:
            os.utime(file_path, (timestamp, timestamp))
        except Exception:
            pass
    
    def process_file(
        self,
        media_file,
        timestamp: Optional[int],
        gps_data: Optional[Tuple[float, float, float]],
        description: Optional[str]
    ) -> Tuple[bool, str]:
        """
        Process a single media file.
        Returns (success, message).
        """
        try:
            # Determine output path
            output_path = self._get_output_path(media_file.path, media_file.relative_path)
            
            # Copy file
            self._copy_file(media_file.path, output_path)
            
            # Check if it's a video
            is_video = media_file.suffix.lower() in {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}
            
            # Build and run ExifTool command
            args = self._build_exiftool_args(
                output_path,
                timestamp,
                gps_data,
                description,
                is_video
            )
            
            success, message = self._run_exiftool(args)
            
            if success and timestamp:
                # Also update file system timestamps
                self._set_file_timestamps(output_path, timestamp)
            
            return success, message
            
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def process_files_batch(
        self,
        files_with_metadata: List[Tuple[Any, Optional[int], Optional[Tuple], Optional[str]]],
        progress_callback=None
    ) -> Tuple[int, int, List[Tuple[Path, str]]]:
        """
        Process multiple files with multi-threading.
        Returns (success_count, error_count, error_files).
        """
        success_count = 0
        error_count = 0
        error_files: List[Tuple[Path, str]] = []
        
        def process_single(args):
            media_file, timestamp, gps_data, description = args
            success, message = self.process_file(media_file, timestamp, gps_data, description)
            
            if progress_callback:
                progress_callback(media_file.path.name)
            
            return media_file.path, success, message
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(process_single, item): item
                for item in files_with_metadata
            }
            
            for future in as_completed(futures):
                file_path, success, message = future.result()
                
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    error_files.append((file_path, message))
        
        # Write error log
        if error_files:
            self._write_error_log(error_files)
        
        return success_count, error_count, error_files
    
    def _write_error_log(self, error_files: List[Tuple[Path, str]]):
        """Write error log file."""
        try:
            with open(self.error_log_path, 'w', encoding='utf-8') as f:
                f.write("# Files that failed processing\n")
                f.write(f"# Total errors: {len(error_files)}\n")
                f.write("# Format: file_path | error_message\n\n")
                
                for file_path, message in error_files:
                    f.write(f"{file_path} | {message}\n")
        except Exception as e:
            logging.warning(f"Failed to write error log: {e}")


class BatchMetadataProcessor:
    """
    High-performance batch processor using ExifTool's stay_open mode.
    This is more efficient for processing thousands of files.
    """
    
    def __init__(
        self,
        output_dir: Path,
        preserve_structure: bool = True,
        exiftool_path: Optional[str] = None,
        error_log_path: Optional[Path] = None
    ):
        self.output_dir = Path(output_dir).resolve()
        self.preserve_structure = preserve_structure
        self.exiftool_path = exiftool_path or "exiftool"
        self.error_log_path = error_log_path or (self.output_dir / "unmatched_files.txt")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.error_files: List[Tuple[Path, str]] = []
        self.exiftool_process: Optional[subprocess.Popen] = None
    
    def _timestamp_to_exif_datetime(self, timestamp: int) -> str:
        """Convert Unix timestamp to EXIF datetime format."""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y:%m:%d %H:%M:%S")
    
    def _start_exiftool(self):
        """Start ExifTool in stay_open mode for batch processing."""
        self.exiftool_process = subprocess.Popen(
            [self.exiftool_path, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    
    def _stop_exiftool(self):
        """Stop ExifTool stay_open process."""
        if self.exiftool_process:
            try:
                self.exiftool_process.stdin.write("-stay_open\nFalse\n")
                self.exiftool_process.stdin.flush()
                self.exiftool_process.wait(timeout=10)
            except Exception:
                self.exiftool_process.kill()
            finally:
                self.exiftool_process = None
    
    def _execute_exiftool_command(self, args: List[str]) -> Tuple[bool, str]:
        """Execute a command through stay_open ExifTool."""
        if not self.exiftool_process:
            return False, "ExifTool not started"
        
        try:
            # Build command
            cmd = "\n".join(args) + "\n-execute\n"
            self.exiftool_process.stdin.write(cmd)
            self.exiftool_process.stdin.flush()
            
            # Read response (simple version - read until ready)
            output = []
            while True:
                line = self.exiftool_process.stdout.readline()
                if "{ready}" in line:
                    break
                output.append(line)
            
            result = "".join(output)
            
            if "Error" in result or "Warning" in result:
                return False, result.strip()
            return True, "OK"
            
        except Exception as e:
            return False, str(e)
    
    def __enter__(self):
        self._start_exiftool()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_exiftool()
        return False
    
    def process_file(
        self,
        media_file,
        timestamp: Optional[int],
        gps_data: Optional[Tuple[float, float, float]],
        description: Optional[str]
    ) -> Tuple[bool, str]:
        """Process a single file using stay_open mode."""
        try:
            # Determine output path
            if self.preserve_structure:
                output_path = self.output_dir / media_file.relative_path
            else:
                output_path = self.output_dir / media_file.path.name
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(media_file.path, output_path)
            
            # Check if video
            is_video = media_file.suffix.lower() in {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}
            
            # Build ExifTool arguments
            args = ["-overwrite_original", "-preserve"]
            
            if timestamp:
                date_str = self._timestamp_to_exif_datetime(timestamp)
                
                if is_video:
                    args.extend([
                        f"-CreateDate={date_str}",
                        f"-ModifyDate={date_str}",
                        f"-TrackCreateDate={date_str}",
                        f"-TrackModifyDate={date_str}",
                        f"-MediaCreateDate={date_str}",
                        f"-MediaModifyDate={date_str}",
                    ])
                else:
                    args.extend([
                        f"-DateTimeOriginal={date_str}",
                        f"-CreateDate={date_str}",
                        f"-ModifyDate={date_str}",
                    ])
            
            if gps_data:
                lat, lon, alt = gps_data
                lat_ref = "N" if lat >= 0 else "S"
                lon_ref = "E" if lon >= 0 else "W"
                
                args.extend([
                    f"-GPSLatitude={abs(lat):.6f}",
                    f"-GPSLatitudeRef={lat_ref}",
                    f"-GPSLongitude={abs(lon):.6f}",
                    f"-GPSLongitudeRef={lon_ref}",
                ])
                
                if alt != 0:
                    args.extend([
                        f"-GPSAltitude={abs(alt):.2f}",
                    ])
            
            if description:
                safe_description = description.replace('"', '\\"')
                if is_video:
                    args.extend([
                        f"-Description={safe_description}",
                        f"-Comment={safe_description}",
                    ])
                else:
                    args.extend([
                        f"-ImageDescription={safe_description}",
                    ])
            
            args.append(str(output_path))
            
            success, message = self._execute_exiftool_command(args)
            
            if success and timestamp:
                try:
                    os.utime(output_path, (timestamp, timestamp))
                except Exception:
                    pass
            
            return success, message
            
        except Exception as e:
            return False, f"Error: {str(e)}"
