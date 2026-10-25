"""Run:  python code/main.py            -> ../output.csv for dataset/deletion_requests.csv
        python code/main.py --sample   -> code/evaluation/sample_pred.csv for the 32 sample cases (then run evaluate.py)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from auditor.config import OUTPUT
from auditor.pipeline import Auditor, write_csv


def main():
    a = Auditor()
    if "--sample" in sys.argv:
        path = Path(__file__).parent / "evaluation" / "sample_pred.csv"
        write_csv(a.run(a.samples), path)
    else:
        path = OUTPUT
        write_csv(a.run(a.data.requests), path)
    print("wrote", path)


if __name__ == "__main__":
    main()
