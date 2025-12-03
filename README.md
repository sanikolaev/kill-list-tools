# SPM Reader Tools

Tools for reading and modifying `.spm` (dead row map) and `.spt` (docid lookup table) files.

## Tools

### 1. `read_killed_docids.py` - Read killed document IDs

Reads `.spm` and `.spt` files to output the document IDs of killed/deleted documents.

**Usage:**
```bash
python3 read_killed_docids.py <path_to_spm_file> <path_to_spt_file>
```

**Example:**
```bash
python3 read_killed_docids.py /var/lib/manticore/index/index.0.spm /var/lib/manticore/index/index.0.spt
```

**Output:** One document ID per line (sorted) to stdout. Progress information and warnings are written to stderr.

### 2. `mark_killed.py` - Mark document IDs as killed

Marks document IDs as killed by updating the `.spm` file.

**Usage:**
```bash
python3 mark_killed.py <table_path> <docids_file>
```

**Example:**
```bash
python3 mark_killed.py /opt/homebrew/var/manticore/t/t.0 /path/to/docids.txt
```

**Input format:** The `docids_file` should contain one document ID per line (plain text). Empty lines and lines starting with `#` are ignored.

**Note:** This script modifies the `.spm` file in place. Make sure you have write permissions and consider backing up the file first.

## File Formats

- **`.spm` file**: Bitmap of killed documents. Each bit represents whether a row ID is killed (1) or alive (0). Array of DWORDs (32-bit unsigned integers).
- **`.spt` file**: Lookup table mapping document IDs to row IDs. Contains checkpoints and blocks for efficient lookup.

## Requirements

- Python 3.6 or later
- No external dependencies (uses only standard library)

## Warning

⚠️ **Modifying `.spm` files directly can corrupt your index if done incorrectly.** Always:
- Back up your index files before modifying them
- Ensure the Manticore Search daemon is not running or the table is locked
- Test on a non-production index first

