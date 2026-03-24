import time
from manager import GestureInterpreter

class MockLandmark:
    def __init__(self, x, y):
        self.x = x
        self.y = y

def test():
    interpreter = GestureInterpreter()
    nose = MockLandmark(0.5, 0.5)

    print("--- Test: Double Clap ---")
    
    # 1. First clap (Hands close together above nose)
    left = MockLandmark(0.45, 0.2)
    right = MockLandmark(0.55, 0.2)
    res1 = interpreter.check_head_clap(left, right, nose)
    print(f"Clap 1: {res1} (Expected False)")
    
    # Wait for debounce
    time.sleep(0.2)
    
    # 2. Move apart
    left_apart = MockLandmark(0.2, 0.2)
    right_apart = MockLandmark(0.8, 0.2)
    res2 = interpreter.check_head_clap(left_apart, right_apart, nose)
    print(f"Moved apart: {res2} (Expected False)")
    
    # 3. Second clap
    res3 = interpreter.check_head_clap(left, right, nose)
    print(f"Clap 2: {res3} (Expected True)")

    print("\n--- Test: Single Clap Bounce ---")
    interpreter = GestureInterpreter()
    
    # First clap
    res_b1 = interpreter.check_head_clap(left, right, nose)
    print(f"Clap 1: {res_b1} (Expected False)")
    
    # Hands slightly apart, then immediately together (bounce)
    interpreter.check_head_clap(MockLandmark(0.3, 0.2), MockLandmark(0.7, 0.2), nose)
    time.sleep(0.05) # under 0.15s cooldown
    res_b2 = interpreter.check_head_clap(left, right, nose)
    print(f"Bounce clap under 0.15s: {res_b2} (Expected False)")

if __name__ == '__main__':
    test()
