from pathlib import Path

from astermax.fea.scaling import scaling_report_json


if __name__ == "__main__":
    report = scaling_report_json((8, 32, 128))
    out = Path("sparse_scaling_report.json")
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"wrote {out.resolve()}")
