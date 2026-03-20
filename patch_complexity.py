import os
import re

def patch_model_complexity(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Targets and their respective max complexity
    target_configs = {
        'Holistic': 2,
        'Pose': 2,
        'Hands': 1
    }
    
    modified = False
    for target, value in target_configs.items():
        # Pattern to find instantiation of the MediaPipe class
        # It looks for something like mp.solutions.pose.Pose( or mp_pose.Pose(
        pattern = re.compile(rf'([.]|\b)({target})\s*\(', re.IGNORECASE)
        
        matches = list(pattern.finditer(content))
        if not matches:
            continue
            
        # We need to reach inside the parenthesis and check for model_complexity
        # For each match, find the closing parenthesis
        new_content = ""
        last_pos = 0
        
        for match in matches:
            start_pos = match.start()
            new_content += content[last_pos:match.end()]
            
            # Look for the closing paren, but be careful with nested ones
            paren_count = 1
            inner_content_start = match.end()
            inner_content_end = inner_content_start
            
            for i in range(inner_content_start, len(content)):
                if content[i] == '(':
                    paren_count += 1
                elif content[i] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        inner_content_end = i
                        break
            
            inner_content = content[inner_content_start:inner_content_end]
            
            # Check if model_complexity is already there
            if 'model_complexity' in inner_content:
                # Replace existing model_complexity value
                updated_inner = re.sub(r'model_complexity\s*=\s*\d+', f'model_complexity={value}', inner_content)
                if updated_inner != inner_content:
                    modified = True
                new_content += updated_inner
            else:
                # Inject model_complexity
                # If there are already arguments, add a comma
                if inner_content.strip():
                    new_content += f"model_complexity={value}, " + inner_content
                else:
                    new_content += f"model_complexity={value}"
                modified = True
            
            last_pos = inner_content_end
            
        new_content += content[last_pos:]
        content = new_content

    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    base_dir = r'c:\Users\go\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows'
    ignore_files = ['patch_complexity.py', 'replace_caps.py', 'patch_fullscreen.py']
    
    count = 0
    for root, dirs, files in os.walk(base_dir):
        # Skip .venv
        if '.venv' in root:
            continue
            
        for file in files:
            if file.endswith('.py') and file not in ignore_files:
                path = os.path.join(root, file)
                if patch_model_complexity(path):
                    print(f"Patched: {path}")
                    count += 1
                    
    print(f"Total files patched: {count}")

if __name__ == "__main__":
    main()
