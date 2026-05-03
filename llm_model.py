# llm_model.py — SAP primary, NVIDIA secondary (STREAMING)

import json
import os
import uuid
import queue
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set, Generator

from openai import OpenAI as OpenAIClient
from dotenv import load_dotenv

load_dotenv()


DEPLOYMENT_ID = (os.getenv("DEPLOYMENT_ID") or "").strip()
NVIDIA_API_KEY = (os.getenv("NVIDIA_API_KEY") or "").strip()
NVIDIA_BASE_URL = (os.getenv("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1").strip()
NVIDIA_MODEL = (os.getenv("NVIDIA_MODEL") or "qwen/qwen2.5-coder-32b-instruct").strip()
NVIDIA_FALLBACK_MODELS = [
    m.strip() for m in (os.getenv("NVIDIA_FALLBACK_MODELS") or "").split(",") if m.strip()
]

TEMPERATURE = float(os.getenv("TEMPERATURE") or "0.2")
MAX_TOKENS = int(os.getenv("MAX_TOKENS") or "16384")
SAP_TIMEOUT = float(os.getenv("SAP_TIMEOUT") or "15")

_sap_client = None
_nvidia_client = None


# ───────────────── DATA CLASSES ───────────────── #

@dataclass
class ToolCall:
    id: str
    name: str
    parameters: Dict[str, Any]


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str = ""


@dataclass
class StreamChunk:
    type: str  # "text", "tool_start", "tool_delta", "tool_end", "done", "status"
    content: str = ""
    tool_name: str = ""
    tool_id: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""


# ───────────────── HELPERS ───────────────── #

def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _safe_json_loads(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)):
        return {"value": list(value)}
    if not isinstance(value, str):
        return {"value": value}
    text = value.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except Exception:
        return {"raw_arguments": text}


def _schema_from_tool_def(tool_def: Dict[str, Any]) -> Dict[str, Any]:
    schema = (
        tool_def.get("input_schema")
        or tool_def.get("inputSchema")
        or tool_def.get("parameters")
    )
    if not schema or not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    return schema


def _tool_name(tc: Any) -> str:
    return str(_get(tc, "name", ""))


def _tool_id(tc: Any, fallback: str) -> str:
    value = _get(tc, "id", None)
    return str(value) if value else fallback


def _assistant_content(msg: Any) -> str:
    content = _get(msg, "content", "")
    if content is None:
        return ""
    return str(content)


def _normalize_tool_params(params: Any) -> Dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, dict):
        return params
    if isinstance(params, str):
        return _safe_json_loads(params)
    return {"value": params}


def _tool_names(tool_definitions: Optional[List[Dict[str, Any]]]) -> Set[str]:
    return {str(t.get("name", "")).strip() for t in (tool_definitions or []) if t.get("name")}


def _build_tool_inventory_text(tool_definitions: Optional[List[Dict[str, Any]]]) -> str:
    tools = tool_definitions or []
    if not tools:
        return "Available tools: none."
    lines = ["Available tools:", ""]
    for i, tool in enumerate(tools, start=1):
        schema = _schema_from_tool_def(tool)
        lines.append(f"{i}. {tool.get('name', '')}")
        if tool.get("description"):
            lines.append(f"   description: {tool.get('description')}")
        lines.append(f"   input_schema: {json.dumps(schema, ensure_ascii=False)}")
        lines.append("")
    return "\n".join(lines)


def _extract_system_prompt(messages: List[Dict[str, Any]]) -> str:
    """Extract system prompt from messages if present."""
    for msg in messages:
        if msg.get("role") == "system":
            return str(msg.get("content", ""))
    return ""


def _build_sap_system_prompt(messages: List[Dict[str, Any]], tool_definitions: Optional[List[Dict[str, Any]]]) -> str:
    """Build SAP system prompt: use agent's system prompt + tool inventory."""
    agent_prompt = _extract_system_prompt(messages)
    if not agent_prompt:
        agent_prompt = "You are an AI coding agent. Use tools when needed."
    return agent_prompt + "\n\n" + _build_tool_inventory_text(tool_definitions)


def _build_nvidia_system_prompt(messages, tool_definitions):
    agent_prompt = _extract_system_prompt(messages) or "You are a coding agent."

    tool_text = _build_tool_inventory_text(tool_definitions)

    return f"""
    {agent_prompt}

    You can use tools when needed.
    Call tools using the provided function interface.
    If no tool is needed, answer normally.
    """
