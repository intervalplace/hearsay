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

from .post import Post
from .profile import Profile

HOLD = 200               # posts kept, at most
OFFER = 40               # ids named in one breath
GIVE_PER_MEETING = 6     # posts handed over before waiting to meet again

HAVE, WANT, GIVE = "h", "w", "g"
FACE = "f"               # a profile, offered without being asked for


@dataclass
class Store:
    """A node's pocket. Ordered newest first."""

    posts: dict = field(default_factory=dict)      # id -> Post
    seen: set = field(default_factory=set)         # ids we once held
    faces: dict = field(default_factory=dict)      # author -> Profile
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
        self.seen.update(raw.get("seen", []))
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
        }, separators=(",", ":"))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(body)
            os.replace(temporary, self.path)
        except OSError:
            pass          # a node that cannot write should still carry
