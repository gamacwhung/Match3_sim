"""
在 Godot web 的 index.html 注入「pck/wasm 版本號 cache-bust」。

Godot 4 的 loader 抓 index.pck / index.wasm 時沒帶版本號 → 瀏覽器(或 Cloudflare)會一直
用舊快取。這裡攔截 fetch，對 .pck / .wasm 自動加上 ?v=<build>，build 用 index.pck 的修改
時間 → 每次重新 export(pck 變了)版本號就變 → 強制重抓最新，舊版快取自動失效。

每次 export 後跑一次：python scripts/inject_cachebust.py
"""
from __future__ import annotations

import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(_ROOT, "godot_demo", "web", "index.html")
PCK = os.path.join(_ROOT, "godot_demo", "web", "index.pck")
MARKER = "/*__cachebust__*/"


def main() -> None:
    build = str(int(os.path.getmtime(PCK)))  # pck 修改時間當版本號
    html = open(INDEX, encoding="utf-8").read()

    snippet = (
        f'<script>{MARKER}(function(){{var B="{build}";var of=window.fetch;'
        'window.fetch=function(u,o){try{if(typeof u==="string"&&/\\.(pck|wasm)(\\?|$)/.test(u))'
        'u+=(u.indexOf("?")>=0?"&":"?")+"v="+B;}catch(e){}return of(u,o);};'
        'console.log("[cache-bust] pck/wasm v="+B);})();</script>'
    )

    # 先移除舊的注入(避免重複 / 更新版本號)，再插到 <head> 之後(要早於 engine 抓檔)
    html = re.sub(r'<script>' + re.escape(MARKER) + r'.*?</script>', '', html, flags=re.S)
    html = html.replace("<head>", "<head>\n\t" + snippet, 1)

    open(INDEX, "w", encoding="utf-8").write(html)
    print(f"[OK] 已注入 cache-bust，build={build}（pck mtime）")


if __name__ == "__main__":
    main()
