"""The page a node serves.

Read from a sofa. The node is the thing that matters and it runs whether
anybody is looking; this is a window onto it.

Standard library only, one file, nothing fetched. A picture upload is the one
thing that arrives as bytes rather than text, and it is handled by the node
rather than the browser, because turning a photograph into thirty-two pixels
is the sort of decision that should be made once in one place.
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class WebView:
    def __init__(self, port: int = 8080, host: str = "0.0.0.0") -> None:
        self.port, self.host = port, host
        self.inbox: "queue.Queue" = queue.Queue()
        self._listeners: list = []
        self._lock = threading.Lock()
        self._latest = "{}"
        self._server = None

    def start(self) -> None:
        view = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def handle(self):
                try:
                    super().handle()
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                    pass

            def do_GET(self):
                if self.path.startswith("/events"):
                    return view._stream(self)
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                if self.path.startswith("/face"):
                    view.inbox.put(("face", raw))
                else:
                    view.inbox.put(("do", raw.decode("utf-8", "replace").strip()))
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()

    def _stream(self, handler) -> None:
        channel: "queue.Queue[str]" = queue.Queue(maxsize=16)
        with self._lock:
            self._listeners.append(channel)
            first = self._latest
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()
        try:
            handler.wfile.write(f"data: {first}\n\n".encode())
            handler.wfile.flush()
            while True:
                try:
                    handler.wfile.write(f"data: {channel.get(timeout=20)}\n\n".encode())
                except queue.Empty:
                    handler.wfile.write(b": still here\n\n")
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with self._lock:
                if channel in self._listeners:
                    self._listeners.remove(channel)

    def publish(self, snapshot: dict) -> None:
        message = json.dumps(snapshot, separators=(",", ":"))
        with self._lock:
            if message == self._latest:
                return
            self._latest = message
            listeners = list(self._listeners)
        for channel in listeners:
            try:
                channel.put_nowait(message)
            except queue.Full:
                pass

    def drain(self) -> list:
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>hearsay</title>
<style>
:root{--paper:#f2efe9;--panel:#e8e3d9;--ink:#1b1a18;--soft:#5f5a52;
      --faint:#8b857b;--rule:#ddd8cf;--red:#b4472f;
      --serif:ui-serif,Charter,Georgia,serif;
      --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);
     font-size:17px;line-height:1.5}
.page{max-width:34rem;margin:0 auto;padding:0 1rem 4rem}
header{display:flex;align-items:baseline;justify-content:space-between;
       gap:.6rem;padding:1.1rem 0 .8rem;border-bottom:1px solid var(--rule)}
h1{font-size:1.15rem;margin:0;font-weight:600;display:flex;align-items:center;gap:.4em}
h1 svg{width:1.1em;height:1.1em;color:var(--red)}
.tally{font-family:var(--mono);font-size:.72rem;color:var(--faint);text-align:right}
form.say{display:flex;gap:.5rem;margin:1rem 0 .3rem}
input,textarea,button{font:inherit}
#writer{margin:.8rem 0;border-top:1px solid var(--rule);padding-top:.7rem}
#writer summary{cursor:pointer;color:var(--red);font-size:.9rem}
#writer label{display:block;font-size:.8rem;color:var(--faint);margin:.6rem 0 0}
#writer input,#writer textarea{width:100%;background:var(--panel);
  border:1px solid var(--rule);color:var(--ink);padding:.35rem .45rem;
  border-radius:2px;font-size:.9rem;margin-top:.15rem}
#writer textarea{font-family:var(--mono);font-size:.82rem;line-height:1.5;
  margin-top:.6rem;resize:vertical}
.prow{display:flex;gap:.7rem;align-items:baseline;margin-top:.5rem}
.prow button{background:var(--panel);border:1px solid var(--rule);
  color:var(--ink);padding:.3rem .8rem;border-radius:2px;cursor:pointer}
textarea{flex:1;resize:none;height:3.1rem;background:#fff;border:1px solid var(--rule);
         color:var(--ink);padding:.5rem .6rem;border-radius:3px;font-size:.95rem;min-width:0}
textarea:focus{outline:2px solid var(--red);outline-offset:1px}
button{background:var(--panel);border:1px solid var(--rule);color:var(--ink);
       padding:.5rem .9rem;border-radius:3px;cursor:pointer}
button:hover{background:#e0dacd}
.left{font-family:var(--mono);font-size:.72rem;color:var(--faint);margin:0 0 1.4rem}
.left b{color:var(--red);font-weight:600}
article{display:flex;gap:.7rem;padding:.85rem 0;border-bottom:1px solid var(--rule)}
article canvas{width:44px;height:44px;flex:none;image-rendering:pixelated;
               border:1px solid var(--rule);background:var(--panel)}
.who{display:flex;gap:.45rem;align-items:baseline;flex-wrap:wrap}
.who b{font-weight:600}
.who .addr,.who .when{font-family:var(--mono);font-size:.7rem;color:var(--faint)}
.body{margin:.15rem 0 .2rem;word-wrap:break-word}
.trail{font-size:.76rem;color:var(--red)}
.trail.direct{color:var(--faint)}
.aside{font-size:.8rem;color:var(--soft);border-left:2px solid var(--rule);
       padding-left:.7rem;margin:.9rem 0}
h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;
   color:var(--faint);margin:2rem 0 .4rem;font-weight:600}
.me{display:flex;gap:.7rem;align-items:center;margin:.4rem 0 0}
.me canvas{width:56px;height:56px;image-rendering:pixelated;border:1px solid var(--rule)}
.me input[type=text]{background:#fff;border:1px solid var(--rule);padding:.4rem .5rem;
                     border-radius:3px;width:11rem}
.me label{font-size:.8rem;color:var(--soft);cursor:pointer;text-decoration:underline;
          text-decoration-color:var(--red)}
.me input[type=file]{display:none}
.note{font-size:.78rem;color:var(--faint);margin:.4rem 0 0}
</style></head><body>
<div class="page">
<header>
  <h1><svg viewBox="0 0 32 32" aria-hidden="true"><g fill="none" stroke="currentColor"
    stroke-width="2.6" stroke-linecap="round"><path d="M4 24 Q10 10 16 24"/>
    <path d="M16 24 Q22 10 28 24"/></g><g fill="currentColor"><circle cx="4" cy="25" r="2.6"/>
    <circle cx="16" cy="25" r="2.6"/><circle cx="28" cy="25" r="2.6"/></g></svg>hearsay</h1>
  <div class="tally" id="tally"></div>
</header>

<details id="writer">
  <summary>write a page</summary>
  <label>a short name <input id="pname" maxlength="32" placeholder="bread"></label>
  <label>the title <input id="ptitle" maxlength="64" placeholder="Bread"></label>
  <textarea id="pbody" rows="9" placeholder="# Bread&#10;&#10;Thursdays, from about seven, until it is gone.&#10;&#10;=&gt; tides the tide table"></textarea>
  <div class="prow">
    <button type="button" onclick="putPage()">put it on the shelf</button>
    <span id="pcount" class="hint"></span>
  </div>
  <p class="hint">Four kilobytes at most, six kinds of line:
    <a href="/page/here/writing">how to write one</a>. A name you have used
    before replaces that page everywhere it has reached.</p>
</details>

<p id="replying"></p>
<form class="say" id="say">
  <textarea id="text" maxlength="140" placeholder="say something"></textarea>
  <button>post</button>
</form>
<p class="left" id="left"></p>

<div id="feed"></div>

<h2>you</h2>
<div class="me">
  <canvas id="myface" width="32" height="32"></canvas>
  <div>
    <input type="text" id="myname" maxlength="18" placeholder="a name">
    <button id="rename" type="button">save</button>
    <div><label for="pick">use a photograph</label>
      <input type="file" id="pick" accept="image/*"></div>
  </div>
</div>
<p class="note" id="mynote"></p>

<h2>on the air</h2>
<div id="log" class="left"></div>
</div>
<script>
let state = {};

/* Faces arrive as a palette and a pixel per byte, which is what the radio
   carries. Drawing them is a loop, not a library. */
function paint(canvas, face){
  const g = canvas.getContext('2d');
  const n = Math.round(Math.sqrt(face.pixels.length));
  canvas.width = n; canvas.height = n;
  const img = g.createImageData(n, n);
  for(let i = 0; i < face.pixels.length; i++){
    const hex = face.colours[face.pixels[i]] || '#000000';
    img.data[i*4]   = parseInt(hex.slice(1,3),16);
    img.data[i*4+1] = parseInt(hex.slice(3,5),16);
    img.data[i*4+2] = parseInt(hex.slice(5,7),16);
    img.data[i*4+3] = 255;
  }
  g.putImageData(img, 0, 0);
}

function ago(seconds){
  if(seconds < 60) return 'just now';
  const m = Math.round(seconds/60);
  if(m < 60) return m + ' min ago';
  const h = Math.round(m/60);
  if(h < 24) return h + ' h ago';
  return Math.round(h/24) + ' d ago';
}

const escaped = s => s.replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));

function render(){
  document.getElementById('tally').innerHTML =
    `${state.holding} held &middot; ${state.faces} faces<br>${state.peers} within earshot`;
  const left = document.getElementById('left');
  left.innerHTML = `<b>${state.airtime}</b> of the hour left`
    + (state.waiting ? ` &middot; ${state.waiting} line(s) waiting for it` : '');

  document.getElementById('feed').innerHTML = (state.feed||[]).map((p, i) => `
    <article>
      <canvas data-face="${i}"></canvas>
      <div>
        <div class="who"><b>${escaped(p.name)}</b>
          <span class="addr">${p.author}</span>
          <span class="when">${ago(p.age)}</span></div>
        ${p.answers ? (p.to && p.to.body
            ? `<div class="answering"><b>${escaped(p.to.name)}</b> ${escaped(p.to.body)}</div>`
            : `<div class="answering gone">answering something that has not
               reached this node</div>`) : ''}
        <div class="body">${escaped(p.body)}</div>
        <div class="trail ${p.hops.length ? '' : 'direct'}">${
          p.hops.length ? 'carried by ' + p.hops.map(escaped).join(', ')
                        : 'heard directly'}<button class="reply"
          onclick="replyTo('${p.id}', '${escaped(p.name).replace(/'/g, "\\'")}')"
          >reply</button></div>
      </div>
    </article>`).join('') || '<p class="aside">Nothing yet. Anything you post waits here until somebody comes within earshot.</p>';

  (state.feed||[]).forEach((p, i) => {
    const c = document.querySelector(`canvas[data-face="${i}"]`);
    if(c && p.face) paint(c, p.face);
  });

  if(state.me){
    paint(document.getElementById('myface'), state.me.face);
    const box = document.getElementById('myname');
    if(document.activeElement !== box) box.value = state.me.name;
    document.getElementById('mynote').textContent =
      `${state.me.author} \u00b7 a name is not checked by anything, which is why the address is next to it`;
  }
  document.getElementById('log').innerHTML =
    (state.log||[]).slice(-12).reverse().map(l => escaped(l)).join('<br>');
}

/* One shape of order, so the page works whether it is being served by a node
   of its own or by the loraline app hosting it. The panel key is ignored by
   the standalone node and is how the host knows where to send it.

   The page used to post plain text to /do, which the standalone node
   understood and the host did not, so every button on this page did nothing
   the moment it was hosted. */
const post = o => fetch('/do', {method:'POST',
  body: JSON.stringify(Object.assign({panel:'hearsay'}, o))});
const send = line => {
  const [verb, ...rest] = line.split(' ');
  post({do: verb, text: rest.join(' ')});
};

document.getElementById('say').onsubmit = e => {
  e.preventDefault();
  const box = document.getElementById('text');
  if(box.value.trim()){
    if(answering) post({do:'reply', to: answering, text: box.value.trim()});
    else send('say ' + box.value.trim());
  }
  box.value = '';
  stopReplying();
};
document.getElementById('rename').onclick = () =>
  send('name ' + document.getElementById('myname').value.trim());

/* The node turns the photograph into thirty-two pixels: that decision is made
   once, in one place, rather than differently in every browser.

   What happens here is only a size guard. A phone takes twelve megapixel
   photographs and there is no sense pushing sixteen megabytes of base64 at a
   thing that is going to throw away all but a thousand pixels of it. Two
   hundred and fifty six square is far more than the reduction can use, so it
   cannot change the outcome. */
const body = () => document.getElementById('pbody');

/* Which post, if any, the next thing you write is an answer to. */
let answering = null;

function replyTo(id, name){
  answering = id;
  const strip = document.getElementById('replying');
  strip.style.display = 'block';
  strip.innerHTML = `answering <b>${name}</b>`
    + `<button type="button" onclick="stopReplying()">not any more</button>`;
  document.getElementById('text').focus();
}

function stopReplying(){
  answering = null;
  document.getElementById('replying').style.display = 'none';
}

function putPage(){
  const name = document.getElementById('pname').value.trim();
  const title = document.getElementById('ptitle').value.trim();
  const text = body().value;
  if(!name || !text.trim()){
    document.getElementById('pcount').textContent = 'it needs a name and something on it';
    return;
  }
  post({do:'put', name, title, text});
  document.getElementById('pname').value = '';
  document.getElementById('ptitle').value = '';
  body().value = '';
  document.getElementById('writer').open = false;
}

/* Four kilobytes is not a number anybody can feel, so show what is left. */
document.addEventListener('input', ev => {
  if(ev.target.id !== 'pbody') return;
  const left = 4096 - ev.target.value.length;
  document.getElementById('pcount').textContent =
    left < 0 ? `${-left} too many` : `${left} characters left`;
});

document.getElementById('pick').onchange = ev => {
  const file = ev.target.files[0];
  if(!file) return;
  const note = document.getElementById('mynote');
  note.textContent = 'sending the picture over\u2026';
  const reader = new FileReader();
  reader.onload = () => {
    const img = new Image();
    img.onload = () => {
      const edge = Math.min(256, Math.max(img.width, img.height));
      const scale = edge / Math.max(img.width, img.height);
      const c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(img.width*scale));
      c.height = Math.max(1, Math.round(img.height*scale));
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      post({do:'face', bytes: c.toDataURL('image/png').split(',')[1]});
      note.textContent = 'sent; it will appear in a moment\u2026';
    };
    img.onerror = () => { note.textContent = 'that file is not a picture.'; };
    img.src = reader.result;
  };
  reader.onerror = () => { note.textContent = 'could not read that file.'; };
  reader.readAsDataURL(file);
  ev.target.value = '';
};

new EventSource('/events').onmessage = m => { state = JSON.parse(m.data); render(); };
</script></body></html>
"""
