# tools/bash_tools.py — Windows-compatible command execution
import subprocess
import os
import platform
from typing import Optional
from dataclasses import dataclass

@dataclass
class BashResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

# Commands that should NEVER be allowed
BLOCKED_COMMANDS = [
    'rm -rf /',
    'rm -rf ~',
    'mkfs',
    ':(){:|:&};:',  # fork bomb
    'dd if=/dev/zero',
    'chmod -R 777 /',
    'format c:',
    'del /f /s /q c:\\',
]

# Commands that require confirmation
DANGEROUS_PATTERNS = [
    'rm -rf',
    'rm -r',
    'sudo',
    'chmod',
    'chown',
    'curl | bash',
    'wget | bash',
    '> /dev/',
    'del /f',
    'rmdir /s',
    'format ',
    'rd /s',
]

IS_WINDOWS = platform.system() == "Windows"


def execute_bash(
    command: str,
    timeout: Optional[int] = 30,
    cwd: Optional[str] = None,
    env: Optional[dict] = None
) -> str:
    """
    Execute a shell command with safety checks.
    Returns the output as a string.
    
    On Windows, uses cmd.exe or PowerShell.
    On Linux/Mac, uses bash.
    """
    # Check blocked commands
    if command is None:
        return "Error: command is None"
    
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return f"Command blocked for safety: contains '{blocked}'"

    # Set up environment
    exec_env = os.environ.copy()
    if env is not None:
        exec_env.update(env)

    work_dir = cwd or os.getcwd()

    # Execute
    try:
        if IS_WINDOWS:
            # On Windows, use cmd.exe
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=work_dir,
                env=exec_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            # On Linux/Mac, use bash with process group
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=work_dir,
                env=exec_env,
                preexec_fn=os.setsid
            )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
            stdout_str = stdout.decode('utf-8', errors='replace').strip()
            stderr_str = stderr.decode('utf-8', errors='replace').strip()
            
            output_parts = []
            if stdout_str:
                output_parts.append(stdout_str)
            if stderr_str:
                output_parts.append(f"STDERR: {stderr_str}")
            output_parts.append(f"Exit code: {process.returncode}")
            
            return "\n".join(output_parts)
            
        except subprocess.TimeoutExpired:
            # Kill the process
            if IS_WINDOWS:
                process.kill()
            else:
                import signal
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            return f"Command timed out after {timeout}s"

    except Exception as e:
        return f"Command execution error: {str(e)}"


def is_dangerous_command(command: str) -> bool:
    """Check if command matches dangerous patterns"""
    return any(p in command for p in DANGEROUS_PATTERNS)	