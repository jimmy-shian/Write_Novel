import os
import sys

print("Current directory:", os.getcwd())
try:
    print("Files in current directory:", os.listdir('.'))
except Exception as e:
    print("Error listing current directory:", e)

try:
    print("Files in current directory using abspath:", os.listdir(os.path.abspath('.')))
except Exception as e:
    print("Error listing absolute current directory:", e)
