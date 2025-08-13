from __future__ import annotations

from pathlib import Path
from typing import Optional

import joblib

_MODEL = None
_MODEL_PATH = Path(__file__).resolve().parent / "model.joblib"


def _load_model():
	global _MODEL
	if _MODEL is None and _MODEL_PATH.exists():
		_MODEL = joblib.load(str(_MODEL_PATH))
	return _MODEL


def classify(text: str) -> Optional[str]:
	model = _load_model()
	if model is None:
		return None
	try:
		return str(model.predict([text])[0])
	except Exception:
		return None
