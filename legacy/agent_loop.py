# from tools.file_tools import list_files, read_file
# from tools.diff_tools import generate_diff
# from llm_model import call_model
# from tools.file_tools import write_file_safe, apply_write
# from tools.registry import TOOL_REGISTRY

# # Get tools from registry
# TOOL_DEFINITIONS = TOOL_REGISTRY.get_definitions()
# # Create a mapping from tool name to function for execution
# TOOL_FUNCTIONS = {tool["name"]: TOOL_REGISTRY.get(tool["name"]) for tool in TOOL_DEFINITIONS if TOOL_REGISTRY.get(tool["name"]) is not None}
# # Create a set of tool names for validation
# TOOL_NAMES = set(TOOL_FUNCTIONS.keys())


# import sys

# def ask_permission(action, input_data):
#     # If not running in a terminal (e.g., when piped), auto-approve for testing
#     if not sys.stdin.isatty():
#         return True
#     ans = input(f"\n⚠️ Allow action '{action}' with input '{input_data}'? (y/n): ")
#     return ans.lower() == "y"


# def parse_response(text):
#     """
#     Parse LLM response to extract action and action input.
#     Supports formats:
#     Action: action_name
#     Action Input: input
    
#     Or for multi-line input:
#     Action: action_name
#     Action Input: 
#     line1
#     line2
#     ...
#     """
#     import re
    
#     # Find Action line
#     action_match = re.search(r'^\s*Action:\s*(.+)$', text, re.MULTILINE | re.IGNORECASE)
#     if not action_match:
#         return None, None
    
#     action = action_match.group(1).strip()
    
#     # Find Action Input line
#     action_input_match = re.search(r'^\s*Action Input:\s*(.*)$', text, re.MULTILINE | re.IGNORECASE)
#     if not action_input_match:
#         return action, None
    
#     # Get the matched input (what's after "Action Input:" on the same line)
#     matched_input = action_input_match.group(1).rstrip()
    
#     # If there's content on the same line after "Action Input:", use it
#     if matched_input:
#         # Check if it looks like a pipe-separated file path and content (for write_file/edit_file)
#         if '|' in matched_input and action in ["write_file", "edit_file"]:
#             parts = matched_input.split('|', 1)  # Split only on first pipe
#             filename = parts[0].strip()
#             content_start = parts[1]
#             # If there's more content on following lines, append it
#             lines = text.split('\n')
#             action_input_line_idx = -1
#             for i, line in enumerate(lines):
#                 if line.strip().lower().startswith('action input:'):
#                     action_input_line_idx = i
#                     break
            
#             if action_input_line_idx != -1:
#                 # Collect content lines after the Action Input line
#                 content_lines = []
#                 for i in range(action_input_line_idx + 1, len(lines)):
#                     line = lines[i]
#                     # Stop if we hit another section header
#                     if re.match(r'^\s*(Action:|Thought:|Final Answer:)', line, re.IGNORECASE):
#                         break
#                     content_lines.append(line)
                
#                 if content_lines:
#                     # Append the multi-line content to the content after the pipe
#                     additional_content = '\n'.join(content_lines)
#                     if content_start:  # If there was content on the same line after pipe
#                         content_start = content_start + '\n' + additional_content
#                     else:
#                         content_start = additional_content
            
#             action_input = [filename, content_start]
#             return action, action_input
#         # Special handling for edit_file: if matched_input looks like just a filename,
#         # treat it as filename and look for content in subsequent lines
#         elif action == "edit_file" and '|' not in matched_input:
#             # Check if this looks like just a filename (reasonable length, no problematic chars)
#             if len(matched_input) < 200 and '\n' not in matched_input and not matched_input.startswith(('http', '/')):
#                 # This looks like a filename, look for content in subsequent lines
#                 lines = text.split('\n')
#                 action_input_line_idx = -1
#                 for i, line in enumerate(lines):
#                     if line.strip().lower().startswith('action input:'):
#                         action_input_line_idx = i
#                         break
                
