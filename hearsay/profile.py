"""Who somebody is: a name and a small picture.

A profile travels exactly as a post does, by being carried, and is signed the
same way. It has to: the person reading it has probably never met the person it
describes, and a carrier handling somebody else's face is precisely the case
where forgery would matter.

It can afford to be much larger than a post because it is sent once and then
only when it changes. A sixteen by sixteen picture in eight colours costs about
the same as a post and a half, against a budget of forty posts an hour, so the
only real argument for keeping it small is that small pictures drawn by hand
are better than large ones.

Everybody has a face before they draw one. The default is derived from the
address, so a stranger arrives already looking like somebody rather than like a
blank.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

SIDE = 32                 # the picture is thirty-two square
DEPTH = 3                 # three bits a pixel, so eight colours
NAME_LIMIT = 18

# Twelve by twelve made a face a blot and twenty-four lost the eyes: at that
# size a pupil is one pixel and eight colours cannot spare one for it. Thirty
# two is where a photograph still looks like the person. It costs 237 seconds
# of owed silence, once, against thirty-six seconds an hour, and a profile is
# sent when it changes and then not again.

# Every picture carries its own eight colours, twelve bytes of them. A fixed
# palette is fine for something drawn and hopeless for a photograph, where the
# eight colours that suit one face suit no other.
DEFAULT_PALETTE = ("#11170f",     # 0 near black, and the usual background
                   "#f4efe4",     # 1 bone
                   "#c2553f",     # 2 rust
                   "#d9a13f",     # 3 amber
                   "#5f8f4a",     # 4 green
                   "#3d7f99",     # 5 sea
                   "#7a5a9a",     # 6 violet
                   "#8a8175")     # 7 stone
PALETTE = DEFAULT_PALETTE         # what a picture uses if it names none


def _pack_palette(colours) -> bytes:
    """Eight colours at four bits a channel. Twelve bytes, and nobody can tell
    the difference at this size."""
    out = bytearray()
    for i in range(8):
        hexed = (colours[i] if i < len(colours) else "#000000").lstrip("#")
        r, g, b = (int(hexed[j:j+2], 16) >> 4 for j in (0, 2, 4))
        out.append((r << 4) | g)
        out.append(b << 4)
    return bytes(out)


def _unpack_palette(raw: bytes) -> tuple:
    out = []
    for i in range(8):
        if len(raw) < i * 2 + 2:
            out.append("#000000")
            continue
        first, second = raw[i*2], raw[i*2+1]
        r, g, b = first >> 4, first & 0xF, second >> 4
        out.append("#%02x%02x%02x" % (r * 17, g * 17, b * 17))
    return tuple(out)


def _clean_name(text: str) -> str:
    out = "".join(ch for ch in (text or "").strip()
                  if ch.isprintable() and ch not in ("\x1e", "\x1f", "|"))
    return " ".join(out.split())[:NAME_LIMIT]


def pack(pixels, colours=None) -> str:
    """A picture into text: its palette, then three bits a pixel, then base64."""
    bits = 0
    value = 0
    out = bytearray(_pack_palette(colours or DEFAULT_PALETTE))
    for pixel in pixels[:SIDE * SIDE]:
        value = (value << DEPTH) | (int(pixel) & 0b111)
        bits += DEPTH
        while bits >= 8:
            bits -= 8
            out.append((value >> bits) & 0xFF)
    if bits:
        out.append((value << (8 - bits)) & 0xFF)
    return base64.b64encode(bytes(out)).decode("ascii")


def unpack(text: str) -> list:
    """And back again. Anything malformed comes out as an empty picture rather
    than an exception, because this arrives from strangers."""
    try:
        raw = base64.b64decode(text, validate=True)[16:]
    except Exception:
        return [0] * (SIDE * SIDE)
    pixels, value, bits = [], 0, 0
    for byte in raw:
        value = (value << 8) | byte
        bits += 8
        while bits >= DEPTH and len(pixels) < SIDE * SIDE:
            bits -= DEPTH
            pixels.append((value >> bits) & 0b111)
    while len(pixels) < SIDE * SIDE:
        pixels.append(0)
    return pixels


def identicon(address: str) -> list:
    """The face somebody has before they draw one.

    Mirrored down the middle, because symmetry is what makes a random blotch
    read as a face, and two colours out of the eight so it is legible at the
    size it will actually be seen.
    """
    seed = hashlib.blake2b(address.encode("utf-8"), digest_size=32).digest()
    ink = 1 + seed[0] % 7
    edge = 1 + seed[1] % 7
    if edge == ink:
        edge = 1 + (ink % 7)
    pixels = [0] * (SIDE * SIDE)
    half = SIDE // 2
    for y in range(SIDE):
        for x in range(half):
            bit = seed[(y * half + x) % len(seed)]
            if y in (0, SIDE - 1) or (bit & 0b11) == 0:
                continue
            colour = ink if bit & 0b100 else edge
            pixels[y * SIDE + x] = colour
            pixels[y * SIDE + (SIDE - 1 - x)] = colour
    return pixels


@dataclass
class Profile:
    """Somebody, as the network knows them."""

    author: str
    name: str
    picture: str              # packed pixels
    updated: int              # unix seconds; the newest one wins
    signature: str = ""
    keys: tuple = ()

    def canonical(self) -> bytes:
        return "\x1e".join(("1", self.author, str(self.updated),
                            self.name, self.picture)).encode("utf-8")

    def sign(self, identity) -> "Profile":
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

    @property
    def pixels(self) -> list:
        return unpack(self.picture)

    @property
    def colours(self) -> tuple:
        """The eight this picture was drawn with."""
        try:
            return _unpack_palette(base64.b64decode(self.picture, validate=True)[:16])
        except Exception:
            return DEFAULT_PALETTE

    def to_wire(self) -> str:
        return "\x1e".join(("1", self.author, str(self.updated), self.name,
                            self.picture, self.signature,
                            self.keys[0] if self.keys else "",
                            self.keys[1] if len(self.keys) > 1 else ""))

    @classmethod
    def from_wire(cls, text: str):
        bits = text.split("\x1e")
        if len(bits) < 8 or bits[0] != "1" or not bits[2].isdigit():
            return None
        return cls(author=bits[1], updated=int(bits[2]), name=bits[3],
                   picture=bits[4], signature=bits[5], keys=(bits[6], bits[7]))


def from_image(path, side: int = SIDE):
    """Turn any picture into something that fits on a radio.

    Square crop, resize, then reduce to eight colours chosen from the image
    itself. What comes out is roughly an icon from 1993, which is the honest
    result of asking a photograph to cross a link that carries a few hundred
    bytes at a time. A face is still a face.

    Needs Pillow, which nothing else here does, so it is imported inside.
    """
    from PIL import Image
    picture = path if hasattr(path, "convert") else Image.open(path)
    picture = picture.convert("RGB")
    # Square from the middle, so a portrait does not come out as somebody's
    # shoulder.
    edge = min(picture.size)
    left = (picture.width - edge) // 2
    top = (picture.height - edge) // 3          # faces sit above centre
    picture = picture.crop((left, top, left + edge, top + edge))
    picture = picture.resize((side, side), Image.LANCZOS)
    # Sharpen first and do not dither. Dithering scatters a one pixel eye
    # across three pixels of nothing, and at this size every feature of a face
    # is one pixel.
    from PIL import ImageEnhance
    picture = ImageEnhance.Sharpness(picture).enhance(2.4)
    reduced = picture.quantize(colors=8, method=Image.MEDIANCUT, dither=Image.NONE)
    table = (reduced.getpalette() or [0] * 24)[:24]
    colours = tuple("#%02x%02x%02x" % tuple(table[i*3:i*3+3]) for i in range(8))
    return list(reduced.tobytes()), colours


def describe(identity, name: str, pixels=None, when: int = 0,
             colours=None) -> Profile:
    """Make and sign a profile. Without a picture you get the one your address
    already had."""
    profile = Profile(author=identity.address,
                      name=_clean_name(name) or identity.address,
                      picture=pack(pixels if pixels is not None
                                   else identicon(identity.address),
                                   colours),
                      updated=int(when))
    return profile.sign(identity)