# ───────────────── TOOL CONFIG BUILDERS ───────────────── #

def build_tool_config(tool_definitions: List[Dict[str, Any]]) -> Dict[str, Any]:
    tools = []
    for tool_def in tool_definitions or []:
        tools.append({
            "toolSpec": {
                "name": tool_def["name"],
                "description": tool_def.get("description") or "No description provided.",
                "inputSchema": {
                    "json": _schema_from_tool_def(tool_def)
                }
            }
        })
    return {"tools": tools}


def build_nvidia_tools(tool_definitions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tools = []
    for tool_def in tool_definitions or []:
        tools.append({
            "type": "function",
            "function": {
                "name": tool_def["name"],
                "description": tool_def.get("description", ""),
                "parameters": _schema_from_tool_def(tool_def),
            }
        })
    return tools


# ───────────────── MESSAGE BUILDERS ───────────────── #

def build_messages_sap(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build SAP Bedrock-format messages. Filters out system messages (handled via system param)."""
    formatted = []
    last_role = None

    for msg in messages:
        role = msg["role"]

        # Skip system messages — they're passed via the system parameter
        if role == "system":
            continue

        if role == "tool_result":
            tool_results = msg.get("results", [])
            content_blocks = []
            for tr in tool_results:
                content_blocks.append({
                    "toolResult": {
                        "toolUseId": tr["tool_use_id"],
                        "content": [{"text": str(tr["content"])}]
                    }
                })
            if last_role == "user" and formatted:
                formatted[-1]["content"].extend(content_blocks)
            else:
                formatted.append({"role": "user", "content": content_blocks})
                last_role = "user"
            continue

        if role == "assistant":
            content_blocks = []
            content = _assistant_content(msg)
            if content:
                content_blocks.append({"text": content})
            for tc in msg.get("tool_calls", []):
                content_blocks.append({
                    "toolUse": {
                        "toolUseId": _tool_id(tc, fallback=str(uuid.uuid4())),
                        "name": _tool_name(tc),
                        "input": _normalize_tool_params(_get(tc, "parameters", {})),
                    }
                })
            if not content_blocks:
                content_blocks.append({"text": " "})
            if last_role == "assistant" and formatted:
                formatted[-1]["content"].extend(content_blocks)
            else:
                formatted.append({"role": "assistant", "content": content_blocks})
                last_role = "assistant"
            continue

        if role == "user":
            content = msg.get("content", "")
            content_blocks = content if isinstance(content, list) else [{"text": str(content) if content else " "}]
            if last_role == "user" and formatted:
                formatted[-1]["content"].extend(content_blocks)
            else:
                formatted.append({"role": "user", "content": content_blocks})
                last_role = "user"

    if formatted and formatted[0]["role"] != "user":
        formatted.insert(0, {"role": "user", "content": [{"text": "Begin."}]})

    # Ensure alternating roles (Bedrock requirement)
    fixed = []
    for msg in formatted:
        if fixed and fixed[-1]["role"] == msg["role"]:
            filler_role = "assistant" if msg["role"] == "user" else "user"
            fixed.append({"role": filler_role, "content": [{"text": "..."}]})
        fixed.append(msg)

    return fixed


def build_messages_nvidia(messages: List[Dict[str, Any]], tool_definitions: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Build OpenAI-format messages. Uses agent's system prompt from messages."""
    messages = [m for m in messages if m.get("role") != "system" or m.get("content")]
    formatted = [{
    "role": "user",
    "content": _build_nvidia_system_prompt(messages, tool_definitions) or "You are a coding agent."
    }]
    for msg in messages:
        role = msg["role"]

        # Skip system messages — already handled above
        if role == "system":
            continue

        if role == "user":
            formatted.append({"role": "user", "content": str(msg.get("content", ""))})
            continue

        if role == "assistant":
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": _assistant_content(msg) or ""}
            tool_calls_out = []
            for idx, tc in enumerate(msg.get("tool_calls", [])):
                tc_id = _tool_id(tc, fallback=f"tool-{idx}-{uuid.uuid4().hex[:8]}")
                tc_name = _tool_name(tc)
                tc_args = _normalize_tool_params(_get(tc, "parameters", {}))
                tool_calls_out.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {"name": tc_name, "arguments": json.dumps(tc_args, ensure_ascii=False)},
                })
            # if tool_calls_out:
            #     assistant_msg["tool_calls"] = tool_calls_out
            # formatted.append(assistant_msg)
            # continue

        if role == "tool_result":
            for tr in msg.get("results", []):
                formatted.append({
                    "role": "assistant",
                    "content": f"Observation: {str(tr.get('content') or '')}"
                })

    return formatted


