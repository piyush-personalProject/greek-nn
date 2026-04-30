# run_tests.py
"""
Test runner script for GreekNN Risk System.
Run this script to execute all unit tests.
"""
import subprocess
import sys

def main():
    """Run pytest with coverage."""
    print("=" * 60)
    print("GreekNN Risk System - Running Tests")
    print("=" * 60)
    
    try:
        # Run pytest
        result = subprocess.run(
            ["pytest", "-v", "--tb=short", "--cov=.", "--cov-report=term-missing"],
            capture_output=False
        )
        sys.exit(result.returncode)
    except FileNotFoundError:
        print("Error: pytest not found. Install with: pip install pytest pytest-cov")
        sys.exit(1)
    except Exception as e:
        print(f"Error running tests: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()