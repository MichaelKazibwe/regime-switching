"""Freeze actual FRED/ALFRED releases without exposing the configured API key."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError

import pandas as pd

from core_constants import settings
from macrovintage import MacroVintageData

SERIES=('UNRATE','CPIAUCSL','INDPRO','DGS10','DGS3MO')


def fetch_series(series_id, cutoff, *, realtime_start='2005-01-01', windowed=False):
    if series_id in {'DGS10','DGS3MO'} and not windowed:
        frames=[]
        start=pd.Timestamp(realtime_start)
        end=pd.Timestamp(cutoff)
        while start<=end:
            stop=min(end,start+pd.DateOffset(years=5)-pd.Timedelta(days=1))
            vintage=fetch_series(series_id,str(stop.date()),realtime_start=str(start.date()),windowed=True)
            frames.append(vintage.releases[['date','realtime_start','value']])
            start=stop+pd.Timedelta(days=1)
        return MacroVintageData(pd.concat(frames,ignore_index=True).drop_duplicates())
    offset=0
    rows=[]
    while True:
        parameters={'series_id':series_id,'api_key':settings.fred_api_key,'file_type':'json',
                    'realtime_start':realtime_start,'realtime_end':cutoff,'observation_start':'2004-01-01',
                    'observation_end':cutoff,'output_type':1,'limit':100000,'offset':offset}
        try:
            with urlopen('https://api.stlouisfed.org/fred/series/observations?'+urlencode(parameters),timeout=60) as response:
                payload=json.load(response)
        except HTTPError as exc:
            try:
                message=json.loads(exc.read()).get('error_message','Request rejected')
                message=str(message).replace(str(settings.fred_api_key),'[REDACTED]')[:300]
            except Exception:
                message='Request rejected'
            raise RuntimeError(f'Macro request rejected for {series_id}: {message}') from None
        except Exception as exc:
            # URL exceptions can contain credentials. Never print or chain them.
            raise RuntimeError(f'Macro request failed for {series_id} ({type(exc).__name__}); check connectivity and the protected FRED configuration.') from None
        batch=payload.get('observations',[])
        rows.extend(batch)
        offset+=len(batch)
        if offset>=int(payload.get('count',0)):
            break
        if not batch:
            raise RuntimeError(f'Incomplete paginated macro history for {series_id}')
    if not rows:
        raise RuntimeError(f'No archived observations for {series_id}')
    return MacroVintageData(pd.DataFrame(rows)[['date','realtime_start','value']])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('var/research/smart-macro-vintages'))
    parser.add_argument('--cutoff',default='2025-10-29')
    args=parser.parse_args()
    if not settings.fred_api_key:
        raise RuntimeError('Configure the protected FRED API key before downloading macro vintages.')
    args.output.mkdir(parents=True,exist_ok=True)
    manifest={'status':'ACTUAL_FRED_RELEASES','retrieved_at':datetime.now(timezone.utc).isoformat(),
              'cutoff':args.cutoff,'series':{},'availability_policy':'NEXT_NEW_YORK_MIDNIGHT'}
    for series in SERIES:
        destination=args.output/f'{series}.csv'
        if destination.exists():
            vintage=MacroVintageData(pd.read_csv(destination))
            if (vintage.releases.realtime_start>pd.Timestamp(args.cutoff)).any():
                raise RuntimeError('Existing archive exceeds the requested cutoff')
            manifest['series'][series]={'path':str(destination),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
                                         'rows':len(vintage.releases),'resumed_existing':True}
        else:
            vintage=fetch_series(series,args.cutoff)
            manifest['series'][series]=vintage.freeze(destination)
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(f'{series}: froze {len(vintage.releases):,} actual observation/vintage records.',flush=True)
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Macro manifest: {args.output / "manifest.json"}')


if __name__=='__main__':
    main()
