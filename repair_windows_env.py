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


def main():
    for rel_path, (before, after) in PATCHES.items():
        path = Path(rel_path)
        if not path.exists():
            print(f"missing {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if before in text:
            path.write_text(text.replace(before, after), encoding="utf-8")
            print(f"patched {path}")
        elif after in text:
            print(f"ok {path}")
        else:
            print(f"unexpected {path}")


if __name__ == "__main__":
    main()
