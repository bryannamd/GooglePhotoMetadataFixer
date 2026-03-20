# Google Photos Metadata Fixer

A Python tool to restore metadata from Google Photos Takeout JSON files into images and videos.

## Problem

When exporting data from Google Photos via Google Takeout, your photos and videos lose their original metadata (EXIF). The metadata—timestamps, GPS locations, descriptions—is stored in separate `.json` sidecar files. When you import these files into other photo managers (iCloud, Synology Photos, etc.), all photos appear with the download date instead of the original capture date.

## Solution

This tool matches media files with their corresponding JSON metadata files and injects the metadata back into the media files:

- **Date & Time**: Restores `DateTimeOriginal` EXIF tag and file modification time
- **GPS Location**: Writes latitude, longitude, and altitude to EXIF GPS tags
- **Descriptions**: Adds image descriptions from Google Photos
- **Handles Edge Cases**: Truncated filenames, edited files, duplicates, Live Photos

## Features

- **Smart File Matching**: Handles Google's inconsistent JSON naming conventions
  - `image.jpg` → `image.jpg.json`, `image.json`, `image.jpg.supplemental-metadata.json`
  - Truncated filenames (Google's 46-47 char limit bug)
  - Duplicate files: `image(1).jpg` → `image.jpg(1).json`
  - Edited files: `image-edited.jpg` uses `image.jpg` metadata
- **Multiple Formats**: JPG, PNG, HEIC, TIFF, MP4, MOV, and more
- **Preserves Structure**: Maintains your folder organization (or flatten if desired)
- **Progress Tracking**: Shows progress bar and detailed statistics
- **Error Handling**: Gracefully handles corrupted files and reports failures

## Installation

```bash
# Clone the repository
git clone https://github.com/bryannamd/GooglePhotoMetadataFixer.git
cd GooglePhotoMetadataFixer

# Install dependencies
pip install -r requirements.txt
```

### Optional: Video Support

For video metadata support, install ExifTool:

```bash
# macOS
brew install exiftool

# Linux
sudo apt-get install libimage-exiftool-perl

# Windows
# Download from https://exiftool.org/
```

## Usage

### Basic Usage

```bash
python -m google_photos_metadata_fixer -i /path/to/takeout -o /path/to/output
```

### Options

```bash
# Flatten output (all files in one directory)
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --flat

# Dry run (see what would be done without making changes)
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --dry-run

# Skip videos
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --skip-videos

# Verbose output
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored -v
```

## How It Works

1. **Scan**: Recursively scans input directory for media files and JSON sidecars
2. **Match**: Uses multiple strategies to match media files with their JSON files
3. **Extract**: Reads `photoTakenTime`, `geoData`, and `description` from JSON
4. **Inject**: Writes metadata to media files:
   - Images: EXIF tags (DateTimeOriginal, GPS)
   - Videos: File modification time (EXIF not supported for videos)
5. **Copy**: Copies files to output directory with restored metadata

## File Matching Logic

The tool tries multiple strategies to find JSON files:

1. Direct match: `image.jpg` → `image.jpg.json`
2. Extension variants: `image.jpg.supplemental-metadata.json`
3. Truncated names: Handles Google's 46-47 character filename limit
4. Bracket swap: `image(1).jpg` → `image.jpg(1).json`
5. Edited files: `image-edited.jpg` → `image.jpg`

## Google Takeout JSON Format

The tool reads Google Photos JSON files with this structure:

```json
{
  "title": "IMG_20230815_142536.jpg",
  "description": "Beach sunset",
  "photoTakenTime": {
    "timestamp": "1692113136",
    "formatted": "Aug 15, 2023, 2:25:36 PM UTC"
  },
  "geoData": {
    "latitude": 36.778259,
    "longitude": -119.417931,
    "altitude": 15.0
  }
}
```

## Limitations

- **Videos**: Most video formats (MP4, MOV) don't support EXIF. Only file modification time is updated.
- **HEIC**: Requires additional libraries for full support
- **Permissions**: May need administrator/root for setting file timestamps on some systems

## Inspired By

This project was inspired by [GooglePhotosTakeoutHelper (GPTH)](https://github.com/TheLastGimbus/GooglePhotosTakeoutHelper) but focuses specifically on metadata restoration rather than file organization.

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
