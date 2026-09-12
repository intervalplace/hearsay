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

from .node import APP, Node, snapshot
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
        me = store.face_of(host.identity.address)
        if me is None or not me.verify():
            me = describe(host.identity, host.nick, when=int(time.time()))
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
        elif what == "face":
            raw = order.get("bytes")
            if raw:
                try:
                    import base64
                    pixels, colours = from_image(io.BytesIO(base64.b64decode(raw)))
                    self.node.set_face(self.node.me.name, pixels, colours)
                except Exception as exc:
                    self.node.note(f"that picture would not go: {exc}", "warn")

    def snapshot(self) -> dict:
        if self.node is None:
            return {"holding": 0, "feed": [], "log": []}
        return snapshot(self.node, time.time())

    def page(self) -> str:
        return PAGE


def _beside_identity() -> str:
    from loraline import crypto
    return str(crypto.DEFAULT_PATH) + ".hearsay.json"
