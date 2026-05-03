# tools/file_tools.py — File operations with line-numbered output
import os
import re
from typing import Tuple, Optional, List
from dataclasses import dataclass


def list_files(path: str = ".") -> str:
    """List files and directories in a path with indicators."""
    try:
        if not os.path.exists(path):
            return f"Error: Path '{path}' does not exist"
        
        items = []
        for item in sorted(os.listdir(path)):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                items.append(f"📁 {item}/")
            else:
                size = os.path.getsize(full_path)
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size // (1024*1024)}MB"
                items.append(f"📄 {item} ({size_str})")
        
        if not items:
            return f"Directory '{path}' is empty"
        
        return "\n".join(items)
    except Exception as e:
        return f"Error listing files: {str(e)}"


def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Read contents of a file with line numbers."""
    try:
        if not os.path.exists(path):
            return f"Error: File '{path}' does not exist"
        
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)

        # Apply line range if specified
        if start_line is not None or end_line is not None:
            start_idx = (start_line - 1) if start_line is not None else 0
            end_idx = end_line if end_line is not None else total_lines
            start_idx = max(0, start_idx)
            end_idx = min(total_lines, end_idx)
            display_lines = lines[start_idx:end_idx]
            line_offset = start_idx
        else:
            display_lines = lines
            line_offset = 0

        # Add line numbers
        numbered = []
        for i, line in enumerate(display_lines):
            line_num = line_offset + i + 1
            numbered.append(f"{line_num:4d} | {line.rstrip()}")

        header = f"File: {path} ({total_lines} lines)"
        if start_line or end_line:
            header += f" [showing lines {line_offset+1}-{line_offset+len(display_lines)}]"

        return header + "\n" + "\n".join(numbered)
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(path: str, content: str) -> str:
    """Write content to a file, creating directories if needed."""
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        # Check if file exists for reporting
        existed = os.path.exists(path)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        lines = content.count('\n') + 1
        action = "Updated" if existed else "Created"
        return f"✓ {action} {path} ({lines} lines)"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def patch_file(path: str, search: str, replace: str) -> str:
    """
    Apply a search/replace patch to a file.
    More surgical than full rewrites.
    """
    try:
        if not os.path.exists(path):
            return f"Error: File '{path}' does not exist"
        
        with open(path, 'r', encoding='utf-8') as f:
            original = f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

    # Check if search text exists
    if search not in original:
        # Try with normalized whitespace
        normalized_search = re.sub(r'\s+', ' ', search.strip())
        normalized_original = re.sub(r'\s+', ' ', original.strip())

        if normalized_search not in normalized_original:
            return (
                f"Error: Search text not found in {path}. "
                f"Make sure you're using the exact text from the file."
            )
        else:
            return (
                f"Error: Search text not found (exact match). "
                f"There may be whitespace differences. Read the file first to get exact content."
            )

    # Count occurrences
    count = original.count(search)
    if count > 1:
        return (
            f"Error: Search text found {count} times in {path}. "
            f"Please provide more context to make it unique."
        )

    # Apply patch
    new_content = original.replace(search, replace, 1)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return f"✓ Patched {path} (replaced {len(search)} chars with {len(replace)} chars)"


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for fuzzy matching"""
    return re.sub(r'\s+', ' ', text.strip())