# hearsay

Posts that travel at walking speed, over LoRa radio, on
[loraline](https://github.com/intervalplace/loraline).

Nothing is routed. A node keeps what it has heard and offers it to whoever
comes into range, so a post reaches you because a person walked between you and
its author, possibly through several others first. Your audience is geography:
everyone within earshot, and nobody beyond it. You cannot build a following and
you cannot go past your radio horizon.

## What the arithmetic decided

At SF7 under a one percent duty cycle a node has thirty-six seconds of airtime
an hour. A 140 character post costs 871 milliseconds to put on the air, which
owes eighty-seven seconds of silence. That is about **forty posts an hour
including everything relayed**.

For four or six people that is not scarcity, it is more than anybody would
write. But it settled three things before any of this was built:

- Posts are short. 140 characters, and the signature alone is eighty-eight.
- Nothing is ever sent to somebody who already has it. A meeting is: here is
  what I hold, then send me these, then here they are.
- A meeting hands over six posts at most, so one node cannot spend another's
  whole hour.

## What is provable and what is not

A post is signed once by its author and the signature travels with it for
ever. An address is sixteen hex characters, sixty-four bits, because it is
what a signature is checked against: at six it was about six minutes of
offline grinding to make a keypair that could write in somebody else's name,
and being on a radio did not help at all.
A carrier can drop a post, refuse to pass it on, or lie about where they got
it. What they cannot do is change a word of it or write one in somebody else's
name: the address is recomputed from the keys carried with the post, so an
invented signing key cannot be attached to a real name.

The trail of who carried it is a **claim, not a proof**. Signing every hop
would make it provable and cost eighty-eight characters a time, which at forty
posts an hour is not a trade worth making.

## Profiles

A name and a twelve by twelve picture in eight colours, signed and carried
exactly as a post is. It has to be signed: the person reading it has almost
certainly never met the person it describes, and a carrier handling somebody
else's face is precisely where forgery would matter.

A profile is 731 characters on the air, sent once and then only when it
changes. That owes 237 seconds of silence, against thirty-six seconds an hour,
which is affordable exactly because nobody changes their face twice a day.

**It can be a photograph.** Every picture brings its own eight colours, chosen
from the image itself, because a fixed palette is fine for something drawn and
hopeless for a face. Twelve square made a face a blot and twenty-four lost the
eyes: at that size a pupil is one pixel and eight colours cannot spare one for
it. Thirty-two is where a photograph still looks like the person, at 731
characters, sent once.

Sharpen first and do not dither. Dithering scatters a one pixel eye across
three pixels of nothing.

### Setting one

Open hearsay, find **you** at the bottom of the page, and click *use a
photograph*. Pick any image; the node squares it, takes the head end, reduces
it to thirty-two pixels and eight colours chosen from the picture itself, signs
it, and hands it on from then on.

The browser only shrinks it to 256 square first, which is a size guard rather
than the reduction: there is no sense pushing sixteen megabytes of a phone
photograph at something that will keep a thousand pixels of it. The reduction
itself happens in one place, in the node, so everybody's face is made the same
way.

**Everybody has a face before they draw one.** The default is derived from your
address, mirrored down the middle, in two of the eight colours. A stranger
arrives already looking like somebody rather than like a blank.

Faces are offered rather than asked for, a few at a time, because a post from
somebody with no face beside it is a worse thing than a few hundred characters
spent unprompted. The newest profile wins, and an older one cannot undo it.

## The pages that come with it

Five of them, at `/page/here/…`: what is here, writing a page, which
frequency, when nobody appears, and how a page travels.

They are local. Served from the program, never signed, never offered to
anybody, and they cost no radio time. Having each node write itself a
reference page would mean every node carrying the same text under a different
name, and two people meeting spending ten minutes of owed silence swapping
documents they both already had.

Everybody who can read a page has the program, and the program is where these
live. That leaves the channel for the only thing worth spending it on: what
somebody actually wrote.

A written page can link into them with `=> here/writing`, which resolves to
the reader's own copy.

## A page names itself

You write the text. Its first heading is its title, and the name it is found
by comes from that: `# Brød` becomes `brod`, which is what a link points at.

Being asked for a name, a title, and a body that begins with a heading was the
same word three times, and the reader only ever drew the heading anyway.

Names keep to letters, digits and hyphens because they go in addresses. The
awkward letters are spelled out rather than blanked, so `brød` is `brod` and
not `br-d`, which is not a word anybody meant.

The editor shows what it will be called as you type, using the same rules the
node uses, so what it promises is what gets stored.

## Answering somebody

A post can carry the id of the post it answers: six characters, signed along
with the words, and free, because it rides inside a frame that was going out
anyway.

It has to be signed. Otherwise a carrier could attach somebody's reply to a
different question, which is a cheap way to make anybody appear to have said
something unpleasant.

Three hops away, the post being answered often has not arrived. The feed says
so rather than pretending a reply was never a reply.

## Asking for a page

Everything else here is offered rather than requested, which works for things
people write and not at all for a link you followed to a page that never came.
So a page can be asked for by name: the reader offers it where a missing page
would otherwise be a dead end, the ask rides along at the next meeting, and
anybody holding that page hands it over.

The asking stops as soon as it arrives.

## Pages

A post is a sentence and a page is a document, and they travel the same way:
signed once, held by whoever has heard it, handed on to whoever comes near.
That is the whole difference, so it is not a separate thing.

The arithmetic settles the format. Two kilobytes of text is twenty frames, six
seconds on air and ten minutes of owed silence; a node can put out about six an
hour. An ordinary web page of two hundred kilobytes is seventeen hours. So:
text, four kilobytes at most, and a meeting hands over one page rather than
six.

Six kinds of line and nothing else:

```
# heading
## smaller heading
> something quoted
* a thing in a list
=> name what it is        a link, here or on somebody's node
```                       everything until the next fence is left alone
anything else             a paragraph
```

**Nothing here is HTML and no document can point off the radio.** A carried
page that could name a picture on the internet would have your browser quietly
fetch it, and then this is not a network that stands on its own, it is a slower
way of using the old one. The format cannot express a reference to anywhere
else, so it cannot be made to: a link is either a page on this radio or it is a
page name, whatever it looks like, and `=> https://example.com/x` becomes a
page nobody has written.

The node turns pages into markup itself, which is why an ordinary browser is
safe to read them with. It never sees anything the node did not write, so there
is nothing to be gained from building a browser.

Read one at `/page/<address>/<name>`, but nobody should ever have to type
that. An address alone goes to somebody's front page, `/pages` lists
everything held with faces beside it, and inside a document a link reads as
`hank/tides` while pointing at `/page/840f29/tides`.

The address is what a link resolves against and always will be: a nick is a
label, anybody can claim one, and two people called hank would collide. What
it is *shown* as is whoever you know that address to be, and somebody you have
never heard of stays six hex characters, which is the honest thing for them to
be.

A page you do not hold is not an error: it is somewhere the network has not
carried anything to you from yet, and it says so.

A newer page by the same author with the same name replaces the older one,
because a page is something somebody keeps rather than something they said
once.

## What a node holds

Two hundred posts, oldest forgotten first. A node is a person's pocket, not an
archive. Something it once held and let go is not asked for again, or two nodes
would trade the same post for ever.

There is no ranking and nothing is promoted. The only thing that ever happened
to a post is that people carried it, and how far it has come is already
visible.

## Running one

```
git clone https://github.com/intervalplace/loraline
git clone https://github.com/intervalplace/hearsay
pip install -r hearsay/requirements.txt
cd hearsay && PYTHONPATH=../loraline python tests.py
```

Then, with a radio:

```
export LORALINE_KEY="the phrase your town agreed"
PYTHONPATH=../loraline python -m hearsay --name yourname \
    --port /dev/ttyUSB0 --band eu868
```

Open `localhost:8080`. Without a radio, `--tcp-listen 4242` and
`--tcp-connect somewhere:4242` will do for trying it.

**It wants to stay running.** A node that is only on while you are looking at
it carries nothing: the whole mechanism is holding posts between meetings and
handing them on when somebody passes. It belongs on something that stays on.

## Surviving being put down

The pocket is written to disk beside the identity and read back at startup,
and everything in it is verified on the way in exactly as if it had arrived
over the air. A file is no more trustworthy than a stranger.

Without this a node forgot everything it was carrying whenever it restarted,
which for a daemon whose entire job is to hold things between meetings is not
a small bug.

## Licence

MIT.
