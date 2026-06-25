"""本機預覽 Godot web build（含 COOP/COEP，Godot 4 web 需要）。
用法: python serve_godot_local.py  → 開 http://localhost:8765/?booth=1
（port 必須跟 streamlit_app.py 的 GODOT_LOCAL_URL 一致）
"""
import http.server, socketserver, os
os.chdir(os.path.join(os.path.dirname(__file__), 'godot_demo', 'web'))
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
PORT = 8765
with socketserver.TCPServer(('', PORT), H) as httpd:
    print(f'Serving godot_demo/web at http://localhost:{PORT}')
    httpd.serve_forever()
