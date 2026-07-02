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
        {"role": "system", "content": "你是一位嚴謹的創作大師。請使用 zh-TW 繁體中文輸出簡潔、深刻、高水準的心得與金律。"},
        {"role": "user", "content": "你作為首席創意總監，對整部作品進行評審，總結全局避坑指南與終極創作金律。"}
    ],
    "stream": True
}
try:
    response = requests.post(url, headers=headers, json=payload, timeout=30, stream=True)
    print(f"Status: {response.status_code}")
    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith("data:"):
                data_str = decoded[5:].strip()
                if data_str == "[DONE]":
                    print("[DONE]")
                    break
                data_json = json.loads(data_str)
                choices = data_json.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content") or ""
                    if content:
                        print(content, end="", flush=True)
    print()
except Exception as e:
    print(f"\nError: {e}")
