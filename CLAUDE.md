# CLAUDE.md — instructions for AI analysis tasks in BRRR Scout

This file documents what Claude must do when the app (or the user, in a chat)
sends a **floorplan image** or an **auction legal pack PDF**. The live prompts
are defined in `analyzer.py` (`CONVERSION_PROMPT`, `PACK_PROMPT`); this file is
the human-readable contract they implement. If you change one, change both.

Model: `claude-sonnet-4-20250514` via `POST https://api.anthropic.com/v1/messages`
with `ANTHROPIC_API_KEY` from the environment. Responses must be **JSON only —
no markdown fences, no preamble** — because the app parses them directly.

---

## Task 1 — Floorplan image: 1-bed → 2-bed conversion check

**When:** a 1-bed listing has a floorplan. The strategy: move the kitchen into
the open-plan living room and turn the old kitchen into a bedroom.

**What Claude must assess, in order:**
1. **Kitchen window** — the old kitchen becomes a habitable room, so it must
   have natural light and ventilation. No window = NOT convertible. If the
   plan doesn't show windows clearly, answer "unclear", never guess.
2. **Kitchen size** — the new bedroom should be ≥ ~7 m². Read dimensions off
   the plan if printed; otherwise estimate from scale and say so.
3. **Living room capacity** — must fit a kitchen run plus remain a usable
   lounge; check for a sensible wall for plumbing/units.
4. **Fire escape** — the new bedroom must not have its only exit through the
   new kitchen area. Look for a hallway/protected route.
5. **Plumbing distance** — note if the new kitchen wall is far from existing
   stack/drainage (cost flag, not a blocker).

**Required JSON shape:**
```json
{
  "convertible": true | false | "maybe",
  "kitchen_has_window": true | false | "unclear",
  "kitchen_size_ok": true | false | "unclear",
  "living_room_fits_kitchen": true | false | "unclear",
  "fire_escape_ok": true | false | "unclear",
  "estimated_kitchen_sqm": 8.2,
  "concerns": ["short, specific issues"],
  "summary": "one sentence"
}
```

**Rules:** be conservative — "maybe" beats a false "yes"; the user spends real
money on these verdicts. Never invent dimensions. Always remind in `concerns`
when relevant that flats need freeholder consent (licence to alter) and all
conversions need Building Regulations sign-off; windows and escape routes must
be verified at viewing.

---

## Task 2 — Legal pack PDF: red-flag screening

**When:** the user uploads an auction legal pack (title register, lease,
searches, special conditions of sale, tenancy docs, EPC).

**What Claude must hunt for, in priority order:**
1. **Lease length** — under 80 years remaining is a refinance killer for BTL
   lenders; under 70 is near-unmortgageable. Freehold = clear this item.
2. **Special conditions money traps** — buyer pays seller's legal fees,
   auctioneer "administration" charges, arrears, ground rent doublers,
   contributions to the seller's costs. Estimate the total extra £.
3. **Title issues** — possessory (not absolute) title, restrictive covenants
   blocking alteration/letting, missing land, rights of way through the plot,
   unregistered portions.
4. **Tenancy reality** — tenant in situ? AST present? rent and arrears stated?
   "Sold with vacant possession" actually evidenced?
5. **Completion window** — 28 days is standard; under 21 flags bridging risk.
6. **Searches** — present and recent, or is the buyer expected to indemnify?
7. **Environmental** — Japanese knotweed, flood zone, mining/contamination.

**Required JSON shape:**
```json
{
  "tenure": "freehold" | "leasehold" | "unclear",
  "lease_years_remaining": 62,
  "tenanted": true | false | "unclear",
  "buyer_pays_seller_fees": true | false | "unclear",
  "extra_buyer_costs_estimate": 3400,
  "title_issues": ["..."],
  "searches_included": true | false | "unclear",
  "japanese_knotweed_or_environmental": true | false | "unclear",
  "completion_days": 28,
  "red_flags": ["one line each, most serious first"],
  "risk": "LOW" | "MEDIUM" | "HIGH",
  "summary": "two sentences max"
}
```

**Risk calibration:** HIGH = any single deal-killer (lease <80y, possessory
title, knotweed, fee traps >£2k, covenant against letting). MEDIUM = gaps and
costs that need pricing in. LOW = clean pack, standard conditions. When the
PDF is partial or scanned poorly, say so in `summary` and never downgrade risk
because information is missing — missing information IS risk.

**Always end the summary with the reminder that this is screening, not legal
advice, and the pack still goes to a solicitor before bidding.**

---

## Task 3 — chat usage (no app)

If the user pastes a floorplan or legal pack directly into a Claude chat and
mentions BRRR Scout or these strategies, follow the same checklists and produce
the same JSON, then add a short plain-English explanation underneath. Same
conservatism rules apply.
