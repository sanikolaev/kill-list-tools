#!/usr/bin/env python3
"""
Read .spm and .spt files to output document IDs of killed documents.

Usage:
    python3 read_killed_docids.py <path_to_spm_file> <path_to_spt_file>
"""

import sys
import struct
from typing import Dict, List

# Constants
INVALID_ROWID = 0xFFFFFFFF
DOCS_PER_CHECKPOINT = 64


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


def read_uint32_le(data: bytes, offset: int) -> int:
    """Read a little-endian 32-bit unsigned integer."""
    return struct.unpack('<I', data[offset:offset+4])[0]


def read_uint64_le(data: bytes, offset: int) -> int:
    """Read a little-endian 64-bit unsigned integer."""
    return struct.unpack('<Q', data[offset:offset+8])[0]


def read_spm_file(spm_path: str) -> List[int]:
    """
    Read .spm file and return list of killed row IDs.
    .spm file is a bitmap: array of DWORDs, where bit (rowID & 31) in DWORD (rowID >> 5) represents rowID.
    """
    with open(spm_path, 'rb') as f:
        data = f.read()
    
    killed_row_ids = []
    num_dwords = len(data) // 4
    
    for dword_idx in range(num_dwords):
        dword = read_uint32_le(data, dword_idx * 4)
        if dword == 0:
            continue  # No killed rows in this DWORD
        
        # Check each bit in this DWORD
        for bit_pos in range(32):
            if dword & (1 << bit_pos):
                row_id = (dword_idx * 32) + bit_pos
                killed_row_ids.append(row_id)
    
    return killed_row_ids


def read_spt_file(spt_path: str) -> Dict[int, int]:
    """
    Read .spt file and build a mapping from row_id -> doc_id.
    
    File format:
    - Header: num_of_docs (4 bytes), docs_per_checkpoint (4 bytes), max_doc_id (8 bytes)
    - Checkpoints array: Each checkpoint has base_doc_id (8 bytes) and block_offset (8 bytes)
    - Blocks: Each block starts with base_row_id (4 bytes), then lookup pairs
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
    
    # Build row_id -> doc_id mapping by reading all blocks
    rowid_to_docid = {}
    
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
        
        # First entry: doc_id is base_doc_id, row_id is stored directly (no docid delta)
        if block_pos + 4 > len(data):
            break
        first_row_id = read_uint32_le(data, block_pos)
        block_pos += 4
        
        if first_row_id != INVALID_ROWID:
            rowid_to_docid[first_row_id] = base_doc_id
        
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
            rowid_to_docid[row_id] = current_doc_id
    
    return rowid_to_docid


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 read_killed_docids.py <path_to_spm_file> <path_to_spt_file>", file=sys.stderr)
        sys.exit(1)
    
    spm_path = sys.argv[1]
    spt_path = sys.argv[2]
    
    try:
        # Read killed row IDs from .spm file
        killed_row_ids = read_spm_file(spm_path)
        
        # Read row_id -> doc_id mapping from .spt file
        rowid_to_docid = read_spt_file(spt_path)
        
        # Output document IDs for killed rows (only to stdout, no other text)
        killed_doc_ids = []
        for row_id in killed_row_ids:
            if row_id in rowid_to_docid:
                killed_doc_ids.append(rowid_to_docid[row_id])
        
        # Sort and output only document IDs
        killed_doc_ids.sort()
        for doc_id in killed_doc_ids:
            print(doc_id)
        
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

