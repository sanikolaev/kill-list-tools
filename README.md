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

# Example of using the tools

```
# mysql -P9306 -h0 -e "drop table if exists t; create table t(f text); insert into t values(123, 'abc'); flush ramchunk t; replace into t values(123, 'def'); flush table t";

# python3 read_killed_docids.py /opt/homebrew/var/manticore/t/t.0.spm /opt/homebrew/var/manticore/t/t.0.spt > /tmp/ids

# cat /tmp/ids

123

# mysql -P9306 -h0 -e "drop table if exists t2; create table t2(f text); insert into t2 values(123, 'abc'),('345', 'def'); flush ramchunk t2; select * from t2"
+------+------+
| id   | f    |
+------+------+
|  123 | abc  |
|  345 | def  |
+------+------+

# searchd --stop

# python3 mark_killed.py /opt/homebrew/var/manticore/t2/t2.0 /tmp/ids
Reading document IDs from /tmp/ids...
Found 1 document IDs to mark as killed
Reading row ID mapping from /opt/homebrew/var/manticore/t2/t2.0.spt...
Loaded 2 document ID mappings
Marking 1 row IDs as killed...
Writing updated .spm file to /opt/homebrew/var/manticore/t2/t2.0.spm...
Successfully marked 1 documents as killed
Updated file: /opt/homebrew/var/manticore/t2/t2.0.spm

# searchd

# mysql -P9306 -h0 -e "select * from t2"
+------+------+
| id   | f    |
+------+------+
|  345 | def  |
+------+------+
```
