"""Clean raw bank text into a merchant name, and guess a category without any AI.

clean_merchant("UPI-SWIGGY-swiggy@icici-1234")  -> "Swiggy"
clean_merchant("JOES PIZZA #4421")              -> "Joes Pizza"
guess_category("Joes Pizza")                    -> "Dining"
"""
import re

# (keyword, display name, category). The first match wins, so specific entries go first.
KNOWN = [
    # video and music streaming
    ("NETFLIX", "Netflix", "Entertainment"),
    ("SPOTIFY", "Spotify", "Entertainment"),
    ("DISNEY", "Disney+", "Entertainment"),
    ("HOTSTAR", "Hotstar", "Entertainment"),
    ("HULU", "Hulu", "Entertainment"),
    ("AMAZON PRIME", "Amazon Prime", "Entertainment"),
    ("PRIME VIDEO", "Prime Video", "Entertainment"),
    ("PRIMEVIDEO", "Prime Video", "Entertainment"),
    ("YOUTUBE", "YouTube", "Entertainment"),
    ("APPLE TV", "Apple Tv", "Entertainment"),
    ("PARAMOUNT", "Paramount+", "Entertainment"),
    ("PEACOCK", "Peacock", "Entertainment"),
    ("HBO", "Hbo Max", "Entertainment"),
    ("SONYLIV", "SonyLIV", "Entertainment"),
    ("ZEE5", "Zee5", "Entertainment"),
    ("BOOKMYSHOW", "BookMyShow", "Entertainment"),
    ("AUDIBLE", "Audible", "Entertainment"),
    ("STEAM", "Steam", "Entertainment"),
    # fitness and health
    ("ANYTIME FITNESS", "Anytime Fitness", "Health & Fitness"),
    ("PLANET FITNESS", "Planet Fitness", "Health & Fitness"),
    ("CULT FIT", "Cult.fit", "Health & Fitness"),
    ("CULTFIT", "Cult.fit", "Health & Fitness"),
    ("APOLLO", "Apollo", "Health & Fitness"),
    ("PHARMEASY", "PharmEasy", "Health & Fitness"),
    ("NETMEDS", "Netmeds", "Health & Fitness"),
    ("1MG", "1mg", "Health & Fitness"),
    ("CVS", "CVS", "Health & Fitness"),
    ("WALGREENS", "Walgreens", "Health & Fitness"),
    # software and cloud
    ("ADOBE", "Adobe", "Software"),
    ("ICLOUD", "iCloud", "Software"),
    ("MICROSOFT", "Microsoft", "Software"),
    ("GOOGLE", "Google", "Software"),
    ("DROPBOX", "Dropbox", "Software"),
    ("GITHUB", "GitHub", "Software"),
    ("OPENAI", "OpenAI", "Software"),
    ("CHATGPT", "ChatGPT", "Software"),
    ("ANTHROPIC", "Anthropic", "Software"),
    ("NOTION", "Notion", "Software"),
    ("CANVA", "Canva", "Software"),
    ("ZOOM", "Zoom", "Software"),
    ("SLACK", "Slack", "Software"),
    ("FIGMA", "Figma", "Software"),
    ("LINKEDIN", "LinkedIn", "Software"),
    # education
    ("COURSERA", "Coursera", "Education"),
    ("UDEMY", "Udemy", "Education"),
    ("UDACITY", "Udacity", "Education"),
    ("SKILLSHARE", "Skillshare", "Education"),
    ("BYJU", "Byjus", "Education"),
    ("UNACADEMY", "Unacademy", "Education"),
    # transport and fuel
    ("UBER", "Uber", "Transport"),
    ("OLA", "Ola", "Transport"),
    ("RAPIDO", "Rapido", "Transport"),
    ("LYFT", "Lyft", "Transport"),
    ("SHELL", "Shell", "Transport"),
    ("BPCL", "BPCL", "Transport"),
    ("HPCL", "HPCL", "Transport"),
    ("INDIAN OIL", "Indian Oil", "Transport"),
    ("EXXON", "Exxon", "Transport"),
    ("CHEVRON", "Chevron", "Transport"),
    ("FASTAG", "Fastag", "Transport"),
    # travel
    ("IRCTC", "IRCTC", "Travel"),
    ("MAKEMYTRIP", "MakeMyTrip", "Travel"),
    ("AIRBNB", "Airbnb", "Travel"),
    ("INDIGO", "IndiGo", "Travel"),
    ("AIR INDIA", "Air India", "Travel"),
    ("EMIRATES", "Emirates", "Travel"),
    ("EXPEDIA", "Expedia", "Travel"),
    ("BOOKING COM", "Booking.com", "Travel"),
    # restaurants, cafes, food delivery
    ("STARBUCKS", "Starbucks", "Dining"),
    ("CHIPOTLE", "Chipotle", "Dining"),
    ("MCDONALD", "McDonalds", "Dining"),
    ("DOMINO", "Dominos", "Dining"),
    ("PIZZA HUT", "Pizza Hut", "Dining"),
    ("BURGER KING", "Burger King", "Dining"),
    ("KFC", "KFC", "Dining"),
    ("SUBWAY", "Subway", "Dining"),
    ("ZOMATO", "Zomato", "Dining"),
    ("SWIGGY", "Swiggy", "Dining"),
    ("DOORDASH", "DoorDash", "Dining"),
    ("GRUBHUB", "Grubhub", "Dining"),
    # groceries
    ("WHOLEFDS", "Whole Foods", "Groceries"),
    ("WHOLE FOODS", "Whole Foods", "Groceries"),
    ("WALMART", "Walmart", "Groceries"),
    ("COSTCO", "Costco", "Groceries"),
    ("KROGER", "Kroger", "Groceries"),
    ("TESCO", "Tesco", "Groceries"),
    ("BIGBASKET", "BigBasket", "Groceries"),
    ("BLINKIT", "Blinkit", "Groceries"),
    ("ZEPTO", "Zepto", "Groceries"),
    ("DMART", "DMart", "Groceries"),
    ("INSTACART", "Instacart", "Groceries"),
    # shopping
    ("AMZN", "Amazon", "Shopping"),
    ("AMAZON", "Amazon", "Shopping"),
    ("FLIPKART", "Flipkart", "Shopping"),
    ("MYNTRA", "Myntra", "Shopping"),
    ("AJIO", "Ajio", "Shopping"),
    ("MEESHO", "Meesho", "Shopping"),
    ("EBAY", "eBay", "Shopping"),
    ("ETSY", "Etsy", "Shopping"),
    ("IKEA", "IKEA", "Shopping"),
    ("TARGET", "Target", "Shopping"),
    # phone, internet, power
    ("JIO", "Jio", "Utilities"),
    ("AIRTEL", "Airtel", "Utilities"),
    ("VODAFONE", "Vodafone", "Utilities"),
    ("BSNL", "BSNL", "Utilities"),
    ("TATA POWER", "Tata Power", "Utilities"),
    ("BESCOM", "Bescom", "Utilities"),
    ("COMCAST", "Comcast", "Utilities"),
    ("VERIZON", "Verizon", "Utilities"),
]

