"""A post, and what makes it somebody's.

Posts travel by being carried. A node holds what it has heard and hands it on
to whoever comes into range, so a post reaches you because a person walked
between you and its author, possibly through several other people first.

That means anybody can be holding anybody's post, and most of the people
handling it were never meant to be trusted. So a post is signed by whoever
wrote it, once, and the signature travels with it for ever. A carrier can drop
a post, or refuse to pass it on, or lie about where they got it. What they
cannot do is change a word of it or write one in somebody else's name.

The arithmetic decides the shape. At SF7 under a one percent duty cycle a node
has thirty-six seconds of airtime an hour, and a 140 character post costs 871
milliseconds to put on the air, which owes eighty-seven seconds of silence.
That is about forty posts an hour including everything relayed. Hence: posts
are short, and nothing is ever sent to somebody who already has it.
"""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass, field

BODY_LIMIT = 140          # characters; the signature alone is eighty-eight
HOP_LIMIT = 8             # how much of the path a post remembers
SEPARATOR = "\x1e"        # inside a payload, distinct from loraline's own


def _clean(text: str) -> str:
    """Strip anything that would confuse the framing or a terminal."""
    out = []
    for ch in text.strip():
        if ch in ("\n", "\r", "\x1f", "\x1e", "|"):
            out.append(" ")
        elif ch.isprintable():
            out.append(ch)
    return " ".join("".join(out).split())[:BODY_LIMIT]


@dataclass
class Post:
    """One thing somebody said, and the trail it came by."""

    author: str               # six-hex address of whoever wrote it
    written: int              # unix seconds, as the author's clock had it
    body: str
    signature: str = ""       # base64, over the canonical bytes
    keys: tuple = ()          # the author's two public halves, for strangers
    hops: tuple = ()          # who has carried it, in order, as a claim
    answers: str = ""         # the id of the post this replies to, if any

    # -- identity ----------------------------------------------------------

    def canonical(self) -> bytes:
        """Exactly what gets signed. The hops are not in it: they change every
        time the post moves, and a signature that had to be redone at every
        pair of hands would not survive the first stranger."""
        # What it answers is signed along with the words. Otherwise a carrier
        # could attach somebody's reply to a different question, which is a
        # cheap way to make anybody appear to have said something unpleasant.
        return SEPARATOR.join(
            ("1", self.author, str(self.written), self.body, self.answers)
        ).encode("utf-8")

    @property
    def id(self) -> str:
        """Six hex characters, which is about the document rather than the
        person: an id says which page or post, in a pocket of a few hundred,
        and nothing is ever checked against it. An address is what a signature
        is checked against, which is why that one is sixteen.

        Long enough that two posts colliding in a store
        of a few hundred is a one in a thousand event, short enough that a list
        of forty of them still fits in a frame or two."""
        return hashlib.blake2b(self.canonical(), digest_size=3).hexdigest()

    # -- signing -----------------------------------------------------------

    def sign(self, identity) -> "Post":
        self.signature = identity.sign(self.canonical())
        self.keys = (identity.public_b64, identity.verify_b64)
        return self

    def verify(self) -> bool:
        """True if this really is what that author wrote.

        Checked against the keys carried with the post, and the address is
        recomputed from those keys, so a carrier cannot attach a signing key it
        invented to somebody else's name.
        """
        if not self.signature or len(self.keys) != 2:
            return False
        try:
            from nacl.signing import VerifyKey
            from loraline.crypto import address_of
            public = base64.b64decode(self.keys[0], validate=True)
            verify = base64.b64decode(self.keys[1], validate=True)
            if address_of(public, verify) != self.author:
                return False
            VerifyKey(verify).verify(
                self.canonical(), base64.b64decode(self.signature, validate=True))
            return True
        except Exception:
            return False

    # -- carrying ----------------------------------------------------------

    def carried_by(self, address: str) -> "Post":
        """Note that somebody passed this along.

        The trail is a claim, not a proof: a carrier could invent a hop or drop
        one. Signing every hop would make it provable and cost eighty-eight
        characters a time, which at forty posts an hour is not a trade worth
        making. What matters is that the author cannot be faked; how it reached
        you is a story the network tells about itself.
        """
        if address in self.hops or address == self.author:
            return self
        self.hops = (self.hops + (address,))[-HOP_LIMIT:]
        return self

    @property
    def distance(self) -> int:
        """How many pairs of hands, as far as anybody claims."""
        return len(self.hops)

    # -- the wire ----------------------------------------------------------

    def to_wire(self) -> str:
        return SEPARATOR.join((
            "1", self.author, str(self.written), self.body,
            self.signature, self.keys[0] if self.keys else "",
            self.keys[1] if len(self.keys) > 1 else "",
            ",".join(self.hops), self.answers,
        ))

    @classmethod
    def from_wire(cls, text: str):
        bits = text.split(SEPARATOR)
        if len(bits) < 8 or bits[0] != "1":
            return None
        if not bits[2].isdigit():
            return None
        hops = tuple(h for h in bits[7].split(",") if h)
        # Posts written before replies existed have eight fields, not nine.
        answers = bits[8] if len(bits) > 8 else ""
        return cls(author=bits[1], written=int(bits[2]), body=bits[3],
                   signature=bits[4], keys=(bits[5], bits[6]),
                   hops=hops[:HOP_LIMIT], answers=_an_id(answers))


def _an_id(text: str) -> str:
    """An id or nothing at all.

    Sieving out the non-hex characters turned "zz;drop table" into "dabe",
    which is not an id anybody meant and happens to look like one.
    """
    text = (text or "").strip().lower()
    ok = len(text) == 6 and all(c in "0123456789abcdef" for c in text)
    return text if ok else ""


def write(identity, body: str, when: float | None = None,
          answers: str = "") -> Post:
    """Compose and sign. Refuses an empty one rather than putting nothing on
    the air at eighty-seven seconds a time."""
    text = _clean(body)
    if not text:
        raise ValueError("nothing to say")
    post = Post(author=identity.address,
                written=int(when if when is not None else time.time()),
                body=text,
                answers=_an_id(answers))
    return post.sign(identity)
