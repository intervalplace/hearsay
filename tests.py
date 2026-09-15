"""hearsay's tests. No hardware, no radio, no waiting."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hearsay.post import SEPARATOR, Post, write, BODY_LIMIT, HOP_LIMIT
from hearsay.store import Store, HOLD, GIVE_PER_MEETING
from loraline.crypto import Identity

PASSED = 0
def ok(text):
    global PASSED
    PASSED += 1
    print(f"  ok  {text}")

hank, dave, mira, liar = Identity(), Identity(), Identity(), Identity()
T = 1789000000

# ---------- a post is somebody's ----------
post = write(hank, "the herring are in, if anybody is about", T)
assert post.verify()
assert post.author == hank.address
ok(f"a post is signed once by whoever wrote it ({len(post.to_wire())} characters on the wire)")

again = Post.from_wire(post.to_wire())
assert again.id == post.id and again.verify()
ok("and survives the round trip through the wire")

edited = Post.from_wire(post.to_wire())
edited.body += " and free beer"
assert not edited.verify()
ok("a carrier cannot change a word of it")

swapped = Post.from_wire(post.to_wire())
swapped.keys = (liar.public_b64, liar.verify_b64)
assert not swapped.verify()
ok("nor attach their own signing key to somebody else's name")

impostor = Post(author=hank.address, written=T, body="I am hank")
impostor.sign(liar)
assert not impostor.verify(), "the address must match the keys that signed"
ok("nor write a post in a name that is not theirs")

# ---------- carrying ----------
travelling = Post.from_wire(post.to_wire())
for who in (dave.address, mira.address, dave.address):
    travelling.carried_by(who)
assert travelling.hops == (dave.address, mira.address)
assert travelling.distance == 2
assert travelling.verify(), "the trail is outside the signature"
ok("the trail of who carried it grows without breaking the signature")

for n in range(HOP_LIMIT + 4):
    travelling.carried_by(f"{n:06x}")
assert len(travelling.hops) == HOP_LIMIT
ok(f"and remembers at most {HOP_LIMIT} pairs of hands")

assert write(hank, "x" * 400, T).body == "x" * BODY_LIMIT
try:
    write(hank, "   ", T)
    assert False, "an empty post should be refused"
except ValueError:
    pass
ok(f"a post is at most {BODY_LIMIT} characters, and never nothing at all")

# ---------- a pocket, not an archive ----------
pocket = Store()
for i in range(HOLD + 40):
    pocket.add(write(hank, f"post number {i}", T + i))
assert len(pocket) == HOLD
oldest = min(p.written for p in pocket.feed(HOLD))
assert oldest > T, "the oldest should have been let go"
ok(f"a node holds {HOLD} posts and forgets the oldest")

assert not pocket.add(Post(author=hank.address, written=T, body="unsigned"))
ok("and refuses anything that does not verify")

# ---------- meeting somebody ----------
def meet(giver, taker, giver_address):
    """One exchange, as it goes over the air."""
    have = giver.have_line().split("|", 1)[1]
    want = taker.want_line(have).split("|", 1)[1]
    taken = []
    for line in giver.give_lines(want, giver_address):
        got = Post.from_wire(line.split("|", 1)[1])
        if taker.add(got):
            taken.append(got)
    return taken

first, second, third = Store(), Store(), Store()
for i, line in enumerate(["the herring are in",
                          "somebody left a net on the point",
                          "rain by four"]):
    first.add(write(hank, line, T + i * 60))

assert len(meet(first, second, hank.address)) == 3
assert len(second) == 3
ok("two nodes meeting trade only what the other lacks")

assert meet(first, second, hank.address) == []
ok("and meeting again trades nothing")

# the post that reaches somebody who was never near its author
carried = meet(second, third, dave.address)
assert len(carried) == 3
assert all(p.author == hank.address for p in carried)
assert all(dave.address in p.hops for p in carried)
assert all(p.verify() for p in carried)
ok("a post reaches somebody who has never met its author, and still checks out")

# and forgetting does not start it circling again
emptied = Store()
emptied.add(write(hank, "seen and let go", T))
old_id = next(iter(emptied.posts))
emptied.posts.clear()                       # as if forgotten by age
assert old_id in emptied.seen
assert emptied.want_line(old_id).split("|", 1)[1] == ""
ok("something already had and let go is not asked for again")

# a meeting is bounded, so one node cannot spend another's whole hour
crowded = Store()
for i in range(40):
    crowded.add(write(hank, f"line {i}", T + i))
fresh = Store()
handed = meet(crowded, fresh, hank.address)
assert len(handed) == GIVE_PER_MEETING, len(handed)
ok(f"one meeting hands over at most {GIVE_PER_MEETING} posts, newest first")
assert handed[0].written > handed[-1].written

# ---------- who somebody is ----------
from hearsay.profile import (Profile, describe, identicon, pack, unpack,
                           PALETTE, SIDE, NAME_LIMIT)

face = describe(hank, "hank", when=T)
assert face.verify()
assert len(face.to_wire()) < 800, len(face.to_wire())
ok(f"a profile is a name and a picture, signed, in {len(face.to_wire())} characters")

# a picture carries its own eight colours, or a photograph is hopeless
from hearsay.profile import _pack_palette, _unpack_palette, DEFAULT_PALETTE
odd = ("#000000", "#ffffff", "#ee3311", "#3355dd",
       "#22aa55", "#ddaa22", "#884499", "#777777")
assert _unpack_palette(_pack_palette(odd)) == odd
assert describe(hank, "hank", colours=odd, when=T).colours == odd
assert describe(hank, "hank", when=T).colours != odd
ok("every picture carries its own eight colours, so a photograph can pick its own")

renamed = Profile.from_wire(face.to_wire())
renamed.name = "somebody else"
assert not renamed.verify()
stolen = Profile.from_wire(face.to_wire())
stolen.keys = (liar.public_b64, liar.verify_b64)
assert not stolen.verify()
ok("and nobody can rename you or put their key against your face")

assert unpack(pack(identicon(hank.address))) == identicon(hank.address)
assert len(unpack("not base64 at all")) == SIDE * SIDE
ok("pictures pack losslessly, and rubbish unpacks to a blank rather than an error")

faces = [tuple(identicon(Identity().address)) for _ in range(40)]
assert len(set(faces)) == len(faces), "two people should not share a face"
mirrored = all(px[y * SIDE + x] == px[y * SIDE + SIDE - 1 - x]
               for px in (identicon(hank.address),)
               for y in range(SIDE) for x in range(SIDE // 2))
assert mirrored
ok("everybody has a face before they draw one, derived from their address")

assert len(describe(hank, "x" * 90, when=T).name) == NAME_LIMIT
assert describe(hank, "   ", when=T).name == hank.address
ok(f"a name is at most {NAME_LIMIT} characters, and never blank")

# faces travel like posts, and reach people who never met their owner
one, two, three = Store(), Store(), Store()
one.meet_face(face)
one.add(write(hank, "the herring are in", T))
for line in one.face_lines(face):
    two.meet_face(Profile.from_wire(line.split("|", 1)[1]))
meet(one, two, hank.address)
for line in two.face_lines(describe(dave, "dave", when=T)):
    three.meet_face(Profile.from_wire(line.split("|", 1)[1]))
meet(two, three, dave.address)
assert three.face_of(hank.address).name == "hank"
assert three.face_of(hank.address).verify()
assert three.faceless() == []
ok("a face reaches somebody who never met its owner, and still checks out")

assert not three.meet_face(describe(hank, "hank the elder", when=T - 100))
assert three.meet_face(describe(hank, "hank again", when=T + 100))
assert three.face_of(hank.address).name == "hank again"
ok("the newest profile wins, and an older one cannot undo it")

orphan = Store()
orphan.add(write(mira, "nobody here knows me", T))
assert orphan.faceless() == [mira.address]
ok("and a post from somebody whose face has not arrived yet says so")


# ---------- a pocket that survives being put down ----------
import tempfile, os, json as _json
with tempfile.TemporaryDirectory() as room:
    where = os.path.join(room, "pocket.json")
    kept = Store().load(where)
    kept.meet_face(describe(hank, "hank", when=T))
    for i in range(5):
        kept.add(write(hank, f"line {i}", T + i))
    kept.save()

    again = Store().load(where)
    assert len(again) == 5 and len(again.faces) == 1
    assert all(p.verify() for p in again.feed())
    assert len(again.seen) == 5
    ok("a node picks up what it was carrying when it starts again")

    # a file on disk is no more trustworthy than a stranger
    raw = _json.loads(open(where).read())
    raw["posts"][0] = raw["posts"][0].replace("line 4", "line 9")
    open(where, "w").write(_json.dumps(raw))
    tampered = Store().load(where)
    assert len(tampered) == 4, len(tampered)
    assert not any("line 9" in p.body for p in tampered.feed())
    ok("and drops anything in the file that does not check out")

    missing = Store().load(os.path.join(room, "nothing-here.json"))
    assert len(missing) == 0
    open(os.path.join(room, "rubbish.json"), "w").write("not json at all")
    assert len(Store().load(os.path.join(room, "rubbish.json"))) == 0
    ok("a missing or unreadable pocket starts empty rather than failing")


# ---------- a face you set stays set ----------
with tempfile.TemporaryDirectory() as room:
    where = os.path.join(room, "pocket.json")
    pocket = Store().load(where)
    chosen = describe(hank, "hank", pixels=[3]*(SIDE*SIDE), when=T + 500)
    pocket.meet_face(chosen)
    pocket.save()

    # Coming back and building a default profile stamps it with the current
    # time, which always wins against the one on disk. A photograph lasted
    # exactly until the next restart.
    back = Store().load(where)
    mine = back.face_of(hank.address)
    assert mine is not None and mine.picture == chosen.picture
    fresh = describe(hank, "hank", when=T + 9000)
    assert fresh.updated > mine.updated
    assert back.meet_face(fresh), "which is exactly how the photograph was lost"
    ok("a saved face is newer than nothing and older than a fresh default")

    # Keeping the pixels while changing the name is the way through.
    kept = describe(hank, "a new name", pixels=chosen.pixels,
                    colours=chosen.colours, when=T + 9001)
    assert kept.picture == chosen.picture and kept.name == "a new name"
    assert kept.verify()
    ok("renaming carries the picture across rather than throwing it away")


# ---------- pages ----------
from hearsay.page import (Page, write as write_page, to_html, links, resolve,
                          BODY_LIMIT)

doc = """# The ledge

