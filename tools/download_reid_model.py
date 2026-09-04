"""Download the named OSNet checkpoint through BoxMOT's official model resolver."""
from pathlib import Path
import hashlib, shutil

MODEL_NAME = "osnet_x0_25_msmt17.pt"
TARGET = Path("models/reid") / MODEL_NAME


def main():
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    from boxmot import ReIDModel
    # BoxMOT resolves this name to its catalog entry and verifies the downloaded file.
    ReIDModel(MODEL_NAME, device="cuda:0", half=False)
    import site
    candidates = [Path(p) / "models" / MODEL_NAME for p in site.getsitepackages()]
    source = next((p for p in candidates if p.exists()), None)
    if source is None: raise FileNotFoundError("BoxMOT downloaded checkpoint was not found")
    if source.resolve() != TARGET.resolve(): shutil.copy2(source, TARGET)
    print("model_path:", TARGET.resolve())
    print("file_size:", TARGET.stat().st_size)
    print("sha256:", hashlib.sha256(TARGET.read_bytes()).hexdigest())
    print("source: BoxMOT official ReID model catalog (osnet_x0_25_msmt17.pt)")


if __name__ == "__main__": main()
