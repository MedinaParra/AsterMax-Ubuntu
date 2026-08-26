from pathlib import Path

from astermax.fea.connected_scaling import connected_scaling_report_json


if __name__ == "__main__":
    report = connected_scaling_report_json((2, 4, 8))
    out = Path("connected_scaling_report.json")
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"wrote {out.resolve()}")
