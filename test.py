import requests

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"

headers = {
    "Authorization": "Bearer nvapi-your_api_key_here",
    "Accept": "text/event-stream"
}

payload = {
    "model": "google/gemma-7b",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 100,
    "temperature": 0.7,
    "stream": True,
}

response = requests.post(invoke_url, headers=headers, json=payload, stream=True)

print("Status:", response.status_code)

for line in response.iter_lines():
    if line:
        decoded = line.decode("utf-8")
        if decoded.startswith("data: "):
            print(decoded[6:])