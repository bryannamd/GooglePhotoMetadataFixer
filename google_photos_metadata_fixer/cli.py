"""
Command-line interface for Google Photos Metadata Fixer.
"""

import sys
import argparse
from pathlib import Path
from typing import List
import shutil
from tqdm import tqdm

from .file_matcher import FileMatcher, MediaFile
from .metadata_writer import MetadataWriter


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Restore metadata from Google Photos Takeout JSON files into images and videos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i /path/to/takeout -o /path/to/output
  %(prog)s -i ./Takeout -o ./Restored --flat
  %(prog)s -i ./Takeout -o ./Restored --dry-run
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
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )
    
    return parser


def print_summary(matched: List[MediaFile], unmatched: List[MediaFile], verbose: bool = False):
    """Print processing summary."""
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Files with metadata:     {len(matched):>6}")
    print(f"Files without metadata:  {len(unmatched):>6}")
    print(f"Total media files:       {len(matched) + len(unmatched):>6}")
    
    if unmatched and verbose:
        print(f"\nUnmatched files:")
        for mf in unmatched[:20]:  # Show first 20
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
    
    # Scan for files
    matcher = FileMatcher(input_dir)
    all_files = matcher.scan_media_files()
    
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
    
    # Process files
    print(f"\nProcessing files...")
    print(f"Output: {output_dir}")
    
    try:
        writer = MetadataWriter(output_dir, preserve_structure=not args.flat)
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    success_count = 0
    error_count = 0
    
    with tqdm(total=len(all_files), desc="Processing", unit="file") as pbar:
        for media_file in all_files:
            pbar.set_postfix(file=media_file.path.name[:30])
            
            if media_file.suffix in FileMatcher.IMAGE_EXTENSIONS:
                success, message = writer.process_image(media_file)
            else:
                success, message = writer.process_video(media_file)
            
            if success:
                success_count += 1
            else:
                error_count += 1
                if args.verbose:
                    tqdm.write(f"Error: {media_file.relative_path} - {message}")
            
            pbar.update(1)
    
    print_summary(matched, unmatched, args.verbose)
    print(f"\nProcessing complete:")
    print(f"  Successful: {success_count}")
    print(f"  Errors: {error_count}")


if __name__ == '__main__':
    main()
