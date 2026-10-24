# AI Subscription & Spending Analyzer

Upload a bank or credit-card statement and the app finds your subscriptions, flags double charges and price rises, shows where your money goes, and suggests where you could save. It reads statements as they come from the bank, with no reformatting.

![Dashboard](docs/dashboard.png)
![Charts](docs/charts.png)

## The problem

Bank statements are a wall of cryptic text (`NETFLIX.COM 866-579-7172`, `UPI-SWIGGY-swiggy@icici-4411`). Subscriptions are easy to forget, prices creep up, services sometimes charge twice, and nothing tells you what to cut. This project turns a raw statement into answers:

- Which charges are subscriptions, and what do they cost per year?
- Did any service charge me twice, or after I cancelled?
- Did a price go up? Am I paying for overlapping services?
- Where does the rest of my money go, and when did it spike?

## Features

- **Reads real statement layouts.** CSV and Excel (.xlsx); junk lines above the header; no header at all; comma, semicolon, tab or pipe separators; UTF-16 files; separate Debit/Credit columns, one signed amount column, or an amount with a Dr/Cr marker; day-first, month-first and ISO dates. The columns, spending direction and date order are worked out automatically, and the app shows what it detected.
- **Subscription detection** from timing and amount, for weekly, monthly and yearly charges.
- **Extra-charge detection.** Double charges and charges after cancelling are flagged with their cost, and they do not hide the subscription they belong to.
- **Bills vs subscriptions.** Rent and utilities are recognised as recurring bills and kept out of the subscription totals.
- **Price-rise detection** and a "possibly cancelled" status.
- **Merchant cleaning and categorization** that works without any AI, with an optional OpenAI step for unfamiliar merchants.
- **Analytics:** monthly spend (subscriptions vs everything else), spending by category, top merchants, unusual monthly spikes.
- **Savings insights:** extra charges, overlapping streaming services, price rises, forgotten gym memberships, your most expensive subscription.
- **Duplicate-safe uploads.** Uploading the same file twice adds nothing, while two genuine identical purchases on one day are both kept.
- **Currency setting** (USD, INR, EUR, GBP and more) and a **Clear data** button.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, pandas |
| Database | PostgreSQL (Docker) |
| AI (optional) | OpenAI API |
| Frontend | React, Vite, Recharts |
| Tests | pytest |

## Architecture

```
React dashboard (Vite)
        |  REST / JSON
FastAPI backend
   |-- parsing.py        finds columns, spending direction and date order in any statement
   |-- upload.py         validation and duplicate-safe import
   |-- merchants.py      raw bank text -> merchant name, and a category guess
   |-- subscriptions.py  recurring-charge and extra-charge detection (rules)
   |-- categorize.py     rule-based categories, optional OpenAI step with caching
   |-- analytics.py      monthly totals, top merchants, spikes
   |-- insights.py       savings insights (rules, optional LLM wording)
   |-- admin.py          currency config and clearing data
        |
PostgreSQL (transactions, subscriptions, insights, merchant_categories)
```

## Design decisions

**Rules for facts, AI for language.** Anything that can be computed is computed with plain code: recurring charges, totals, price changes and savings estimates. The language model is optional and used only for categorizing unfamiliar merchants and rewording insight text. The app is cheaper, faster, testable, and cannot invent numbers.

**The AI cannot change the numbers.** When a model rewrites an insight, the code checks that every amount and percentage from the original is still present. If not, the original text is used.

**It works with no API key.** Merchant names are cleaned by general rules plus a list of about 100 well-known brands, and categories come from keyword rules. If an API key is missing, out of credit, or fails, the app falls back to these rules and says which source it used. Only paid AI answers are cached, so improving the rules improves old data too.

**Noise must not hide a subscription.** Real data contains double charges and post-cancellation charges. A strict "regular gaps" check drops exactly the merchants a user most needs to hear about. The detector first separates extra charges from normal billing cycles, then checks regularity on the normal ones.

## How subscription detection works

