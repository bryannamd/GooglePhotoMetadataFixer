# Google Photos Metadata Fixer

A Python tool to restore metadata from Google Photos Takeout JSON files into images and videos using ExifTool.

## Problem

When exporting data from Google Photos via Google Takeout, your photos and videos lose their original metadata (EXIF). The metadata—timestamps, GPS locations, descriptions—is stored in separate `.json` sidecar files. When you import these files into other photo managers (iCloud, Synology Photos, etc.), all photos appear with the download date instead of the original capture date.

## Solution

This tool matches media files with their corresponding JSON metadata files and injects the metadata back into the media files using **ExifTool**:

- **Date & Time**: Restores `DateTimeOriginal` (images) and `CreateDate`/`TrackCreateDate`/`MediaCreateDate` (videos)
- **GPS Location**: Writes latitude, longitude, and altitude to EXIF GPS tags (images) and QuickTime tags (videos)
- **Descriptions**: Adds image/video descriptions from Google Photos
- **Handles Edge Cases**: Truncated filenames, edited files, duplicates, Live Photos

## Features

- **Smart File Matching**: Handles Google's inconsistent JSON naming conventions
  - `image.jpg` → `image.jpg.json`, `image.json`, `image.jpg.supplemental-metadata.json`
  - Truncated filenames (Google's 46-47 char limit bug)
  - Duplicate files: `image(1).jpg` → `image.jpg(1).json`
  - Edited files: `image-edited.jpg` uses `image.jpg` metadata
  - Live Photos: Pairs `.jpg` + `.mov` files
- **Full Video Support**: Uses ExifTool to write QuickTime metadata tags (not just file timestamps)
- **Multi-threading**: Parallel processing for faster batch operations
- **Error Logging**: Failed files are recorded in `unmatched_files.txt`
- **Preserves Structure**: Maintains your folder organization (or flatten if desired)
- **Progress Tracking**: Shows progress bar and detailed statistics

## Prerequisites

### ExifTool Installation (Required)

This tool requires ExifTool to be installed on your system:

```bash
# macOS
brew install exiftool

# Ubuntu/Debian Linux
sudo apt-get install libimage-exiftool-perl

# Other Linux distributions
# Download from https://exiftool.org/install.html

# Windows
# Download from https://exiftool.org/install.html
# Add to PATH or use --exiftool-path option
```

Verify installation:
```bash
exiftool -ver
```

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/bryannamd/GooglePhotoMetadataFixer.git
cd GooglePhotoMetadataFixer
```

### 2. Set Up Virtual Environment (Recommended)

Using a virtual environment ensures isolated dependencies and avoids conflicts with system Python packages.

**Using `venv` (Python 3.8+):**

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

**Using `conda`:**

```bash
# Create conda environment
conda create -n gpmf python=3.11

# Activate conda environment
conda activate gpmf
```

### 3. Install Dependencies

With the virtual environment activated, install the required packages:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Usage

> **Note:** Ensure your virtual environment is activated before running the tool.
> ```bash
> # On macOS/Linux:
> source .venv/bin/activate
> 
> # On Windows:
> .venv\Scripts\activate
> ```

### Basic Usage

```bash
python -m google_photos_metadata_fixer -i /path/to/takeout -o /path/to/output
```

### All Options

```bash
# Flatten output (all files in one directory)
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --flat

# Dry run (see what would be done without making changes)
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --dry-run

# Skip videos (process only images)
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --skip-videos

# Skip images (process only videos)
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --skip-images

# Use more workers for faster processing (default: 4)
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --workers 8

# Specify custom ExifTool path
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --exiftool-path /usr/local/bin/exiftool

# Custom error log location
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored --error-log errors.txt

# Verbose output
python -m google_photos_metadata_fixer -i ./Takeout -o ./Restored -v
```

## How It Works

1. **Scan**: Recursively scans input directory for media files and JSON sidecars
2. **Match**: Uses multiple strategies to match media files with their JSON files
3. **Extract**: Reads `photoTakenTime`, `geoData`, and `description` from JSON
4. **Inject**: Writes metadata to media files using ExifTool:
   - **Images**: EXIF tags (`DateTimeOriginal`, `CreateDate`, `ModifyDate`, GPS)
   - **Videos**: QuickTime tags (`CreateDate`, `TrackCreateDate`, `MediaCreateDate`, `ModifyDate`, GPS)
5. **Copy**: Copies files to output directory with restored metadata
6. **Log**: Failed files are recorded in error log

## File Matching Logic

The tool tries multiple strategies to find JSON files:

1. Direct match: `image.jpg` → `image.jpg.json`
2. Extension variants: `image.jpg.supplemental-metadata.json`
3. Truncated names: Handles Google's 46-47 character filename limit
4. Bracket swap: `image(1).jpg` → `image.jpg(1).json`
5. Edited files: `image-edited.jpg` → `image.jpg`
6. Live Photos: Pairs `image.jpg` + `image.mov` with single JSON

## Metadata Tags Written

### Images (JPEG, PNG, HEIC, etc.)
- `DateTimeOriginal` - Original capture time
- `CreateDate` - Creation time
- `ModifyDate` - Modification time
- `GPSLatitude` / `GPSLongitude` / `GPSAltitude` - Location
- `ImageDescription` - Description

### Videos (MP4, MOV, etc.)
- `CreateDate` - File creation time
- `TrackCreateDate` - Video track creation time
- `MediaCreateDate` - Media creation time
- `ModifyDate` / `TrackModifyDate` / `MediaModifyDate` - Modification times
- `GPSLatitude` / `GPSLongitude` / `GPSAltitude` - Location
- `Description` / `Comment` - Description

## Error Handling

Files that fail processing are logged to `unmatched_files.txt` (or your specified error log) with the following format:

```
# Files that failed processing
# Total errors: 5
# Format: file_path | error_message

/path/to/failed/image.jpg | ExifTool error: Warning: Bad format (0) for XMP entry 0
/path/to/failed/video.mp4 | Error running ExifTool: [Errno 2] No such file or directory
```

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

## Performance Tips

- Use `--workers` to increase parallel processing (default: 4)
- For thousands of files, higher worker counts (8-16) can significantly speed up processing
- ExifTool is efficient for batch operations and supports parallel processing

## Limitations

- **HEIC**: Requires additional libraries for some operations
- **Permissions**: May need administrator/root for setting file timestamps on some systems
- **ExifTool Required**: Must be installed separately

## Inspired By

This project was inspired by [GooglePhotosTakeoutHelper (GPTH)](https://github.com/TheLastGimbus/GooglePhotosTakeoutHelper) but focuses specifically on metadata restoration rather than file organization.

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
