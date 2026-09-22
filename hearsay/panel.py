"""hearsay, riding on the loraline app.

The node is unchanged. What changes is that it no longer owns a radio, a
process or a port: loraline owns those, and hands this whatever arrives with
its tag on it.

This is the panel that is always on. A game can stop when nobody is looking at
it; something holding other people's messages cannot, because the entire
mechanism is being there when somebody walks past.
"""

from __future__ import annotations

import io
import time

from loraline.host import Panel

import os as _os

from . import manual
from .node import APP, Node, snapshot
from .page import Page, to_html
from .profile import describe, from_image
from .store import Store
from .web import PAGE


class HearsayPanel(Panel):
    tag = APP
    title = "hearsay"
    route = "/hearsay"
    always = True

    def __init__(self) -> None:
        self.node = None
        self.host = None

    def start(self, host) -> None:
        self.host = host
        pocket = str(getattr(host.identity, "path", "")) or ""
        store = Store().load(pocket + ".hearsay.json" if pocket
                             else _beside_identity())
        # Whatever face we had, if we had one. Building a fresh default here
        # stamped it with the current time, which always wins against the one
        # on disk, so a photograph lasted exactly until the next restart.
        # The picture comes from loraline, which holds it for everything. What
        # hearsay adds is a signature, because its readers are strangers three
        # hops away rather than people in earshot: one picture, two ways of
        # getting it to somebody.
        theirs = self.borrowed(host)
        me = store.face_of(host.identity.address)
        if me is None or not me.verify():
            me = describe(host.identity, host.nick, pixels=theirs[0],
                          colours=theirs[1], when=int(time.time()))
            store.meet_face(me)
        elif theirs[0] is not None and list(me.pixels) != list(theirs[0]):
            me = describe(host.identity, host.nick, pixels=theirs[0],
                          colours=theirs[1], when=int(time.time()))
            store.meet_face(me)
        elif me.name != host.nick:
            # A name changed in the app should follow through, but the picture
            # should not be thrown away with it.
            me = describe(host.identity, host.nick, pixels=me.pixels,
                          colours=me.colours, when=int(time.time()))
            store.meet_face(me)
        self.node = Node(client=host.client, identity=host.identity,
                         store=store, me=me)
        kept = len(store)
        self.node.note(f"Carrying {kept} post(s) from before." if kept
                       else "Nothing in the pocket yet.")

    def borrowed(self, host):
        """The picture loraline is holding for us.

        One picture, two ways of getting it to somebody: loraline hands it to
        people in earshot, and this wraps the same pixels in a signature so
        strangers three hops away can check whose it is.
        """
        try:
            from loraline import face as lface
            picture = host.face()
            if not picture:
                return (None, None)
            return (lface.unpack(picture), lface.colours_of(picture))
        except Exception:
            return (None, None)

    def follow_face(self, host) -> None:
        """Pick up a change made in loraline, without asking every tick."""
        pixels, colours = self.borrowed(host)
        if pixels is None or self.node is None:
            return
        if list(self.node.me.pixels) == list(pixels):
            return
        self.node.set_face(self.node.me.name, pixels, colours)

    def heard(self, src: str, payload: str) -> None:
        if self.node is not None:
            self.node.heard(src, payload)

    def tick(self, now: float) -> None:
        """Offer what we are holding, and hand over what was asked for.

        Deliberately not the node's own loop: the host pumps the radio, so all
        that is left here is deciding what to say next.
        """
        if self.node is None:
            return
        # A face is changed once and then almost never, so this is a cheap
        # comparison every few seconds rather than anything clever.
        if now - getattr(self, "_checked", 0.0) > 5.0:
            self._checked = now
            self.follow_face(self.host)
        self.node.offer(now)
        self.node.pump_outbox()
        if self.node.dirty and now - self.node.last_save > 5.0:
            self.node.store.save()
            self.node.dirty, self.node.last_save = False, now

    def handle(self, order: dict) -> None:
        if self.node is None:
            return
        what = order.get("do")
        if what == "say":
            text = (order.get("text") or "").strip()
            if text and not self.node.say(text):
                self.node.note("nothing to say", "warn")
        elif what == "name":
            name = (order.get("text") or "").strip()
            if name:
                self.node.set_face(name)
        elif what == "ask":
            if not self.node.ask_for(order.get("at", "")):
                self.node.note("already asking, or it is already here", "muted")
        elif what == "reply":
            if not self.node.say(order.get("text", ""),
                                 answers=order.get("to", "")):
                self.node.note("nothing to say", "warn")
        elif what == "put":
            if not self.node.put(order.get("name", ""), order.get("title", ""),
                                 order.get("text", "")):
                self.node.note("that page would not go", "warn")
        elif what == "face":
            # Setting a picture is loraline's job now, so this hands it over
            # and the change comes back the same way anybody else's would.
            raw = order.get("bytes")
            if raw and self.host is not None:
                try:
                    import base64
                    from loraline import face as lface
                    self.host.set_face(lface.from_image(
                        io.BytesIO(base64.b64decode(raw))))
                    self.follow_face(self.host)
                except Exception as exc:
                    self.node.note(f"that picture would not go: {exc}", "warn")

    def snapshot(self) -> dict:
        if self.node is None:
            return {"holding": 0, "feed": [], "log": []}
        return snapshot(self.node, time.time())

    def owns(self, path: str) -> bool:
        here = "/" + path.lstrip("/").split("?")[0]
        return (here.rstrip("/") in (self.route, "/pages")
                or here.startswith("/page/"))

    def page(self, path: str = "") -> str:
        """The reader, when a path names one; otherwise the feed.

        Every page is turned into markup here, by the node, from six kinds of
        line. Nothing a document can say produces a reference to anywhere off
        the radio, which is why an ordinary browser is safe to read it with:
        it never sees anything this did not write.
        """
        if self.node is None:
            return PAGE
        here = "/" + path.lstrip("/").split("?")[0]
        if here.rstrip("/") == "/pages":
            return shelf(self.node)
        if "/page/" not in path:
            return PAGE
        at = path.partition("/page/")[2].strip("/")
        # An address on its own means their front page, so somebody can be
        # pointed at a person rather than at a document.
        if at and "/" not in at:
            at = at + "/index"
        who, _, what = at.partition("/")
        if who == manual.HOME:
            return builtin(what or "index", self.node)
        return reader(at, self.node.store.page_at(at), self.node)