1. **Clean the merchant.** `SPOTIFY P1A2B3` and `SPOTIFY P9Z8Y7` both become `Spotify`, because tokens containing digits (reference numbers) and bank words (UPI, POS, NEFT) are dropped.
2. **Separate extra charges.** For a monthly-style merchant, a charge within 10 days of the previous one for a similar amount (within 5%) is an extra charge.
3. **Check regularity** on the remaining charges: at least 80% of the gaps must be close to 7, 30 or 365 days, with at least 4 weekly, 3 monthly or 2 yearly charges.
4. **Check the amounts:** consecutive charges must be within 5% of each other, so one price rise does not break detection.
5. **Set the status:** no charge for 1.5 billing cycles means `possibly_cancelled`.
6. **Classify:** recurring payments in Housing or Utilities are bills, and everything else is a subscription.

Starbucks (random amounts, random days) fails steps 3 and 4. Netflix passes, and a rise from 15.49 to 17.99 is reported as a price change.

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker Desktop

### 1. Clone and start the database

```bash
git clone https://github.com/spandanagowda1330-ai/spend-analyzer.git
cd spend-analyzer
docker compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```
DATABASE_URL=postgresql+psycopg://spend:spend@localhost:5432/spendly
OPENAI_API_KEY=
CURRENCY=USD
```

`OPENAI_API_KEY` is optional. Set `CURRENCY` to `INR`, `EUR`, `GBP` and so on to change the symbol.

Generate fake sample data and start the API:

```bash
python scripts/generate_sample_data.py
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, click **Upload statement**, and choose `backend/sample_transactions.csv` (or your own statement).

## Using your own statements

Export a CSV or Excel file from your bank and upload it as it is. A green message shows which columns were used and how spending was detected. If a result looks wrong, open **Options** and set whether spending is negative or positive, or whether dates are day-first or month-first, then **Clear data** and upload again.

Not supported: PDF statements, old `.xls` files (save as `.xlsx` or `.csv`), extra Excel sheets beyond the first, and mixed currencies in one file. Refunds are ignored rather than subtracted, so "Total spent" is gross spending.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/upload` | Import a statement (optional form fields `spend_sign`, `date_order`) |
| POST | `/process` | Clean merchants and detect subscriptions |
| POST | `/categorize` | Categorize merchants |
| GET | `/subscriptions` | Subscriptions and bills with annual cost, price changes and extra charges |
| GET | `/categories/summary` | Spending per category |
| GET | `/analytics/overview` | Totals and averages |
| GET | `/analytics/monthly` | Monthly spend, subscriptions vs other |
| GET | `/analytics/top-merchants` | Biggest merchants |
| GET | `/analytics/spikes` | Unusual monthly category spend |
| POST | `/insights/generate` | Build savings insights |
| GET | `/insights` | List insights |
| GET | `/config` | Currency symbol |
| DELETE | `/data` | Clear transactions, subscriptions and insights |

## Tests

```bash
cd backend
python -m pytest -q
```

39 tests cover statement parsing (many layouts, date orders, headerless files, bad input), merchant cleaning and categories, subscription and extra-charge detection, and the bill/subscription split.

The reader was tested on generated statements in the layouts above and on two sample datasets with planted problems (double charges, charges after cancelling, refunds). Real bank exports vary, so an unreadable file produces a clear error message rather than wrong numbers.

## Privacy

The repository contains only generated sample data. Do not commit real statements. `.env`, CSV and Excel files are listed in `.gitignore`. Everything runs on your own machine, and the only outgoing call is the optional OpenAI request, which sends merchant names and insight text, not raw statements.

## Limitations and next steps

- Single user, no authentication
- Categories for unfamiliar merchants rely on keyword rules unless an AI key is set, so some land in "Other"
- A subscription needs at least 3 monthly charges, so a one-month statement shows no subscriptions
- Tables are created on startup rather than through migrations (Alembic is the next step)
- Ideas: editable categories that the app remembers, refund matching, PDF statement import, a one-command Docker setup for the whole stack
