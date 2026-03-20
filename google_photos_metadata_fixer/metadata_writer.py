"""
EXIF and metadata writing functionality.
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
from fractions import Fraction
import shutil

try:
    import piexif
    from piexif.helper import UserComment
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False

from .file_matcher import MediaFile, load_json_metadata, extract_phototaken_time, extract_gps_data, extract_description


class MetadataWriter:
    """Handles writing metadata to media files."""
    
    def __init__(self, output_dir: Path, preserve_structure: bool = True):
        self.output_dir = Path(output_dir).resolve()
        self.preserve_structure = preserve_structure
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if not PIEXIF_AVAILABLE:
            raise ImportError("piexif is required. Install with: pip install piexif")
    
    def _decimal_to_dms(self, decimal: float) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
        """Convert decimal coordinates to DMS (degrees, minutes, seconds) format."""
        degrees = int(abs(decimal))
        minutes_full = (abs(decimal) - degrees) * 60
        minutes = int(minutes_full)
        seconds = int((minutes_full - minutes) * 60 * 100)
        
        return (
            (degrees, 1),
            (minutes, 1),
            (seconds, 100)
        )
    
    def _create_gps_exif(self, latitude: float, longitude: float, altitude: float = 0) -> dict:
        """Create GPS EXIF data structure."""
        gps_ifd = {
            piexif.GPSIFD.GPSVersionID: (2, 0, 0, 0),
            piexif.GPSIFD.GPSLatitudeRef: 'N' if latitude >= 0 else 'S',
            piexif.GPSIFD.GPSLatitude: self._decimal_to_dms(latitude),
            piexif.GPSIFD.GPSLongitudeRef: 'E' if longitude >= 0 else 'W',
            piexif.GPSIFD.GPSLongitude: self._decimal_to_dms(longitude),
        }
        
        if altitude != 0:
            gps_ifd[piexif.GPSIFD.GPSAltitudeRef] = 0 if altitude >= 0 else 1
            gps_ifd[piexif.GPSIFD.GPSAltitude] = (int(abs(altitude) * 100), 100)
        
        return gps_ifd
    
    def _timestamp_to_exif_datetime(self, timestamp: int) -> str:
        """Convert Unix timestamp to EXIF datetime format."""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y:%m:%d %H:%M:%S")
    
    def process_image(self, media_file: MediaFile) -> Tuple[bool, str]:
        """
        Process a single image file: copy to output and inject metadata.
        Returns (success, message).
        """
        try:
            # Determine output path
            if self.preserve_structure:
                output_path = self.output_dir / media_file.relative_path
            else:
                output_path = self.output_dir / media_file.path.name
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(media_file.path, output_path)
            
            # Load metadata
            metadata = load_json_metadata(media_file.json_path)
            if not metadata:
                return True, "Copied (no metadata found)"
            
            # Extract metadata fields
            timestamp = extract_phototaken_time(metadata)
            gps_data = extract_gps_data(metadata)
            description = extract_description(metadata)
            
            # Load existing EXIF or create new
            try:
                exif_dict = piexif.load(str(output_path))
            except Exception:
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            
            # Update DateTimeOriginal
            if timestamp:
                date_str = self._timestamp_to_exif_datetime(timestamp)
                exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str
                exif_dict["0th"][piexif.ImageIFD.DateTime] = date_str
            
            # Update GPS data
            if gps_data:
                lat, lon, alt = gps_data
                exif_dict["GPS"] = self._create_gps_exif(lat, lon, alt)
            
            # Update description
            if description:
                try:
                    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = description.encode('utf-8')
                except Exception:
                    pass
            
            # Save EXIF data
            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, str(output_path))
            
            # Update file modification time
            if timestamp:
                os.utime(output_path, (timestamp, timestamp))
            
            return True, "Metadata restored successfully"
            
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def process_video(self, media_file: MediaFile) -> Tuple[bool, str]:
        """
        Process a single video file: copy to output.
        Note: Videos don't support EXIF. We only copy and update file timestamps.
        """
        try:
            # Determine output path
            if self.preserve_structure:
                output_path = self.output_dir / media_file.relative_path
            else:
                output_path = self.output_dir / media_file.path.name
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(media_file.path, output_path)
            
            # Load metadata
            metadata = load_json_metadata(media_file.json_path)
            if not metadata:
                return True, "Copied (no metadata found)"
            
            # Extract timestamp and update file modification time
            timestamp = extract_phototaken_time(metadata)
            if timestamp:
                os.utime(output_path, (timestamp, timestamp))
                return True, "File timestamp restored"
            
            return True, "Copied"
            
        except Exception as e:
            return False, f"Error: {str(e)}"
