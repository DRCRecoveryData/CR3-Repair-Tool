#!/usr/bin/env python3
"""
CR3 File Fixer / Carver Utility (Batch Mode)

This script accurately determines the size of Canon CR3 (or other BMFF) files
by parsing their ISO Base Media File Format (BMFF) atoms and saves the
correctly sized file. It now processes all files found in an input directory.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import io

MB = 1024 * 1024

# --- Core Logic for Atom Parsing ---

def CR3_atoms(file, endianess="big"):
    """
    Generator that scans a binary file stream for CR3 atoms (boxes)
    and yields their starting position, name (tag), and total size (header + data).
    This logic walks the file structure based on reported atom sizes.
    """
    assert file.seekable()

    while True:
        pos = file.tell()

        # 1. Read Atom Size (4 bytes)
        size_bytes = file.read(4)
        if len(size_bytes) < 4:  # End of file or incomplete read
            break

        # 2. Read Atom Name (4 bytes)
        name = file.read(4)
        if len(name) < 4:
            break

        # Decode size
        size = int.from_bytes(size_bytes, endianess)

        # 3. Handle 64-bit size extension (size == 1)
        if size == 1:
            # The actual size is in the next 8 bytes
            size_ext_bytes = file.read(8)
            if len(size_ext_bytes) < 8:
                 break
            size = int.from_bytes(size_ext_bytes, endianess)
        
        if size <= 0:
             # Invalid or empty size reported, stop parsing
             break

        yield (pos, name, size)

        # 4. Jump to the next atom: seek to (current_pos + total_size)
        file.seek(pos + size)


# --- Size Calculation Function ---

def CR3_size(file_handle, last_chunk_name=b'mdat', endianess="big", log=None):
    """
    Calculates the total size of the CR3 file by summing atom sizes
    until the termination condition is met (defaulting to the 'mdat' atom).

    Args:
        file_handle (file object): An open file object positioned at the start of the CR3 file.
        last_chunk_name (bytes): The name of the final atom to include (e.g., b'mdat').
        endianess (str): Endianness for reading size fields.
        log (logger): Logging object for output messages.

    Returns:
        int: The total calculated size of the file in bytes, or 0 if invalid structure.
    """
    total_size = 0
    
    # Store initial position in case we need to rewind
    initial_pos = file_handle.tell()

    # Iterate through atoms starting from the current file position
    for index, (offset, name, size) in enumerate(CR3_atoms(file_handle, endianess)):
        
        # Rule 1: Must start with the ftyp atom
        if index == 0 and name != b'ftyp':
            if log:
                log.error(f"Invalid start atom: {name.decode('utf-8', 'ignore')}. Expected b'ftyp'")
            file_handle.seek(initial_pos) # Rewind on failure
            return 0

        total_size += size

        if log:
            log.debug(f"Atom index={index}, name={name.decode('utf-8', 'ignore')}, size={size:,d}")

        # Rule 2: Termination condition (e.g., reaching 'mdat')
        if name == last_chunk_name:
            if log:
                log.info(f"Termination atom '{name.decode('utf-8', 'ignore')}' reached. Logical size found: {total_size:,d} B")
            file_handle.seek(initial_pos) # Rewind before returning
            return total_size

    if log:
        log.warning(f"File ended before reaching termination atom '{last_chunk_name.decode('utf-8', 'ignore')}'. Returning 0.")
    file_handle.seek(initial_pos) # Rewind before returning
    return 0


# --- Application Class ---

class Application:
    """Handles the file processing, size calculation, and saving in batch mode."""
    def __init__(self, args, log):
        self.args = args
        self.log = log
        # Use directories instead of single files
        self.input_dir = args.input_dir
        self.output_dir = args.output_dir
        self.last_chunk_name = args.lastchunk

    def run(self):
        """Executes the file fixing process on all files in the input directory."""
        self.log.info(f"Analyzing files in input directory: {self.input_dir}")

        processed_count = 0
        
        # Iterate over all items in the input directory
        for input_path in self.input_dir.iterdir():
            # Skip non-files (directories, symlinks, etc.)
            if not input_path.is_file():
                self.log.debug(f"Skipping non-file object: {input_path.name}")
                continue

            # Define the output path for the current file
            output_path = self.output_dir / input_path.name

            # Check if output already exists (to prevent overwriting)
            if output_path.exists():
                self.log.warning(f"Output file already exists: {output_path.name}. Skipping.")
                continue

            self.log.info(f"\n--- Processing {input_path.name} ---")
            
            try:
                with input_path.open('rb') as infile:
                    start_offset = 0
                    infile.seek(start_offset)
                    
                    # 1. Calculate the correct file size
                    size = CR3_size(infile, 
                                    last_chunk_name=self.last_chunk_name, 
                                    log=self.log)

                    if size > 0:
                        # 2. Restore/save the file
                        # Pass the specific output path to restore
                        self.restore(infile, output_path, start_offset, size)
                        processed_count += 1
                    else:
                        self.log.error(f"Failed to determine a valid CR3 structure and size for {input_path.name}. File not saved.")

            except FileNotFoundError:
                # Should not happen if iterdir worked, but good safeguard
                self.log.critical(f"Input file not found (unexpected): {input_path.name}")
            except Exception as e:
                self.log.critical(f"An unexpected error occurred during processing {input_path.name}: {e}", exc_info=self.args.verbose)
        
        self.log.info(f"\n--- Batch Processing Complete. {processed_count} files successfully saved. ---")

    def restore(self, infile, output_path, offset, size):
        """Reads 'size' bytes starting from 'offset' and writes to the output file."""
        path = output_path
        
        if path.exists():
            # Already checked in run(), but kept for internal robustness
            self.log.warning(f"{path.name} already exists: skipping save attempt.")
            return

        infile.seek(offset)
        bufsize = 8 * MB
        self.log.info(f"Saving {path.name}, calculated size {size:,d} B")

        # Use a temporary file first for robust (atomic) write
        tmp = Path(str(path) + ".tmp")
        try:
            with tmp.open('wb') as out:
                bytes_remaining = size
                while bytes_remaining > 0:
                    k = min(bufsize, bytes_remaining)
                    buf = infile.read(k)
                    
                    if not buf:
                        self.log.error(f"Premature EOF encountered while reading {size:,d} B for {path.name}")
                        break
                    
                    out.write(buf)
                    bytes_remaining -= len(buf)

            if bytes_remaining == 0:
                # Rename temp file to final path on successful write
                tmp.rename(path)
                self.log.info(f"[SUCCESS] File successfully fixed and saved to {path.name}")
            else:
                self.log.error(f"[ERROR] Incomplete save for {path.name}. Saved only {size - bytes_remaining:,d} bytes.")
                if tmp.exists():
                    os.remove(tmp) # Clean up failed temp file

        except Exception as e:
            self.log.critical(f"Error restoring file {path.name}: {e}")
            if tmp.exists():
                os.remove(tmp) # Clean up failed temp file


# --- CLI and Setup ---

def parse_args():
    """Parses command line arguments."""
    p = argparse.ArgumentParser(description="Fixes Canon CR3 files in batch mode by calculating their true size via atom parsing and carving the correct data.")

    p.add_argument('--input-dir',
                    type=Path,
                    required=True,
                    help="Path to the input directory containing files to be fixed.",
                    metavar="INPUT_DIR")
    p.add_argument('--output-dir',
                    type=Path,
                    required=True,
                    help="Path to the output directory where fixed files will be saved.",
                    metavar="OUTPUT_DIR")
    p.add_argument('-v', '--verbose',
                    action="store_true",
                    default=False,
                    help="Enable verbose (DEBUG) logging.")
    p.add_argument('--lastchunk',
                    type=str,
                    default='mdat',
                    metavar="NAME",
                    help="Name of the last chunk to include (e.g., 'mdat' for full file). [default '%(default)s']")

    args = p.parse_args()
    
    # Encode lastchunk name to bytes for comparison
    args.lastchunk = bytes(args.lastchunk, encoding='utf-8')
    if not args.lastchunk:
        p.error("--lastchunk must not be empty")

    # Validate input directory
    if not args.input_dir.exists() or not args.input_dir.is_dir():
        p.error(f"Input path must be an existing directory: {args.input_dir}")

    # Create output directory if it doesn't exist
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        p.error(f"Could not create output directory {args.output_dir}: {e}")
            
    return args


def setup_logger(verbose=False):
    """Sets up the global logger."""
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    log.addHandler(ch)
    return log


if __name__ == '__main__':
    # Parse arguments early to get verbosity settings
    try:
        args = parse_args()
    except Exception as e:
        # Handle argparse errors gracefully outside of the main logger setup
        sys.exit(f"Error: {e}")
    
    # Setup logger based on arguments
    log = setup_logger(args.verbose)

    # Execute the application
    log.info("--- CR3 File Fixer Initialized (Batch Mode) ---")
    app = Application(args, log)
    app.run()
    log.info("--- CR3 File Fixer Complete ---")