# ───────────────── CLIENTS ───────────────── #

def _get_sap_client():
    global _sap_client
    if _sap_client is None:
        from gen_ai_hub.proxy.native.amazon.clients import Session
        _sap_client = Session().client(deployment_id=DEPLOYMENT_ID)
    return _sap_client


def _get_nvidia_client():
    global _nvidia_client
    if _nvidia_client is None:
        api_key = NVIDIA_API_KEY or ""
        if not api_key:
            raise RuntimeError("No NVIDIA API key found.")
        import httpx
        _nvidia_client = OpenAIClient(
            base_url=NVIDIA_BASE_URL,
            api_key=api_key,
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
            http_client=httpx.Client(timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)),
        )
    return _nvidia_client


# ───────────────── TEXT TOOL-CALL EXTRACTION (FALLBACK) ───────────────── #

def _extract_tool_call_from_text(text: str, valid_names: Optional[Set[str]] = None) -> Optional[ToolCall]:
    if not text or "CALL_TOOL:" not in text:
        return None
    marker = text.find("CALL_TOOL:")
    fragment = text[marker + len("CALL_TOOL:"):].strip()
    fragment = fragment.lstrip("` \n\t")
    first_brace = fragment.find("{")
    if first_brace == -1:
        return None
    fragment = fragment[first_brace:]
    try:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(fragment)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", "")).strip()
    if not name:
        return None
    if valid_names and name not in valid_names:
        return None
    arguments = _normalize_tool_params(data.get("arguments", {}))
    return ToolCall(id=str(uuid.uuid4()), name=name, parameters=arguments)


# ───────────────── RESPONSE PARSERS ───────────────── #

def _parse_sap_response(response: Dict[str, Any]) -> LLMResponse:
    result = LLMResponse()
    result.stop_reason = response.get("stopReason", "")
    usage = response.get("usage", {})
    result.input_tokens = usage.get("inputTokens", 0)
    result.output_tokens = usage.get("outputTokens", 0)
    output_msg = response.get("output", {}).get("message", {})
    content_blocks = output_msg.get("content", [])
    all_text = ""
    for block in content_blocks:
        if "text" in block:
            all_text += block["text"]
    for block in content_blocks:
        if "text" in block:
            result.content += block["text"]
        elif "toolUse" in block:
            tool_use = block["toolUse"]
            params = _normalize_tool_params(tool_use.get("input", {}))
            if not params and all_text:
                tc = _extract_tool_call_from_text(all_text)
                if tc and tc.name == str(tool_use.get("name", "")):
                    params = tc.parameters
            result.tool_calls.append(ToolCall(
                id=str(tool_use.get("toolUseId", "")),
                name=str(tool_use.get("name", "")),
                parameters=params,
            ))
    if not result.tool_calls and all_text:
        tc = _extract_tool_call_from_text(all_text)
        if tc:
            result.tool_calls = [tc]
            result.content = ""
    return result


