# src/ipobot/nlp/sentiment.py
from typing import List, Dict

# ---------- simple rule-based fallback (keeps app alive if model fails) ----------
def _rule_sentiment_score(news_items: List[Dict]) -> float:
    if not news_items:
        return 0.0
    score = 0
    for n in news_items:
        s = (n.get("sent") or n.get("tone") or "neutral").lower()
        if "pos" in s:
            score += 1
        elif "neg" in s:
            score -= 1
    return max(-1.0, min(1.0, score / max(1, len(news_items))))

# ---------- FinBERT (lazy load, cached) ----------
_model = None
_tokenizer = None
_device = "cpu"

def _load_finbert(model_name: str = "ProsusAI/finbert"):
    global _model, _tokenizer
    if _model is not None:
        return
    # Optional: silence HF tokenizers parallelism warning
    import os
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    _tokenizer = AutoTokenizer.from_pretrained(model_name)
    _model = AutoModelForSequenceClassification.from_pretrained(model_name)
    _model.eval()

def _finbert_score_headlines(headlines: List[str], max_len: int = 128) -> float:
    if not headlines:
        return 0.0
    import torch
    from torch.nn.functional import softmax

    inputs = _tokenizer(
        headlines,
        padding=True,
        truncation=True,
        max_length=max_len,
        return_tensors="pt"
    )
    with torch.no_grad():
        outputs = _model(**inputs)
        probs = softmax(outputs.logits, dim=-1)  # [N, 3] -> ['negative','neutral','positive']

    neg = probs[:, 0].mean().item()
    neu = probs[:, 1].mean().item()
    pos = probs[:, 2].mean().item()
    # expectation mapping to [-1, 1]
    return float((-1.0 * neg) + (0.0 * neu) + (+1.0 * pos))

# ---------- public API ----------
def sentiment_score(news_items: List[Dict]) -> float:
    """
    Returns sentiment in [-1, 1].
    If config.use_live_sentiment is true -> use FinBERT, else rule-based.
    Falls back to rule-based if anything goes wrong (no crash).
    """
    try:
        from ipobot.config import load_config
        cfg = load_config() or {}
        if not cfg.get("use_live_sentiment", False):
            return _rule_sentiment_score(news_items)

        s_cfg = cfg.get("sentiment", {}) or {}
        model_name = s_cfg.get("model", "ProsusAI/finbert")
        max_len = int(s_cfg.get("max_len", 128))

        _load_finbert(model_name)
        headlines = [str(n.get("title") or "").strip() for n in news_items if (n.get("title") or "").strip()]
        if not headlines:
            return 0.0
        return _finbert_score_headlines(headlines, max_len=max_len)

    except Exception:
        # Graceful fallback
        return _rule_sentiment_score(news_items)
