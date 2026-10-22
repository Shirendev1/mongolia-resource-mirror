"""Shared settings for the Mongolia Resource Mirror.

Add a commodity here and both the fetcher and the analysis pick it up.
"""

MONGOLIA = 496
CHINA = 156

# HS code -> names (Mongolian, English)
COMMODITIES = {
    "2701": {"mn": "Нүүрс", "en": "Coal"},
    "2603": {"mn": "Зэсийн баяжмал", "en": "Copper ores & concentrates"},
}

# Each "mirror pair" compares what the exporter says it sent with what the
# importer says it received.
PAIRS = [
    # (exporter, importer)
    (MONGOLIA, CHINA),
]

FIRST_YEAR = 2019

# Flag thresholds
VALUE_GAP_PCT = 5.0      # |gap| above this % of the exporter's value is flagged
WEIGHT_GAP_PCT = 10.0    # weight gaps are noisier (wet vs dry tonnes), so looser
PRICE_GAP_PCT = 10.0     # price per tonne also differs by moisture (wet vs dry), so looser
