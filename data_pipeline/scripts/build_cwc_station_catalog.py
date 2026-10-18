#!/usr/bin/env python3
"""Build a review-only catalogue of CWC stations from normalized discharge CSV.
Coordinates are NOT considered verified just because they are in the source archive.
"""
from __future__ import annotations
import argparse, csv, json, math, pathlib
from collections import defaultdict

FIELDS = ["station_id","station_name","state","district","river","basin","latitude","longitude","record_count","first_observed_at","last_observed_at","source_urls","coordinate_valid_range","coordinate_verified","coordinate_source_url","review_status"]
REQUIRED = {"station_id","station_name","state","district","river","basin","latitude","longitude","observed_at","source_url"}

def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument('--input',required=True,type=pathlib.Path); p.add_argument('--output',required=True,type=pathlib.Path); p.add_argument('--report',required=True,type=pathlib.Path); a=p.parse_args()
 groups={}; conflicts=defaultdict(set)
 with a.input.open(newline='',encoding='utf-8-sig') as f:
  reader=csv.DictReader(f); missing=sorted(REQUIRED-set(reader.fieldnames or []))
  if missing: raise SystemExit(f'Missing columns: {missing}')
  for r in reader:
   sid=(r.get('station_id') or '').strip()
   if not sid: continue
   key=((r.get('state') or '').strip().casefold(),(r.get('station_name') or '').strip().casefold())
   conflicts[key].add(((r.get('latitude') or '').strip(),(r.get('longitude') or '').strip()))
   if sid not in groups:
    groups[sid]={**{k:(r.get(k) or '').strip() for k in ['station_id','station_name','state','district','river','basin','latitude','longitude']},'record_count':0,'first_observed_at':(r.get('observed_at') or '').strip(),'last_observed_at':(r.get('observed_at') or '').strip(),'_urls':set()}
   g=groups[sid]; g['record_count']+=1; d=(r.get('observed_at') or '').strip()
   if d and (not g['first_observed_at'] or d<g['first_observed_at']): g['first_observed_at']=d
   if d>g['last_observed_at']: g['last_observed_at']=d
   if r.get('source_url'): g['_urls'].add(r['source_url'].strip())
 rows=[]
 for sid,g in groups.items():
  try: lat,lon=float(g['latitude']),float(g['longitude']); valid=math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180
  except (ValueError,TypeError): valid=False
  key=(g['state'].casefold(),g['station_name'].casefold()); conflict=len(conflicts[key])>1
  rows.append({**{k:g[k] for k in FIELDS if k in g},'source_urls':';'.join(sorted(g['_urls'])),'coordinate_valid_range':str(valid).lower(),'coordinate_verified':'false','coordinate_source_url':'','review_status':'coordinate_conflict' if conflict else ('invalid_coordinate_range' if not valid else 'needs_manual_coordinate_verification')})
 rows.sort(key=lambda x:(x['state'].casefold(),x['station_name'].casefold(),x['station_id']))
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open('w',newline='',encoding='utf-8') as f: w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
 report={'input':str(a.input),'output':str(a.output),'stations':len(rows),'valid_coordinate_ranges':sum(x['coordinate_valid_range']=='true' for x in rows),'coordinate_conflicts':sum(x['review_status']=='coordinate_conflict' for x in rows),'manual_verification_required':len(rows),'guardrail':'All stations remain unverified until a human checks coordinates against a reliable source.'}
 a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps(report,indent=2))
if __name__=='__main__': main()
