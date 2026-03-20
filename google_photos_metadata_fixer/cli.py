"""
Command-line interface for Google Photos Metadata Fixer.
Uses ExifTool for metadata injection (images and videos).
"""

import sys
import argparse
from pathlib import Path
from typing import List
import shutil
from tqdm import tqdm

from .file_matcher import FileMatcher, MediaFile, load_json_metadata, extract_phototaken_time, extract_gps_data, extract_description
from .exiftool_writer import ExifToolMetadataWriter


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Restore metadata from Google Photos Takeout JSON files into images and videos using ExifTool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i /path/to/takeout -o /path/to/output
  %(prog)s -i ./Takeout -o ./Restored --flat
  %(prog)s -i ./Takeout -o ./Restored --dry-run
  %(prog)s -i ./Takeout -o ./Restored --workers 8
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Input directory containing Google Takeout files'
    )
    
    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output directory for restored files'
    )
    
    parser.add_argument(
        '--flat',
        action='store_true',
        help='Flatten output structure (all files in one directory)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    parser.add_argument(
        '--skip-videos',
        action='store_true',
        help='Skip video files'
    )
    
    parser.add_argument(
        '--skip-images',
        action='store_true',
        help='Skip image files'
    )
    
    parser.add_argument(
        '--exiftool-path',
        default='exiftool',
        help='Path to ExifTool executable (default: exiftool)'
    )
    
    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=4,
        help='Number of parallel workers for processing (default: 4)'
    )
    
    parser.add_argument(
        '--error-log',
        default='unmatched_files.txt',
        help='Path to error log file (default: unmatched_files.txt in output dir)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.1.0'
    )
    
    return parser


def print_summary(matched: List[MediaFile], unmatched: List[MediaFile], verbose: bool = False):
    """Print processing summary."""
    print(f"\n{'='*60}")
    print("SCAN SUMMARY")
    print(f"{'='*60}")
    print(f"Files with metadata:     {len(matched):>6}")
    print(f"Files without metadata:  {len(unmatched):>6}")
    print(f"Total media files:       {len(matched) + len(unmatched):>6}")
    
    if unmatched and verbose:
        print(f"\nUnmatched files:")
        for mf in unmatched[:20]:
            print(f"  - {mf.relative_path}")
        if len(unmatched) > 20:
            print(f"  ... and {len(unmatched) - 20} more")


def main():
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    
    # Validate input
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not input_dir.is_dir():
        print(f"Error: Input is not a directory: {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Check output directory
    if output_dir.exists() and not args.dry_run:
        response = input(f"Output directory exists: {output_dir}\nOverwrite? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)
        shutil.rmtree(output_dir)
    
    print(f"Scanning: {input_dir}")
    print(f"ExifTool: {args.exiftool_path}")
    
    # Scan for files
    try:
        matcher = FileMatcher(input_dir)
        all_files = matcher.scan_media_files()
    except Exception as e:
        print(f"Error scanning files: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Filter by type
    if args.skip_images:
        all_files = [f for f in all_files if f.suffix not in FileMatcher.IMAGE_EXTENSIONS]
    if args.skip_videos:
        all_files = [f for f in all_files if f.suffix not in FileMatcher.VIDEO_EXTENSIONS]
    
    matched = matcher.get_matched_files()
    unmatched = matcher.get_unmatched_files()
    
    print(f"Found {len(all_files)} media files")
    print(f"  - With JSON metadata: {len(matched)}")
    print(f"  - Without JSON: {len(unmatched)}")
    
    if args.dry_run:
        print("\n[DRY RUN] No changes will be made")
        print_summary(matched, unmatched, args.verbose)
        sys.exit(0)
    
    # Prepare files with metadata
    files_with_metadata = []
    for media_file in all_files:
        if media_file.json_path:
            metadata = load_json_metadata(media_file.json_path)
            if metadata:
                timestamp = extract_phototaken_time(metadata)
                gps_data = extract_gps_data(metadata)
                description = extract_description(metadata)
                files_with_metadata.append((media_file, timestamp, gps_data, description))
        else:
            # Files without JSON - still copy them
            files_with_metadata.append((media_file, None, None, None))
    
    # Process files
    print(f"\nProcessing files...")
    print(f"Output: {output_dir}")
    print(f"Workers: {args.workers}")
    
    error_log_path = output_dir / args.error_log
    
    try:
        writer = ExifToolMetadataWriter(
            output_dir,
            preserve_structure=not args.flat,
            exiftool_path=args.exiftool_path,
            error_log_path=error_log_path,
            max_workers=args.workers
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nPlease install ExifTool:", file=sys.stderr)
        print("  macOS: brew install exiftool", file=sys.stderr)
        print("  Linux: sudo apt-get install libimage-exiftool-perl", file=sys.stderr)
        print("  Windows: https://exiftool.org/install.html", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing writer: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Progress callback
    pbar = tqdm(total=len(files_with_metadata), desc="Processing", unit="file")
    
    def progress_callback(filename):
        pbar.set_postfix(file=filename[:30])
        pbar.update(1)
    
    # Process files with multi-threading
    success_count, error_count, error_files = writer.process_files_batch(
        files_with_metadata,
        progress_callback=progress_callback
    )
    
    pbar.close()
    
    # Print results
    print_summary(matched, unmatched, args.verbose)
    print(f"\nProcessing complete:")
    print(f"  Successful: {success_count}")
    print(f"  Errors: {error_count}")
    
    if error_files:
        print(f"\nError log written to: {error_log_path}")
        print(f"  ({len(error_files)} files failed)")
        
        if args.verbose:
            print("\nFailed files:")
            for path, msg in error_files[:10]:
                print(f"  - {path}: {msg}")
            if len(error_files) > 10:
                print(f"  ... and {len(error_files) - 10} more")


if __name__ == '__main__':
    main()
