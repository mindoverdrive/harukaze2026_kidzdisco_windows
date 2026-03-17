import os
import re

directory = os.path.dirname(os.path.abspath(__file__))
pattern = re.compile(r'cv2\.VideoCapture\([0-9]\)')

count = 0
for filename in os.listdir(directory):
    if filename.endswith(".py") and filename not in ['manager.py', 'replace_caps.py']:
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = pattern.sub('cv2.VideoCapture(3)', content)
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                count += 1
                print(f"Updated {filename}")
        except Exception as e:
            print(f"Error {filename}: {e}")

print(f"Total files updated: {count}")
