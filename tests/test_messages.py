# tests/test_messages.py — Tests for message format builders and response parsing

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSAPMessageBuilder:
    """Test build_messages_sap produces correct Bedrock format."""

    def setup_method(self):
        from llm_model import build_messages_sap
        self.build = build_messages_sap

    def test_simple_user_message(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        result = self.build(messages)
        # System messages should be filtered out
        assert all(m["role"] != "system" for m in result)
        # Should have at least one user message
        assert any(m["role"] == "user" for m in result)

    def test_alternating_roles(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi", "tool_calls": []},
            {"role": "user", "content": "How are you?"},
        ]
        result = self.build(messages)
        # Verify alternating roles
        for i in range(1, len(result)):
            assert result[i]["role"] != result[i-1]["role"], \
                f"Consecutive same roles at index {i-1} and {i}: {result[i-1]['role']}"

    def test_tool_result_becomes_user(self):
        messages = [
            {"role": "user", "content": "Read file"},
            {"role": "assistant", "content": "OK", "tool_calls": [
                {"id": "tc1", "name": "read_file", "parameters": {"path": "x.py"}}
            ]},
            {"role": "tool_result", "results": [
                {"tool_use_id": "tc1", "content": "file contents here"}
            ]},
        ]
        result = self.build(messages)
        # tool_result should be converted to a user message
        has_tool_result_as_user = False
        for msg in result:
            if msg["role"] == "user":
                for block in msg.get("content", []):
                    if isinstance(block, dict) and "toolResult" in block:
                        has_tool_result_as_user = True
        assert has_tool_result_as_user

    def test_first_message_is_user(self):
        messages = [
            {"role": "assistant", "content": "I started first", "tool_calls": []},
        ]
        result = self.build(messages)
        assert result[0]["role"] == "user"

    def test_empty_assistant_content(self):
        messages = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc1", "name": "bash", "parameters": {"command": "ls"}}
            ]},
        ]
        result = self.build(messages)
        # Should not crash, assistant message should have content blocks
        assistant_msgs = [m for m in result if m["role"] == "assistant"]
        assert len(assistant_msgs) > 0
        assert len(assistant_msgs[0]["content"]) > 0


class TestNVIDIAMessageBuilder:
    """Test build_messages_nvidia produces correct OpenAI format."""

    def setup_method(self):
        from llm_model import build_messages_nvidia
        self.build = build_messages_nvidia

    def test_includes_system_prompt(self):
        messages = [
            {"role": "system", "content": "You are an agent."},
            {"role": "user", "content": "Hello"},
        ]
        result = self.build(messages)
        assert result[0]["role"] == "system"
        # System prompt should contain agent's prompt
        assert "agent" in result[0]["content"].lower()

    def test_system_not_duplicated(self):
        messages = [
            {"role": "system", "content": "You are an agent."},
            {"role": "user", "content": "Hello"},
        ]
        result = self.build(messages)
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1  # Only one system message

    def test_tool_calls_formatted(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "I'll read that", "tool_calls": [
                {"id": "tc1", "name": "read_file", "parameters": {"path": "x.py"}}
            ]},
        ]
        result = self.build(messages)
        assistant_msgs = [m for m in result if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert "tool_calls" in assistant_msgs[0]
        tc = assistant_msgs[0]["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "read_file"
        # arguments should be JSON string
        args = json.loads(tc["function"]["arguments"])
        assert args["path"] == "x.py"

    def test_tool_result_formatted(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc1", "name": "bash", "parameters": {"command": "ls"}}
            ]},
            {"role": "tool_result", "results": [
                {"tool_use_id": "tc1", "content": "file1.py\nfile2.py"}
            ]},
        ]
        result = self.build(messages)
        tool_msgs = [m for m in result if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "tc1"
        assert "file1.py" in tool_msgs[0]["content"]


class TestToolCallParsing:
    """Test tool call extraction from text (fallback parsing)."""

    def setup_method(self):
        from llm_model import _extract_tool_call_from_text
        self.extract = _extract_tool_call_from_text

    def test_valid_call_tool(self):
        text = 'I will read the file.\nCALL_TOOL: {"name": "read_file", "arguments": {"path": "main.py"}}'
        tc = self.extract(text)
        assert tc is not None
        assert tc.name == "read_file"
        assert tc.parameters["path"] == "main.py"

    def test_no_call_tool(self):
        text = "Just a regular response without any tool calls."
        tc = self.extract(text)
        assert tc is None

    def test_invalid_json(self):
        text = "CALL_TOOL: {not valid json}"
        tc = self.extract(text)
        assert tc is None

    def test_valid_name_filter(self):
        text = 'CALL_TOOL: {"name": "read_file", "arguments": {"path": "x.py"}}'
        tc = self.extract(text, valid_names={"bash", "write_file"})
        assert tc is None  # read_file not in valid_names

        tc = self.extract(text, valid_names={"read_file", "write_file"})
        assert tc is not None
        assert tc.name == "read_file"

    def test_missing_name(self):
        text = 'CALL_TOOL: {"arguments": {"path": "x.py"}}'
        tc = self.extract(text)
        assert tc is None


class TestContextCompression:
    """Test context compression handles all message types."""

    def setup_method(self):
        from context.compression import ContextCompressor
        self.compressor = ContextCompressor()

    def test_count_tokens_string(self):
        messages = [{"role": "user", "content": "a" * 100}]
        tokens = self.compressor._count_tokens(messages)
        assert tokens == 25  # 100 chars / 4

    def test_count_tokens_tool_result(self):
        messages = [
            {"role": "tool_result", "results": [
                {"tool_use_id": "tc1", "content": "x" * 400}
            ]}
        ]
        tokens = self.compressor._count_tokens(messages)
        assert tokens == 100  # 400 / 4

    def test_truncate_old_tool_results(self):
        # Create 10 messages, tool result at index 0 with large content
        messages = [
            {"role": "tool_result", "results": [
                {"tool_use_id": "tc1", "content": "x" * 5000}
            ]},
        ]
        # Add 7 more messages to push it past the cutoff
        for i in range(7):
            messages.append({"role": "user", "content": f"msg {i}"})

        result = self.compressor._truncate_old_results(messages, max_result_len=100)
        # First message's tool result should be truncated
        tr_content = result[0]["results"][0]["content"]
        assert len(tr_content) < 5000
        assert "truncated" in tr_content

    def test_no_truncation_for_short_history(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = self.compressor._truncate_old_results(messages)
        assert result == messages  # Unchanged
