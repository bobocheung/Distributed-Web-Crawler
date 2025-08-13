from __future__ import annotations

import csv
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

DATA_PATH = Path(__file__).resolve().parent / "data" / "sample.csv"
MODEL_PATH = Path(__file__).resolve().parent / "model.joblib"


def load_data():
	texts = []
	labels = []
	if not DATA_PATH.exists():
		raise FileNotFoundError(f"Training data not found at {DATA_PATH}")
	with DATA_PATH.open("r", encoding="utf-8") as f:
		reader = csv.DictReader(f)
		for row in reader:
			text = (row.get("title", "") + "\n" + row.get("summary", "")).strip()
			label = row.get("label", "general")
			if text:
				texts.append(text)
				labels.append(label)
	return texts, labels


def main():
	texts, labels = load_data()

	pipeline = Pipeline(
		steps=[
			("tfidf", TfidfVectorizer(max_features=20000, ngram_range=(1, 2), stop_words="english")),
			("clf", LinearSVC()),
		]
	)

	X_train, X_test, y_train, y_test = train_test_split(texts, labels, test_size=0.2, random_state=42, stratify=labels)
	pipeline.fit(X_train, y_train)

	y_pred = pipeline.predict(X_test)
	print(classification_report(y_test, y_pred))

	MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
	joblib.dump(pipeline, str(MODEL_PATH))
	print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
	main()