def _parse_nvidia_response(response: Any, tool_definitions: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
    result = LLMResponse()
    valid_names = _tool_names(tool_definitions)
    choices = _get(response, "choices", []) or []
    if not choices:
        usage = _get(response, "usage", {}) or {}
        result.input_tokens = _get(usage, "prompt_tokens", 0) or 0
        result.output_tokens = _get(usage, "completion_tokens", 0) or 0
        return result
    choice0 = choices[0]
    message = _get(choice0, "message", None)
    result.stop_reason = str(_get(choice0, "finish_reason", "") or "")
    usage = _get(response, "usage", {}) or {}
    result.input_tokens = int(_get(usage, "prompt_tokens", 0) or 0)
    result.output_tokens = int(_get(usage, "completion_tokens", 0) or 0)
    if message is None:
        return result
    content = _get(message, "content", "") or ""
    native_tool_calls = _get(message, "tool_calls", []) or []
    if native_tool_calls:
        for idx, call in enumerate(native_tool_calls):
            fn = _get(call, "function", {}) or {}
            name = str(_get(fn, "name", "")).strip()
            if valid_names and name not in valid_names:
                continue
            arguments = _safe_json_loads(_get(fn, "arguments", {}))
            tc_id = _get(call, "id", None) or f"nvidia-{idx}-{uuid.uuid4().hex[:12]}"
            result.tool_calls.append(ToolCall(id=str(tc_id), name=name, parameters=arguments))
        return result
    tool_call = _extract_tool_call_from_text(content, valid_names=valid_names)
    if tool_call:
        result.tool_calls = [tool_call]
        result.content = ""
    else:
        result.content = str(content).strip()
    return result


# ───────────────── STREAMING — SAP ───────────────── #

def _stream_sap(messages: List[Dict[str, Any]], tool_definitions: Optional[List[Dict[str, Any]]] = None) -> Generator[StreamChunk, None, None]:
    yield StreamChunk(type="status", content="Thinking via SAP...")

    _SENTINEL = object()
    chunk_queue: queue.Queue = queue.Queue()

    def _worker():
        try:
            client = _get_sap_client()
            formatted_messages = build_messages_sap(messages)
            system_prompt = _build_sap_system_prompt(messages, tool_definitions)
            kwargs = {
                "messages": formatted_messages,
                "system": [{"text": system_prompt}],
                "inferenceConfig": {"maxTokens": MAX_TOKENS, "temperature": TEMPERATURE},
            }
            if tool_definitions:
                kwargs["toolConfig"] = build_tool_config(tool_definitions)

            try:
                stream = client.converse_stream(**kwargs)
            except Exception as e:
                chunk_queue.put(RuntimeError(f"SAP AI Hub stream failed: {e}"))
                return

            current_tool = None
            full_content = ""
            input_tokens = 0
            output_tokens = 0
            stop_reason = ""

            for event in stream.get("stream", []):
                if "contentBlockStart" in event:
                    block = event["contentBlockStart"].get("start", {})
                    if "toolUse" in block:
                        current_tool = {
                            "id": block["toolUse"]["toolUseId"],
                            "name": block["toolUse"]["name"],
                            "input": ""
                        }
                        chunk_queue.put(StreamChunk(type="tool_start", tool_name=current_tool["name"], tool_id=current_tool["id"]))

                elif "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    if "text" in delta:
                        text = delta["text"]
                        full_content += text
                        chunk_queue.put(StreamChunk(type="text", content=text))
                    elif "toolUse" in delta:
                        if current_tool:
                            tool_delta = delta["toolUse"].get("input")
                            if tool_delta is not None:
                                if isinstance(tool_delta, dict):
                                    current_tool["input"] = tool_delta
                                elif isinstance(tool_delta, str):
                                    if isinstance(current_tool["input"], str):
                                        current_tool["input"] += tool_delta
                                    else:
                                        current_tool["input"] = tool_delta

                elif "contentBlockStop" in event:
                    if current_tool:
                        if isinstance(current_tool["input"], str):
                            try:
                                current_tool["input"] = json.loads(current_tool["input"])
                            except (json.JSONDecodeError, TypeError):
                                current_tool["input"] = {}
                        chunk_queue.put(StreamChunk(type="tool_end", tool_name=current_tool["name"], tool_id=current_tool["id"], tool_input=current_tool["input"]))
                        current_tool = None

                elif "messageStop" in event:
                    sr = event["messageStop"].get("stopReason", "")
                    stop_reason = sr

                elif "metadata" in event:
                    usage = event["metadata"].get("usage", {})
                    input_tokens = usage.get("inputTokens", 0)
                    output_tokens = usage.get("outputTokens", 0)

            chunk_queue.put(StreamChunk(type="done", stop_reason=stop_reason or "end_turn", model_used="SAP", input_tokens=input_tokens, output_tokens=output_tokens))

        except Exception as e:
            chunk_queue.put(RuntimeError(str(e)))
        finally:
            chunk_queue.put(_SENTINEL)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    deadline = SAP_TIMEOUT
    while True:
        try:
            item = chunk_queue.get(timeout=deadline)
        except queue.Empty:
            raise RuntimeError(f"SAP timed out after {SAP_TIMEOUT}s")

        if item is _SENTINEL:
            return
        if isinstance(item, Exception):
            raise item
        yield item
        if item.type == "text":
            deadline = SAP_TIMEOUT


# ───────────────── STREAMING — NVIDIA ───────────────── #

def _stream_nvidia(messages: List[Dict[str, Any]], tool_definitions: Optional[List[Dict[str, Any]]] = None, model: Optional[str] = None) -> Generator[StreamChunk, None, None]:
    active_model = model or NVIDIA_MODEL
    yield StreamChunk(type="status", content=f"Thinking via NVIDIA ({active_model.split('/')[-1]})...")
    client = _get_nvidia_client()
    formatted_messages = build_messages_nvidia(messages, tool_definitions)
    kwargs = {
        "model": active_model,
        "messages": formatted_messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    tools = build_nvidia_tools(tool_definitions or [])
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"


    

    try:
        stream = client.chat.completions.create(**kwargs)
    except Exception as e:
        err_str = str(e)
        if "400" in err_str and ("DEGRADED" in err_str or "degraded" in err_str.lower()):
            raise RuntimeError(f"NVIDIA model '{active_model}' is degraded/unavailable")
        if "Tool use has not been enabled" in err_str or "unsupported" in err_str.lower():
            raise RuntimeError(f"NVIDIA model '{active_model}' does not support tool calling")
        raise RuntimeError(f"NVIDIA API stream failed: {err_str}")

    # Track multiple parallel tool calls by index
    active_tools: Dict[int, Dict[str, Any]] = {}  # index -> {id, name, input_buffer}
    input_tokens = 0
    output_tokens = 0
    got_any_chunk = False

    try:
        for chunk in stream:
            got_any_chunk = True
            if hasattr(chunk, "usage") and chunk.usage:
                input_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            # Text content
            if hasattr(delta, "content") and delta.content:
                yield StreamChunk(type="text", content=delta.content)

            # Tool calls — handle ALL indices, not just index 0
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    tc_index = getattr(tc_delta, "index", 0)
                    fn = getattr(tc_delta, "function", None)

                    if tc_index not in active_tools:
                        # New tool call starting
                        name = getattr(fn, "name", "") if fn else ""
                        tc_id = getattr(tc_delta, "id", "") or f"nvidia-stream-{tc_index}-{uuid.uuid4().hex[:8]}"
                        active_tools[tc_index] = {"id": tc_id, "name": name, "input_buffer": ""}
                        if name:
                            yield StreamChunk(type="tool_start", tool_name=name, tool_id=tc_id)

                    # Accumulate arguments
                    if fn and hasattr(fn, "arguments") and fn.arguments:
                        active_tools[tc_index]["input_buffer"] += fn.arguments

                    # If we got a name update on an existing tool (some models do this)
                    if fn and hasattr(fn, "name") and fn.name and not active_tools[tc_index]["name"]:
                        active_tools[tc_index]["name"] = fn.name
                        yield StreamChunk(type="tool_start", tool_name=fn.name, tool_id=active_tools[tc_index]["id"])

            # Finish — emit all pending tool calls
            if finish_reason:
                for tc_index in sorted(active_tools.keys()):
                    tool_info = active_tools[tc_index]
                    try:
                        parsed_input = json.loads(tool_info["input_buffer"]) if tool_info["input_buffer"] else {}
                    except (json.JSONDecodeError, TypeError):
                        parsed_input = {}
                    yield StreamChunk(
                        type="tool_end",
                        tool_name=tool_info["name"],
                        tool_id=tool_info["id"],
                        tool_input=parsed_input,
                    )
                active_tools.clear()
                yield StreamChunk(type="done", stop_reason=finish_reason, model_used=f"NVIDIA ({active_model})", input_tokens=input_tokens, output_tokens=output_tokens)
                return
    except Exception as e:
        raise RuntimeError(f"NVIDIA streaming error: {e}")

    if not got_any_chunk:
        raise RuntimeError("NVIDIA API connected but returned no chunks")

    # Emit any remaining tools
    for tc_index in sorted(active_tools.keys()):
        tool_info = active_tools[tc_index]
        try:
            parsed_input = json.loads(tool_info["input_buffer"]) if tool_info["input_buffer"] else {}
        except (json.JSONDecodeError, TypeError):
            parsed_input = {}
        yield StreamChunk(type="tool_end", tool_name=tool_info["name"], tool_id=tool_info["id"], tool_input=parsed_input)

    yield StreamChunk(type="done", stop_reason="stop", model_used=f"NVIDIA ({active_model})", input_tokens=input_tokens, output_tokens=output_tokens)



# def _stream_nvidia(messages: List[Dict[str, Any]], tool_definitions: Optional[List[Dict[str, Any]]] = None, model: Optional[str] = None) -> Generator[StreamChunk, None, None]:
#     active_model = model or NVIDIA_MODEL
#     yield StreamChunk(type="status", content=f"Thinking via NVIDIA ({active_model.split('/')[-1]})...")

#     client = _get_nvidia_client()
#     formatted_messages = build_messages_nvidia(messages, tool_definitions)

#     kwargs = {
#         "model": active_model,
#         "messages": formatted_messages,
#         "temperature": TEMPERATURE,
#         "max_tokens": min(MAX_TOKENS, 4096),  # 🔴 limit Gemma rambling
#         "stream": True,
#         "stream_options": {"include_usage": True},

#         # 🔴 CRITICAL: force stop
#         "stop": [
#             "Final Answer:",
#             "\nObservation:",
#             "\nUser:",
#         ],
#     }

    tools = build_nvidia_tools(tool_definitions or [])
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

#     try:
#         stream = client.chat.completions.create(**kwargs)
#     except Exception as e:
#         raise RuntimeError(f"NVIDIA API stream failed: {e}")

#     active_tools: Dict[int, Dict[str, Any]] = {}
#     input_tokens = 0
#     output_tokens = 0

#     # 🔴 NEW: safety controls
#     collected_text = ""
#     MAX_CHARS = 15000
#     idle_counter = 0
#     MAX_IDLE = 200  # chunks without finish

#     try:
#         for chunk in stream:
#             if hasattr(chunk, "usage") and chunk.usage:
#                 input_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
#                 output_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0

#             if not chunk.choices:
#                 continue

#             delta = chunk.choices[0].delta
#             finish_reason = chunk.choices[0].finish_reason

#             # TEXT
#             if hasattr(delta, "content") and delta.content:
#                 text = delta.content
#                 collected_text += text
#                 yield StreamChunk(type="text", content=text)

#                 # 🔴 HARD STOP CONDITIONS
#                 if "Final Answer:" in collected_text:
#                     yield StreamChunk(
#                         type="done",
#                         stop_reason="manual_final_answer",
#                         model_used=f"NVIDIA ({active_model})",
#                         input_tokens=input_tokens,
#                         output_tokens=output_tokens,
#                     )
#                     return

#                 if len(collected_text) > MAX_CHARS:
#                     yield StreamChunk(
#                         type="done",
#                         stop_reason="max_chars_reached",
#                         model_used=f"NVIDIA ({active_model})",
#                         input_tokens=input_tokens,
#                         output_tokens=output_tokens,
#                     )
#                     return

#             # TOOL CALLS (unchanged)
#             if hasattr(delta, "tool_calls") and delta.tool_calls:
#                 for tc_delta in delta.tool_calls:
#                     tc_index = getattr(tc_delta, "index", 0)
#                     fn = getattr(tc_delta, "function", None)

#                     if tc_index not in active_tools:
#                         name = getattr(fn, "name", "") if fn else ""
#                         tc_id = getattr(tc_delta, "id", "") or f"nvidia-stream-{tc_index}-{uuid.uuid4().hex[:8]}"
#                         active_tools[tc_index] = {"id": tc_id, "name": name, "input_buffer": ""}
#                         if name:
#                             yield StreamChunk(type="tool_start", tool_name=name, tool_id=tc_id)

#                     if fn and hasattr(fn, "arguments") and fn.arguments:
#                         active_tools[tc_index]["input_buffer"] += fn.arguments

#             # 🔴 NORMAL FINISH
#             if finish_reason:
#                 for tc_index in sorted(active_tools.keys()):
#                     tool_info = active_tools[tc_index]
#                     try:
#                         parsed_input = json.loads(tool_info["input_buffer"]) if tool_info["input_buffer"] else {}
#                     except Exception:
#                         parsed_input = {}
#                     yield StreamChunk(
#                         type="tool_end",
#                         tool_name=tool_info["name"],
#                         tool_id=tool_info["id"],
#                         tool_input=parsed_input,
#                     )

#                 yield StreamChunk(
#                     type="done",
#                     stop_reason=finish_reason,
#                     model_used=f"NVIDIA ({active_model})",
#                     input_tokens=input_tokens,
#                     output_tokens=output_tokens,
#                 )
#                 return

#             # 🔴 IDLE DETECTION
#             idle_counter += 1
#             if idle_counter > MAX_IDLE:
#                 yield StreamChunk(
#                     type="done",
#                     stop_reason="idle_timeout",
#                     model_used=f"NVIDIA ({active_model})",
#                     input_tokens=input_tokens,
#                     output_tokens=output_tokens,
#                 )
#                 return

#     except Exception as e:
#         raise RuntimeError(f"NVIDIA streaming error: {e}")

#     # 🔴 FALLBACK EXIT
#     yield StreamChunk(
#         type="done",
#         stop_reason="stream_end_fallback",
#         model_used=f"NVIDIA ({active_model})",
#         input_tokens=input_tokens,
#         output_tokens=output_tokens,
#     )






# ───────────────── BACKEND SELECTION ───────────────── #

_active_backend: str = "auto"

def set_active_backend(backend: str):
    """Set preferred backend: 'sap', 'nvidia', or 'auto'."""
    global _active_backend
    _active_backend = backend.lower()

def get_active_backend() -> str:
    return _active_backend

def call_model_stream(messages: List[Dict[str, Any]], tool_definitions: Optional[List[Dict[str, Any]]] = None) -> Generator[StreamChunk, None, None]:
    """
    Streaming backend priority:
    1) If backend is 'sap' -> SAP only
    2) If backend is 'nvidia' -> NVIDIA only
    3) If backend is 'auto' -> SAP first, then NVIDIA fallback
    """
    errors = []
    backend = _active_backend

    if backend == "sap":
        if not DEPLOYMENT_ID:
            raise RuntimeError("SAP backend selected but DEPLOYMENT_ID is not set.")
        yield from _stream_sap(messages, tool_definitions)
        return

    if backend == "nvidia":
        if not NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA backend selected but NVIDIA_API_KEY is not set.")
        yield from _stream_nvidia(messages, tool_definitions)
        return

    # auto mode
    if DEPLOYMENT_ID:
        try:
            yield from _stream_sap(messages, tool_definitions)
            return
        except Exception as e:
            errors.append(f"SAP: {e}")
            yield StreamChunk(type="status", content=f"SAP failed, trying NVIDIA fallback...")

    if NVIDIA_API_KEY:
        nvidia_models = [NVIDIA_MODEL] + [m for m in NVIDIA_FALLBACK_MODELS if m != NVIDIA_MODEL]
        for nvidia_model in nvidia_models:
            try:
                yield from _stream_nvidia(messages, tool_definitions, model=nvidia_model)
                return
            except Exception as e:
                errors.append(f"NVIDIA ({nvidia_model}): {e}")
                if nvidia_model != nvidia_models[-1]:
                    yield StreamChunk(type="status", content=f"  {nvidia_model.split('/')[-1]} unavailable, trying next...")

    raise RuntimeError(
        "All model backends failed.\n" + "\n".join(f"- {err}" for err in errors)
        if errors else
        "No usable backend was configured. Set DEPLOYMENT_ID or NVIDIA_API_KEY in .env"
    )


def call_model(messages: List[Dict[str, Any]], tool_definitions: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
    """Non-streaming wrapper that consumes the stream for backward compatibility."""
    result = LLMResponse()
    current_tool = None
    tool_input = ""

    for chunk in call_model_stream(messages, tool_definitions):
        if chunk.type == "text":
            result.content += chunk.content
        elif chunk.type == "tool_start":
            current_tool = {"id": chunk.tool_id, "name": chunk.tool_name, "input": ""}
            tool_input = ""
        elif chunk.type == "tool_delta":
            tool_input += chunk.content
        elif chunk.type == "tool_end":
            if current_tool:
                if chunk.tool_input and isinstance(chunk.tool_input, dict):
                    params = chunk.tool_input
                else:
                    try:
                        params = json.loads(tool_input) if tool_input else {}
                    except Exception:
                        params = {}
                result.tool_calls.append(ToolCall(
                    id=current_tool["id"],
                    name=current_tool["name"],
                    parameters=params,
                ))
                current_tool = None
        elif chunk.type == "done":
            result.stop_reason = chunk.stop_reason
            result.input_tokens = chunk.input_tokens
            result.output_tokens = chunk.output_tokens
            result.model_used = chunk.model_used

    return result