#                 if action_input_line_idx != -1:
#                     # Collect all lines after Action Input until next section or end
#                     content_lines = []
#                     for i in range(action_input_line_idx + 1, len(lines)):
#                         line = lines[i]
#                         # Stop if we hit another section header
#                         if re.match(r'^\s*(Action:|Thought:|Final Answer:)', line, re.IGNORECASE):
#                             break
#                         content_lines.append(line)
                    
#                     content = '\n'.join(content_lines).rstrip('\n')
#                     if content:  # Only use content if we actually got some
#                         action_input = [matched_input, content]
#                         return action, action_input
            
#             # Fall back to using matched_input as action_input
#             action_input = matched_input
#             return action, action_input
#         else:
#             action_input = matched_input
#             return action, action_input
    
#     # Otherwise, look for multi-line content after the Action Input line
#     lines = text.split('\n')
#     action_input_line_idx = -1
#     for i, line in enumerate(lines):
#         if line.strip().lower().startswith('action input:'):
#             action_input_line_idx = i
#             break
    
#     if action_input_line_idx == -1:
#         return action, None
        
#     # Collect all lines after Action Input until next section or end
#     content_lines = []
#     for i in range(action_input_line_idx + 1, len(lines)):
#         line = lines[i]
#         # Stop if we hit another section header
#         if re.match(r'^\s*(Action:|Thought:|Final Answer:)', line, re.IGNORECASE):
#             break
#         content_lines.append(line)
    
#     action_input = '\n'.join(content_lines).rstrip('\n')
    
#     # Handle special case for pipe-separated values (backward compatibility)
#     if '|' in action_input and '\n' not in action_input:
#         action_input = [part.strip() for part in action_input.split('|')]
    
#     # Special handling for edit_file: if we got multi-line content that looks like "filename\ncontent"
#     if action == "edit_file" and isinstance(action_input, str) and action_input:
#         parts = action_input.split('\n', 1)
#         if len(parts) == 2:
#             potential_filename = parts[0].strip()
#             potential_content = parts[1]
#             # If the first part looks like a filename (no excessive length or spaces)
#             if len(potential_filename) < 200 and ' ' not in potential_filename:
#                 action_input = [potential_filename, potential_content]
    
#     return action, action_input if action_input else None

# def run_agent(user_input):
#     messages = [{"role": "user", "content": user_input}]

#     for step in range(15):  # max steps
#         print(f"\n🔄 Step {step+1}")

#         response = call_model(messages)
#         text = response["content"]

#         print("\n🤖", text)

#         # ✅ Stop condition
#         if "Final Answer" in text:
#             break

#         action, action_input = parse_response(text)

#         if not action:
#             print("❌ No action found")
#             break

#         if action not in TOOL_NAMES:
#             print(f"❌ Unknown tool: {action}")
#             break

#         # 🔐 permission for all tools using registry
#         permission_level = TOOL_REGISTRY.get_permission_level(action)
#         if permission_level == "confirm":
#             if not ask_permission(action, action_input):
#                 print("❌ Action denied")
#                 break

#         # run tool using registry
#         try:
#             # Handle None action_input
#             if action_input is None:
#                 action_input = "" if action in ["list_files", "read_file"] else []
            
#             # Get the tool function from registry
#             tool_func = TOOL_FUNCTIONS.get(action)
#             if tool_func is None:
#                 result = f"Tool '{action}' not found in registry"
#             else:
#                 # Execute the tool with proper parameter handling
#                 if isinstance(action_input, list):
#                     result = tool_func(*action_input)
#                 else:
#                     result = tool_func(action_input)
#         except Exception as e:
#             result = f"Tool execution error: {str(e)}"

#         print("\n📌 Observation:", result)

#         # add to memory
#         messages.append({
#             "role": "assistant",
#             "content": text
#         })
#         messages.append({
#             "role": "user",
#             "content": f"Observation: {result}"
#         })