"""Pages, carried.

A post is a sentence and a page is a document, and they travel the same way:
signed once by whoever wrote it, held by whoever has heard it, handed on to
whoever comes into range. That is the whole of the difference, so this is not
a separate thing, it is the same thing at a different length.

The arithmetic decides the format entirely. Two kilobytes of text is twenty
frames, six seconds on air and ten minutes of owed silence; a node can put out
about six of those an hour. Two hundred kilobytes, which is an ordinary web
page, is seventeen hours. So: text, and not much of it.

That is not a compromise so much as a rediscovery. Gopher and Gemini are the
same shape and the constraint that made them was the same constraint.

Nothing here is HTML. A carried document that could name a picture on the
internet would have your browser quietly fetch it, and the whole point of this
is that nothing leaves the radio. The format cannot express a reference to
anywhere else, so it cannot be made to.
"""

from __future__ import annotations

import base64
import hashlib
import re
import time
from dataclasses import dataclass

BODY_LIMIT = 4096         # about thirteen seconds on air, twenty minutes owed
NAME_LIMIT = 32
TITLE_LIMIT = 64
SEPARATOR = "\x1e"


def _clean_name(text: str) -> str:
    """A page name. Lowercase, no punctuation worth arguing about, because it
    is going to be typed by people and printed in links."""
    kept = re.sub(r"[^a-z0-9._-]+", "-", (text or "").strip().lower())
    return kept.strip("-.")[:NAME_LIMIT] or "index"


def _clean_body(text: str) -> str:
    out = []
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = "".join(ch for ch in line
                       if ch.isprintable() or ch == "\t").replace("\x1e", " ")
        out.append(line.rstrip())
    body = "\n".join(out).strip("\n")
    return body[:BODY_LIMIT]


@dataclass
class Page:
    """One document, and the trail it came by."""

    author: str
    name: str
    title: str
    written: int
    body: str
    signature: str = ""
    keys: tuple = ()
    hops: tuple = ()

    def canonical(self) -> bytes:
        return SEPARATOR.join(
            ("1", self.author, self.name, str(self.written), self.title, self.body)
        ).encode("utf-8")

    @property
    def id(self) -> str:
        return hashlib.blake2b(self.canonical(), digest_size=3).hexdigest()

    @property
    def at(self) -> str:
        """How a page is named out loud: whose it is, and which one."""
        return f"{self.author}/{self.name}"

    def sign(self, identity) -> "Page":
        self.signature = identity.sign(self.canonical())
        self.keys = (identity.public_b64, identity.verify_b64)
        return self

    def verify(self) -> bool:
        if not self.signature or len(self.keys) != 2:
            return False
        try:
            from nacl.signing import VerifyKey
            from loraline.crypto import address_of
            public = base64.b64decode(self.keys[0], validate=True)
            check = base64.b64decode(self.keys[1], validate=True)
            if address_of(public, check) != self.author:
                return False
            VerifyKey(check).verify(
                self.canonical(), base64.b64decode(self.signature, validate=True))
            return True
        except Exception:
            return False

    def carried_by(self, address: str) -> "Page":
        if address in self.hops or address == self.author:
            return self
        self.hops = (self.hops + (address,))[-8:]
        return self

    @property
    def distance(self) -> int:
        return len(self.hops)

    def to_wire(self) -> str:
        return SEPARATOR.join((
            "1", self.author, self.name, str(self.written), self.title, self.body,
            self.signature, self.keys[0] if self.keys else "",
            self.keys[1] if len(self.keys) > 1 else "", ",".join(self.hops)))

    @classmethod
    def from_wire(cls, text: str):
        bits = text.split(SEPARATOR)
        if len(bits) < 10 or bits[0] != "1" or not bits[3].isdigit():
            return None
        hops = tuple(h for h in bits[9].split(",") if h)
        return cls(author=bits[1], name=bits[2], written=int(bits[3]),
                   title=bits[4], body=bits[5], signature=bits[6],
                   keys=(bits[7], bits[8]), hops=hops[:8])


def write(identity, name: str, title: str, body: str, when=None) -> Page:
    text = _clean_body(body)
    if not text:
        raise ValueError("nothing on the page")
    page = Page(author=identity.address, name=_clean_name(name),
                title=(title or "").strip()[:TITLE_LIMIT] or _clean_name(name),
                written=int(when if when is not None else time.time()), body=text)
    return page.sign(identity)


# --------------------------------------------------------------------------
# The format
# --------------------------------------------------------------------------
#
# Six kinds of line and nothing else. There is no way to write a reference to
# anything off the radio, which is the point: a document that could name a
# picture on the internet would have a browser fetch it, and then this is not
# a network that stands on its own, it is a slower way of using the old one.
#
#   # heading            one, at the top, usually
#   ## smaller heading
#   > something quoted
#   * a thing in a list
#   => name what it is   a link to another page, here or on somebody's node
#   ```                  everything until the next ``` is left exactly alone
#   anything else        a paragraph

