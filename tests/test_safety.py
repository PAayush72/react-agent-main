# tests/test_safety.py — Bash command safety and sandbox path validation tests

import os
import sys
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCommandSafety:
    """Test bash command allowlist and injection prevention."""

    def setup_method(self):
        from mcp_server import is_command_safe
        self.check = is_command_safe

    # ── Allowed commands ──

    def test_simple_ls(self):
        safe, _ = self.check("ls")
        assert safe

    def test_ls_with_args(self):
        safe, _ = self.check("ls -la")
        assert safe

    def test_python_script(self):
        safe, _ = self.check("python script.py")
        assert safe

    def test_git_status(self):
        safe, _ = self.check("git status")
        assert safe

    def test_cat_file(self):
        safe, _ = self.check("cat README.md")
        assert safe

    def test_grep_pattern(self):
        safe, _ = self.check("grep -r TODO .")
        assert safe

    def test_mkdir(self):
        safe, _ = self.check("mkdir new_dir")
        assert safe

    def test_echo(self):
        safe, _ = self.check("echo hello")
        assert safe

    # ── Blocked commands ──

    def test_empty_command(self):
        safe, reason = self.check("")
        assert not safe
        assert "Empty" in reason

    def test_unknown_command(self):
        safe, reason = self.check("malware --install")
        assert not safe
        assert "not in the allowed list" in reason

    def test_recursive_rm(self):
        safe, reason = self.check("rm -rf /")
        assert not safe

    def test_rm_glob(self):
        safe, reason = self.check("rm *.py")
        assert not safe

    def test_sudo(self):
        safe, reason = self.check("sudo rm file")
        assert not safe

    # ── Command injection prevention ──

    def test_semicolon_injection(self):
        safe, reason = self.check("echo hello; rm -rf /")
        assert not safe
        assert "metacharacter" in reason.lower() or "not allowed" in reason.lower()

    def test_and_chain(self):
        safe, reason = self.check("echo hello && rm -rf /")
        assert not safe

    def test_or_chain(self):
        safe, reason = self.check("echo hello || rm -rf /")
        assert not safe

    def test_pipe(self):
        safe, reason = self.check("cat file | bash")
        assert not safe

    def test_backtick_injection(self):
        safe, reason = self.check("echo `rm -rf /`")
        assert not safe

    def test_dollar_paren_injection(self):
        safe, reason = self.check("echo $(rm -rf /)")
        assert not safe

    def test_redirect_output(self):
        safe, reason = self.check("echo pwned > /etc/passwd")
        assert not safe

    def test_redirect_input(self):
        safe, reason = self.check("bash < evil_script.sh")
        assert not safe


class TestSandboxPath:
    """Test that safe_path blocks access outside the sandbox."""

    def setup_method(self):
        from mcp_server import safe_path, BASE_DIR
        self.safe_path = safe_path
        self.base_dir = BASE_DIR

    def test_relative_path(self):
        result = self.safe_path("README.md")
        assert result.startswith(self.base_dir)

    def test_subdirectory(self):
        result = self.safe_path("core/agent.py")
        assert result.startswith(self.base_dir)

    def test_dot_path(self):
        result = self.safe_path(".")
        assert result == self.base_dir

    def test_parent_traversal_blocked(self):
        with pytest.raises(ValueError, match="outside sandbox"):
            self.safe_path("../../etc/passwd")

    def test_absolute_path_outside_blocked(self):
        if sys.platform == "win32":
            with pytest.raises(ValueError, match="outside sandbox"):
                self.safe_path("C:\\Windows\\System32\\cmd.exe")
        else:
            with pytest.raises(ValueError, match="outside sandbox"):
                self.safe_path("/etc/passwd")

    def test_double_dot_sneaky(self):
        with pytest.raises(ValueError, match="outside sandbox"):
            self.safe_path("subdir/../../..")


class TestCommandSafetyEdgeCases:
    """Edge cases for command safety."""

    def setup_method(self):
        from mcp_server import is_command_safe
        self.check = is_command_safe

    def test_whitespace_only(self):
        safe, _ = self.check("   ")
        assert not safe

    def test_command_with_path(self):
        safe, _ = self.check("/usr/bin/python script.py")
        assert safe  # basename "python" is allowed

    def test_windows_exe(self):
        safe, _ = self.check("python.exe script.py")
        assert safe  # strips .exe

    def test_shutdown_blocked(self):
        safe, _ = self.check("shutdown -h now")
        assert not safe

    def test_reboot_blocked(self):
        safe, _ = self.check("reboot")
        assert not safe
