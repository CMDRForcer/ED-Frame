.pragma library

// Display-only localization. Never substitute these labels into model/filter keys.
var keys = {
    "OPEN": "presentation.label_0",
    "CONFIRMED": "presentation.label_1",
    "UNKNOWN": "presentation.label_2",
    "RANK UNCONFIRMED": "presentation.label_3",
    "RANK REQUIRED": "presentation.label_4",
    "RANK CONFIRMED": "presentation.label_5",
    "PERMIT MISSING": "presentation.label_6",
    "PERMIT NOT CONFIRMED": "presentation.label_7",
    "STANDARD PURCHASE": "presentation.label_8",
    "ACQUISITION UNKNOWN": "presentation.label_9",
    "POWERPLAY · UNLOCK UNKNOWN": "presentation.label_10",
    "TECH BROKER · UNLOCK UNKNOWN": "presentation.label_11",
    "ENGINEER OUTFITTING": "presentation.label_12",
    "LEGACY · NOT NORMAL STOCK": "presentation.label_13",
    "SPECIAL · ACQUISITION UNKNOWN": "presentation.label_14",
    "VARIANT REQUIREMENTS DIFFER": "presentation.label_15",
    "REFERENCE": "presentation.label_16",
    "OBSERVED": "presentation.label_17",
    "ESTIMATED": "presentation.label_18",
    "PURCHASE CONFIRMED": "presentation.label_19",
    "DISCOUNTED": "presentation.label_20",
    "STATION RULE": "presentation.label_21",
    "HARDPOINTS": "presentation.label_22",
    "UTILITY": "presentation.label_23",
    "UTILITY MOUNTS": "presentation.label_24",
    "CORE": "presentation.label_25",
    "CORE INTERNAL": "presentation.label_26",
    "OPTIONAL": "presentation.label_27",
    "OPTIONAL INTERNAL": "presentation.label_28",
    "MINING": "presentation.label_29",
    "TECH BROKER": "presentation.label_30",
    "POWERPLAY": "presentation.label_31",
    "SELECT A SHOP CATEGORY": "presentation.label_32",
    "AGE UNKNOWN": "presentation.label_33",
}

function label(window, value) {
    var raw = value === undefined || value === null ? "" : String(value)
    return window && keys[raw] ? window.t(keys[raw], raw) : raw
}
