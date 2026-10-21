#!/usr/bin/env python3
"""Package only validated public source files."""
import argparse
from pathlib import Path
import zipfile
from check_release import check

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path, help='ZIP path outside the source directory')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = args.output.resolve()
if output == root or root in output.parents:
    parser.error('ZIP must be outside the source directory')
files = check()
output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, Path('note4-weather')/path.relative_to(root))
print(f'Packaged {len(files)} public files: {output.name}')