There is a spot below the rocks nobody uses.

* follow the sand north
* past the reeds

> the bass are there at dusk

=> tides when to go
=> a1b2c3/bait somebody else on bait
"""
sheet = write_page(hank, "The Ledge!", "The ledge", doc, T)
assert sheet.name == "the-ledge" and sheet.at == f"{hank.address}/the-ledge"
assert sheet.verify()
again = Page.from_wire(sheet.to_wire())
assert again.id == sheet.id and again.verify()
ok(f"a page is signed like a post, in {len(sheet.to_wire())} characters")

edited = Page.from_wire(sheet.to_wire())
edited.body += "\nand free beer"
assert not edited.verify()
stolen = Page.from_wire(sheet.to_wire())
stolen.keys = (liar.public_b64, liar.verify_b64)
assert not stolen.verify()
ok("and cannot be changed or claimed by somebody else either")

# A bare name is the same author's; an address before the slash is somebody
# else's; anything that is not an address is a name, whatever it looks like.
assert resolve("tides", hank.address) == f"{hank.address}/tides"
assert resolve(f"{dave.address}/bait", hank.address) == f"{dave.address}/bait"
assert resolve("https://example.com/x", hank.address).startswith(hank.address + "/")
assert resolve("../../etc/passwd", hank.address) == f"{hank.address}/etc-passwd"
ok("a link is a page on this radio or it is a page name, never a place")

# Nothing a document can say may produce a reference off the radio, because a
# browser would fetch it and then this is a slower way of using the old
# internet rather than a network that stands on its own.
nasty = write_page(hank, "x", "x",
                   '=> https://example.com/thing look\n'
                   '<img src="https://evil/x">\n'
                   '<script>alert(1)</script>\n', T)
html = to_html(nasty)
assert "<script>" not in html and "<img" not in html
assert "&lt;script&gt;" in html, "it is shown as text, which is what it is"
# What matters is live attributes, not the letters h-t-t-p. A web address
# printed as words is a page saying something; one in an href is a browser
# leaving the radio.
import re as _re
for attribute in _re.findall(r'(?:href|src)="([^"]*)"', html):
    assert attribute.startswith("/page/"), attribute
ok("and no document can make a browser fetch anything off the radio")

# a page is something somebody keeps, so a newer one replaces it
shelf = Store()
assert shelf.shelve(sheet)
assert shelf.page_at(sheet.at).title == "The ledge"
later = write_page(hank, "the-ledge", "The ledge, again", doc + "\nmore", T + 900)
assert shelf.shelve(later)
assert shelf.page_at(sheet.at).title == "The ledge, again"
assert len(shelf.pages) == 1, "the old one is not kept beside the new one"
earlier = write_page(hank, "the-ledge", "stale", doc, T - 900)
assert not shelf.shelve(earlier)
ok("a newer page replaces the one it is a new version of, and an older is refused")

# and one at a time, because one is ten minutes of owed silence
crowd = Store()
for n in range(6):
    crowd.shelve(write_page(hank, f"page-{n}", f"Page {n}", f"# {n}\nsomething", T + n))
empty = Store()
have = crowd.pages_line().split("|", 1)[1]
want = empty.want_page_line(have).split("|", 1)[1]
handed = crowd.give_page_lines(want, dave.address)
assert len(handed) == 1, len(handed)
got = Page.from_wire(handed[0].split("|", 1)[1])
assert empty.shelve(got) and dave.address in got.hops and got.verify()
ok("a meeting hands over one page: two kilobytes is ten minutes of owed silence")


# ---------- finding a page without typing an address ----------
# An address is the true name of a person and cannot be anything else: a nick
# is a label and anybody can claim one, so a link never resolves against a
# name. But nobody should have to type an address either.
known = {hank.address: "hank", dave.address: "mira"}
naming = lambda address: known.get(address, address)
signed = write_page(hank, "x", "x",
                    f"=> tides when to go\n=> {dave.address}/bait mira on bait\n"
                    f"=> {mira.address}/x somebody nobody knows\n", T)
shown = to_html(signed, naming=naming)
assert f'href="/page/{hank.address}/tides"' in shown, "followed by address"
assert "<i>hank/tides</i>" in shown, "read as a person"
assert "<i>mira/bait</i>" in shown
assert f"<i>{mira.address}/x</i>" in shown, "somebody unknown stays their address"
ok("a link is followed by address and read as whoever you know them as")

plain = to_html(signed)
assert f"<i>{hank.address}/tides</i>" in plain
ok("and with nobody to name, the address is what it says")


# ---------- how long an address is ----------
from loraline.crypto import ADDRESS_BYTES

assert ADDRESS_BYTES * 8 >= 64, "twenty-four bits is six minutes of grinding"
assert len(hank.address) == ADDRESS_BYTES * 2
# A cross-author link has to resolve against whatever an address actually is,
# not against a length somebody typed once. This was a fixed six and stopped
# matching anything real the moment addresses grew.
elsewhere = resolve(f"{dave.address}/bait", hank.address)
assert elsewhere == f"{dave.address}/bait", elsewhere
assert resolve("a1b2c3/bait", hank.address).startswith(hank.address), \
    "something that is not an address is a page name, whatever it looks like"
ok(f"an address is {ADDRESS_BYTES*8} bits and a link resolves against that length")


# ---------- the pages that came with the program ----------
from hearsay import manual
from hearsay.page import HOME as _HOME

# Having each node write itself a reference page would mean every node on the
# radio carrying the same text under a different name, and two people meeting
# spending ten minutes of owed silence swapping documents they both had.
assert manual.has("index") and manual.has("writing")
for name, title in manual.listing():
    built = Page(author=_HOME, name=name, title=title, written=0,
                 body=manual.body(name))
    shown = to_html(built, naming=lambda a: a)
    for attribute in _re.findall(r'(?:href|src)="([^"]*)"', shown):
        assert attribute.startswith("/page/"), attribute
    assert not built.signature, "a built-in page is not signed by anybody"
ok(f"{len(manual.listing())} pages come with the program, none of them signed")

# and a written page can point into them
assert resolve("here/writing", hank.address) == "here/writing"
assert resolve("writing", hank.address) == f"{hank.address}/writing"
assert resolve("herefordshire/x", hank.address).startswith(hank.address)
ok("a written page can link into the manual, and only by that exact name")

# the manual is never offered on the air
shelf_only = Store()
shelf_only.shelve(write_page(hank, "bread", "Bread", "# Bread\nThursdays.", T))
offered = shelf_only.pages_line()
assert _HOME not in offered
ok("and the manual is never named in what a node offers")


# ---------- answering somebody ----------
question = write(hank, "anything in the cellar?", T)
answer = write(mira, "still nothing", T + 300, answers=question.id)
assert answer.answers == question.id and answer.verify()
plain = write(mira, "still nothing", T + 300)
assert len(answer.to_wire()) - len(plain.to_wire()) == 6
ok("a reply is six characters, and it rides in a frame that was going anyway")

# What it answers is inside the signature, so a carrier cannot re-point a
# reply at a different question and make somebody appear to have answered it.
moved = Post.from_wire(answer.to_wire())
moved.answers = "ffffff"
assert not moved.verify()
ok("and what it answers is signed, so nobody can re-point it")

# a post written before replies existed has eight fields, not nine
older = SEPARATOR.join(["1", hank.address, str(T), "hello", "", "", "", ""])
assert Post.from_wire(older) is not None
assert write(mira, "x", T, answers="zz;drop table").answers == ""
ok("older posts still read, and a broken id is no id at all")

threaded = Store()
for each in (question, answer, write(hank, "try the back wall", T + 600,
                                     answers=question.id)):
    threaded.add(each)
assert threaded.by_id(question.id).body == "anything in the cellar?"
assert [p.body for p in threaded.answers_to(question.id)] == \
    ["still nothing", "try the back wall"]
ok("and a node can find what answers what, in the order it was written")

# ---------- asking for a page by name ----------
from hearsay.store import ASK_PAGE

holder, seeker = Store(), Store()
wanted = write_page(hank, "tides", "Tides", "# Tides\ndusk, mostly.", T)
holder.shelve(wanted)
# Everything else is offered rather than requested, which leaves a link to a
# page nobody carried as a dead end.
seeker.note_wanted(wanted.at)
asked = seeker.ask_line()
assert asked.startswith(ASK_PAGE) and wanted.at in asked
handed = holder.answer_asked(asked.split("|", 1)[1], dave.address)
assert len(handed) == 1
assert seeker.shelve(Page.from_wire(handed[0].split("|", 1)[1]))
assert not seeker.asked_for, "once it arrives, stop asking"
ok("a page can be asked for by name, and the asking stops when it arrives")

assert Store().answer_asked("ffffffffffffffff/nope", "x") == []
assert not seeker.ask_line().split("|", 1)[1]
ok("asking after something nobody holds costs one short line and no more")

print(f"\nALL PASS  ({PASSED} checks)")
