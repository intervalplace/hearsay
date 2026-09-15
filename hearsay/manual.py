"""The pages that come with the program.

There is an obvious way to do this badly: have each node write itself a
reference page at first run, signed by whoever owns it. Then every node on the
radio is carrying its own copy of the same text under a different name, and
two people meeting spend ten minutes of owed silence swapping documents they
both already had.

So these are local. They are served from here, they cost no airtime, they are
never offered to anybody and never signed. Everybody who can read a page has
the program, and the program is where these live.

That leaves carried pages for the only thing worth spending the channel on:
what somebody actually wrote.
"""

HOME = "here"          # not sixteen hex characters, so it cannot be an address

PAGES = {
    "index": ("What is here", """# What is here

These pages came with the program. They cost no radio time and never leave
this machine.

=> here/writing writing a page of your own
=> here/bands which frequency you are allowed to use
=> here/trouble when two radios cannot hear each other
=> here/carrying how a page reaches somebody else

Everything else on the shelf was written by a person and carried to you.
"""),

    "writing": ("Writing a page", """# Writing a page

A page is text, four kilobytes at most. Six kinds of line and nothing else:

```
# a heading
## a smaller heading
> something quoted
* a thing in a list
=> name what the link says
anything else is a paragraph
```

A link is either a page on this radio or it is a page name. Write a bare name
for one of your own pages, or an address and a name for somebody else's. There
is no way to point at anything off the radio, which is deliberate: a page that
could name a picture on the internet would have your browser fetch it.

Your name for the page becomes part of its address, so keep it short. Writing
a page with a name you have used before replaces the old one everywhere it has
reached.

## What is worth putting on one

Things that matter to people near you and nobody else. When the bread is
ready. Which spot is worth fishing. What the tide does. A page that would be
just as useful to a stranger a thousand miles away probably belongs on the
ordinary internet, where it is free to send.
"""),

    "bands": ("Which frequency", """# Which frequency

This is a legal matter rather than a preference, and it differs by country.
The program asks you once and then remembers.

## Europe, the UK, Norway

868 MHz. You may transmit for 1% of the hour, which is thirty-six seconds.
That is not a small allowance: a short message is about a quarter of a second.
The program shows what is left and holds messages back rather than pretending
they were sent.

## United States, Canada, Australia, New Zealand

915 MHz. No hourly limit. The program is still slow, because the radio is
slow, but nothing is rationed.

> Everybody you talk to has to be on the same band. If somebody cannot hear
> you, this is the first thing to check.
"""),

    "trouble": ("When nobody appears", """# When nobody appears

Three different faults look identical from the outside. This tells them apart.

Start the program with a trace:

```
LORALINE_TRACE=/tmp/loraline.log
```

Every line the radio hears is written to that file, with whether it decoded.

## Nothing in the file at all

The radios are not reaching each other, or one of them is not on the band it
thinks it is. Check both are on the same band. Then move one of them: two
radios a metre apart on the same desk is a harder test than two rooms apart,
because a receiver can be deafened by a transmitter that close.

## Lines arriving, marked NOT FOR US

They are reaching each other. The passphrases differ. Agree one out loud and
set it in the room panel.

## Lines decoding but nobody appearing

That is a fault in the program rather than in the radio. Worth reporting.
"""),

    "carrying": ("How a page travels", """# How a page travels

Nothing is routed. A page reaches you because somebody carried it.

When two nodes come into range they say what they are holding, as a list of
short ids. Anything you have never held, you ask for. One page crosses per
meeting, because two kilobytes is six seconds on the air and ten minutes of
owed silence afterwards.

So a page spreads at walking speed, and only as far as people actually walk.
Something nobody carries dies, which is the closest thing here to an editor.

## What can be proved

The signature travels with the page. Anybody can check that the person whose
address is on it wrote those exact words, even three hops away, even having
never met them.

The trail of who carried it is a claim rather than a proof. A carrier can drop
a page or lie about where it came from. They cannot change a word of it or
write one in somebody else's name.
"""),
}


def has(name: str) -> bool:
    return name in PAGES


def titled(name: str) -> str:
    return PAGES[name][0] if name in PAGES else name


def body(name: str) -> str:
    return PAGES[name][1] if name in PAGES else ""


def listing() -> list:
    """(name, title) for the shelf, index first."""
    order = ["index"] + [n for n in PAGES if n != "index"]
    return [(n, PAGES[n][0]) for n in order]
