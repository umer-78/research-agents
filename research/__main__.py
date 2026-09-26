"""python -m research bench    100 research runs against the local web, written to results/"""
import sys

from .bench import bench

if __name__ == "__main__":
    if sys.argv[1:] != ["bench"]:
        sys.exit(__doc__)
    print(bench())
