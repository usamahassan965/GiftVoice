"""Shared gift vocabularies so the LLM, seed script and search all speak the same terms."""

OCCASIONS = [
    "birthday", "anniversary", "wedding", "housewarming", "thank_you", "graduation",
    "new_baby", "retirement", "valentines", "mothers_day", "fathers_day", "eid",
    "christmas", "diwali", "get_well", "congratulations", "corporate", "just_because",
]

RECIPIENTS = [
    "mom", "dad", "wife", "husband", "partner", "her", "him", "friend", "sibling",
    "coworker", "boss", "teacher", "host", "teen", "kid", "baby", "grandparent", "anyone",
]

# Words shoppers say -> canonical recipient
RECIPIENT_SYNONYMS = {
    "mother": "mom", "mum": "mom", "ammi": "mom", "mama": "mom",
    "father": "dad", "abbu": "dad", "papa": "dad",
    "girlfriend": "partner", "boyfriend": "partner", "fiance": "partner", "fiancee": "partner",
    "sister": "sibling", "brother": "sibling",
    "colleague": "coworker", "manager": "boss",
    "son": "kid", "daughter": "kid", "nephew": "kid", "niece": "kid", "child": "kid",
    "grandma": "grandparent", "grandpa": "grandparent", "nani": "grandparent", "dadi": "grandparent",
    "woman": "her", "man": "him",
}

# Recipients that should also match gender-general items
RECIPIENT_EXPANSION = {
    "mom": ["mom", "her"], "wife": ["wife", "partner", "her"], "dad": ["dad", "him"],
    "husband": ["husband", "partner", "him"], "partner": ["partner", "wife", "husband"],
    "her": ["her"], "him": ["him"],
}

WRAP_OPTIONS = {
    "classic": {"label": "Classic kraft paper & ribbon", "fee": 4.0},
    "premium": {"label": "Premium gift box with satin bow", "fee": 9.0},
    "eco": {"label": "Reusable furoshiki cloth wrap", "fee": 6.0},
}

# DummyJSON categories we keep, with gift metadata inferred per category.
DUMMYJSON_CATEGORY_MAP = {
    "fragrances": dict(category="fragrances", interests=["perfume", "beauty", "fashion"],
                       occasions=["birthday", "anniversary", "valentines", "eid", "mothers_day"],
                       recipients=["her", "him", "partner", "wife", "husband"]),
    "womens-jewellery": dict(category="jewellery", interests=["jewellery", "fashion"],
                             occasions=["birthday", "anniversary", "valentines", "mothers_day", "wedding"],
                             recipients=["her", "wife", "mom", "sibling"]),
    "womens-watches": dict(category="watches", interests=["fashion", "watches"],
                           occasions=["birthday", "anniversary", "graduation", "mothers_day"],
                           recipients=["her", "wife", "mom"]),
    "mens-watches": dict(category="watches", interests=["fashion", "watches"],
                         occasions=["birthday", "anniversary", "graduation", "fathers_day", "retirement"],
                         recipients=["him", "husband", "dad", "boss"]),
    "womens-bags": dict(category="bags", interests=["fashion"],
                        occasions=["birthday", "anniversary", "mothers_day", "eid"],
                        recipients=["her", "wife", "mom", "sibling"]),
    "sunglasses": dict(category="accessories", interests=["fashion", "travel", "outdoors"],
                       occasions=["birthday", "graduation", "just_because"],
                       recipients=["him", "her", "teen", "friend"]),
    "skin-care": dict(category="beauty", interests=["skincare", "self care", "beauty"],
                      occasions=["birthday", "mothers_day", "just_because", "valentines"],
                      recipients=["her", "mom", "wife", "friend"]),
    "beauty": dict(category="beauty", interests=["makeup", "beauty", "self care"],
                   occasions=["birthday", "just_because", "valentines"],
                   recipients=["her", "teen", "friend", "sibling"]),
    "home-decoration": dict(category="home-decor", interests=["home decor"],
                            occasions=["housewarming", "wedding", "birthday", "eid"],
                            recipients=["host", "partner", "mom", "anyone"]),
    "kitchen-accessories": dict(category="kitchen", interests=["cooking", "baking"],
                                occasions=["housewarming", "wedding", "mothers_day"],
                                recipients=["host", "mom", "partner", "anyone"]),
    "sports-accessories": dict(category="sports", interests=["sports", "fitness", "outdoors"],
                               occasions=["birthday", "graduation", "just_because"],
                               recipients=["him", "teen", "kid", "friend"]),
    "mobile-accessories": dict(category="tech", interests=["tech", "gadgets"],
                               occasions=["birthday", "graduation", "corporate"],
                               recipients=["teen", "him", "coworker", "anyone"]),
    "womens-shoes": dict(category="fashion", interests=["fashion"],
                         occasions=["birthday", "eid", "just_because"],
                         recipients=["her", "wife", "sibling"]),
    "mens-shoes": dict(category="fashion", interests=["fashion", "sports"],
                       occasions=["birthday", "eid", "just_because"],
                       recipients=["him", "husband", "teen"]),
}


def normalize_recipient(word: str | None) -> str | None:
    if not word:
        return None
    w = word.strip().lower()
    if w in RECIPIENTS:
        return w
    return RECIPIENT_SYNONYMS.get(w)
