"""
File matching logic for Google Photos Takeout.

Handles complex filename matching scenarios:
1. Standard matching: image.jpg -> image.jpg.json
2. Extension variants: image.jpg.json, image.json, image.jpg.supplemental-metadata.json
3. Truncated filenames (Google's 46-47 char limit bug)
4. Duplicate files: image(1).jpg -> image.jpg(1).json
5. Edited files: image-edited.jpg -> image.jpg (find original JSON)
6. Live Photos: image.jpg + image.mov (paired files)
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
import json


@dataclass
class MediaFile:
    """Represents a media file with its potential JSON sidecar."""
    path: Path
    relative_path: Path
    json_path: Optional[Path] = None
    is_edited: bool = False
    is_duplicate: bool = False
    original_name: Optional[str] = None
    
    @property
    def name(self) -> str:
        return self.path.name
    
    @property
    def stem(self) -> str:
        return self.path.stem
    
    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()


class FileMatcher:
    """Handles matching between media files and their JSON metadata files."""
    
    # Supported media extensions
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.tiff', '.tif', '.gif', '.webp', '.raw', '.cr2', '.nef', '.arw'}
    VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm'}
    ALL_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
    
    # JSON file patterns (in order of preference)
    JSON_PATTERNS = [
        '{name}{ext}.json',                    # image.jpg.json (most common)
        '{name}.json',                          # image.json
        '{name}{ext}.supplemental-metadata.json',  # newer format
        '{name}{ext}.suppl.json',
        '{name}{ext}.metadata.json',
    ]
    
    def __init__(self, input_dir: Path):
        self.input_dir = Path(input_dir).resolve()
        self.json_files: Dict[str, Path] = {}  # normalized name -> path
        self.media_files: List[MediaFile] = []
        self._scan_json_files()
    
    def _scan_json_files(self):
        """Scan and index all JSON files in the input directory."""
        for json_path in self.input_dir.rglob('*.json'):
            # Skip Google's metadata.json files (album-level metadata)
            if json_path.name == 'metadata.json':
                continue
            
            normalized = self._normalize_json_name(json_path.name)
            self.json_files[normalized] = json_path
    
    def _normalize_json_name(self, json_name: str) -> str:
        """
        Normalize JSON filename for matching.
        Handles various Google Takeout naming conventions.
        """
        # Remove common suffixes to get base for matching
        name = json_name
        
        # Remove .json extension
        if name.endswith('.json'):
            name = name[:-5]
        
        # Remove supplemental-metadata suffixes
        suffixes_to_remove = [
            '.supplemental-metadata',
            '.supplemental-metadat',
            '.supplemental-metada',
            '.supplemental-metad',
            '.supplemental-meta',
            '.supplemental-met',
            '.supplemental-me',
            '.supplemental-m',
            '.supplemental-',
            '.supplemental',
            '.supplementa',
            '.supplement',
            '.suppl',
            '.supp',
            '.sup',
            '.su',
            '.s',
            '.metadata',
            '.metadat',
            '.metada',
            '.metad',
            '.meta',
            '.met',
            '.me',
            '.m',
        ]
        
        for suffix in suffixes_to_remove:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        
        return name.lower()
    
    def _is_truncated_match(self, media_stem: str, json_normalized: str) -> bool:
        """
        Check if a media file matches a potentially truncated JSON name.
        Google truncates filenames at ~46-47 characters.
        """
        # If exact match or media name starts with json name (truncated case)
        media_lower = media_stem.lower()
        json_lower = json_normalized.lower()
        
        # Exact match
        if media_lower == json_lower:
            return True
        
        # Check for truncation - json name should be prefix of media name
        # and length should be around 46-47 chars (truncation point)
        if len(json_lower) >= 40 and media_lower.startswith(json_lower):
            return True
        
        # Also check reverse (sometimes media is truncated, not JSON)
        if len(media_lower) >= 40 and json_lower.startswith(media_lower):
            return True
        
        return False
    
    def _find_json_for_media(self, media_path: Path) -> Optional[Path]:
        """
        Find the matching JSON file for a media file.
        Tries multiple strategies in order of preference.
        """
        media_name = media_path.name
        media_stem = media_path.stem
        media_ext = media_path.suffix
        media_dir = media_path.parent
        
        # Strategy 1: Direct match with same directory
        for pattern in self.JSON_PATTERNS:
            json_name = pattern.format(name=media_stem, ext=media_ext)
            json_path = media_dir / json_name
            if json_path.exists():
                return json_path
        
        # Strategy 2: Check for duplicate file pattern
        # image(1).jpg -> image.jpg(1).json
        duplicate_match = re.match(r'(.+)\((\d+)\)(\.\w+)$', media_name)
        if duplicate_match:
            base_name = duplicate_match.group(1)
            dup_num = duplicate_match.group(2)
            ext = duplicate_match.group(3)
            
            # Try pattern: image.jpg(1).json
            json_name = f"{base_name}{ext}({dup_num}).json"
            json_path = media_dir / json_name
            if json_path.exists():
                return json_path
            
            # Also try: image(1).jpg.json
            json_name = f"{media_name}.json"
            json_path = media_dir / json_name
            if json_path.exists():
                return json_path
        
        # Strategy 3: Search in our JSON index
        # Try exact normalized match
        normalized_target = self._normalize_json_name(f"{media_stem}{media_ext}.json")
        if normalized_target in self.json_files:
            return self.json_files[normalized_target]
        
        # Try with truncated matching
        for normalized_name, json_path in self.json_files.items():
            if self._is_truncated_match(f"{media_stem}{media_ext}", normalized_name):
                # Verify it's in the same directory or nearby
                if self._is_same_context(media_path, json_path):
                    return json_path
        
        return None
    
    def _is_same_context(self, media_path: Path, json_path: Path) -> bool:
        """Check if JSON file is in same or parent directory of media file."""
        media_dir = media_path.parent
        json_dir = json_path.parent
        
        # Same directory
        if media_dir == json_dir:
            return True
        
        # JSON in parent (sometimes Google puts JSONs one level up)
        if json_dir == media_dir.parent:
            return True
        
        return False
    
    def scan_media_files(self) -> List[MediaFile]:
        """
        Scan input directory for all media files and match with JSON files.
        """
        self.media_files = []
        
        for media_path in self.input_dir.rglob('*'):
            if not media_path.is_file():
                continue
            
            # Skip JSON files
            if media_path.suffix.lower() == '.json':
                continue
            
            # Check if it's a supported media file
            if media_path.suffix.lower() not in self.ALL_MEDIA_EXTENSIONS:
                continue
            
            # Calculate relative path
            relative_path = media_path.relative_to(self.input_dir)
            
            # Detect edited files
            is_edited = False
            original_name = None
            
            # Check for -edited suffix
            if '-edited' in media_path.stem.lower():
                is_edited = True
                # Remove -edited to find original
                original_stem = re.sub(r'-edited$', '', media_path.stem, flags=re.IGNORECASE)
                original_name = f"{original_stem}{media_path.suffix}"
            
            # Check for duplicate pattern
            is_duplicate = bool(re.search(r'\(\d+\)\.', media_path.name))
            
            # Find JSON file
            if is_edited and original_name:
                # For edited files, look for original file's JSON
                original_path = media_path.parent / original_name
                json_path = self._find_json_for_media(original_path)
            else:
                json_path = self._find_json_for_media(media_path)
            
            media_file = MediaFile(
                path=media_path,
                relative_path=relative_path,
                json_path=json_path,
                is_edited=is_edited,
                is_duplicate=is_duplicate,
                original_name=original_name
            )
            
            self.media_files.append(media_file)
        
        return self.media_files
    
    def get_unmatched_files(self) -> List[MediaFile]:
        """Return media files that don't have a matching JSON file."""
        return [mf for mf in self.media_files if mf.json_path is None]
    
    def get_matched_files(self) -> List[MediaFile]:
        """Return media files that have a matching JSON file."""
        return [mf for mf in self.media_files if mf.json_path is not None]


