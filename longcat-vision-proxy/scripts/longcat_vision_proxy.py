#!/usr/bin/env python3
"""
LongCat Vision Proxy — 把标准 OpenAI 图片格式转成 LongCat Omni 格式

Hermes 配置:
  auxiliary.vision.base_url = http://localhost:18765
  auxiliary.vision.model    = LongCat-Flash-Omni-2603
  auxiliary.vision.provider = custom

用法:
  python3 longcat_vision_proxy.py [--port 18765]
"""

import json
import re
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from base64 import b64encode

LONGCAT_ENDPOINT = "https://api.longcat.chat/openai/v1/chat/completions"
API_KEY = "ak_2LV4Sv0348dZ6vQ8363hE7EY0nU3I"


def convert_content_item(item):
    t = item.get("type", "")
    if t == "image_url":
        url = item.get("image_url", {}).get("url", "")
        m = re.match(r"^data:image/[^;]+;base64,(.+)$", url)
        if m:
            b64_data = m.group(1)
        else:
            try:
                resp = urlopen(url, timeout=30)
                b64_data = b64encode(resp.read()).decode()
            except Exception as e:
                return {"type": "text", "text": f"[图片加载失败: {e}]"}
        return {
            "type": "input_image",
            "input_image": {"type": "base64", "data": [b64_data]},
        }
    return item


def convert_messages(messages):
    converted = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            items = [convert_content_item(item) for item in content]
            images = [i for i in items if i.get("type") == "input_image"]
            texts = [i for i in items if i.get("type") == "text"]
            others = [i for i in items if i.get("type") not in ("input_image", "text")]
            content = images + texts + others
        converted.append({"role": role, "content": content})
    return converted


class ProxyHandler(BaseHTTPRequestHandler):
    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "proxy": "longcat-vision"})
        elif self.path == "/v1/models":
            self._send_json(200, {
                "object": "list",
                "data": [{"id": "LongCat-Flash-Omni-2603", "object": "model"}]
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self._send_json(404, {"error": "not found"})
            return
        body = self._read_body()
        try:
            req_data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON"})
            return
        omni_request = {
            "model": "LongCat-Flash-Omni-2603",
            "messages": convert_messages(req_data.get("messages", [])),
            "max_tokens": req_data.get("max_tokens", 2048),
            "temperature": req_data.get("temperature", 0.7),
            "stream": req_data.get("stream", False),
            "output_modalities": ["text"],
            "top_p": req_data.get("top_p", 0.1),
        }
        raw_body = json.dumps(omni_request).encode()
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
        try:
            req = Request(LONGCAT_ENDPOINT, data=raw_body, headers=headers, method="POST")
            lc_body = urlopen(req, timeout=120).read()
        except HTTPError as e:
            err = e.read().decode(errors="replace") if hasattr(e, "read") else str(e)
            self._send_json(e.code, {"error": f"upstream HTTP {e.code}: {err[:500]}"})
            return
        except Exception as e:
            self._send_json(502, {"error": str(e)})
            return
        try:
            lc_resp = json.loads(lc_body)
        except json.JSONDecodeError:
            self._send_json(502, {"error": "bad upstream response"})
            return
        if "choices" in lc_resp and lc_resp["choices"]:
            c = lc_resp["choices"][0]
            c.pop("delta", None)
            c.get("message", {}).pop("audio", None)
        for k in ("session_id", "lastOne", "content"):
            lc_resp.pop(k, None)
        self._send_json(200, lc_resp)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="LongCat Vision Proxy")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    server = HTTPServer(("0.0.0.0", args.port), ProxyHandler)
    print(f"LongCat Vision Proxy → http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