def _beside_identity() -> str:
    from loraline import crypto
    return str(crypto.DEFAULT_PATH) + ".hearsay.json"


READER = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{/*THEME*/--mono:ui-monospace,Menlo,Consolas,monospace;}}
body{{margin:0;background:var(--paper);color:var(--ink);
  font:18px/1.6 ui-serif,Charter,Georgia,serif}}
.page{{max-width:38rem;margin:0 auto;padding:0 1.3rem 5rem}}
.bar{{display:flex;gap:.8rem;align-items:baseline;padding:1.1rem 0 .7rem;
  border-bottom:1px solid var(--rule);font:12px var(--mono);color:var(--faint)}}
.bar a{{color:var(--red);text-decoration:none}}
h1{{font-size:1.9rem;margin:1.6rem 0 .6rem;line-height:1.2}}
h2{{font-size:1.2rem;margin:2rem 0 .5rem}}
blockquote{{margin:0 0 1rem;padding-left:1rem;border-left:2px solid var(--rule);
  color:var(--soft)}}
pre.lit{{font:13px/1.5 var(--mono);background:#e8e3d9;padding:.8rem 1rem;
  overflow-x:auto;border-left:2px solid var(--red)}}
p.link a{{color:var(--ink);text-decoration-color:var(--red)}}
p.link i{{font-style:normal;font-size:.75rem;color:var(--faint);
  font-family:var(--mono)}}
.trail{{font:12px var(--mono);color:var(--faint);margin-top:2.5rem;
  padding-top:.8rem;border-top:1px solid var(--rule)}}
.gone{{color:var(--soft)}}
</style></head><body><div class="page">
<div class="bar"><a href="/hearsay">&larr; hearsay</a>
<a href="/pages">everything held</a><span>{at}</span></div>
{body}
<p class="trail">{trail}</p>
<script>
/* The braces are doubled because this whole page is a str.format template.
   Single ones raised, the host caught it, and the reader quietly served the
   feed instead. */
