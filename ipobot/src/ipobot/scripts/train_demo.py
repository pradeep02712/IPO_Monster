
import os, pickle, pathlib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "demo_model.pkl"
MODEL.parent.mkdir(parents=True, exist_ok=True)

def gen_data(n=500):
    rng = np.random.default_rng(42)
    sent = rng.uniform(-1, 1, size=n)
    pe_disc = rng.uniform(-0.2, 0.3, size=n)
    roe = rng.integers(0, 2, size=n)
    d2e = rng.integers(0, 2, size=n)
    growth = rng.integers(0, 2, size=n)
    fscore = 0.33*roe + 0.33*d2e + 0.34*growth
    X = np.stack([sent, pe_disc, roe, d2e, growth, fscore], axis=1)
    # True prob from latent function
    p = 0.5 + 0.25*sent + 0.15*fscore
    y = (rng.uniform(0,1,n) < p.clip(0.05,0.95)).astype(int)
    return X, y

def main():
    X, y = gen_data(1000)
    clf = RandomForestClassifier(n_estimators=200, random_state=0)
    clf.fit(X, y)
    with open(MODEL, "wb") as f:
        pickle.dump(clf, f)
    print(f"Saved model to {MODEL}")

if __name__ == "__main__":
    main()
