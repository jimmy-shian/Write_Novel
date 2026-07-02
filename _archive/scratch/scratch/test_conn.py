# -*- coding: utf-8 -*-
import requests
import json
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

url = "https://integrate.api.nvidia.com/v1/chat/completions"

def test_api(key, stream):
    print(f"\n--- Testing Key: {key} | Stream: {stream} ---")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "patcher-main",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! Reply in one short sentence."}
        ],
        "stream": stream
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60, stream=stream)
        print(f"Status Code: {response.status_code}")
        if stream:
            count = 0
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    count += 1
                    if count <= 10 or decoded.startswith("data: [DONE]"):
                        print(f"Stream line: {decoded}")
                    elif count == 11:
                        print("... (truncated stream lines) ...")
        else:
            print(f"Response Text: {response.text}")
    except Exception as e:
        print(f"Error occurred: {e}")

test_api("2", True)
test_api("3", True)
