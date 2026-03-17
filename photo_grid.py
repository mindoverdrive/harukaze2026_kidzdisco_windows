# =============================================================================
# [AUTO-INJECTED] Scene Preload & Wait Logic
# =============================================================================
import sys
import argparse
import socket
import json

# Only execute the wait logic if we are running the script directly
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true", help="Wait for START signal via UDP")
    parser.add_argument("--port", type=int, default=0, help="UDP port to listen on for START signal")
    # Parse known args so we don't crash if other args are passed
    args, _ = parser.parse_known_args()

    if args.wait and args.port > 0:
        print(f"[Scene] Started in PRELOAD mode. Waiting for START command on port {args.port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", args.port))
        sock.settimeout(None) # Wait indefinitely
        
        while True:
            data, addr = sock.recvfrom(1024)
            try:
                msg = json.loads(data.decode('utf-8'))
                if msg.get("cmd") == "START":
                    print("[Scene] Received START command. Booting up...")
                    sock.close()
                    break
            except Exception as e:
                pass
# =============================================================================
import cv2
import mediapipe as mp
import pygame
import display_utils
import numpy as np
import math
import time

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
GRID_ROWS = 3
GRID_COLS = 3

# Colors
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
BLACK = (0, 0, 0)
YELLOW = (255, 255, 0)

# MediaPipe Setup
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

class DraggablePiece:
    def __init__(self, surface, x, y, width, height, row, col):
        self.surface = surface
        self.rect = pygame.Rect(x, y, width, height)
        self.original_width = width
        self.original_height = height
        self.dragging = False
        self.offset_x = 0
        self.offset_y = 0
        self.row = row
        self.col = col
        self.creation_time = time.time() # For animation effects

    def draw(self, screen):
        screen.blit(self.surface, self.rect)
        # Draw border
        pygame.draw.rect(screen, WHITE, self.rect, 2)

class Action:
    DELETE = 0
    CAPTURE = 1
    def __init__(self, type, data):
        self.type = type
        self.data = data