# Rules for merchants we have never seen. The first category with a matching word wins.
CATEGORY_RULES = [
    ("Health & Fitness", ["PHARMACY", "PHARMA", "MEDICAL", "MEDICINES", "HOSPITAL", "CLINIC", "DENTAL",
                          "DIAGNOSTIC", "DIAGNOSTICS", "LAB", "GYM", "FITNESS", "YOGA", "HEALTH",
                          "OPTICAL", "DOCTOR", "WELLNESS", "SALON", "SPA"]),
    ("Housing", ["RENT", "LEASE", "MORTGAGE", "HOUSING", "LANDLORD", "MAINTENANCE", "SOCIETY"]),
    ("Cash", ["CASH", "WITHDRAWAL"]),
    ("Groceries", ["GROCERY", "GROCERIES", "SUPERMARKET", "HYPERMARKET", "MART", "FRESH", "KIRANA",
                   "PROVISION", "PROVISIONS", "BAZAAR", "MARKET", "SUPERSTORE", "DAIRY", "MILK",
                   "VEGETABLE", "VEGETABLES", "FRUIT", "FRUITS", "SUPERMARKT"]),
    ("Dining", ["RESTAURANT", "CAFE", "COFFEE", "TEA", "PIZZA", "BURGER", "KITCHEN", "BAKERY",
                "DINER", "BISTRO", "GRILL", "BIRYANI", "DHABA", "FOOD", "FOODS", "EATERY", "SWEETS",
                "PUB", "BAR", "BREWERY", "SNACKS", "JUICE", "DESSERT", "DOSA", "TIFFIN", "CATERING"]),
    ("Transport", ["FUEL", "PETROL", "DIESEL", "TAXI", "CAB", "CABS", "METRO", "TOLL", "PARKING",
                   "TRANSPORT", "BUS", "GARAGE", "GAS STATION", "AUTO"]),
    ("Travel", ["HOTEL", "HOTELS", "RESORT", "AIRLINES", "AIRWAYS", "FLIGHT", "TRAVEL", "TRAVELS",
                "RAILWAY", "RAILWAYS", "HOLIDAY", "HOLIDAYS", "TOURS", "HOSTEL", "LODGE"]),
    ("Entertainment", ["CINEMA", "MOVIE", "MOVIES", "THEATRE", "THEATER", "GAMES", "GAMING", "MUSIC",
                       "STREAMING", "CONCERT", "PVR", "INOX", "ENTERTAINMENT"]),
    ("Utilities", ["ELECTRICITY", "POWER", "WATER", "BROADBAND", "INTERNET", "RECHARGE", "TELECOM",
                   "DTH", "INSURANCE", "UTILITY", "UTILITIES", "LOAN", "EMI",
                   "MOBILE"]),
    ("Education", ["COURSE", "COURSES", "ACADEMY", "UNIVERSITY", "SCHOOL", "COLLEGE", "TUITION",
                   "LEARNING", "CLASSES", "INSTITUTE", "EDUCATION"]),
    ("Software", ["SOFTWARE", "CLOUD", "HOSTING", "DOMAIN", "SAAS", "TECHNOLOGIES", "TECHNOLOGY"]),
    ("Shopping", ["STORE", "STORES", "SHOP", "SHOPS", "MALL", "RETAIL", "FASHION", "APPAREL", "CLOTHING",
                  "TEXTILES", "ELECTRONICS", "JEWELLERS", "JEWELERS", "BOOKS", "STATIONERY", "GIFT",
                  "GIFTS", "MARKETPLACE", "ONLINE"]),
]

