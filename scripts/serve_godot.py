"""
godot_demo/web/ 的 no-cache HTTP server。

為什麼不直接用 `python -m http.server`?
  Godot web export 由 index.html 動態載入 index.pck / index.wasm,
  瀏覽器預設會 cache 這些大檔。重 export 之後 iframe 還是抓到舊 PCK,
  demo 時非常容易踩到。

這個 server 對所有 response 加上 Cache-Control: no-store,
強制 fetch 最新檔案。同時也加 COOP/COEP header(雖然單執行緒
Godot 4.6 export 不需要,但加了無害,以後切多執行緒 export 直接可用)。

用法:
    python scripts/serve_godot.py                   # port 8765
    python scripts/serve_godot.py --port 9000
    python scripts/serve_godot.py --dir godot_demo/web
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


# 哪些 Godot 資源檔需要在 index.html 內被 rewrite 加 ?v=BUILD_HASH。
# 不包含 index.html 自己(那本來就 no-store)。
_REWRITE_TARGETS = (
    'index.js',
    'index.wasm',
    'index.pck',
    'index.side.wasm',
    'index.png',
    'index.icon.png',
    'index.apple-touch-icon.png',
    'index.audio.worklet.js',
    'index.audio.position.worklet.js',
)


def _compute_build_hash(serve_dir: Path) -> str:
    """用 index.pck 的 mtime 算 build hash(重 export 後 hash 變)。"""
    candidates = [serve_dir / 'index.pck', serve_dir / 'index.wasm', serve_dir / 'index.js']
    mtimes = [int(p.stat().st_mtime) for p in candidates if p.is_file()]
    if not mtimes:
        return '0'
    return str(max(mtimes))


class NoCacheGodotHandler(SimpleHTTPRequestHandler):
    """Send strong no-cache headers + COOP/COEP and rewrite index.html URLs with build hash."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.wasm': 'application/wasm',
        '.pck': 'application/octet-stream',
        '.js': 'application/javascript',
        '.json': 'application/json',
    }

    def end_headers(self) -> None:
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Resource-Policy', 'cross-origin')
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write(f'[godot-web] {self.address_string()} - {fmt % args}\n')

    # ------------------------------------------------------------------
    # 攔截 index.html(以及 `/`),動態注入 cache-buster JS。
    # 其它檔案走 SimpleHTTPRequestHandler 預設行為。
    # ------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split('?', 1)[0]
        if path in ('/', '/index.html'):
            self._serve_index_html()
            return
        super().do_GET()

    def _serve_index_html(self) -> None:
        index_path = Path(self.translate_path('/index.html'))
        if not index_path.is_file():
            self.send_error(404, 'index.html not found')
            return
        try:
            html = index_path.read_text(encoding='utf-8')
        except OSError as exc:
            self.send_error(500, f'failed to read index.html: {exc}')
            return

        # 重點:用 index.pck/wasm mtime 算 build_hash,每次重 export 自動換值。
        # 兩件事一起做:
        #   (A) 把 index.html 內**靜態** URL(`<script src="index.js">`、icon)
        #       都加 ?v=BUILD,讓 <script> tag 載入時就走新 URL → cache miss
        #   (B) 注入一段 cache-buster JS,hook window.fetch:Engine 內部
        #       動態用 executable+'.pck' 組的 URL(fetch)會被自動加 ?v=BUILD
        #
        # 為什麼這次不會撞到上次的 WASM instantiate error:上次失敗是因為
        # 舊 cache 的 index.js 配新版 PCK/WASM,binding 不一致;現在
        # `<script src="index.js?v=BUILD">` 走新 URL,Chrome cache miss,
        # 載到新版 index.js,跟新版 PCK/WASM 完全一致。
        build_hash = _compute_build_hash(Path(self.directory))

        # (A) 靜態 URL rewrite — 只改 HTML attribute 內的 URL,不動 JSON key
        # 匹配 src="index.js" / href="index.png" 這類 attribute,
        # 不會誤傷 GODOT_CONFIG 的 "fileSizes" 內的 JSON key
        def _rewrite_attr(match: 're.Match[str]') -> str:
            attr = match.group(1)
            quote = match.group(2)
            url = match.group(3)
            return f'{attr}={quote}{url}?v={build_hash}{quote}'

        targets_alt = '|'.join(re.escape(t) for t in _REWRITE_TARGETS)
        # (src|href)="(index.xxx)" 或 ='(index.xxx)'
        attr_re = re.compile(
            r'\b(src|href)=(["\'])(' + targets_alt + r')\2',
            re.IGNORECASE,
        )
        html = attr_re.sub(
            lambda m: f'{m.group(1)}={m.group(2)}{m.group(3)}?v={build_hash}{m.group(2)}',
            html,
        )

        # (B) cache-buster JS:hook fetch + XHR,讓 Engine 內部 fetch 也帶 ?v=
        cb_script = (
            '<script>'
            '(function(){'
            f'var V="{build_hash}";'
            'var rx=/(^|\\/)index\\.(wasm|pck|side\\.wasm|audio\\.worklet\\.js|audio\\.position\\.worklet\\.js)(\\?|$)/;'
            'function tag(u){'
            '  if(typeof u!=="string")return u;'
            '  if(u.indexOf("v="+V)>=0)return u;'
            '  if(!rx.test(u))return u;'
            '  return u+(u.indexOf("?")>=0?"&":"?")+"v="+V;'
            '}'
            'var of=window.fetch.bind(window);'
            'window.fetch=function(i,init){'
            '  try{'
            '    if(typeof i==="string")i=tag(i);'
            '    else if(i&&i.url){var nu=tag(i.url);if(nu!==i.url)i=new Request(nu,i);}'
            '  }catch(e){}'
            '  return of(i,init);'
            '};'
            'var oo=XMLHttpRequest.prototype.open;'
            'XMLHttpRequest.prototype.open=function(m,u){'
            '  try{if(typeof u==="string")arguments[1]=tag(u);}catch(e){}'
            '  return oo.apply(this,arguments);'
            '};'
            'console.log("[cache-buster] build="+V);'
            '})();'
            '</script>'
        )
        # 注入到第一個 <script ...> 之前(在 index.js 載入之前 patch fetch)
        marker = '<script'
        idx = html.find(marker)
        if idx != -1:
            html = html[:idx] + cb_script + html[idx:]

        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--dir', type=str, default='godot_demo/web')
    p.add_argument('--bind', type=str, default='127.0.0.1')
    args = p.parse_args()

    serve_dir = Path(args.dir).resolve()
    if not serve_dir.is_dir():
        print(f'[godot-web] target dir not found: {serve_dir}', file=sys.stderr)
        return 1

    os.chdir(serve_dir)
    # 用 ThreadingHTTPServer 而非 HTTPServer:
    #   單執行緒 server 在抓 35MB WASM 時會卡住,Streamlit / 第二個分頁
    #   的 socket 檢查會 timeout 顯示 "server down"。多執行緒每個請求
    #   獨立 socket → 不會互卡。
    httpd = ThreadingHTTPServer((args.bind, args.port), NoCacheGodotHandler)
    httpd.daemon_threads = True
    print(f'[godot-web] serving {serve_dir} at http://{args.bind}:{args.port}/  (no-cache, threaded)', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('[godot-web] stopped')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
