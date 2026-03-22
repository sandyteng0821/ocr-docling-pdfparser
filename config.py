"""
config.py — 書本專屬修正設定
換書時只需要改這裡，run_parser.py 不用動。
留空 dict 代表不做任何修正。
"""

# key: 藥名去除非字母數字後的小寫版本
#      例如 "Hypromellose Phthalate" → "hypromellosephthalate"
"""
NAME_CORRECTIONS = {
    "seetablei":            "Aliphatic Polyesters",
    "butane":               "Hydrocarbons HC",
    "kaliicitras":          "Potassium Citrate",
    "hypromellosiphthalas": "Hypromellose Phthalate",
    "saccharinsodium":      "Saccharin Sodium",
    "agar":                 "Agar",
    "alitame":              "Alitame",
}
"""
NAME_CORRECTIONS = {}

# key: 0-based page index（對應原始全書頁碼）
"""
INDEX_CORRECTIONS = {
    36: "Agar",
    50: "Alitame",
}
"""
INDEX_CORRECTIONS = {}