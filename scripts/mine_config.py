"""Settings for the mine-output registry (Уурхайн гарцын бүртгэл).

Every batch of ore or concentrate that leaves a mine is measured (by an
on-belt analyser, a handheld XRF or a laboratory) and every measurement is
written to a hash-chained ledger. The analysis then compares what was
measured with what the company declared.
"""

# Element column in the CSV files -> label and unit.
#   factor: converts (tonnes of material x grade) into the "contained" unit
#   contained_unit: unit used when reporting how much metal a gap represents
ELEMENTS = {
    "Cu_pct":  {"mn": "Зэс",            "en": "Copper",      "unit": "%",   "factor": 0.01, "contained_unit": "т"},
    "Mo_pct":  {"mn": "Молибден",       "en": "Molybdenum",  "unit": "%",   "factor": 0.01, "contained_unit": "т"},
    "Au_gpt":  {"mn": "Алт",            "en": "Gold",        "unit": "г/т", "factor": 0.001, "contained_unit": "кг"},
    "Ag_gpt":  {"mn": "Мөнгө",          "en": "Silver",      "unit": "г/т", "factor": 0.001, "contained_unit": "кг"},
    "Fe_pct":  {"mn": "Төмөр",          "en": "Iron",        "unit": "%",   "factor": 0.01, "contained_unit": "т"},
    "Zn_pct":  {"mn": "Цайр",           "en": "Zinc",        "unit": "%",   "factor": 0.01, "contained_unit": "т"},
    "REE_ppm": {"mn": "Газрын ховор элемент", "en": "Rare earths (total)", "unit": "ppm", "factor": 0.001, "contained_unit": "кг"},
}

# A measured grade at or above this level is worth declaring. If the
# declaration leaves the element out (or at zero) the batch is flagged.
DECLARE_THRESHOLD = {
    "Cu_pct": 0.5,
    "Mo_pct": 0.05,
    "Au_gpt": 0.5,
    "Ag_gpt": 10.0,
    "Fe_pct": 20.0,
    "Zn_pct": 1.0,
    "REE_ppm": 500.0,
}

# Who took the measurement. Only these count as independent of the company.
INDEPENDENT_SOURCES = {"independent", "customs"}

METHODS = {
    "PGNAA": "Конвейер дээрх нейтрон анализатор (PGNAA)",
    "LIBS": "Лазер анализатор (LIBS)",
    "XRF_HANDHELD": "Гар XRF төхөөрөмж",
    "LAB": "Лабораторийн шинжилгээ",
}

# Flag thresholds
GRADE_GAP_PCT = 10.0     # declared grade lower than measured by more than this
SOURCE_GAP_PCT = 10.0    # company and independent measurements differ by more than this
TONNAGE_GAP_PCT = 3.0    # declared tonnes differ from weighed tonnes by more than this
