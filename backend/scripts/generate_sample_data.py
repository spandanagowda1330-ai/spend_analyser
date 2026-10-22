import csv
import random
from datetime import date, timedelta

random.seed(42)
START = date(2025, 10, 1)
MONTHS = 12

# (description, amount, day of month)
SUBSCRIPTIONS = [
    ("NETFLIX.COM 866-579-7172", 15.49, 5),
    ("SPOTIFY P2B3C4D5E6", 11.99, 12),
    ("DISNEY PLUS 888-905-7888", 13.99, 18),
    ("HULU 877-8244858", 17.99, 20),
    ("ANYTIME FITNESS #4482", 39.00, 1),
    ("ADOBE *CREATIVE CLOUD", 59.99, 25),
    ("ICLOUD.COM/BILL", 2.99, 9),
]

# (description, min amount, max amount)
ONE_OFFS = [
    ("UBER *TRIP HELP.UBER.COM", 8, 30),
    ("STARBUCKS STORE 11823", 4, 9),
    ("WHOLEFDS MKT #10234", 25, 110),
    ("AMZN MKTP US*2K4LM9", 10, 120),
    ("SWIGGY*ORDER", 8, 35),
    ("SHELL OIL 5744", 30, 60),
    ("CHIPOTLE 2291", 9, 16),
]

rows = []

for m in range(MONTHS):
    month_start = date(START.year + (START.month - 1 + m) // 12,
                       (START.month - 1 + m) % 12 + 1, 1)

    for desc, amount, day in SUBSCRIPTIONS:
        price = amount
        if "NETFLIX" in desc and m >= 6:
            price = 17.99  # price hike
        charge_day = min(day + random.choice([0, 0, 1]), 28)
        rows.append((month_start.replace(day=charge_day), desc, price))

    for _ in range(random.randint(25, 40)):
        desc, low, high = random.choice(ONE_OFFS)
        d = month_start + timedelta(days=random.randint(0, 27))
        rows.append((d, desc, round(random.uniform(low, high), 2)))

rows.sort(key=lambda r: r[0])

with open("sample_transactions.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["date", "description", "amount"])
    for d, desc, amt in rows:
        writer.writerow([d.isoformat(), desc, amt])

print(f"Wrote {len(rows)} transactions")