function ask(at){{
  fetch('/do', {{method:'POST',
    body: JSON.stringify({{panel:'hearsay', do:'ask', at}})}});
  document.querySelector('button.ask').outerHTML =
    '<span class="gone">Asking after it whenever somebody comes within earshot.</span>';
}}
</script>
</div></body></html>"""


def _when(written: int) -> str:
    """The date a page was written, plainly.

    The day is what matters and the minute is noise, except today, when the
    minute is the whole of it.
    """
    from datetime import datetime
    if not written:
        return "undated"
    try:
        made = datetime.fromtimestamp(written)
    except (OSError, OverflowError, ValueError):
        return "undated"
    today = datetime.now()
    if made.date() == today.date():
        return made.strftime("today at %H:%M")
    if (today.date() - made.date()).days == 1:
        return "yesterday"
    if made.year == today.year:
        return made.strftime("%-d %B") if _os.name == "posix" \
            else made.strftime("%d %B").lstrip("0")
    return made.strftime("%-d %B %Y") if _os.name == "posix" \
        else made.strftime("%d %B %Y").lstrip("0")


def reader(at: str, held, node) -> str:
    """One page, or an honest account of why there is not one.

    A page you do not hold is not an error. It is somewhere the network has
    not carried anything to you from yet, which is a different thing and
    should read like one.
    """
    from .page import escape
    if held is None:
        # Everything else here is offered rather than asked for, which leaves
        # a link to a page nobody carried as a dead end. This is the way out
        # of it: say you want it, and wait for somebody holding it.
        wanted = at in getattr(node.store, "asked_for", set())
        button = ('<p class="gone">Asking after it whenever somebody comes '
                  'within earshot.</p>' if wanted else
                  f'<p><button class="ask" onclick="ask(\'{escape(at)}\')">'
                  f'ask for it</button></p>')
        return READER.format(
            title=escape(at), at=escape(at),
            body='<h1>Nothing here yet</h1>'
                 '<p class="gone">No page by that name has been carried to this '
                 'node. It may not exist, or nobody who has it has been within '
                 'earshot.</p>' + button,
            trail="")
    who = node.who(held.author)
    # When it was written, which is signed along with the words. A page can
    # sit on somebody's shelf for weeks before it reaches you, so "the bread
    # is ready Thursday" means nothing without knowing which Thursday.
    when = _when(held.written)
    trail = (f"by {escape(who)} ({escape(held.author)}), {when}, carried by "
             + ", ".join(escape(node.who(h)) for h in held.hops)
             if held.hops else
             f"by {escape(who)} ({escape(held.author)}), {when}, heard directly")
    who_of = lambda address: node.who(address)
    shown = f"{who_of(held.author)}/{held.name}"
    return READER.format(title=escape(held.title), at=escape(shown),
                         body=to_html(held, naming=who_of), trail=trail)


SHELF = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pages</title><style>
:root{/*THEME*/--mono:ui-monospace,Menlo,Consolas,monospace;}
body{margin:0;background:var(--paper);color:var(--ink);
  font:17px/1.55 ui-serif,Charter,Georgia,serif}
.page{max-width:38rem;margin:0 auto;padding:0 1.3rem 5rem}
.bar{display:flex;gap:.8rem;align-items:baseline;padding:1.1rem 0 .7rem;
  border-bottom:1px solid var(--rule);font:12px var(--mono);color:var(--faint)}
.bar a{color:var(--red);text-decoration:none}
h1{font-size:1.5rem;margin:1.5rem 0 .3rem}
.who{display:flex;gap:.6rem;align-items:center;margin:1.8rem 0 .3rem}
.who canvas{width:30px;height:30px;image-rendering:pixelated;
  border:1px solid var(--rule);flex:none}
.who b{font-size:1rem}
.who span{font:11px var(--mono);color:var(--faint)}
ul{list-style:none;padding:0;margin:0 0 0 2.4rem}
li{padding:.3rem 0;border-bottom:1px solid var(--rule)}
li a{color:var(--ink);text-decoration-color:var(--red)}
li i{font-style:normal;font:11px var(--mono);color:var(--faint);margin-left:.4rem}
.empty{color:var(--soft)}
</style></head><body><div class="page">
<div class="bar"><a href="/hearsay">&larr; hearsay</a><span>everything held</span></div>
<h1>Pages on this node</h1>
{body}
<script>
const FACES = {faces};
for(const [id, face] of Object.entries(FACES)){
  const c = document.getElementById('f' + id);
  if(!c || !face.pixels.length) continue;
  const n = Math.round(Math.sqrt(face.pixels.length));
  c.width = n; c.height = n;
  const g = c.getContext('2d'), img = g.createImageData(n, n);
  for(let i = 0; i < face.pixels.length; i++){
    const hex = face.colours[face.pixels[i]] || '#000000';
    img.data[i*4]=parseInt(hex.slice(1,3),16);
    img.data[i*4+1]=parseInt(hex.slice(3,5),16);
    img.data[i*4+2]=parseInt(hex.slice(5,7),16);
    img.data[i*4+3]=255;
  }
  g.putImageData(img,0,0);
}
</script>
</div></body></html>"""


