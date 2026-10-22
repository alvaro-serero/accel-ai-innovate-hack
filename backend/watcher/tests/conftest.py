import sys
from pathlib import Path

# Make `import backend...` work whatever directory pytest is started from.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
