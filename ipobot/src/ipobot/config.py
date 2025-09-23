
import os, yaml, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "config.yaml"

def load_config():
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