def load_json_metadata(json_path: Path) -> Optional[dict]:
    """Load and parse Google Photos JSON metadata file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, IOError) as e:
        # Try with different encoding
        try:
            with open(json_path, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except Exception:
            return None


def extract_phototaken_time(metadata: dict) -> Optional[int]:
    """
    Extract photo taken timestamp from metadata.
    Returns Unix timestamp or None if not found.
    """
    # Try photoTakenTime first (most accurate)
    if 'photoTakenTime' in metadata:
        timestamp = metadata['photoTakenTime'].get('timestamp')
        if timestamp:
            return int(timestamp)
    
    # Fallback to creationTime
    if 'creationTime' in metadata:
        timestamp = metadata['creationTime'].get('timestamp')
        if timestamp:
            return int(timestamp)
    
    return None


def extract_gps_data(metadata: dict) -> Optional[Tuple[float, float, float]]:
    """
    Extract GPS coordinates from metadata.
    Returns (latitude, longitude, altitude) or None.
    """
    # Try geoData first
    geo_data = metadata.get('geoData')
    if geo_data and geo_data.get('latitude') is not None:
        return (
            float(geo_data.get('latitude', 0)),
            float(geo_data.get('longitude', 0)),
            float(geo_data.get('altitude', 0))
        )
    
    # Try geoDataExif as fallback
    geo_data_exif = metadata.get('geoDataExif')
    if geo_data_exif and geo_data_exif.get('latitude') is not None:
        return (
            float(geo_data_exif.get('latitude', 0)),
            float(geo_data_exif.get('longitude', 0)),
            float(geo_data_exif.get('altitude', 0))
        )
    
    return None


def extract_description(metadata: dict) -> Optional[str]:
    """Extract description from metadata."""
    return metadata.get('description') or None
