# -*- coding: utf-8 -*-
import requests
import json
import time
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

url = "https://integrate.api.nvidia.com/v1/chat/completions"

def test_key3():
    headers = {
        "Authorization": "Bearer 3",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "patcher-main",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"}
        ],
        "stream": True
    }
    print(f"[{time.strftime('%H:%M:%S')}] Sending request with Key 3...")
    try:
        # 10s connection timeout, 60s read timeout
        response = requests.post(url, headers=headers, json=payload, timeout=(10, 60), stream=True)
        print(f"[{time.strftime('%H:%M:%S')}] Response status code: {response.status_code}")
        
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                print(f"[{time.strftime('%H:%M:%S')}] Stream line: {decoded}")
                # Print only the first few stream lines to avoid clutter
                break
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error: {e}")

test_key3()
