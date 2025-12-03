#!/usr/bin/env python3
"""
Mark document IDs as killed by updating the .spm file.

Note: Only the .spm file is modified. The .spt file is read-only and doesn't
track killed status - it's only used to map document IDs to row IDs.

Usage:
    python3 mark_killed.py <table_path> <docids_file>

Example:
    python3 mark_killed.py /opt/homebrew/var/manticore/t/t.0 /path/to/docids.txt
"""

import sys
import struct
import os
from typing import Dict, Set

# Import functions from read_killed_docids.py
# We'll duplicate the necessary functions here for standalone use
INVALID_ROWID = 0xFFFFFFFF
DOCS_PER_CHECKPOINT = 64


def read_uint32_le(data: bytes, offset: int) -> int:
    """Read a little-endian 32-bit unsigned integer."""
    return struct.unpack('<I', data[offset:offset+4])[0]


def read_uint64_le(data: bytes, offset: int) -> int:
    """Read a little-endian 64-bit unsigned integer."""
    return struct.unpack('<Q', data[offset:offset+8])[0]


def unzip_offset_be(data: bytes, offset: int) -> tuple[int, int]:
    """
    Decode a variable-length big-endian encoded integer.
    Returns (value, bytes_consumed)
    """
    pos = offset
    res = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        res = (res << 7) | (b & 0x7f)
        if not (b & 0x80):
            break
    return res, pos - offset


def read_spt_file(spt_path: str) -> Dict[int, int]:
    """
    Read .spt file and build a mapping from doc_id -> row_id.
    Returns dict mapping document ID to row ID.
    """
    with open(spt_path, 'rb') as f:
        data = f.read()
    
    if len(data) < 16:
        raise ValueError(f"File too short: {len(data)} bytes")
    
    pos = 0
    
    # Read header
    num_docs = read_uint32_le(data, pos)
    pos += 4
    docs_per_checkpoint = read_uint32_le(data, pos)
    pos += 4
    max_doc_id = read_uint64_le(data, pos)
    pos += 8
    
    num_checkpoints = (num_docs + docs_per_checkpoint - 1) // docs_per_checkpoint
    
    # Read checkpoints
    checkpoints = []
    for i in range(num_checkpoints):
        if pos + 16 > len(data):
            break
        base_doc_id = read_uint64_le(data, pos)
        pos += 8
        block_offset = read_uint64_le(data, pos)
        pos += 8
        checkpoints.append((base_doc_id, block_offset))
    
    # Build doc_id -> row_id mapping by reading all blocks
    docid_to_rowid = {}
    
    for checkpoint_idx, (base_doc_id, block_offset) in enumerate(checkpoints):
        if block_offset >= len(data):
            continue
        
        block_pos = int(block_offset)
        
        # Determine number of docs in this checkpoint
        if checkpoint_idx == len(checkpoints) - 1:
            # Last checkpoint may be incomplete
            leftover = num_docs % docs_per_checkpoint
            docs_in_checkpoint = leftover if leftover else docs_per_checkpoint
        else:
            docs_in_checkpoint = docs_per_checkpoint
        
        # First entry: doc_id is base_doc_id, row_id is stored directly
        if block_pos + 4 > len(data):
            break
        first_row_id = read_uint32_le(data, block_pos)
        block_pos += 4
        
        if first_row_id != INVALID_ROWID:
            docid_to_rowid[base_doc_id] = first_row_id
        
        current_doc_id = base_doc_id
        
        # Read remaining entries in this checkpoint
        for i in range(1, docs_in_checkpoint):
            if block_pos >= len(data):
                break
            
            # Read delta-encoded doc_id
            delta_doc_id, delta_bytes = unzip_offset_be(data, block_pos)
            block_pos += delta_bytes
            
            if block_pos + 4 > len(data):
                break
            
            # Read row_id
            row_id = read_uint32_le(data, block_pos)
            block_pos += 4
            
            if row_id == INVALID_ROWID:
                break
            
            current_doc_id += delta_doc_id
            docid_to_rowid[current_doc_id] = row_id
    
    return docid_to_rowid


def read_spm_file(spm_path: str) -> bytes:
    """Read .spm file and return its contents as bytes."""
    with open(spm_path, 'rb') as f:
        return f.read()


def write_spm_file(spm_path: str, data: bytes) -> None:
    """Write .spm file."""
    with open(spm_path, 'wb') as f:
        f.write(data)


