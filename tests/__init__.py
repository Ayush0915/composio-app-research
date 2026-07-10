# Initialize tests package
import sys
from pathlib import Path

# Add project root to sys.path so schema and research_agent can be imported during tests
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
