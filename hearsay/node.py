"""A hearsay node.

It holds what it has heard and hands it on to whoever comes into range. There
is nothing else to it: no routing, no server, no schedule. A post moves because
a person did.

The thing this has to get right is not sending, but restraint. A node has
thirty-six seconds of airtime an hour and an eager one would spend the lot
telling its neighbours things they already knew. So every line is costed before
it goes out, the budget can refuse it, and a refused line waits rather than
disappearing: loraline retransmits chat until it is acknowledged, but nothing
retransmits application frames, which is a lesson that cost a stuck game once
already.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field

from loraline import crypto, protocol as proto
from loraline.client import Client
from loraline.crypto import GROUP, Identity, Keyring
from loraline.session import AppEvent, MessageEvent, SystemEvent
from loraline.transport import (Link, LoRaInterface, RadioConfig,
                                TCPClientInterface, TCPServerInterface)

from .page import Page, heading_of, name_from, write as write_page
from .post import Post, write
from .profile import Profile, describe, from_image
from .store import (ASK_PAGE, FACE, GIVE, GIVE_PAGE, HAVE, PAGES, Store,
                    WANT, WANT_PAGE)

APP = "hearsay"
BANDS = {"eu868": dict(channel=18, sf=7, power=8, duty=0.01),
         "us915": dict(channel=65, sf=10, power=22, duty=1.0),
         "au915": dict(channel=65, sf=10, power=22, duty=1.0)}

# How often to say what we are holding, when somebody is about. Often enough
# that a walk past is not wasted, rarely enough that two nodes sitting in the
# same room do not spend the hour greeting each other.
OFFER_EVERY = 90.0
QUIET_OFFER = 900.0      # when nobody has been heard for a while


@dataclass
class Node:
    """The daemon. Everything it does is decide what to say next."""

    client: Client
    identity: Identity
    store: Store
    me: Profile
    outbox: list = field(default_factory=list)     # lines waiting for airtime
    log: list = field(default_factory=list)
    last_offer: dict = field(default_factory=dict)  # peer -> when we last told them
    sent: int = 0
    held_back: int = 0
    dirty: bool = False
    last_save: float = 0.0
    greeted: set = field(default_factory=set)   # who was in range last time

    # -- saying things -----------------------------------------------------

    def note(self, text: str, role: str = "muted") -> None:
        self.log.append((time.time(), text, role))
        del self.log[:-120]

    def queue(self, line: str) -> None:
        """Join the queue. Nothing goes out until the radio can afford it."""
        if line not in self.outbox:
            self.outbox.append(line)

    def affordable(self, line: str) -> bool:
        """Would this fit in what is left of the hour?

        Asked before every line, because an application frame that the budget
        refuses is simply gone: nothing here is retransmitted for us.
        """
        frame = proto.data(self.client.session.address, GROUP, APP, line)
        return self.client.link.can_send(frame, GROUP)

    def pump_outbox(self) -> None:
        """One line at a time, while the radio will take it."""
        while self.outbox:
            line = self.outbox[0]
            if not self.affordable(line):
                self.held_back += 1
                return
            self.outbox.pop(0)
            self.client.session.send_app(APP, line)
            self.sent += 1

    # -- meeting somebody --------------------------------------------------

    def offer(self, now: float) -> None:
        """Tell whoever is about what we are holding.

        One line for everybody rather than one each: the radio is a broadcast
        and a second copy of the same list would be pure waste.
        """
        peers = self.client.session.online_peers()
        # Somebody who has just walked into range should not wait out the rest
        # of a ninety second cycle before hearing what anybody is holding.
        # Two people in a room watching nothing happen assume it is broken.
        here = {p.address for p in peers}
        arrived = here - self.greeted
        self.greeted = here
        gap = OFFER_EVERY if peers else QUIET_OFFER
        if not arrived and now - self.last_offer.get(GROUP, 0.0) < gap:
            return
        self.last_offer[GROUP] = now
        self.queue(self.store.have_line())
        for line in self.store.face_lines(self.me):
            self.queue(line)
        # Pages are offered as a list of ids like posts are, and are only ever
        # sent when somebody asks. One is ten minutes of owed silence.
        if self.store.pages:
            self.queue(self.store.pages_line())
        if self.store.asked_for:
            self.queue(self.store.ask_line())

    def heard(self, src: str, payload: str) -> None:
        """Somebody said something in our language."""
        kind, _, body = payload.partition("|")

        if kind == HAVE:
            want = self.store.want_line(body)
            if want.split("|", 1)[1]:
                self.queue(want)

        elif kind == WANT:
            for line in self.store.give_lines(body, self.client.session.address):
                self.queue(line)

        elif kind == GIVE:
            post = Post.from_wire(body)
            if post is None:
                return
            if self.store.add(post):
                self.dirty = True
                face = self.store.face_of(post.author)
                who = face.name if face else post.author
                trail = (" by way of " + ", ".join(self.who(h) for h in post.hops)
                         if post.hops else "")
                self.note(f"{who}: {post.body}{trail}", "post")
            elif not post.verify():
                self.note(f"a post arrived that does not check out, from {src}", "warn")

        elif kind == PAGES:
            want = self.store.want_page_line(body)
            if want.split("|", 1)[1]:
                self.queue(want)

        elif kind == ASK_PAGE:
            for line in self.store.answer_asked(body, self.client.session.address):
                self.queue(line)

        elif kind == WANT_PAGE:
            for line in self.store.give_page_lines(body, self.client.session.address):
                self.queue(line)

        elif kind == GIVE_PAGE:
            page = Page.from_wire(body)
            if page is None:
                return
            if self.store.shelve(page):
                self.dirty = True
                who = self.who(page.author)
                self.note(f"a page arrived: {page.title} \u2014 {who}", "post")
            elif not page.verify():
                self.note(f"a page arrived that does not check out, from {src}",
                          "warn")

        elif kind == FACE:
            face = Profile.from_wire(body)
            if face is not None and self.store.meet_face(face):
                self.dirty = True
                self.note(f"{face.name} has a face now ({face.author})")

    def who(self, address: str) -> str:
        face = self.store.face_of(address)
        return face.name if face else address

    # -- the loop ----------------------------------------------------------

    def turn(self, now: float) -> None:
        """Standalone: pump the radio ourselves. When hosted by loraline the
        host does that and calls the pieces below directly."""
        for event in self.client.pump():
            if isinstance(event, AppEvent):
                if event.app == APP:
                    self.heard(event.src, event.payload)
            elif isinstance(event, MessageEvent) and event.incoming:
                self.note(f"{event.who} said, out loud: {event.text}", "said")
            elif isinstance(event, SystemEvent):
                self.note(event.text, "warn" if event.level == "warn" else "muted")
        self.offer(now)
        self.pump_outbox()
        # Written every few seconds rather than on every change: a pocket that
        # rewrites itself for each arriving post spends its evening on a disk.
        if self.dirty and now - self.last_save > 5.0:
            self.store.save()
            self.dirty, self.last_save = False, now

    # -- what a person does ------------------------------------------------

    def ask_for(self, at: str) -> bool:
        """Put a page on the list of things to ask about at the next meeting."""
        before = len(self.store.asked_for)
        self.store.note_wanted(at)
        if len(self.store.asked_for) == before:
            return False
        self.dirty = True
        self.note(f"Asking after {at} when somebody comes near.", "muted")
        return True

    def put(self, name: str = "", title: str = "", body: str = "") -> bool:
        """Write a page. It sits on your shelf and is offered from then on.

        The title and the name come from the page's first heading unless you
        say otherwise. Being asked for a name, a title and a body beginning
        with a heading was the same word three times, and only the heading is
        the one anybody actually writes.
        """
        title = title.strip() or heading_of(body)
        name = name.strip() or name_from(title)
        try:
            page = write_page(self.identity, name, title, body)
        except ValueError:
            return False
        if not self.store.shelve(page):
            return False
        self.dirty = True
        self.note(f"You wrote {page.at}.", "mine")
        return True

    def say(self, body: str, answers: str = "") -> bool:
        """Write something. It goes out at once and then waits to be asked
        for by everybody who was not listening.

        `answers` is the id of a post this replies to. Six characters, signed
        along with the words, and free: it rides inside a frame that was going
        out anyway.
        """
        try:
            post = write(self.identity, body, answers=answers)
        except ValueError:
            return False
        if not self.store.add(post):
            return False
        self.dirty = True
        if post.answers:
            to = self.store.by_id(post.answers)
            who = self.who(to.author) if to else "somebody"
            self.note(f"{self.me.name} to {who}: {post.body}", "mine")
        else:
            self.note(f"{self.me.name}: {post.body}", "mine")
        self.queue(GIVE + "|" + post.to_wire())
        return True

    def set_face(self, name: str, pixels=None, colours=None) -> None:
        """Change what people see. Goes out once, and then only when it
        changes again."""
        self.me = describe(self.identity, name, pixels=pixels,
                           when=int(time.time()), colours=colours)
        self.store.meet_face(self.me)
        self.dirty = True
        self.queue(FACE + "|" + self.me.to_wire())
        self.note(f"you are {self.me.name} now")


def snapshot(node: "Node", now: float) -> dict:
    """What the page needs to draw. Faces come as a palette and a pixel each,
    which is what the radio carried anyway."""
    budget = None
    for bearer in node.client.link.interfaces:
        if getattr(bearer, "budget", None) is not None:
            budget = bearer.budget
            break
    left = budget.remaining_ms(now) / 1000.0 if budget is not None else 36.0

    feed = []
    for post in node.store.feed(40):
        face = node.store.face_of(post.author)
        # What it answers, if that post is still held. Three hops away it
        # often is not, and saying so is better than pretending a reply was
        # never a reply.
        to = node.store.by_id(post.answers) if post.answers else None
        feed.append({
            "id": post.id,
            "author": post.author,
            "name": face.name if face else post.author,
            "body": post.body,
            "age": max(0, int(now - post.written)),
            "hops": [node.who(h) for h in post.hops],
            "answers": post.answers,
            "to": ({"name": node.who(to.author), "body": to.body}
                   if to else ({"name": "", "body": ""} if post.answers else None)),
            "face": {"pixels": (face.pixels if face else []),
                     "colours": list(face.colours) if face else []},
        })
    return {
        "holding": len(node.store),
        "faces": len(node.store.faces),
        "peers": len(node.client.session.online_peers()),
        "airtime": f"{left:.0f} s",
        "waiting": len(node.outbox),
        # Whether the silence is nobody being there or no airtime left. They
        # look identical on the page and mean opposite things.
        "held_back": node.held_back,
        "me": {"author": node.me.author, "name": node.me.name,
               "face": {"pixels": node.me.pixels,
                        "colours": list(node.me.colours)}},
        "feed": feed,
        "log": [text for _, text, _ in node.log[-40:]],
    }


def run(node: "Node", view) -> None:
    """The daemon. It keeps going whether or not anybody is reading."""
    while True:
        now = time.time()
        node.turn(now)
        for kind, body in view.drain():
            if kind == "face":          # the raw upload path, still there
                try:
                    import io
                    pixels, colours = from_image(io.BytesIO(body))
                    node.set_face(node.me.name, pixels, colours)
                except Exception as exc:
                    node.note(f"that picture would not go: {exc}", "warn")
                continue
            # The page speaks one shape of order whether it is here or being
            # hosted by loraline, so this reads the same thing the panel does.
            try:
                order = json.loads(body)
            except Exception:
                continue
            what, rest = order.get("do", ""), (order.get("text") or "").strip()
            if what == "say" and rest:
                if not node.say(rest):
                    node.note("nothing to say", "warn")
            elif what == "name" and rest:
                node.set_face(rest)
            elif what == "face" and order.get("bytes"):
                try:
                    import base64
                    import io
                    pixels, colours = from_image(
                        io.BytesIO(base64.b64decode(order["bytes"])))
                    node.set_face(node.me.name, pixels, colours)
                except Exception as exc:
                    node.note(f"that picture would not go: {exc}", "warn")
        view.publish(snapshot(node, now))
        time.sleep(0.25)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hearsay")
    parser.add_argument("--name", default="", help="what people see; your address if blank")
    parser.add_argument("--port", help="serial port of the radio")
    parser.add_argument("--band", choices=sorted(BANDS))
    parser.add_argument("--key", default=os.environ.get("LORALINE_KEY", ""))
    parser.add_argument("--identity")
    parser.add_argument("--tcp-listen", type=int)
    parser.add_argument("--tcp-connect")
    parser.add_argument("--web", type=int, nargs="?", const=8080, default=8080)
    args = parser.parse_args(argv)

    id_path = args.identity or crypto.DEFAULT_PATH
    identity = Identity.load_or_create(id_path)
    keyring = Keyring(identity, args.key or None,
                      keystore=str(id_path) + ".peers.json")

    bearers = []
    if args.port:
        if not args.band:
            print("--band is required with --port", file=sys.stderr)
            return 2
        preset = BANDS[args.band]
        bearers.append(LoRaInterface(args.port, RadioConfig(
            channel=preset["channel"], sf=preset["sf"],
            power=preset["power"], duty=preset["duty"])))
    if args.tcp_listen:
        bearers.append(TCPServerInterface(port=args.tcp_listen))
    if args.tcp_connect:
        host, _, port = args.tcp_connect.partition(":")
        bearers.append(TCPClientInterface(host, int(port or 4242)))
    if not bearers:
        bearers.append(TCPServerInterface(port=4242))
    for bearer in bearers:
        bearer.start()

    link = Link(bearers, keyring=keyring)
    client = Client(link, identity, keyring, nick=args.name or identity.address)
    store = Store().load(str(id_path) + ".hearsay.json")
    kept = len(store)
    me = describe(identity, args.name or identity.address, when=int(time.time()))
    store.meet_face(me)
    node = Node(client=client, identity=identity, store=store, me=me)
    node.note(f"hearsay. You are {me.name} ({identity.address}).")
    node.note("It holds what it hears and hands it on to whoever comes near.")
    if kept:
        node.note(f"Picked up {kept} post(s) it was already carrying.")

    from .web import WebView
    view = WebView(port=args.web)
    view.start()
    print(f"hearsay as {me.name}. Open http://localhost:{args.web}")
    try:
        run(node, view)
    except KeyboardInterrupt:
        pass
    finally:
        store.save()
        view.close()
        link.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
