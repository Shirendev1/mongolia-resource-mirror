"""Shared settings for the Mongolia Resource Mirror.

Add a commodity or a trading partner here and both the fetcher and the
analysis pick it up.
"""

MONGOLIA = 496

# UN Comtrade country codes -> names (Mongolian, English)
COUNTRIES = {
    496: {"mn": "Монгол", "en": "Mongolia"},
    156: {"mn": "Хятад", "en": "China"},
    757: {"mn": "Швейцарь", "en": "Switzerland"},
    410: {"mn": "Өмнөд Солонгос", "en": "Rep. of Korea"},
    380: {"mn": "Итали", "en": "Italy"},
}

# HS code -> names and the unit used on the dashboard ("t" tonnes, "kg")
COMMODITIES = {
    "2701": {"mn": "Нүүрс", "en": "Coal", "unit": "t"},
    "2603": {"mn": "Зэсийн баяжмал", "en": "Copper ores & concentrates", "unit": "t"},
    "7108": {"mn": "Алт", "en": "Gold", "unit": "kg"},
    "51": {"mn": "Ноос, ноолуур", "en": "Wool & fine animal hair (HS ch. 51)", "unit": "t"},
    "2529": {"mn": "Жонш", "en": "Fluorspar", "unit": "t"},
}

# Each pair compares what Mongolia says it sent to `partner` with what the
# partner says it received from Mongolia. `monthly` adds month-by-month data
# (slower to download, so only for the biggest flows).
PAIRS = [
    {"partner": 156, "hs": ["2701", "2603", "51", "2529"], "monthly": True},
    {"partner": 757, "hs": ["7108"], "monthly": False},
    {"partner": 410, "hs": ["7108"], "monthly": False},
    {"partner": 380, "hs": ["51"], "monthly": False},
]

FIRST_YEAR = 2019

# Flag thresholds
VALUE_GAP_PCT = 5.0      # |gap| above this % of the exporter's value is flagged
WEIGHT_GAP_PCT = 10.0    # weight gaps are noisier (wet vs dry tonnes), so looser
PRICE_GAP_PCT = 10.0     # price per tonne also differs by moisture (wet vs dry), so looser

# Notes shown next to a flagged commodity/partner, explaining common innocent causes
NOTES = {
    "7108": "Алтыг зарим улс гарал үүслийн улсаар бүртгэдэг (Швейцарь). Монголбанкны нөөцийн (мөнгөний) алтыг олон улс импортын статистикт оруулдаггүй. Цэвэршүүлээгүй алт (doré) жингийн зөрүү үүсгэнэ.",
    "2603": "Баяжмалыг нойтон эсвэл хуурай тонноор бүртгэдэг тул жин 5–10% зөрөх нь хэвийн.",
    "2701": "Хилийн боомтод саатсан ачаа дараа сард/онд бүртгэгдэж болно.",
    "51": "Ноолуурыг нэг улс “самнасан”, нөгөө нь “түүхий” гэж өөр кодоор бүртгэх нь элбэг тул бүлэг (51) түвшинд харьцуулна.",
    "2529": "Жоншийг хүчлийн болон металлургийн гэсэн өөр зэрэглэлээр бүртгэдэг. Тонн таарч үнэ зөрвөл үнийн мэдүүлгийг шалгах хэрэгтэй.",
}