def set_bit_in_spm(spm_data: bytes, row_id: int) -> bytes:
    """
    Set a bit in the .spm bitmap for the given row_id.
    Returns new bytes with the bit set.
    """
    # Convert to bytearray for mutability
    spm_array = bytearray(spm_data)
    
    # Calculate which DWORD and which bit
    dword_idx = row_id >> 5  # row_id // 32
    bit_pos = row_id & 31    # row_id % 32
    
    # Calculate byte offset for this DWORD
    byte_offset = dword_idx * 4
    
    if byte_offset + 4 > len(spm_array):
        # Need to extend the file
        needed_dwords = dword_idx + 1
        needed_bytes = needed_dwords * 4
        if len(spm_array) < needed_bytes:
            spm_array.extend(b'\x00' * (needed_bytes - len(spm_array)))
    
    # Read the DWORD
    dword = read_uint32_le(bytes(spm_array), byte_offset)
    
    # Set the bit
    dword |= (1 << bit_pos)
    
    # Write the DWORD back
    struct.pack_into('<I', spm_array, byte_offset, dword)
    
    return bytes(spm_array)


def read_docids_file(docids_path: str) -> Set[int]:
    """Read document IDs from a text file (one per line)."""
    docids = set()
    with open(docids_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    docid = int(line)
                    docids.add(docid)
                except ValueError:
                    print(f"Warning: Skipping invalid line: {line}", file=sys.stderr)
    return docids


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 mark_killed.py <table_path> <docids_file>", file=sys.stderr)
        print("", file=sys.stderr)
        print("Example:", file=sys.stderr)
        print("  python3 mark_killed.py /opt/homebrew/var/manticore/t/t.0 /path/to/docids.txt", file=sys.stderr)
        sys.exit(1)
    
    table_path = sys.argv[1]
    docids_path = sys.argv[2]
    
    # Construct file paths
    spt_path = f"{table_path}.spt"
    spm_path = f"{table_path}.spm"
    
    # Check if files exist
    if not os.path.exists(spt_path):
        print(f"Error: .spt file not found: {spt_path}", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.exists(spm_path):
        print(f"Error: .spm file not found: {spm_path}", file=sys.stderr)
        print("Note: The .spm file should exist. If it doesn't, the table may need to be created first.", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.exists(docids_path):
        print(f"Error: Document IDs file not found: {docids_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Read document IDs to kill
        print(f"Reading document IDs from {docids_path}...", file=sys.stderr)
        docids_to_kill = read_docids_file(docids_path)
        print(f"Found {len(docids_to_kill)} document IDs to mark as killed", file=sys.stderr)
        
        if not docids_to_kill:
            print("No document IDs to process.", file=sys.stderr)
            return
        
        # Read .spt file to build doc_id -> row_id mapping
        print(f"Reading row ID mapping from {spt_path}...", file=sys.stderr)
        docid_to_rowid = read_spt_file(spt_path)
        print(f"Loaded {len(docid_to_rowid)} document ID mappings", file=sys.stderr)
        
        # Find row IDs for the document IDs we want to kill
        row_ids_to_kill = []
        not_found = []
        
        for docid in docids_to_kill:
            if docid in docid_to_rowid:
                row_ids_to_kill.append(docid_to_rowid[docid])
            else:
                not_found.append(docid)
        
        if not_found:
            print(f"Warning: {len(not_found)} document IDs not found in lookup table:", file=sys.stderr)
            for docid in sorted(not_found)[:10]:  # Show first 10
                print(f"  {docid}", file=sys.stderr)
            if len(not_found) > 10:
                print(f"  ... and {len(not_found) - 10} more", file=sys.stderr)
        
        if not row_ids_to_kill:
            print("No valid row IDs to mark as killed.", file=sys.stderr)
            return
        
        print(f"Marking {len(row_ids_to_kill)} row IDs as killed...", file=sys.stderr)
        
        # Read existing .spm file
        spm_data = read_spm_file(spm_path)
        
        # Update .spm file for each row ID
        for row_id in row_ids_to_kill:
            spm_data = set_bit_in_spm(spm_data, row_id)
        
        # Write updated .spm file
        print(f"Writing updated .spm file to {spm_path}...", file=sys.stderr)
        write_spm_file(spm_path, spm_data)
        
        print(f"Successfully marked {len(row_ids_to_kill)} documents as killed", file=sys.stderr)
        print(f"Updated file: {spm_path}", file=sys.stderr)
        
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"Error: Permission denied: {e}", file=sys.stderr)
        print("Make sure you have write permission to the .spm file", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

