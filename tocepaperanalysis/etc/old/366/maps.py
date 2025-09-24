import os
import subprocess
import shutil
from pathlib import Path

# Define directories
base_dir = Path(__file__).resolve().parent
maps_dir = base_dir / "maps"

# List all Python files in the maps directory
py_files = sorted(f for f in maps_dir.glob("*.py") if f.name != Path(__file__).name)

# Run each Python file
for py_file in py_files:
    print(f"Running: {py_file.name}")
    subprocess.run(["python3", str(py_file)], check=True)

print("All scripts executed")
