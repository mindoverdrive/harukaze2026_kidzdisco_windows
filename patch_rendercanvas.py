"""
Patch all RenderCanvas-based scripts to add display_utils.setup_rendercanvas_fullscreen(canvas) 
after each RenderCanvas(...) creation.
"""
import os
import re

BASE_DIR = r'c:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows'

# Files that use RenderCanvas and their canvas variable patterns
# We'll find lines like: self.canvas = RenderCanvas(...) or canvas = RenderCanvas(...)
# and add display_utils.setup_rendercanvas_fullscreen(canvas_var) right after

IGNORE_FILES = {'patch_rendercanvas.py', 'patch_fullscreen.py', 'patch_complexity.py', 'display_utils.py', 'test_gfx_transparency.py'}

def patch_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'RenderCanvas(' not in content:
        return False
    
    if 'setup_rendercanvas_fullscreen' in content:
        return False  # Already patched
    
    lines = content.split('\n')
    new_lines = []
    patched = False
    
    for line in lines:
        new_lines.append(line)
        # Match: variable = RenderCanvas(...)
        match = re.match(r'^(\s*)([\w.]+)\s*=\s*RenderCanvas\(', line)
        if match:
            indent = match.group(1)
            var_name = match.group(2)
            # Add setup call after canvas creation
            new_lines.append(f'{indent}display_utils.setup_rendercanvas_fullscreen({var_name})')
            patched = True
    
    if patched:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        return True
    return False

count = 0
for f in os.listdir(BASE_DIR):
    if f.endswith('.py') and f not in IGNORE_FILES:
        path = os.path.join(BASE_DIR, f)
        if patch_file(path):
            print(f"Patched: {f}")
            count += 1

print(f"\nTotal files patched: {count}")
