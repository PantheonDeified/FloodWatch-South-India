#!/usr/bin/env python3
"""Convert normalized CWC discharge to the common observations schema.

This is a schema adapter only: it does not verify station coordinates, correct
source measurements, infer a timezone, or label floods.
"""
from __future__ import annotations
import argparse, csv, json, pathlib

INPUT_REQUIRED = {"station_id","station_name","state","district","river","basin","latitude","longitude","observed_at","discharge_m3_s","source_url","source_file","source_timezone"}
OUTPUT_FIELDS = ["station_id","station_name","state","district","river","basin","latitude","longitude","observed_at","kind","value","unit","source_url","source_file","source_timezone","quality_flag"]

def convert(source: pathlib.Path, output: pathlib.Path) -> dict:
    output.parent.mkdir(parents=True,exist_ok=True)
    rows_in=rows_out=bad=0
    with source.open(newline="",encoding="utf-8-sig") as src, output.open("w",newline="",encoding="utf-8") as dst:
        reader=csv.DictReader(src)
        missing=sorted(INPUT_REQUIRED-set(reader.fieldnames or []))
        if missing: raise ValueError(f"Input is missing required normalized CWC columns: {missing}")
        writer=csv.DictWriter(dst,fieldnames=OUTPUT_FIELDS); writer.writeheader()
        for row in reader:
            rows_in+=1
            try:
                value=float(row["discharge_m3_s"])
                if value < 0 or value != value or value in (float("inf"),float("-inf")): raise ValueError
            except (TypeError,ValueError):
                bad+=1; continue
            if not (row.get("station_id") or "").strip() or not (row.get("observed_at") or "").strip() or not (row.get("source_url") or "").strip():
                bad+=1; continue
            writer.writerow({
                "station_id":row["station_id"],"station_name":row["station_name"],"state":row["state"],
                "district":row["district"],"river":row["river"],"basin":row["basin"],
                "latitude":row["latitude"],"longitude":row["longitude"],"observed_at":row["observed_at"],
                "kind":"river_discharge","value":format(value,".12g"),"unit":"m3/s",
                "source_url":row["source_url"],"source_file":row["source_file"],
                "source_timezone":row["source_timezone"] or "unspecified",
                "quality_flag":row.get("quality_flag","unreviewed"),
            }); rows_out+=1
    return {"input":str(source),"output":str(output),"input_rows":rows_in,"output_rows":rows_out,"rows_skipped":bad,"mapping":{"kind":"river_discharge","unit":"m3/s"},"status":"schema_conversion_only_not_data_validation"}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",required=True,type=pathlib.Path); p.add_argument("--output",required=True,type=pathlib.Path); p.add_argument("--report",type=pathlib.Path); a=p.parse_args()
    result=convert(a.input,a.output)
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
