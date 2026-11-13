#!/usr/bin/env python3
import json
import math
import os
import platform
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>免费云电脑 · 口播计时器</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#10151b;color:#edf3fa}*{box-sizing:border-box}body{margin:0;padding:45px 20px}main{max-width:1000px;margin:auto}.tag,.state{color:#91e5ce;font-size:12px}h1{font-size:clamp(27px,4vw,42px);margin-bottom:10px}p,.label,.unit{color:#9baab9}.layout{display:grid;grid-template-columns:1.7fr 1fr;gap:20px;margin:30px 0}.card{background:#192129;border:1px solid #2d3b46;border-radius:20px;padding:25px}label{display:block;font-size:14px;margin-bottom:12px}textarea,input,button{font:inherit;border-radius:10px;padding:14px}textarea,input{width:100%;background:#11191f;color:#edf3fa;border:1px solid #35444e}textarea{height:260px;line-height:1.8;resize:vertical}.controls{display:flex;gap:14px;align-items:end;margin-top:18px}.controls label{margin:0;flex:1}input{margin-top:8px}button{border:0;background:#91e5ce;color:#10251f;font-weight:bold;cursor:pointer}button:disabled{opacity:.5}.hint,footer{font-size:12px;color:#8497a8}.metric{font-size:52px;margin:8px 0;font-variant-numeric:tabular-nums}.unit{font-size:14px;margin-left:8px}.divider{height:1px;background:#30404a;margin:24px 0}.state{margin-top:20px}.error{color:#ffb5a8;min-height:22px;font-size:13px;margin-top:12px}footer{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}@media(max-width:700px){.layout{grid-template-columns:1fr}body{padding:25px 16px}}
</style><main>
<div class="tag">● CLOUD WORKSPACE</div>
<h1>免费云电脑 · 口播计时器</h1><p>粘贴一段文案，看看大约要讲多久。</p>
<div class="layout"><section class="card"><form id="form">
<label for="text">口播文案</label><textarea id="text" maxlength="50000">把重复的事交给工具，把省下的时间留给创作。</textarea>
<div class="controls"><label for="cpm">每分钟字数<input id="cpm" type="number" min="60" max="600" step="1" value="240" required></label><button id="button">计算时长 →</button></div>
<p class="hint">去掉空白，标点计入；估时不含停顿。支持 60–600 字/分钟。</p>
<div id="error" class="error" role="alert"></div></form></section>
<section class="card" aria-live="polite"><div class="label">有效字符</div><div class="metric"><span id="count">—</span><span class="unit">字</span></div>
<div class="divider"></div><div class="label">预计口播时长</div><div class="metric"><span id="seconds">—</span><span class="unit">秒</span></div><div id="duration" class="label">等待计算</div><div id="state" class="state">计算将在 Python 后端执行</div></section></div>
<footer><span id="env" class="env">读取运行环境…</span><span id="utc"></span></footer></main>
<script>
const $=id=>document.getElementById(id);
$('form').onsubmit=async e=>{e.preventDefault();$('button').disabled=true;$('error').textContent='';
try{const r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('text').value,cpm:Number($('cpm').value)})});const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');$('count').textContent=d.char_count;$('seconds').textContent=d.estimated_seconds;$('duration').textContent='约 '+(d.estimated_seconds/60).toFixed(2)+' 分钟 · '+d.cpm+' 字/分钟';$('state').textContent='✓ Python 后端已完成计算';}catch(e){$('error').textContent=e.message;$('state').textContent='本次计算未完成';}finally{$('button').disabled=false;}};
fetch('/api/status').then(r=>r.json()).then(d=>{$('env').textContent=d.system+' · Python '+d.python+' · 可见逻辑 CPU '+d.cpu_visible;$('utc').textContent='UTC '+d.utc;}).catch(()=>{$('env').textContent='运行环境暂时不可读';});
</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, html=False):
        body = (data if html else json.dumps(data, ensure_ascii=False)).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.reply(200, PAGE, True)
        elif path == "/api/status":
            self.reply(200, {"system": platform.system(), "python": platform.python_version(), "cpu_visible": os.cpu_count(), "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        else:
            self.reply(404, {"error": "页面不存在"})

    def do_POST(self):
        if self.path != "/api/analyze":
            return self.reply(404, {"error": "接口不存在"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 300000:
                raise ValueError("文案过长或请求为空")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or not isinstance(data.get("text"), str):
                raise ValueError("请提供文字文案")
            if len(data["text"]) > 50000 or isinstance(data.get("cpm"), bool):
                raise ValueError("请检查文案长度和语速")
            speed = float(data.get("cpm", 240))
            if not math.isfinite(speed) or not 60 <= speed <= 600:
                raise ValueError("每分钟字数须在 60–600 之间")
            count = sum(not char.isspace() for char in data["text"])
            self.reply(200, {"char_count": count, "cpm": speed, "estimated_seconds": round(count * 60 / speed, 2)})
        except (ValueError, TypeError, UnicodeDecodeError):
            self.reply(400, {"error": "输入无效：文案最多 50000 字符，语速为 60–600 字/分钟"})

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"口播计时器：http://127.0.0.1:{port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