BUILTIN = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{/*THEME*/--mono:ui-monospace,Menlo,Consolas,monospace;}}
body{{margin:0;background:var(--paper);color:var(--ink);
  font:18px/1.6 ui-serif,Charter,Georgia,serif}}
.page{{max-width:38rem;margin:0 auto;padding:0 1.3rem 5rem}}
.bar{{display:flex;gap:.8rem;align-items:baseline;padding:1.1rem 0 .7rem;
  border-bottom:1px solid var(--rule);font:12px var(--mono);color:var(--faint)}}
.bar a{{color:var(--red);text-decoration:none}}
h1{{font-size:1.9rem;margin:1.6rem 0 .6rem;line-height:1.2}}
h2{{font-size:1.2rem;margin:2rem 0 .5rem}}
blockquote{{margin:0 0 1rem;padding-left:1rem;border-left:2px solid var(--rule);
  color:var(--soft)}}
pre.lit{{font:13px/1.5 var(--mono);background:#e8e3d9;padding:.8rem 1rem;
  overflow-x:auto;border-left:2px solid var(--red)}}
p.link a{{color:var(--ink);text-decoration-color:var(--red)}}
p.link i{{font-style:normal;font-size:.75rem;color:var(--faint);
  font-family:var(--mono)}}
.trail{{font:12px var(--mono);color:var(--faint);margin-top:2.5rem;
  padding-top:.8rem;border-top:1px solid var(--rule)}}
</style></head><body><div class="page">
<div class="bar"><a href="/hearsay">&larr; hearsay</a>
<a href="/pages">everything held</a><span>{at}</span></div>
{body}
<p class="trail">Came with the program. Costs no radio time and is never sent
to anybody.</p>
</div></body></html>"""


def builtin(name: str, node) -> str:
    """One of the pages that came with the program.

    Rendered by the same six-line reader as anything carried, so a built-in
    page and a written one look the same and follow the same rules.
    """
    from .page import escape
    if not manual.has(name):
        return BUILTIN.format(title="Nothing here", at=escape(manual.HOME + "/" + name),
                              body="<h1>No such page</h1>")
    shown = Page(author=manual.HOME, name=name, title=manual.titled(name),
                 written=0, body=manual.body(name))
    return BUILTIN.format(title=escape(shown.title),
                          at=escape(manual.HOME + "/" + name),
                          body=to_html(shown, naming=lambda a: a))


def shelf(node) -> str:
    """Everything held, by whoever wrote it.

    Nobody should ever have to type an address. An address is the true name of
    a person and cannot be anything else, but typing one is not how anybody
    would want to find a page: this is, and it is a list of people you have
    already heard of with their faces beside them.
    """
    import json
    from .page import escape
    by_author = {}
    for page in node.store.shelf():
        by_author.setdefault(page.author, []).append(page)
    here = ('<div class="who"><div><b>came with the program</b><br>'
            '<span>never sent to anybody</span></div></div><ul>'
            + "".join(f'<li><a href="/page/{manual.HOME}/{n}">{t}</a>'
                      f'<i>{n}</i></li>' for n, t in manual.listing())
            + "</ul>")
    if not by_author:
        return (SHELF.replace("{body}", here + '<p class="empty">Nothing carried '
                              'yet. Pages arrive the way posts do, by somebody '
                              'carrying them past.</p>').replace("{faces}", "{}"))

    faces, out = {}, []
    for author, pages in sorted(by_author.items(),
                                key=lambda kv: node.who(kv[0]).lower()):
        face = node.store.face_of(author)
        faces[author] = ({"pixels": face.pixels, "colours": list(face.colours)}
                         if face else {"pixels": [], "colours": []})
        out.append(f'<div class="who"><canvas id="f{escape(author)}"></canvas>'
                   f'<div><b>{escape(node.who(author))}</b><br>'
                   f'<span>{escape(author)}</span></div></div><ul>')
        for page in sorted(pages, key=lambda p: p.name):
            trail = (" carried by " + ", ".join(node.who(h) for h in page.hops)
                     if page.hops else "")
            out.append(f'<li><a href="/page/{escape(page.at)}">'
                       f'{escape(page.title)}</a>'
                       f'<i>{_when(page.written)}'
                       f'{escape(trail)}</i></li>')
        out.append("</ul>")
    return (SHELF.replace("{body}", here + "\n".join(out))
                 .replace("{faces}", json.dumps(faces, separators=(",", ":"))))
