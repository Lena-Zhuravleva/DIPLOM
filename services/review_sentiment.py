import re
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification


MODEL_NAME = "blanchefort/rubert-base-cased-sentiment"

_tokenizer = None
_model = None


LABELS = {
    0: "neutral",
    1: "positive",
    2: "negative"
}


def load_sentiment_model():
    global _tokenizer, _model

    if _tokenizer is None or _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        _model.eval()

    return _tokenizer, _model


def split_reviews(text):
    if not text:
        return []

    parts = re.split(r"\n+|[•]+", text)
    reviews = []

    for p in parts:
        clean = p.strip()
        if len(clean) >= 10:
            reviews.append(clean)

    return reviews


def predict_review_sentiment(review_text):
    tokenizer, model = load_sentiment_model()

    inputs = tokenizer(
        review_text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=256
    )

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=1)[0]

    label_id = int(torch.argmax(probs).item())

    return {
        "label": LABELS[label_id],
        "neutral": float(probs[0]),
        "positive": float(probs[1]),
        "negative": float(probs[2])
    }


def analyze_reviews_text(text):
    reviews = split_reviews(text)

    if not reviews:
        return {
            "reviews_count": 0,
            "positive_share": 0,
            "neutral_share": 1,
            "negative_share": 0,
            "sentiment_score": 0.5,
            "rating": 3.0,
            "risk_score": 0.5,
            "quality_comment": "Отзывы не указаны, использована нейтральная оценка."
        }

    positive = 0
    neutral = 0
    negative = 0

    for review in reviews:
        result = predict_review_sentiment(review)

        if result["label"] == "positive":
            positive += 1
        elif result["label"] == "negative":
            negative += 1
        else:
            neutral += 1

    total = len(reviews)

    positive_share = positive / total
    neutral_share = neutral / total
    negative_share = negative / total

    sentiment_score = (
        positive_share * 1.0 +
        neutral_share * 0.5 +
        negative_share * 0.0
    )

    rating = 1 + sentiment_score * 4

    risk_score = (
        negative_share * 0.8 +
        neutral_share * 0.35 +
        positive_share * 0.1
    )

    risk_score = max(0, min(1, risk_score))

    if sentiment_score >= 0.75:
        quality_comment = "Отзывы преимущественно положительные, внешний риск низкий."
    elif sentiment_score >= 0.45:
        quality_comment = "Отзывы смешанные, внешний риск средний."
    else:
        quality_comment = "В отзывах много негативных признаков, внешний риск высокий."

    return {
        "reviews_count": total,
        "positive_share": round(positive_share, 3),
        "neutral_share": round(neutral_share, 3),
        "negative_share": round(negative_share, 3),
        "sentiment_score": round(sentiment_score, 3),
        "rating": round(rating, 2),
        "risk_score": round(risk_score, 3),
        "quality_comment": quality_comment
    }