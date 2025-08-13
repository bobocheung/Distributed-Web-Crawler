from __future__ import annotations

import re
from typing import Dict, List

# Compiled regex patterns for precise matching.
# English patterns use word boundaries; Chinese/Japanese/Korean use direct substrings.

def _r(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)

REGEXES: Dict[str, List[re.Pattern]] = {
    "technology": [
        _r(r"\bai\b|artificial intelligence|machine learning|deep learning"),
        _r(r"\bsemiconductor(s)?\b|\bchip(s)?\b|半導體|晶片"),
        _r(r"\bsoftware\b|\bapp(s)?\b|軟體"),
        _r(r"cyber ?security|資訊安全"),
        _r(r"cloud|雲端"),
        _r(r"\b5g\b|\b6g\b"),
        _r(r"blockchain|區塊鏈"),
        _r(r"electric vehicle|ev |電動車"),
        _r(r"tech(nology)?|科技"),
    ],
    "economy": [
        _r(r"經濟|景氣|通膨|物價|通貨膨脹"),
        _r(r"\bgdp\b|\bcpi\b|\bppi\b|economic growth|inflation"),
        _r(r"unemployment|retail sales|消費|就業"),
    ],
    "finance": [
        _r(r"finance|financial|bank(s)?|banking|利率|加息|減息|息口"),
        _r(r"stock(s)?|equit(y|ies)|market(s)?|證券|股市|股票|指數|基金|債券"),
        _r(r"\bipo\b|\bspac\b|並購|收購"),
    ],
    "politics": [
        _r(r"政策|法案|立法|監管|政府|內閣|部長|特首|總統|首相"),
        _r(r"election|parliament|congress|cabinet|government|regulation"),
    ],
    "health": [
        _r(r"健康|醫療|醫院|疫苗|新冠|疫情|癌"),
        _r(r"covid|vaccine|healthcare|hospital"),
    ],
    "sports": [
        _r(r"sports?|football|soccer|basketball|tennis|olympic|world cup|比賽|球隊|球員|體育"),
    ],
    "entertainment": [
        _r(r"娛樂|電影|影視|音樂|明星|演唱會|藝人"),
        _r(r"movie|film|music|celebrity|hollywood"),
    ],
    "environment": [
        _r(r"環境|氣候|減碳|碳排|污染|保育"),
        _r(r"climate|emission(s)?|carbon|environment"),
    ],
}


# Optional source biases to add default categories for certain outlets
SOURCE_BIASES: Dict[str, List[str]] = {
    # normalized source names (lowercase)
    "the economist finance": ["economy", "finance"],
    "bloomberg": ["finance", "economy"],
    "wall street journal": ["finance", "economy"],
    "financial times": ["finance", "economy"],
    "reuters apac": ["world"],
    "scmp hong kong": ["local"],
}


def classify_categories(text: str) -> List[str]:
    if not text:
        return []
    text_l = text.lower()
    matched: List[str] = []
    for cat, patterns in REGEXES.items():
        for p in patterns:
            if p.search(text_l):
                matched.append(cat)
                break
    # keep deterministic order
    order = [
        "technology","finance","economy","politics","health",
        "sports","entertainment","environment",
    ]
    return [c for c in order if c in matched]

