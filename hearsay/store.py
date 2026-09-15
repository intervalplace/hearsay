"""What a node is holding, and what it says when it meets somebody.

Nothing is routed. A node keeps what it has heard and offers it to whoever
comes into range; posts spread because people move, at the speed people move.

The exchange has to be miserly. A node has thirty-six seconds of airtime an
hour, a post costs the best part of a second, and the alternative to being
careful is a channel that spends its whole allowance sending people things
they already had. So a meeting goes:

    I hold these          a list of ids, a few bytes each
    then send me these    only the ones they lack
    here they are         newest first, and only a handful

Which is also why the store is small and forgets. A node is a person's pocket,
not an archive.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .page import Page
from .post import Post
from .profile import Profile

HOLD = 200               # posts kept, at most
OFFER = 40               # ids named in one breath
GIVE_PER_MEETING = 6     # posts handed over before waiting to meet again

# Pages are twenty times the size of a post and read far less often, so a
# node holds fewer of them and parts with one at a time. Two kilobytes is ten
# minutes of owed silence; handing over six would be an hour of the channel.
HOLD_PAGES = 40
GIVE_PAGES_PER_MEETING = 1

HAVE, WANT, GIVE = "h", "w", "g"
FACE = "f"               # a profile, offered without being asked for
PAGES, WANT_PAGE, GIVE_PAGE = "p", "q", "r"
ASK_PAGE = "a"           # by name, for a page you have only seen a link to


@dataclass
class Store:
    """A node's pocket. Ordered newest first."""

    posts: dict = field(default_factory=dict)      # id -> Post
    seen: set = field(default_factory=set)         # ids we once held
    faces: dict = field(default_factory=dict)      # author -> Profile
    pages: dict = field(default_factory=dict)      # id -> Page
    read_pages: set = field(default_factory=set)   # page ids once held
    asked_for: set = field(default_factory=set)    # author/name wanted, by name
    path: object = None                            # where it lives on disk

    # -- keeping -----------------------------------------------------------

    def add(self, post: Post) -> bool:
        """Take a post in. Returns True if it was new to us.

        Refuses anything that does not verify, because a post that cannot be
        checked is a post somebody wrote in another person's name, and the
        whole arrangement depends on that being impossible.
        """
        if not post.verify():
            return False
        here = self.posts.get(post.id)
        if here is not None:
            # Same post, longer trail: keep whichever knows more of its own
            # history, so a story does not lose its path by arriving twice.
            if post.distance > here.distance:
                here.hops = post.hops
            return False
        self.posts[post.id] = post
        self.seen.add(post.id)
        self._forget()
        return True

    def meet_face(self, profile: Profile) -> bool:
        """Take somebody's profile in, if it is really theirs and newer.

        Profiles are not asked for. They are small, they change rarely, and a
        post from a stranger with no face beside it is a worse thing than a
        few hundred characters spent unprompted.
        """
        if profile is None or not profile.verify():
            return False
        known = self.faces.get(profile.author)
        if known is not None and known.updated >= profile.updated:
            return False
        self.faces[profile.author] = profile
        return True

    def face_of(self, author: str):
        """Whatever we know of somebody. None means we have their posts but
        have never been near anybody carrying their face."""
        return self.faces.get(author)

    def faceless(self) -> list:
        """Authors whose posts we hold and whose faces we do not."""
        return sorted({p.author for p in self.posts.values()} - set(self.faces))

    def _forget(self) -> None:
        """A pocket has a size. The oldest go first: a post that has been
        around for a week has either arrived or is not going to."""
        if len(self.posts) <= HOLD:
            return
        ordered = sorted(self.posts.values(), key=lambda p: (-p.written, p.id))
        self.posts = {p.id: p for p in ordered[:HOLD]}

    def by_id(self, post_id: str):
        """One post by its id, if it is still held."""
        return self.posts.get(post_id)

    def answers_to(self, post_id: str) -> list:
        """Everything held that replies to this one, oldest first."""
        return sorted((p for p in self.posts.values() if p.answers == post_id),
                      key=lambda p: (p.written, p.id))

    def recent(self, limit: int = OFFER) -> list:
        return sorted(self.posts.values(),
                      key=lambda p: (-p.written, p.id))[:limit]

    def __contains__(self, post_id: str) -> bool:
        return post_id in self.posts

    def __len__(self) -> int:
        return len(self.posts)

    # -- meeting somebody --------------------------------------------------

    def have_line(self) -> str:
        """What to say first: the ids of what we are carrying."""
        return HAVE + "|" + ",".join(p.id for p in self.recent())

    def want_line(self, have_text: str) -> str:
        """What we would like out of what they just offered.

        Only ids we have never held. Something we took in and later forgot is
        something we have already had our turn with, and asking for it back
        would have a pair of nodes trading the same post for ever.
        """
        offered = [i for i in have_text.split(",") if i]
        missing = [i for i in offered if i not in self.posts and i not in self.seen]
        return WANT + "|" + ",".join(missing[:GIVE_PER_MEETING * 2])

    def give_lines(self, want_text: str, carrier: str,
                   limit: int = GIVE_PER_MEETING) -> list:
        """The posts they asked for, newest first, and not too many.

        Our own address goes on as we hand each one over, so the post carries
        the trail of who it passed through.
        """
        asked = [i for i in want_text.split(",") if i]
        out = []
        for post_id in asked:
            post = self.posts.get(post_id)
            if post is None:
                continue
            out.append(GIVE + "|" + post.carried_by(carrier).to_wire())
            if len(out) >= limit:
                break
        return out

    # -- reading ------------------------------------------------------------

    # -- pages -------------------------------------------------------------

    def shelve(self, page: Page) -> bool:
        """Take a page in, if it is really that person's.

        A newer page by the same author with the same name replaces the older
        one: a page is a thing somebody keeps rather than a thing they said
        once, which is the whole difference from a post.
        """
        if page is None or not page.verify():
            return False
        here = self.pages.get(page.id)
        if here is not None:
            if page.distance > here.distance:
                here.hops = page.hops
            return False
        older = [p for p in self.pages.values()
                 if p.at == page.at and p.written < page.written]
        newer = [p for p in self.pages.values()
                 if p.at == page.at and p.written >= page.written]
        if newer:
            return False          # we already have this one or a later one
        for stale in older:
            self.pages.pop(stale.id, None)
        self.pages[page.id] = page
        self.read_pages.add(page.id)
        self.asked_for.discard(page.at)
        if len(self.pages) > HOLD_PAGES:
            ordered = sorted(self.pages.values(), key=lambda p: (-p.written, p.id))
            self.pages = {p.id: p for p in ordered[:HOLD_PAGES]}
        return True

    def page_at(self, at: str):
        """Somebody's page by name, the newest we hold of it."""
        found = [p for p in self.pages.values() if p.at == at]
        return max(found, key=lambda p: p.written) if found else None

    def shelf(self, limit: int = HOLD_PAGES) -> list:
        return sorted(self.pages.values(), key=lambda p: (-p.written, p.at))[:limit]

    def pages_line(self) -> str:
        return PAGES + "|" + ",".join(p.id for p in self.shelf(OFFER))

    def want_page_line(self, have_text: str) -> str:
        offered = [i for i in have_text.split(",") if i]
        missing = [i for i in offered
                   if i not in self.pages and i not in self.read_pages]
        return WANT_PAGE + "|" + ",".join(missing[:2])

    def ask_line(self) -> str:
        """Pages somebody has pointed at that nobody has carried here.

        Everything else in hearsay is offered rather than requested, which
        works for things people write and not at all for a link you followed
        to a page that never arrived.
        """
        return ASK_PAGE + "|" + ",".join(sorted(self.asked_for)[:4])

    def answer_asked(self, asked_text: str, carrier: str,
                     limit: int = GIVE_PAGES_PER_MEETING) -> list:
        """Hand over a named page, if this node happens to hold it."""
        out = []
        for at in (x for x in asked_text.split(",") if x):
            page = self.page_at(at)
            if page is None:
                continue
            out.append(GIVE_PAGE + "|" + page.carried_by(carrier).to_wire())
            if len(out) >= limit:
                break
        return out

    def note_wanted(self, at: str) -> None:
        if at and self.page_at(at) is None and len(self.asked_for) < 16:
            self.asked_for.add(at)

    def give_page_lines(self, want_text: str, carrier: str,
                        limit: int = GIVE_PAGES_PER_MEETING) -> list:
        asked = [i for i in want_text.split(",") if i]
        out = []
        for page_id in asked:
            page = self.pages.get(page_id)
            if page is None:
                continue
            out.append(GIVE_PAGE + "|" + page.carried_by(carrier).to_wire())
            if len(out) >= limit:
                break
        return out

    def face_lines(self, mine=None, limit: int = 3) -> list:
        """Faces worth offering at a meeting: ours first, then a few others we
        are carrying. A face travels the same way a post does."""
        out = []
        if mine is not None:
            out.append(FACE + "|" + mine.to_wire())
        for author in sorted(self.faces):
            if mine is not None and author == mine.author:
                continue
            out.append(FACE + "|" + self.faces[author].to_wire())
            if len(out) >= limit:
                break
        return out

    def feed(self, limit: int = 60) -> list:
        """Everything held, newest first. There is no ranking and nothing is
        promoted: the only thing that happened to a post is that people carried
        it, and that is already visible in how far it has come."""
        return sorted(self.posts.values(), key=lambda p: (-p.written, p.id))[:limit]

    def by(self, author: str) -> list:
        return [p for p in self.feed(HOLD) if p.author == author]

    # -- surviving a restart ----------------------------------------------

    def load(self, path) -> "Store":
        """Read the pocket back.

        A node is a daemon: it is supposed to be holding things between
        meetings, and one that forgets everything when it restarts carries
        nothing at all. Everything is verified on the way in, exactly as if it
        had arrived over the air, because a file on disk is no more
        trustworthy than a stranger.
        """
        self.path = Path(path)
        if not self.path.exists():
            return self
        try:
            raw = json.loads(self.path.read_text())
        except Exception:
            return self
        for line in raw.get("posts", []):
            post = Post.from_wire(line)
            if post is not None:
                self.add(post)
        for line in raw.get("faces", []):
            self.meet_face(Profile.from_wire(line))
        for line in raw.get("pages", []):
            self.shelve(Page.from_wire(line))
        self.seen.update(raw.get("seen", []))
        self.read_pages.update(raw.get("read", []))
        self.asked_for.update(raw.get("asked", []))
        return self

    def save(self) -> None:
        """Written whole and moved into place, so a node killed mid-write
        comes back to the pocket it had rather than half of one."""
        if self.path is None:
            return
        body = json.dumps({
            "posts": [p.to_wire() for p in self.recent(HOLD)],
            "faces": [f.to_wire() for f in self.faces.values()],
            "seen": sorted(self.seen)[-HOLD * 4:],
            "pages": [p.to_wire() for p in self.shelf()],
            "read": sorted(self.read_pages)[-HOLD_PAGES * 4:],
            "asked": sorted(self.asked_for),
        }, separators=(",", ":"))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(body)
            os.replace(temporary, self.path)
        except OSError:
            pass          # a node that cannot write should still carry
