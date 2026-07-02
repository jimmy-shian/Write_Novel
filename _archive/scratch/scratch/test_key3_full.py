# -*- coding: utf-8 -*-
import requests
import json
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

url = "https://integrate.api.nvidia.com/v1/chat/completions"
headers = {
    "Authorization": "Bearer 3",
    "Content-Type": "application/json"
}
payload = {
    "model": "patcher-main",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hi! Answer with 'Yes, I am working.'"}
    ],
    "stream": True
}
try:
    response = requests.post(url, headers=headers, json=payload, timeout=30, stream=True)
    print(f"Status: {response.status_code}")
    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            print(decoded)
except Exception as e:
    print(f"Error: {e}")
