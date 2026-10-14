# Product strategy: open reference hardware (2026-10-14)

Captured from Joe's thinking on the drive in, 2026-10-14. Strategy note, not a plan: no product is committed yet.
Related: `Claude Reefer Upgrade Plan` (Group 4 control target), LSSS repo `docs/GROUP-7-HARDEN-LSSS.md`
(the safety layer the hardware leans on).

## Where this came from
- Over the last ~6 weeks Joe watched a wave of people use Claude, ChatGPT and the like to build their own front ends
  for Apex and Hydros. It was discouraging: the software layer he had been working on was something he thought he
  could innovate in, and suddenly everyone could make one.
- Joe's conclusion: you can't fight that waterfall, and you shouldn't try. Everyone has access to the same tools.
  Instead, put a boat in the water.
- The long-term goal behind all of it: a career in the coral business, whether coral or equipment.

## The thesis
- **The software front end is now a commodity.** Anyone can make one with an AI. Let them. Give the software ideas
  away (designs, patterns, the LSSS approach) for people to iterate on.
- **The hardware is the return path.** Those front ends all hit the same wall: Apex and Hydros are closed monitors.
  The AI can see everything and safely touch almost nothing. What people come back for is a piece of hardware they
  can actually act through.
- **What to build: open, network-connected devices** that work in any ecosystem: driven from Hydros inputs, Apex,
  GHL, the LSSS, or directly from someone's own AI. A universal, open controller family.
- **Safety lives in the device, not the model.** Veto, max-on timer, auto-off, never failing silently: built into the
  hardware and firmware, so the AI never has to be trusted with the dangerous part. This is the same split already
  used at home: the LSSS is the deterministic layer, Claude Reefer the intelligence on top.
- **The LSSS becomes the reference implementation**, the working proof of how these devices are meant to be used,
  rather than a controller competing head-on with Apex.
- **Open source and for sale at once.** Publish the design; sell the built, tested unit. Joe: it works on both sides.

## A product line, not one product (Joe 10-14)
Joe: the current outlet box is "absolutely crazy", optimised for heater control and heavy duty, and does a lot most
people don't need. The line needs layers:

| Tier | What it is | Role |
|---|---|---|
| USB ESP temperature probe | Plug into USB, log your own temperature easily | Simplest entry; open design + sold unit |
| ATO | Simple on/off: an outlet or dry contact driving a pump | Simple, but where failure costs real money (flood / dry pump) |
| Basic outlet box | Switching for "don't care if it's off" gear (skimmer, powerheads, roller, mixing pump) | Everyday switching, open to any controller or AI |
| Heater-grade outlet box | Joe's current design | Top tier; the only thing that should ever control heaters |

Common thread: one clean, open, documented protocol across every device, with safety in the hardware.

## Open questions
- Which device ships first: the simple entry device (adoption, credibility, gets people in the door) or the
  heater-grade outlet box (furthest along, proves the ceiling)?
- What the open protocol looks like, and how it plugs into Hydros inputs, Apex, GHL and plain AI clients.
- Licence for the open designs, and what stays proprietary (if anything).
- How Joe's Coral Reef / Corallite Labs fit: where the equipment line sits next to the coral business.
- Whether the basic outlet box is a cut-down heater box or its own simpler design.

## Effect on current work
- Group 4 switching is built against Joe's own outlet box (decided 10-14), which is now also the first proof of the
  product thesis.
- Group 7 (never fail silently, plain-language notices, sign-in, scoped machine keys) is product work, not just home
  lab polish: it is the behaviour the reference design has to demonstrate.
