from __future__ import annotations
"""Extract ASA#4 dose series (Mobil base oil, new >65dB bench standard) from the
frozen source workbook. Cell-level provenance: every value carries its origin cell.

Replay Mode: extraction + normalization only. No statistics, no optimization.
Normalization policy per Real Case Audit Gate: raw preserved; derived view tagged
DERIVED_UNVERIFIED; normalization factor recorded; no silent normalization.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(r"D:\临时文件-工作\风电-临时文件\风电导电油&抗电蚀剂开发过程记录\Lubemater WT 抗电蚀复合剂开发-20260510.xlsx")
SHEET = "ASA#4验证"
# ponytail: sheet format is 'Xh=Y...' or 'Xh+=Y...dB'; trailing commentary ignored
BENCH_NOISE_RE = re.compile(r"^(?P<dur>[0-9.]+)h\+?=(?P<db>[0-9.]+)", re.IGNORECASE)

# Columns B..O = Mobil + ASA#4 dose series, new standard era (samples 251210..251223,
# tests 251211..260105), per sheet header rows 1-3 and audit ruling old/new split.
DOSE_COLS = ["B", "C", "F", "I", "J", "K", "L", "M", "N", "O"]  # 0.5..10%


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_bench(text: str):
    """Parse 'Xh=YdB' bench noise strings. Returns dict or None."""
    m = BENCH_NOISE_RE.match(text.strip())
    if not m:
        return None
    return {"duration_h": float(m.group("dur")), "noise_db": float(m.group("db"))}


def main() -> int:
    src_sha = sha256_file(SRC)
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb[SHEET]

    records = []
    for col in DOSE_COLS:
        dose_frac = ws[f"{col}3"].value          # e.g. 0.005 == 0.5%
        sample_id = ws[f"{col}6"].value           # e.g. 美孚+2%ASA#4
        sample_date = ws[f"{col}7"].value         # yymmdd
        test_date = ws[f"{col}8"].value
        bench_raw = ws[f"{col}9"].value or ""
        note = ws[f"{col}5"].value or ""
        parsed = parse_bench(str(bench_raw))
        if parsed is None:
            raise SystemExit(f"unparseable bench cell {SHEET}!{col}9: {bench_raw!r}")
        base_frac = round(1.0 - dose_frac, 12)
        rec = {
            "run_reference": f"WGO001-ASA4-{col}",
            "provenance": {
                "source_file": SRC.name,
                "source_file_sha256": src_sha,
                "sheet": SHEET,
                "dose_cell": f"{SHEET}!{col}3",
                "sample_id_cell": f"{SHEET}!{col}6",
                "sample_date_cell": f"{SHEET}!{col}7",
                "test_date_cell": f"{SHEET}!{col}8",
                "bench_result_cell": f"{SHEET}!{col}9",
                "note_cell": f"{SHEET}!{col}5",
                "raw_bench_text": bench_raw,
                "raw_note": str(note),
            },
            "sample_date_yymmdd": sample_date,
            "bench_test_date_yymmdd": test_date,
            "base_oil": "MOBIL",
            "asa4_dose_fraction": dose_frac,
            "mobil_fraction_raw": base_frac,
            "fraction_sum": round(base_frac + dose_frac, 12),
            "normalization": {
                "status": "IDENTITY",
                "factor": 1.0,
                "reason": "two-component dose series sums to exactly 1.0 by construction",
            },
            "bench_noise_db": parsed["noise_db"],
            "bench_duration_h": parsed["duration_h"],
            "bench_standard": ">65dB_new",
            "quality_tags": {
                "bench_method_version": "PARTIALLY_VERIFIED(new std, no formal change record E-04)",
                "replicate": "NONE(E-05)",
                "price_basis": "NOT_APPLICABLE(descriptive stats only)",
            },
        }
        records.append(rec)

    out_dir = ROOT / "data" / "real_cases" / "WGO_001" / "normalized"
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "snapshot_id": "WGO_001_ASA4_DOSE_V1",
        "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "source_files": [{"path": str(SRC), "sha256": src_sha}],
        "record_count": len(records),
        "data_owner_source": "CF-30C/WT project R&D workbook (ASA#4验证 sheet)",
        "notes": [
            "new bench standard >65dB subset only; old >75dB excluded (E-04)",
            "Mobil base oil only; Shell/Castrol/red-Mobil/aged/current-var columns excluded",
        ],
    }
    (out_dir / "DATA_SNAPSHOT.json").write_bytes(
        (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    dataset = {
        "dataset_id": "WGO001_ASA4_DOSE_BENCH_V1",
        "response": {"ctq": "EROSION_NOISE_DB", "unit": "dB", "direction": "LOWER_IS_BETTER",
                     "guardrail": "<=65 dB @10h (new standard)"},
        "design_type_tag": "HISTORICAL_OFAT",
        "analysis_class": "DESCRIPTIVE_ONLY",
        "evidence_strength": "DESCRIPTIVE",
        "records": records,
    }
    out_path = out_dir / "asa4_dose_bench.json"
    out_path.write_bytes((json.dumps(dataset, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"output": str(out_path.relative_to(ROOT)), "records": len(records),
                      "source_sha256": src_sha[:16] + "..."}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
