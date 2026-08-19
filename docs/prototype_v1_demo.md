# Prototype v1 — 10–15 minute stakeholder demo

Use the **live Farmer Edition UI** and the canonical **Knockrow Mixed Farm** sample.
This is labelled **SAMPLE / DEMO DATA** in the sidebar. Do not present it as a real farm.

Start locally (`docs/deployment.md`):

```bash
set FARMBIDDY_SEED_DEMO=1
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The farm is mixed (Dairy, Beef and Sheep) and analysis is always whole-farm. Wait until **Your Farm at a Glance** fills in.

Keep the story on farmer problems, not modules. Do not mention Monte Carlo, SQL, or APIs until the last 60 seconds.

---

## A. The problem (≈1 min)

Farm money is usually split across paperwork, invoices, spreadsheets, the accountant, and the processor.

FarmBiddy’s job in this prototype is to **collect → organise → understand → compare → forecast → act** so the farmer can answer everyday questions without becoming a modeller.

Say clearly: today the farmer (or a demo operator) still types invoices and records. Later, the main FarmBiddy platform can feed this service automatically. **OCR, bank feeds and accounting sync are not in this prototype.**

---

## B. Home — “How am I doing?” (≈2 min)

Stay on **Overview**.

Point to, in this order:

1. **SAMPLE / DEMO DATA** on the left — this is the canonical demo farm.
2. **This Month** — Income (money in), Costs (money out), Difference.
3. **Your Farm at a Glance**
   - Cash Available
   - Expected Future Cash (lowest point) — this is the early-warning number
   - Expected Cash Over the Year
   - Expected Annual Farm Profit
   - Needs Your Attention / What To Do Next
4. **Cash Position — Actual & Forecast** — solid line = already happened; dashed = expected ahead.

Ask the room: *Can a farmer answer cash, in/out, performance, and “is anything coming up” from this one screen?* Then move on. Do not open “More detail” unless asked.

---

## C. Recording finances (≈2 min)

**Cash Flow → Income & Expenses**

Show organised categories (where money came from / went). Point at **Add an entry**. Say: this is how a farmer records a cheque or a bill today.

**Cash Flow → Invoices & Receipts**

The demo already has:

- a paid **receipt** (diesel)
- an unpaid **invoice** (silage contractor)

Walk: add → review → confirm paid. Paid + confirmed documents become farm Actuals. Unpaid invoices stay visible without pretending the cash has left.

**Intended direction (one sentence):** manual and document entry now; later a provider can propose documents (OCR / bank / accounts) and the farmer still confirms before Actuals change. That seam exists; no live provider is wired.

Do not click Advanced Analysis here.

---

## D. Cash flow (≈2 min)

**Cash Flow → Forecast**

Show expected cash and profit over the next year. Name **Actual** (already recorded), **Budget** (the plan), **Forecast** (what the engine expects). They are three different things and are never mixed into one fake number.

Call out **Expected Future Cash (lowest point)** on Overview and the same dip on this forecast. On the canonical demo the lowest point is **late in the forecast (month 12)** and **Needs Your Attention** includes future negative cash / widening overdraft. That is the point of looking forward: time to talk to the lender, delay a purchase, or change a payment — before the month arrives.

**Cash Flow → Loans & Finance** (30 seconds) — two loans on the demo farm; repayments sit in the cash picture.

---

## E. Budget vs Actual (≈1.5 min)

**Cash Flow → Budget vs Actual**

1. **Monthly Budget vs Actual** — is the farm ahead or behind plan on cash in/out?
2. **Budget by Category** — which categories drive that.

On the seeded demo the **overall category position is slightly ahead** (milk income above its budget). **Feed** and **fertiliser** are above budget — use those as “what’s causing the cost overruns,” not as a claim that the whole farm is behind. Missing budget is “not set yet”, not zero.

---

## F. Profitability / previous performance (≈1.5 min)

**Farm Performance → Sector Performance** — dairy / beef / sheep contribution.

**Farm Performance → Previous Years** — income, costs, farm profit, cash generated, like-for-like months. The demo has full 2024 and 2025 history plus a seeded later month.

This answers: *How am I doing compared with last year?*

---

## G. What If? (≈2 min)

**Advanced Analysis → What If?**

Click **Milk price falls 5c/L**. Wait for the comparison cards:

- Income change
- Profit change
- Lowest cash point
- Year-end cash

Say: nothing here is saved as a real farm figure. It is the same forecast engine with one assumption changed.

If asked “what else?”: feed +10%, fertiliser, labour, fuel, or a machinery purchase. Do not open Engine Charts or dwell on the profit-outlook range unless the audience is technical.

---

## H. Needs Your Attention (≈1 min)

**Action Plan → Alerts (Needs Your Attention)**

The demo analysis typically surfaces several issues (for example widening overdraft / cash-flow warnings). Read **what / when / why it matters**, then note that the farmer is not expected to inspect every chart.

The Overview card already tees this up; this screen is the list they would actually work.

---

## I. Advisor / accountant (≈1 min)

**Action Plan → Reports**

Select **Accountant / Advisor Summary** → **Preview Report**. Cards should show cash in the model, last-12-months net, lowest expected cash, and total debt — not dashes. Optionally **Generate & Download PDF**.

Walk the pack: SAMPLE cover with legal name / VAT / processor; farm position (cash, debtors, creditors, land, stock, drawings); loans with principal and estimated outstanding; cash forecast as **Jan–Dec**, not “Month 12”. It is **not** statutory accounts. Do not generate Full or Investment for this beat.

---

## J. Future integration (≈45 sec, optional)

Only if the audience is technical or FarmBiddy platform owners:

```
Main FarmBiddy Platform
  → authenticates the user and authorised farm
  → calls this Financial API
  → IdentityProvider maps claims
  → financial services stay farm-scoped
  → forecast_engine calculates
  → structured response
```

This prototype uses a development identity adapter. Real login belongs on the main platform. Details: `docs/main_platform_integration.md`.

---

## Timing cheat-sheet

| Min | Stop |
|---|---|
| 0–1 | Problem |
| 1–3 | Overview |
| 3–5 | Records + documents |
| 5–7 | Cash / loans |
| 7–9 | Budget vs Actual + performance |
| 9–11 | What If? |
| 11–13 | Alerts + advisor report |
| 13–15 | Questions / integration one-liner |

If short on time: **B → D → G → H**. Those four prove collect, forecast, decide, act.