class FadingDottedRect:
    def __init__(self, rect, color=WHITE):
        self.rect = rect
        self.color = color
        self.alpha = 255
        self.life = 0.5 # Reduced from 1.0 to 0.5 for 2x speed
        self.initial_life = 0.5

    def update(self):
        self.life -= 0.016 # approx 60fps
        self.alpha = int((self.life / self.initial_life) * 255)

    def is_finished(self):
        return self.life <= 0

    def draw(self, screen):
        if self.life <= 0: return
        
        # Draw dotted line (simulated)
        # Top
        self._draw_dotted_line(screen, self.rect.topleft, self.rect.topright)
        # Bottom
        self._draw_dotted_line(screen, self.rect.bottomleft, self.rect.bottomright)
        # Left
        self._draw_dotted_line(screen, self.rect.topleft, self.rect.bottomleft)
        # Right
        self._draw_dotted_line(screen, self.rect.topright, self.rect.bottomright)

    def _draw_dotted_line(self, screen, start, end):
        # manually draw segments
        dist = math.hypot(end[0]-start[0], end[1]-start[1])
        
        # Dynamic segment length based on life
        # Life goes 1.0 -> 0.0
        # Segment length: Start at 20, go down to 2
        seg_len = max(2, int(20 * self.life))
        
        if seg_len <= 0: seg_len = 1
        
        steps = int(dist // seg_len) 
        if steps == 0: steps = 1
        
        dx = (end[0] - start[0]) / steps
        dy = (end[1] - start[1]) / steps
        
        for i in range(0, steps, 2): # Skip every other
            s = (start[0] + dx*i, start[1] + dy*i)
            e = (start[0] + dx*(i+1), start[1] + dy*(i+1))
            pygame.draw.line(screen, (255, 255, 255), s, e, 2)

class PhotoGridApp:
    def __init__(self):
        self.screen, _pg_size = display_utils.setup_pygame_fullscreen()
        pygame.display.set_caption("Photo Grid MediaPipe")
        self.clock = pygame.time.Clock()
        self.running = True

        # Camera
        self.cap = cv2.VideoCapture(3)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, WINDOW_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, WINDOW_HEIGHT)
        
        # Hands
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        
        self.pieces = []
        
        # Trash Bin
        try:
            self.trash_icon = pygame.image.load("test/trashbin.png")
            self.trash_icon = pygame.transform.scale(self.trash_icon, (100, 100))
            self.trash_icon.set_colorkey(WHITE) # Make white transparent
        except:
             # Fallback
            self.trash_icon = pygame.Surface((100, 100))
            self.trash_icon.fill((50, 50, 50))
            pygame.draw.rect(self.trash_icon, RED, (20, 20, 60, 60))

        # Position: Top right, slightly left to avoid cutting off hand
        self.trash_can_rect = self.trash_icon.get_rect(topright=(WINDOW_WIDTH - 200, 20))
        
        # Reset Button Icon
        try:
            self.reset_icon = pygame.image.load("test/reset.png")
            self.reset_icon = pygame.transform.scale(self.reset_icon, (100, 100))
            self.reset_icon.set_colorkey(WHITE) # Make white transparent
        except:
            self.reset_icon = pygame.Surface((100, 100))
            self.reset_icon.fill(RED)
            pygame.draw.circle(self.reset_icon, WHITE, (50, 50), 40, 5)

        # Position: Symmetrical to trash bin (left side)
        self.reset_rect = self.reset_icon.get_rect(topleft=(200, 20))
        
        # Undo Icon
        try:
            self.undo_icon = pygame.image.load("test/undo.jpg")
            self.undo_icon = pygame.transform.scale(self.undo_icon, (100, 100))
            self.undo_icon.set_colorkey(WHITE)
        except:
            self.undo_icon = pygame.Surface((100, 100))
            self.undo_icon.fill(BLUE)
            pygame.draw.circle(self.undo_icon, WHITE, (50, 50), 40, 5)

        # Position: Center-ish (Between Reset and Trash)
        self.undo_rect = self.undo_icon.get_rect(center=(WINDOW_WIDTH // 2, 70))
        
        self.pinch_threshold = 0.05 # Normalized distance
        self.index_finger_tip = 8
        self.thumb_tip = 4
        self.middle_finger_tip = 12
        
        self.capture_cooldown = 0
        self.flash_timer = 0
        
        # Capture Guidelines State
        self.current_capture_rect = None
        
        # History & Effects
        self.history = [] # Stack of Action objects
        self.effects = [] # List of effect objects (e.g., FadingDottedRect)

    def get_hand_data(self, results, width, height):
        hands_data = []
        if results.multi_hand_landmarks:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                label = handedness.classification[0].label
                # Points in pixel coords
                points = []
                for lm in hand_landmarks.landmark:
                    points.append((int(lm.x * width), int(lm.y * height)))
                
                # Normalized points for gestures
                norm_points = []
                for lm in hand_landmarks.landmark:
                    norm_points.append((lm.x, lm.y))
                    
                hands_data.append({
                    "label": label,
                    "points": points,
                    "norm_points": norm_points
                })
        return hands_data

    def is_pinching(self, hand):
        # Dynamic Pinch Threshold based on Hand Size
        # Scale = Distance between Wrist (0) and Middle Finger MCP (9)
        wrist = hand["norm_points"][0]
        middle_mcp = hand["norm_points"][9]
        
        hand_scale = math.hypot(wrist[0] - middle_mcp[0], wrist[1] - middle_mcp[1])
        
        # Thresholds relative to hand scale
        # PINCH: < 45% of hand scale (increased from 30% for better detection at distance)
        # OPEN: > 40% of hand scale (decreased from 50% for middle finger check)
        # Also add minimum thresholds to handle very small hand detections
        pinch_threshold_dynamic = max(hand_scale * 0.39, 0.04)
        open_threshold_dynamic = max(hand_scale * 0.38, 0.03)
        
        # Strict Pinch: Thumb and Index close, Middle finger FAR
        thumb = hand["norm_points"][self.thumb_tip]
        index = hand["norm_points"][self.index_finger_tip]
        middle = hand["norm_points"][self.middle_finger_tip]
        
        dist_ti = math.hypot(thumb[0] - index[0], thumb[1] - index[1])
        dist_tm = math.hypot(thumb[0] - middle[0], thumb[1] - middle[1])
        
        # Thumb-Index close AND Thumb-Middle far enough
        return dist_ti < pinch_threshold_dynamic and dist_tm > open_threshold_dynamic

    def create_grid(self, frame_surface, rect):
        x, y, w, h = rect
        # Ensure within bounds
        x = max(0, x)
        y = max(0, y)
        w = min(w, WINDOW_WIDTH - x)
        h = min(h, WINDOW_HEIGHT - y)
        
        if w < 100 or h < 100: return False # Too small (increased from 50)
        
        # --- Layered Capture ---
        # 1. Create a composition surface (Background + Existing Pieces)
        composition_surface = frame_surface.copy()
        
        # 2. Draw existing pieces onto the composition surface
        #    Note: Pieces are drawn at their absolute screen coordinates.
        #    frame_surface is already the size of the screen.
        for piece in self.pieces:
            piece.draw(composition_surface)
            
        # 3. Crop from this composite surface
        try:
            sub_surface = composition_surface.subsurface((x, y, w, h)).copy()
        except ValueError:
            return False # Fallback for edge cases
        
        cell_w = w // GRID_COLS
        cell_h = h // GRID_ROWS
        
        new_pieces = []
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                px = c * cell_w
                py = r * cell_h
                # Adjust for last row/col to fill remaining pixels
                pw = cell_w if c < GRID_COLS - 1 else w - px
                ph = cell_h if r < GRID_ROWS - 1 else h - py
                
                piece_surf = sub_surface.subsurface((px, py, pw, ph)).copy()
                # Initial position is where capturing rect was
                # Place them exactly where they were captured
                piece = DraggablePiece(piece_surf, x + px, y + py, pw, ph, r, c)
                
                # Make slightly transparent 
                piece.surface.set_alpha(230)
                
                new_pieces.append(piece)
        
        # Add to main list
        self.pieces.extend(new_pieces)
        
        # Record Action for Undo
        self.history.append(Action(Action.CAPTURE, new_pieces))
        return True

    def perform_undo(self):
        if not self.history:
            print("[Undo] History is empty!")
            return
        
        action = self.history.pop()
        print(f"[Undo] Action type: {action.type}")
        
        if action.type == Action.DELETE:
            # Restore deleted piece
            piece = action.data
            print(f"[Undo] Restoring piece: {piece}")
            
            # Ensure target is fully within screen
            max_x = max(0, WINDOW_WIDTH - piece.rect.width)
            max_y = max(0, WINDOW_HEIGHT - piece.rect.height)
            target_x = np.random.randint(0, max_x + 1)
            target_y = np.random.randint(0, max_y + 1)
            print(f"[Undo] Target position: ({target_x}, {target_y})")
            
            # Start at trash
            start_x, start_y = self.trash_can_rect.center
            print(f"[Undo] Start position (trash center): ({start_x}, {start_y})")
            
            # Set piece to start pos (center aligned to trash center)
            piece.rect.center = (start_x, start_y)
            
            # Reset State
            piece.dragging = False
            
            # Use float position for animation
            piece.anim_x = float(piece.rect.x)
            piece.anim_y = float(piece.rect.y)
            piece.target_x = float(target_x)
            piece.target_y = float(target_y)
            
            # Calculate velocity (pixels per frame)
            dx = target_x - piece.rect.x
            dy = target_y - piece.rect.y
            piece.vel_x = dx / 20.0
            piece.vel_y = dy / 20.0
            print(f"[Undo] Velocity: ({piece.vel_x}, {piece.vel_y})")
            
            # Re-add to pieces list
            self.pieces.append(piece)
            print(f"[Undo] Piece added to list. Total pieces: {len(self.pieces)}")
            
        elif action.type == Action.CAPTURE:
            # Remove captured pieces
            captured_pieces = action.data
            # We need to know the bounds of these pieces to draw the dotted rect
            if captured_pieces:
                # Calculate bounding box of all pieces
                min_x = min(p.rect.x for p in captured_pieces)
                min_y = min(p.rect.y for p in captured_pieces)
                max_x = max(p.rect.right for p in captured_pieces)
                max_y = max(p.rect.bottom for p in captured_pieces)
                rect = pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
                
                # Create Fading Dotted Line Effect
                self.effects.append(FadingDottedRect(rect))
                
                # Remove pieces
                for p in captured_pieces:
                    if p in self.pieces:
                        self.pieces.remove(p)

    def run(self):
        # State for dragging: {"Left": {"piece": piece_obj, "offset": (dx, dy)}, ...}
        self.drag_states = {} 

        while self.running:
            dt = self.clock.tick(60) / 1000.0
            if self.capture_cooldown > 0:
                self.capture_cooldown -= dt
            if self.flash_timer > 0:
                self.flash_timer -= dt
                
            # Update Effects
            for effect in self.effects[:]:
                effect.update()
                if effect.is_finished():
                    self.effects.remove(effect)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        self.running = False
                    elif event.key == pygame.K_ESCAPE:
                        self.running = False

            success, img = self.cap.read()
            if not success: continue

            # Mirror image
            img = cv2.flip(img, 1)
            img_h, img_w, _ = img.shape
            
            # MediaPipe
            img_rgb_mp = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = self.hands.process(img_rgb_mp)
            
            # Prepare Pygame surface (Background)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_rgb = np.transpose(img_rgb, (1, 0, 2))
            frame_surface = pygame.surfarray.make_surface(img_rgb)
            
            self.screen.fill(BLACK)
            self.screen.blit(frame_surface, (0, 0))

            # Process Hands
            hands_data = self.get_hand_data(results, WINDOW_WIDTH, WINDOW_HEIGHT)
            
            # Reset capture rect for this frame
            self.current_capture_rect = None
            
            # --- Logic for Capture ---
            if len(hands_data) == 2:
                h1 = hands_data[0]
                h2 = hands_data[1]
                
                idx1 = h1["points"][8]
                idx2 = h2["points"][8]
                
                rect_x = min(idx1[0], idx2[0])
                rect_y = min(idx1[1], idx2[1])
                rect_w = abs(idx1[0] - idx2[0])
                rect_h = abs(idx1[1] - idx2[1])
                
                capture_rect = (rect_x, rect_y, rect_w, rect_h)
                self.current_capture_rect = capture_rect
                
                # Check for Dual Pinch
                pinch1 = self.is_pinching(h1)
                pinch2 = self.is_pinching(h2)
                
                if pinch1 and pinch2:
                    # Prevent capture if currently dragging anything
                    if not self.drag_states: 
                        if self.capture_cooldown <= 0:
                            # Trigger Capture and only flash if successful!
                            if self.create_grid(frame_surface, capture_rect):
                                self.capture_cooldown = 1.0 
                                self.flash_timer = 0.5
            
            # --- Logic for Interaction (Move Pieces) ---
            current_hand_labels = set()
            
            for hand in hands_data:
                label = hand["label"]
                current_hand_labels.add(label)
                
                is_pinching = self.is_pinching(hand)
                cursor_pos = hand["points"][8]
                
                # Calculate scale for visuals
                wrist = hand["norm_points"][0]
                middle_mcp = hand["norm_points"][9]
                hand_scale = math.hypot(wrist[0] - middle_mcp[0], wrist[1] - middle_mcp[1])

                # Visual Cursor Dynamic Size
                # Scale roughly 0.05 (far) to 0.3 (close)
                cursor_radius = int(hand_scale * 100)
                cursor_radius = max(5, min(cursor_radius, 40)) # Clamp size
                
                line_width = int(hand_scale * 20)
                line_width = max(1, min(line_width, 8))

                color = GREEN if is_pinching else RED
                pygame.draw.circle(self.screen, color, cursor_pos, cursor_radius, line_width)
                
                # Check Buttons (Reset / Undo)
                if is_pinching:
                    if self.reset_rect.collidepoint(cursor_pos):
                        # RESET
                        if self.pieces:
                            self.pieces.clear()
                            self.history.clear() # Clear history on reset
                            # Removed flash on reset as requested
                    elif self.undo_rect.collidepoint(cursor_pos):
                        # UNDO
                        if self.capture_cooldown <= 0: # Debounce undo
                            self.perform_undo()
                            self.capture_cooldown = 0.5 # cooldown for undo too
                
                # Interaction State Machine
                if label in self.drag_states:
                    # CURRENTLY DRAGGING
                    drag_info = self.drag_states[label]
                    piece = drag_info["piece"]
                    
                    if is_pinching:
                        # Continue dragging
                        off_x, off_y = drag_info["offset"]
                        piece.rect.x = cursor_pos[0] - off_x
                        piece.rect.y = cursor_pos[1] - off_y
                    else:
                        # RELEASE EVENT
                        # Check trash deletion
                        # Simple collision check with center of piece
                        if self.trash_can_rect.colliderect(piece.rect):
                            # Delete
                            if piece in self.pieces:
                                self.pieces.remove(piece)
                                self.history.append(Action(Action.DELETE, piece)) # Log Delete
                        
                        del self.drag_states[label]
                        piece.dragging = False
                        
                else:
                    # NOT DRAGGING, CHECK START
                    if is_pinching and self.capture_cooldown < 0.7: # Prevent immediate drag after shutter (1.0 -> 0.7 window)
                        # Find piece to pick up
                        found_piece = None
                        # Search reverse order to pick top-most
                        for piece in reversed(self.pieces):
                            if piece.rect.collidepoint(cursor_pos):
                                found_piece = piece
                                break
                        
                        if found_piece:
                            # Start Drag
                            # If piece is already being dragged by OTHER hand?
                            is_busy = False
                            for other_label, other_info in self.drag_states.items():
                                if other_info["piece"] == found_piece:
                                    is_busy = True
                                    break
                            
                            if not is_busy:
                                offset_x = cursor_pos[0] - found_piece.rect.x
                                offset_y = cursor_pos[1] - found_piece.rect.y
                                
                                self.drag_states[label] = {
                                    "piece": found_piece,
                                    "offset": (offset_x, offset_y)
                                }
                                found_piece.dragging = True
                                
                                # Move to front
                                if found_piece in self.pieces:
                                    self.pieces.remove(found_piece)
                                    self.pieces.append(found_piece)
            
            # Cleanup stale drags (if hand lost tracking while pinching)
            lost_labels = [lbl for lbl in self.drag_states if lbl not in current_hand_labels]
            for lbl in lost_labels:
                piece = self.drag_states[lbl]["piece"]
                piece.dragging = False
                del self.drag_states[lbl]

            # Simple Animation Logic for Restored Pieces (float-based)
            for p in self.pieces:
                if hasattr(p, 'vel_x') and hasattr(p, 'target_x'):
                    # Update float position
                    p.anim_x += p.vel_x
                    p.anim_y += p.vel_y
                    
                    # Update rect from float position
                    p.rect.x = int(p.anim_x)
                    p.rect.y = int(p.anim_y)
                    
                    # Check if arrived
                    if abs(p.anim_x - p.target_x) < 5 and abs(p.anim_y - p.target_y) < 5:
                        # Snap to target
                        p.rect.x = int(p.target_x)
                        p.rect.y = int(p.target_y)
                        # Clean up animation attributes
                        del p.anim_x
                        del p.anim_y
                        del p.target_x
                        del p.target_y
                        del p.vel_x
                        del p.vel_y
                        print(f"[Undo Animation] Piece arrived at target.")

            # Draw Pieces
            for piece in self.pieces:
                piece.draw(self.screen)
            
            # Draw Trash Can
            self.screen.blit(self.trash_icon, self.trash_can_rect)
            
            # Draw Reset Button
            self.screen.blit(self.reset_icon, self.reset_rect)
            self.screen.blit(self.undo_icon, self.undo_rect)
            
            # Draw Effects
            for effect in self.effects:
                effect.draw(self.screen)
            
            # Draw Capture Guidelines (Top Layer)
            if self.current_capture_rect:
                pygame.draw.rect(self.screen, BLUE, self.current_capture_rect, 2)

            # Flash Effect
            if self.flash_timer > 0:
                s = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
                s.set_alpha(150)
                s.fill(WHITE)
                self.screen.blit(s, (0,0))
                
            pygame.display.flip()
        
        self.cap.release()
        pygame.quit()

if __name__ == "__main__":
    app = PhotoGridApp()
    app.run()


