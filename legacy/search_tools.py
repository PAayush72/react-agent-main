# tools/search_tools.py
import os
import subprocess
import glob as glob_module
from typing import List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class SearchResult:
    matches: List[Tuple[str, int, str]]  # (file_path, line_number, line_content)
    query: str
    total_matches: int

def glob_search(pattern: str, path: str = ".") -> str:
    """
    Search for files matching a glob pattern.
    
    Args:
        pattern: Glob pattern (e.g., "*.py", "**/*.txt")
        path: Directory to search in (default: current directory)
        
    Returns:
        String with matching file paths, one per line
    """
    try:
        # Change to the specified path
        old_cwd = os.getcwd()
        os.chdir(path)
        
        # Use glob with recursive search
        matches = glob_module.glob(pattern, recursive=True)
        
        # Restore original working directory
        os.chdir(old_cwd)
        
        if not matches:
            return f"No files matching pattern '{pattern}' found in {path}"
            
        return "\n".join(sorted(matches))
    except Exception as e:
        return f"Error during glob search: {str(e)}"

def grep_search(
    pattern: str, 
    path: str = ".", 
    include: Optional[str] = None,
    use_ripgrep: bool = True
) -> str:
    """
    Search for content matching a regex pattern.
    
    Args:
        pattern: Regex pattern to search for
        path: Directory to search in (default: current directory)
        include: File pattern to include (e.g., "*.py")
        use_ripgrep: Whether to use ripgrep if available
        
    Returns:
        String with search results in format: file_path:line_number:line_content
    """
    try:
        # Try ripgrep first if available and requested
        if use_ripgrep:
            try:
                result = _ripgrep_search(pattern, path, include)
                if result is not None:
                    return result
            except (FileNotFoundError, subprocess.SubprocessError):
                # Fall back to Python implementation
                pass
        
        # Python fallback implementation
        return _python_grep_search(pattern, path, include)
    except Exception as e:
        return f"Error during grep search: {str(e)}"

def _ripgrep_search(pattern: str, path: str, include: Optional[str]) -> Optional[str]:
    """Search using ripgrep subprocess."""
    cmd = ["rg"]
    
    if include:
        cmd.extend(["-g", include])
    
    cmd.extend([
        "--line-number", 
        "--no-heading", 
        "--color", "never",
        pattern,
        path
    ])
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30
    )
    
    if result.returncode == 0:
        return result.stdout
    elif result.returncode == 1:  # No matches found
        return ""
    else:  # Error
        raise subprocess.SubprocessError(f"ripgrep failed: {result.stderr}")

def _python_grep_search(pattern: str, path: str, include: Optional[str]) -> str:
    """Python implementation of grep search."""
    import re
    
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex pattern: {str(e)}"
    
    matches = []
    
    # Determine files to search
    if include:
        # Use glob to find matching files
        search_pattern = os.path.join(path, "**", include)
        file_paths = glob_module.glob(search_pattern, recursive=True)
    else:
        # Walk directory tree
        file_paths = []
        for root, dirs, files in os.walk(path):
            for file in files:
                file_paths.append(os.path.join(root, file))
    
    # Search each file
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    if regex.search(line):
                        # Remove trailing newline for cleaner output
                        line_content = line.rstrip('\n\r')
                        matches.append(f"{file_path}:{line_num}:{line_content}")
        except (IOError, UnicodeDecodeError):
            # Skip files that can't be read
            continue
    
    if not matches:
        return f"No matches for pattern '{pattern}' found in {path}"
        
    return "\n".join(matches)