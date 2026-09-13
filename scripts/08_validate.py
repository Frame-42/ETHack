"""Validate the shipped snapshot offline; optionally refresh its summary."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import OUT
from pipeline.validate import validate

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-summary', action='store_true', help='Write data/out/snapshot_summary.json')
    args = parser.parse_args()
    summary = validate()
    if args.write_summary:
        (OUT / 'snapshot_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
