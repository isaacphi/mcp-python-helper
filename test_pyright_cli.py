import subprocess
import sys
import json

def run_pyright():
    # Run pyright directly on example.py
    result = subprocess.run(
        ["pyright", "--outputjson", "example.py"],
        capture_output=True,
        text=True
    )
    
    print("Exit code:", result.returncode)
    
    try:
        output = json.loads(result.stdout)
        print("\nFormatted output:")
        print(json.dumps(output, indent=2))
    except json.JSONDecodeError:
        print("\nRaw stdout:")
        print(result.stdout)
    
    if result.stderr:
        print("\nStderr:")
        print(result.stderr)

if __name__ == "__main__":
    run_pyright()