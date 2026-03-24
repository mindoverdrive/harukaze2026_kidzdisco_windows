import time
import math

CONFIG_DIST = 0.15

class GestureInterpreter:
    def __init__(self):
        self.last_clap_time = 0.0
        self.clap_count = 0
        self.hands_were_apart = True

    def check_head_clap(self, left_hand, right_hand, nose):
        if not (left_hand and right_hand and nose):
            return False

        if left_hand.y > nose.y + 0.1 or right_hand.y > nose.y + 0.1:
            return False

        dist = math.sqrt((left_hand.x - right_hand.x) ** 2 + (left_hand.y - right_hand.y) ** 2)
        current_time = time.time()

        if dist > CONFIG_DIST * 1.5:
            self.hands_were_apart = True
            return False

        if dist < CONFIG_DIST and self.hands_were_apart:
            self.hands_were_apart = False
            time_diff = current_time - self.last_clap_time

            if time_diff < 0.15:
                pass
            elif time_diff <= 1.5:
                self.clap_count += 1
            else:
                self.clap_count = 1

            self.last_clap_time = current_time
            if self.clap_count >= 2:
                self.clap_count = 0
                return True

        return False
        
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
