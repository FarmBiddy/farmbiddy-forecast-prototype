# Prototype v1 — farmer feedback script

Use this when sitting with a farmer (or farm manager) in front of the **live** Prototype v1 UI and the Knockrow Mixed Farm **SAMPLE / DEMO** data.

Do not pitch. Do not explain the screen first. Watch what they do, then ask.

Session length: **20–30 minutes**. One facilitator, one note-taker if possible.

Remind them this is sample data, not their farm. We are testing whether the **product idea** solves the survey problems (one place for money, less paperwork, clearer in vs out, profit, future cash, history, simplicity).

---

## Setup

1. App running (`FARMBIDDY_SEED_DEMO=1`), Overview loaded, analysis finished.
2. Sectors: Dairy + Beef + Lamb.
3. Facilitation machine: tablet or laptop (the prototype is demonstrated primarily on desktop/tablet).
4. Do not hover over the mouse unless they are stuck for more than ~20 seconds — then give the smallest hint and mark the task **hinted**.

Score each task:

| Code | Meaning |
|---|---|
| U | Unassisted — found it and explained it |
| H | Hinted — needed one prompt |
| F | Failed — did not find or misunderstood |
| N | Not attempted |

---

## Tasks (do these first)

### Task 1 — First impression

**Prompt:** *Without me explaining the screen, tell me how you think the farm is doing.*

Listen for, in their own words:

- cash / money on hand
- money in / money out
- profit or “how the year looks”
- a warning or something coming up

| Observed | Y / N / unclear |
|---|---|
| Mentions cash | |
| Mentions income or costs | |
| Mentions profit or performance | |
| Notices a warning / “attention” | |
| Thinks SAMPLE data is their real farm | |

Task score: U / H / F

Notes:

### Task 2 — Record an expense

**Prompt:** *Show me where you would record a farm expense.*

Success: they reach **Cash Flow → Income & Expenses** (add entry) **or** **Invoices & Receipts**. Either is valid; note which they chose.

| Observed | Y / N |
|---|---|
| Found a recording place without a hint | |
| Confused with Farm Data / Settings / What If? | |
| Would rather photograph a docket than type | |

Task score: U / H / F

Notes:

### Task 3 — Future cash problem

**Prompt:** *Find out whether the farm is expected to have a cash problem later this year.*

Success: Overview **Expected Future Cash (lowest point)**, or **Cash Flow → Forecast**, or an alert about cash/overdraft. They should say *when* if the UI shows a month.

| Observed | Y / N |
|---|---|
| Used Overview lowest-cash card | |
| Opened Cash Flow forecast | |
| Used Needs Your Attention | |
| Confused Actual with Forecast | |

Task score: U / H / F

Notes:

### Task 4 — Feed vs budget

**Prompt:** *Tell me whether feed spending is ahead or behind budget.*

Success: **Cash Flow → Budget vs Actual → Budget by Category**, and a correct ahead/behind (or “over/under”) for feed.

| Observed | Y / N |
|---|---|
| Found category Budget vs Actual | |
| Looked only at monthly cash budget | |
| Treated “no budget” as zero | |
| Correct direction for feed | |

Task score: U / H / F

Notes:

### Task 5 — Milk price fall

**Prompt:** *See what would happen if milk price fell.*

Success: **Advanced Analysis → What If?** and **Milk price falls 5c/L** (or they type a similar change). They should mention profit and/or cash, not just “it would be worse”.

| Observed | Y / N |
|---|---|
| Found What If? without a hint | |
| Looked in Ask Farm Intelligence instead | |
| Mentions profit impact | |
| Mentions cash / lowest cash | |
| Worried the scenario had saved over real figures | |

Task score: U / H / F

Notes:

---

## After the tasks — short questions

Ask only what you still need. Keep answers concrete.

1. What was confusing or easy to miss?
2. What information would you check most often? (cash / in-out / budget / forecast / alerts / other)
3. What would you never use?
4. What still requires too much work compared with how you do it now?
5. What would you want FarmBiddy to collect automatically? (invoices, bank, processor, accountant file, other)
6. Would this replace any spreadsheet or paper process you currently use? Which?
7. What would make you open FarmBiddy every week?
8. What would make this worth paying for? (time back, lender conversations, fewer surprises, replacing an accountant visit, other)

Do **not** ask “do you like it?”

---

## Scoring (1–5)

1 = not at all · 3 = mixed / only with help · 5 = strongly yes

| Dimension | 1 | 2 | 3 | 4 | 5 | Notes |
|---|---|---|---|---|---|---|
| Usefulness — would this help run the farm’s money? | | | | | | |
| Ease of use — could they find things without us? | | | | | | |
| Clarity — words and numbers made sense | | | | | | |
| Time saving — less work than current method | | | | | | |
| Trust — would they act on these numbers? | | | | | | |
| Willingness to use — would they open it weekly? | | | | | | |
| Willingness to pay — would they pay if it did X? | | | | | | |

Record what “X” was for willingness to pay (e.g. “if invoices came in automatically”).

---

## Session log (one row per farmer)

| Field | Value |
|---|---|
| Date | |
| Role (farmer / partner / manager / other) | |
| Sectors they actually run | |
| Task 1–5 scores | |
| Hint count | |
| Would replace paper/spreadsheet? | Y / N / partial |
| Auto-collect wish | |
| Weekly-use trigger | |
| Pay trigger | |
| Biggest confusion | |
| Quote (optional, one sentence) | |

After a handful of sessions, the next development priority should come from **repeated** F/H tasks and pay/weekly-use answers — not from a new feature list.