NOISE = {
    "UPI", "POS", "ECOM", "ECS", "ACH", "NEFT", "IMPS", "RTGS", "NACH", "ATM", "DEBIT", "CREDIT",
    "CARD", "PURCHASE", "PAYMENT", "PAYMENTS", "PYMT", "PMT", "TXN", "TRANSFER", "TRF", "TO", "FROM",
    "BY", "INB", "MOB", "MB", "VPS", "SQ", "TST", "SP", "PAYPAL", "STRIPE", "WWW", "HTTP", "HTTPS",
    "COM", "NET", "ORG", "CO", "IN", "US", "UK", "PVT", "LTD", "LIMITED", "INC", "LLC", "LLP", "CORP",
    "THE", "AND", "OF", "FOR", "REF", "NO", "ID", "DR", "CR", "BILLPAY", "MKTP",
}

BY_NAME = {name.lower(): category for _, name, category in KNOWN}


def _normalize(text: str) -> str:
    return " " + " ".join(re.findall(r"[A-Z0-9]+", str(text).upper())) + " "


def _matches(normalized: str, keyword: str) -> bool:
    keyword = " ".join(re.findall(r"[A-Z0-9]+", keyword.upper()))
    if len(keyword) >= 6:
        return keyword in normalized      # long names: also match inside longer words
    return f" {keyword} " in normalized   # short names: whole words only (so OLA != COLA)


def _known(text: str):
    normalized = _normalize(text)
    for keyword, name, category in KNOWN:
        if _matches(normalized, keyword):
            return name, category
    return None


def clean_merchant(raw: str) -> str:
    text = str(raw)
    hit = _known(text)
    if hit:
        return hit[0]

    upper = text.upper()
    # keep the name part of UPI-style handles: joes@okaxis -> joes
    upper = re.sub(r"([A-Z0-9._-]+)@[A-Z0-9.-]+", r" \1 ", upper)
    words = []
    for token in re.findall(r"[A-Z0-9]+", upper):
        if any(ch.isdigit() for ch in token):      # reference numbers, ids, store numbers
            continue
        if len(token) < 2 or token in NOISE:
            continue
        if words and words[-1] == token:
            continue
        words.append(token)

    if not words:
        fallback = re.sub(r"\s+", " ", text).strip().title()[:100]
        return fallback or "Unknown"
    return " ".join(words[:2]).title()[:100]


def guess_category(merchant: str, context: str = "") -> str:
    """Category from the merchant name; falls back to the original bank text (context)."""
    known = BY_NAME.get(str(merchant).lower())
    if known:
        return known
    hit = _known(merchant)
    if hit:
        return hit[1]
    for text in (merchant, context):
        if not text:
            continue
        normalized = _normalize(text)
        for category, words in CATEGORY_RULES:
            if any(_matches(normalized, w) for w in words):
                return category
    return "Other"
