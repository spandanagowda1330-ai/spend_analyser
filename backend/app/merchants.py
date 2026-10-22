import re

# keyword found in the raw bank text -> clean merchant name
KNOWN_MERCHANTS = {
    "NETFLIX": "Netflix",
    "SPOTIFY": "Spotify",
    "DISNEY": "Disney+",
    "HULU": "Hulu",
    "ANYTIME FITNESS": "Anytime Fitness",
    "ADOBE": "Adobe",
    "ICLOUD": "iCloud",
    "UBER": "Uber",
    "STARBUCKS": "Starbucks",
    "WHOLEFDS": "Whole Foods",
    "AMZN": "Amazon",
    "SWIGGY": "Swiggy",
    "SHELL": "Shell",
    "CHIPOTLE": "Chipotle",
}


def clean_merchant(raw: str) -> str:
    text = raw.upper()
    for keyword, name in KNOWN_MERCHANTS.items():
        if keyword in text:
            return name

    # Fallback for unknown merchants: drop digits and symbols, keep first 2 words
    letters_only = re.sub(r"[^A-Z ]", " ", text)
    words = [w for w in letters_only.split() if len(w) > 1]
    if words:
        return " ".join(words[:2]).title()
    return raw.strip().title()[:100]