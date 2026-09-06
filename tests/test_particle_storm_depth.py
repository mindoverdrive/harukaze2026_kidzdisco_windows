"""Run the actual physics callback on CPU, isolated from native-library mocks."""
import ast
from importlib.machinery import PathFinder
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def physics(positions, velocities, hands, seed=42):
    import numpy as np

    # Load only constants and this callback: no camera, window, MediaPipe or GPU.
    tree = ast.parse((ROOT / "particle_storm_2.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ParticleStormApp")
    callback = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "update_physics")
    constants = [n for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)]
    rng = np.random.RandomState(seed)
    namespace = {"np": SimpleNamespace(**{**vars(np), "random": rng})}
    exec(compile(ast.Module(body=[*constants, callback], type_ignores=[]), str(ROOT / "particle_storm_2.py"), "exec"), namespace)
    namespace["NUM_PARTICLES"] = len(positions)
    colors = np.ones((len(positions), 4), dtype=np.float32)
    app = SimpleNamespace(positions=positions.copy(), velocities=velocities.copy(), colors=colors,
                          hand_data=hands, geometry=SimpleNamespace(
                              positions=SimpleNamespace(data=positions.copy(), update_range=lambda: None),
                              colors=SimpleNamespace(data=colors.copy(), update_range=lambda: None)))
    return app, lambda dt: namespace["update_physics"](app, dt)


def xy_case():
    import numpy as np

    # Preserve the old force's XY and 3D falloff, including hand-proximity alpha.
    p = np.array([[200, -300, -700], [-400, 100, 900], [0, 0, 0]], dtype=np.float32)
    v = np.array([[10, 20, 30], [-20, 50, -30], [0, 0, 0]], dtype=np.float32)
    for gesture in (1.0, -2.0):
        h = np.array([90, 40, 250], dtype=np.float32)
        app, step = physics(p, v, [{"pos": h, "gest": gesture}])
        delta = h - p
        dist = np.sqrt(np.sum(delta ** 2, axis=1) + 1000.0)
        strength = 450000.0 / (dist + 200.0) if gesture > 0 else -600000.0 / (dist + 50.0)
        force = delta / dist[:, None] * strength[:, None]
        noise = (np.random.RandomState(42).rand(len(p), 3) - 0.5) * 10.0
        expected_v = v.copy()
        expected_v += (force + noise) / 30.0
        expected_v *= 0.95
        step(1 / 30)
        np.testing.assert_allclose(app.velocities[:, :2], expected_v[:, :2], rtol=1e-6, atol=1e-6)
        np.testing.assert_allclose(app.positions[:, :2], (p + expected_v / 30.0)[:, :2], rtol=1e-6, atol=1e-6)
        np.testing.assert_allclose(app.colors[:, 3], 0.9 - np.clip(dist / 1000.0, 0, 1) * 0.4)


def z_case():
    import numpy as np

    rng = np.random.RandomState(9)
    p = rng.uniform(-1000, 1000, (256, 3)).astype(np.float32)
    v = rng.uniform(-20, 20, p.shape).astype(np.float32)
    # Include existing per-axis bounds and nonzero depth momentum.
    p[:2, 2] = [-1501, 1501]
    pull = {"pos": np.array([250, -200, 600], dtype=np.float32), "gest": 1.0}
    push = {"pos": np.array([-50, 300, -400], dtype=np.float32), "gest": -2.0}
    for hands in ([pull], [push], [pull, push]):
        control, control_step = physics(p, v, [])
        app, step = physics(p, v, hands)
        for _ in range(90):
            control_step(1 / 30)
            step(1 / 30)
        np.testing.assert_array_equal(app.positions[:, 2], control.positions[:, 2])
        np.testing.assert_array_equal(app.velocities[:, 2], control.velocities[:, 2])
        assert np.isfinite(app.positions).all()


def long_case():
    import numpy as np

    rng = np.random.RandomState(8)
    p = rng.uniform(-1000, 1000, (256, 3)).astype(np.float32)
    app, step = physics(p, np.zeros_like(p), [{"pos": np.zeros(3, dtype=np.float32), "gest": 1.0}])
    initial = float(p[:, 2].std())
    for _ in range(30 * 180):
        step(1 / 30)
    final = float(app.positions[:, 2].std())
    print(f"180 simulated seconds: Z std {initial:.3f} -> {final:.3f}")
    assert np.isfinite(app.positions).all() and np.isfinite(app.velocities).all()
    assert final > initial * 0.9, "Sustained XY attraction collapsed the depth distribution"
    assert final < initial * 1.1, "Depth spread grew unexpectedly"


@unittest.skipUnless(PathFinder.find_spec("numpy") is not None, "Requires the graphics runtime's real NumPy")
class ParticleStormDepthTests(unittest.TestCase):
    def run_case(self, name):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()), "--case", name],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_xy_force_and_proximity_alpha_keep_existing_falloff(self):
        self.run_case("xy")

    def test_pull_push_and_two_hands_cannot_change_depth_motion(self):
        self.run_case("z")

    def test_sustained_attraction_retains_depth_spread(self):
        self.run_case("long")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--case":
        {"xy": xy_case, "z": z_case, "long": long_case}[sys.argv[2]]()
    else:
        unittest.main()
