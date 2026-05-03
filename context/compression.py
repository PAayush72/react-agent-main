# context/compression.py — Token-based context compression (no LLM dependency)
from typing import List, Dict, Any


class ContextCompressor:
    """Compresses conversation history to fit within token limits.

    Uses heuristic compression — no LLM calls needed.
    """

    def _count_tokens(self, messages: List[Dict]) -> int:
        """Approximate token count (1 token ≈ 4 chars)."""
        total = 0
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str):
                total += len(content) // 4
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        total += len(str(item)) // 4

            # Count tokens in tool_calls (assistant messages with tool use)
            tool_calls = msg.get('tool_calls', [])
            if tool_calls and isinstance(tool_calls, list):
                for tc in tool_calls:
                    if hasattr(tc, 'parameters') and tc.parameters:
                        total += len(str(tc.parameters)) // 4
                    elif isinstance(tc, dict):
                        total += len(str(tc)) // 4

            # Count tokens in tool_result messages
            results = msg.get('results', [])
            if results:
                for tr in results:
                    tr_content = tr.get('content', '')
                    if isinstance(tr_content, str):
                        total += len(tr_content) // 4
                    else:
                        total += len(str(tr_content)) // 4
        return total

    def compress(self, messages: List[Dict], target_tokens: int) -> List[Dict]:
        """Compress message history to fit within target tokens."""
        current = self._count_tokens(messages)
        if current <= target_tokens:
            return messages

        # Step 1: Truncate large tool results in older messages
        messages = self._truncate_old_results(messages)
        if self._count_tokens(messages) <= target_tokens:
            return messages

        # Step 2: Remove old messages, keep system + last N
        keep_last = min(6, len(messages))
        if len(messages) > keep_last + 1:
            summary_msg = {
                "role": "user",
                "content": "[Earlier conversation messages were removed to save context space]"
            }
            messages = [messages[0], summary_msg] + messages[-keep_last:]

        return messages

    def _truncate_old_results(self, messages: List[Dict], max_result_len: int = 2000) -> List[Dict]:
        """Truncate large tool results in older messages."""
        if len(messages) <= 6:
            return messages

        result = []
        cutoff = len(messages) - 6

        for i, msg in enumerate(messages):
            if i < cutoff:
                # Truncate string content
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > max_result_len:
                    truncated = content[:max_result_len] + f"\n\n... [truncated {len(content) - max_result_len} chars]"
                    msg = {**msg, "content": truncated}

                # Truncate tool_result messages
                if msg.get("role") == "tool_result" and "results" in msg:
                    truncated_results = []
                    for tr in msg["results"]:
                        tr_content = tr.get("content", "")
                        if isinstance(tr_content, str) and len(tr_content) > max_result_len:
                            tr = {
                                **tr,
                                "content": tr_content[:max_result_len] + f"\n\n... [truncated {len(tr_content) - max_result_len} chars]"
                            }
                        truncated_results.append(tr)
                    msg = {**msg, "results": truncated_results}

            result.append(msg)

        return result