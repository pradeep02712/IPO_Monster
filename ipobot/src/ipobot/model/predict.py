
import os, pickle, pathlib
from typing import Tuple

def load_or_train_model(path: str):
    p = pathlib.Path(path)
    if p.exists():
        with open(p, "rb") as f:
            return pickle.load(f)
    # Fallback: return a trivial stub that mimics predict_proba
    class Stub:
        def predict_proba(self, X):
            # X: [[sentiment, pe_discount, roe_flag, d2e_flag, growth_flag, fscore]]
            # naive conversion to probability
            import numpy as np
            arr = np.array(X)
            prob = 0.5 + 0.25*arr[:,0] + 0.15*arr[:,5]
            prob = prob.clip(0.01, 0.99)
            return np.stack([1-prob, prob], axis=1)
    return Stub()

def predict_gain(model, sent: float, fdetail: dict) -> Tuple[float, float]:
    import numpy as np
    x = [[
        float(sent or 0.0),
        float(fdetail.get("pe_discount_vs_peer") or 0.0),
        1.0 if fdetail.get("roe_flag") else 0.0,
        1.0 if fdetail.get("d2e_flag") else 0.0,
        1.0 if fdetail.get("growth_flag") else 0.0,
        # simple composite
        float(0.33*(fdetail.get("roe_flag") and 1 or 0) + 0.33*(fdetail.get("d2e_flag") and 1 or 0) + 0.34*(fdetail.get("growth_flag") and 1 or 0))
    ]]
    prob = float(model.predict_proba(x)[0,1])
    # expected gain heuristic: map prob [0,1] -> [-10%, +30%]
    gain = -10 + 40*prob
    return prob, round(gain, 1)
