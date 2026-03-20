from pathlib import Path


PATCHES = {
    ".venv/Lib/site-packages/mediapipe/python/solutions/hands.py": (
        "class Hands(model_complexity=1, SolutionBase):",
        "class Hands(SolutionBase):",
    ),
    ".venv/Lib/site-packages/mediapipe/python/solutions/holistic.py": (
        "class Holistic(model_complexity=2, SolutionBase):",
        "class Holistic(SolutionBase):",
    ),
    ".venv/Lib/site-packages/mediapipe/python/solutions/pose.py": (
        "class Pose(model_complexity=2, SolutionBase):",
        "class Pose(SolutionBase):",
    ),
    ".venv/Lib/site-packages/pygfx/objects/_skins.py": (
        "def pose(model_complexity=2, self):",
        "def pose(self):",
    ),
}


def _patch_mediapipe_solution_files():
    here = Path(__file__).resolve().parent
    for rel_path, (before, after) in PATCHES.items():
        path = here / rel_path
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if before not in text:
            continue
        try:
            path.write_text(text.replace(before, after), encoding="utf-8")
            print(f"[sitecustomize] patched {path.name}")
        except Exception:
            pass


_patch_mediapipe_solution_files()