LINK = re.compile(r"^=>\s*(\S+)(?:\s+(.*))?$")


def parse(body: str) -> list:
    """Lines, as (kind, text, extra). Kept separate from the drawing so the
    same document can be read by something that is not a browser."""
    out = []
    preformatted = False
    for line in body.split("\n"):
        if line.startswith("```"):
            preformatted = not preformatted
            out.append(("fence", "", ""))
            continue
        if preformatted:
            out.append(("pre", line, ""))
            continue
        if not line.strip():
            out.append(("gap", "", ""))
        elif line.startswith("## "):
            out.append(("h2", line[3:].strip(), ""))
        elif line.startswith("# "):
            out.append(("h1", line[2:].strip(), ""))
        elif line.startswith("> "):
            out.append(("quote", line[2:].strip(), ""))
        elif line.startswith("* "):
            out.append(("item", line[2:].strip(), ""))
        else:
            hit = LINK.match(line)
            if hit:
                out.append(("link", hit.group(2) or hit.group(1), hit.group(1)))
            else:
                out.append(("text", line.strip(), ""))
    return out


def links(body: str) -> list:
    """Everywhere this page points. Used to decide what is worth asking for."""
    return [extra for kind, _, extra in parse(body) if kind == "link"]


HOME = "here"          # the pages that came with the program


def _looks_like_address(text: str) -> bool:
    """Is this an address rather than a page name?

    Asked of the part before a slash. It was a fixed six characters, which
    quietly stopped matching anything real the moment addresses became
    sixteen: every cross-author link would have been read as a page name by
    the same author, and the tests would not have noticed because the tests
    said a1b2c3.
    """
    from loraline.crypto import ADDRESS_BYTES
    if text == HOME:
        # The built-in pages, so a written page can point into them. It is not
        # a real address and cannot be one: nobody can grind sixteen hex
        # characters that spell "here".
        return True
    return (len(text) == ADDRESS_BYTES * 2
            and all(c in "0123456789abcdef" for c in text))


def resolve(target: str, author: str) -> str:
    """A link, as an author and a page name.

    A bare name means a page by the same person, which is what makes somebody's
    pages feel like a set rather than a pile.

    The part before the slash has to be an address, or it is not one. Without that check `=> https://example.com/thing` came out as a
    link to a page named after a website, which could not actually fetch
    anything but read as though it might, and a format whose whole promise is
    that nothing leaves the radio should not print things that look like they
    do.
    """
    who, slash, what = target.partition("/")
    if slash and _looks_like_address(who.lower()):
        return f"{who.lower()}/{_clean_name(what)}"
    return f"{author}/{_clean_name(target)}"


def escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def to_html(page: "Page", naming=None) -> str:
    """Into markup, by the node, from six kinds of line.

    Every link comes out pointing at this machine, and nothing in the document
    can produce a reference anywhere else. That is why an ordinary browser is
    safe to read this with: it never sees anything the node did not write.

    `naming` turns an address into whatever that person is called here, so a
    link reads as a person rather than as six hex characters.
    """
    out, in_list, in_pre = [], False, False
    for kind, text, extra in parse(page.body):
        if kind == "fence":
            out.append("</pre>" if in_pre else '<pre class="lit">')
            in_pre = not in_pre
            continue
        if in_pre:
            out.append(escape(text))
            continue
        if kind != "item" and in_list:
            out.append("</ul>")
            in_list = False
        if kind == "h1":
            out.append(f"<h1>{escape(text)}</h1>")
        elif kind == "h2":
            out.append(f"<h2>{escape(text)}</h2>")
        elif kind == "quote":
            out.append(f"<blockquote>{escape(text)}</blockquote>")
        elif kind == "item":
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{escape(text)}</li>")
        elif kind == "link":
            where = resolve(extra, page.author)
            who, _, what = where.partition("/")
            # The address is the true name and cannot be anything else, but it
            # does not have to be the thing a person reads. What is shown is
            # whoever you know that address as; what is followed is the
            # address. A nick is a label and anybody can claim one, so it is
            # never what a link resolves against.
            shown = naming(who) if naming else who
            out.append(f'<p class="link"><a href="/page/{escape(where)}">'
                       f'{escape(text)}</a> '
                       f'<i>{escape(shown)}/{escape(what)}</i></p>')
        elif kind == "text":
            out.append(f"<p>{escape(text)}</p>")
    if in_list:
        out.append("</ul>")
    if in_pre:
        out.append("</pre>")
    return "\n".join(out)
