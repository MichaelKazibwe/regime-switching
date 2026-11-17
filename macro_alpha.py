"""Prospective macro-regime research monitor; never an allocation or order gate."""

from datetime import datetime, timezone
from pathlib import Path
import fcntl

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from fourregimestrategies import quadrant
from macrovintage import MacroVintageData
from strategy_integrity import strict_json, file_hash, fingerprint
from strategy_receipts import atomic_json
from strategy_report import load_training_report
from strategy_training_data import usable_session

NAMES = ('disinflationary_growth', 'inflationary_growth', 'stagflation', 'deflationary_slowdown')
SETTINGS = dict(horizon_sessions=63, training_sessions=1260, minimum_training=252,
                regularization_C=1.0, probability_shrink=0.25)
SOURCES = ('macro_alpha.py', 'macro_feature_contract.py', 'macrovintage.py',
           'fourregimestrategies.py', 'research/global_asset_registry.json')


def components(views, stamp):
    """Independent exact-period features; missing components stay missing."""
    date = pd.Timestamp(stamp).tz_convert('America/New_York').date()
    values, missing, periods = {}, {}, {}

    def required(key, offsets):
        s = views[key].dropna()
        limit = 14 if key.startswith('DGS') else 90
        if s.empty or (date - s.index[-1].date()).days > limit:
            raise ValueError(f'{key}: missing or stale observations')
        if s.index[-1].date() > date or not np.isfinite(s.to_numpy()).all():
            raise ValueError(f'{key}: invalid or future observations')
        if key.startswith('DGS'):
            return s
        s = pd.Series(s.to_numpy(), index=s.index.to_period('M'))
        if not s.index.is_unique:
            raise ValueError(f'{key}: ambiguous monthly periods')
        needed = [s.index[-1] - n for n in offsets]
        absent = [str(p) for p in needed if p not in s]
        if absent:
            raise ValueError(f'{key}: missing required periods {", ".join(absent)}')
        periods.setdefault(key, set()).update(str(p) for p in needed)
        return [float(s.loc[p]) for p in needed]

    for name in ('ip_growth', 'unemployment_change', 'inflation_change', 'yield_curve'):
        try:
            if name == 'ip_growth':
                a, b = required('INDPRO', [0, 6])
                if min(a,b) <= 0:
                    raise ValueError('Nonpositive production index')
                value = 100 * ((a / b) ** 2 - 1)
            elif name == 'unemployment_change':
                u = required('UNRATE', [0, 1, 2, 3, 4, 5])
                value = np.mean(u[:3]) - np.mean(u[3:])
            elif name == 'inflation_change':
                a, b, c, d = required('CPIAUCSL', [0, 12, 3, 15])
                if min(a,b,c,d) <= 0:
                    raise ValueError('Nonpositive CPI index')
                value = 100 * (a/b - c/d)
            else:
                a, b = required('DGS10', []), required('DGS3MO', [])
                aligned = pd.concat([a,b], axis=1, join='inner').dropna()
                if aligned.empty or (date - aligned.index[-1].date()).days > 14:
                    raise ValueError('Missing or stale aligned yields')
                value = aligned.iloc[-1,0] - aligned.iloc[-1,1]
            if not np.isfinite(value):
                raise ValueError('Nonfinite component')
            values[name] = float(value)
        except ValueError as error:
            missing[name] = str(error)
    return values, missing, {k: sorted(v) for k,v in periods.items()}


def predict(features, current, settings=None):
    settings = settings or SETTINGS
    if not features or [r['date'] for r in features] != sorted({r['date'] for r in features}):
        raise ValueError('Unique sorted feature history required')
    horizon = settings['horizon_sessions']
    stop = len(features) - 1 - horizon
    names = sorted(current)
    if not set(names) <= {'ip_growth','unemployment_change','inflation_change','yield_curve'}:
        raise ValueError('Unknown macro component')
    if not np.isfinite(list(current.values())).all():
        raise ValueError('Nonfinite current macro inputs')
    ids = [i for i in range(max(0,stop-settings['training_sessions']),max(0,stop))
           if features[i].get('macro_valid', False) and features[i+horizon].get('macro_valid', False)
           and all(np.isfinite(features[i][k]) for k in names)]
    labels = np.array([quadrant(features[i+horizon]) for i in ids], dtype=int)
    baseline = (np.bincount(labels,minlength=4)+1)/(len(ids)+4)
    probabilities = None
    if names and len(ids) >= settings['minimum_training'] and len(np.unique(labels)) >= 2:
        model = make_pipeline(StandardScaler(), LogisticRegression(C=settings['regularization_C'],max_iter=1000))
        model.fit([[features[i][k] for k in names] for i in ids], labels)
        learned = np.zeros(4)
        learned[model[-1].classes_] = model.predict_proba([[current[k] for k in names]])[0]
        probabilities = ((1-settings['probability_shrink'])*baseline + settings['probability_shrink']*learned).tolist()
    return dict(probabilities=probabilities, baseline=baseline.tolist(), feature_names=names,
                training_examples=len(ids), last_training_label_date=features[ids[-1]+horizon]['date'] if ids else None,
                settings=settings)


def build(capture_path, training_path):
    capture_path, training_path = Path(capture_path), Path(training_path)
    capture, report = strict_json(capture_path), load_training_report(training_path)
    if not report['current_numerical_source_match'] or file_hash(capture_path) != report['capture_sha256']:
        raise ValueError('Source-matched macro alpha inputs required')
    for name,digest in capture['files'].items():
        if Path(name).name != name or file_hash(capture_path.parent/name) != digest:
            raise ValueError('Macro alpha capture integrity mismatch')
    features = strict_json(training_path.parent/'features.json')
    if features[-1]['date'] != report['market_session']:
        raise ValueError('Macro alpha decision session mismatch')
    stamp = pd.Timestamp(features[-1]['as_of'])
    if stamp.tzinfo is None or str(stamp.tz_convert('America/New_York').date()) != report['market_session']:
        raise ValueError('Aware matching decision timestamp required')
    views = {k:MacroVintageData.from_csv(capture_path.parent/f'{k}.csv',
             expected_sha256=capture['files'][f'{k}.csv']).as_of(stamp) for k in
             ('UNRATE','CPIAUCSL','INDPRO','DGS10','DGS3MO')}
    current, missing, periods = components(views,stamp)
    prediction = predict(features,current)
    protocol = fingerprint(dict(sources={p:file_hash(p) for p in SOURCES},settings=SETTINGS,
                                feature_names=prediction['feature_names']))
    result = dict(schema_version=1, synthetic_fixture=bool(capture.get('synthetic_fixture',False)), status=('MONITORING_PARTIAL_INPUTS' if missing else 'MONITORING_FULL_INPUTS')
                  if prediction['probabilities'] else 'MONITORING_WAITING_FOR_INPUTS_OR_HISTORY',
                  monitoring_enabled=True, market_session=report['market_session'], as_of=stamp.isoformat(),
                  protocol_id=protocol, components=current, missing_components=missing, required_periods=periods,
                  strict_full_input_available=bool(features[-1].get('macro_valid',False)),
                  strict_input_reason=features[-1].get('macro_unavailable_reason'),
                  regimes=list(NAMES), prediction=prediction,
                  source_hashes={p:file_hash(p) for p in SOURCES},
                  provenance=dict(capture_sha256=file_hash(capture_path),training_sha256=file_hash(training_path),
                                  features_sha256=file_hash(training_path.parent/'features.json')),
                  applies_to='Shared research monitoring for every portfolio, benchmark and strategy; no allocation override',
                  alpha_established=False, portfolio_activation_enabled=False, execution_enabled=False,promotion_enabled=False,
                  limitations=['Partial-input model is a separate research challenger, not the full-input incumbent.',
                               'Target is the released-condition regime 63 market sessions ahead, not a return forecast.',
                               'Training uses only full-valid historical rows and matured labels strictly before origin; missing components are excluded, never filled.',
                               'Fixed parameters, 25% model / 75% frequency shrinkage; no demonstrated predictive or portfolio advantage.',
                               'Reconstructed history is training evidence, not live-issued observations.'])
    evidence=strict_json('research/macro_gap_evidence.json')
    result['availability_diagnostics']=[{**gap,'use':'POST_HOC_CONTEXT_NOT_MODEL_INPUT'}
        for gap in evidence['gaps'] if any(gap['series'] in reason and gap['period'] in reason for reason in missing.values())]
    result['forecast_id'] = fingerprint(result)
    return result


def record(result, features, root, *, now=None):
    """Issue one immutable genuine-session prediction and score only matured origins."""
    now = now or datetime.now(timezone.utc)
    if result.get('synthetic_fixture') and __import__('os').environ.get('PILOT_ALLOW_SYNTHETIC_QA') != '1':
        raise ValueError('Synthetic forecasts cannot enter genuine observation streams')
    if now.tzinfo is None or result['market_session'] != str(usable_session(now).date()) or pd.Timestamp(result['as_of']) > pd.Timestamp(now):
        raise ValueError('Macro alpha must be observed on the genuine completed session')
    if fingerprint({k:v for k,v in result.items() if k != 'forecast_id'}) != result['forecast_id']:
        raise ValueError('Macro alpha forecast integrity mismatch')
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/'monitor.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=root/f"{result['market_session']}-{result['protocol_id']}.json"
        if path.exists():
            if strict_json(path)['forecast']['forecast_id'] != result['forecast_id']:
                raise ValueError('Macro alpha session already sealed with different evidence')
        else:
            atomic_json(path,dict(issued_at=now.isoformat(),forecast=result),exclusive=True)
        sessions={r['date']:i for i,r in enumerate(features)}
        groups = {}
        groups[result['protocol_id']] = dict(pending=0, matured_unscorable=0, outcomes=[])
        for p in sorted(root.glob('????-??-??-*.json')):
            issued=strict_json(p)
            r=issued['forecast']
            if fingerprint({k:v for k,v in r.items() if k != 'forecast_id'}) != r['forecast_id']:
                raise ValueError('Stored macro alpha forecast integrity mismatch')
            if datetime.fromisoformat(issued['issued_at']) > now:
                raise ValueError('Future macro alpha receipt')
            if r['prediction']['probabilities'] is None:
                continue
            group = groups.setdefault(r['protocol_id'], dict(pending=0, matured_unscorable=0, outcomes=[]))
            i=sessions.get(r['market_session'])
            h=r['prediction']['settings']['horizon_sessions']
            if i is None or i+h >= len(features):
                group["pending"]+=1
                continue
            target_compatible = all(r.get('source_hashes', {}).get(k) == result.get('source_hashes', {}).get(k)
                                    for k in ('macro_feature_contract.py', 'fourregimestrategies.py'))
            if not target_compatible or not features[i+h].get('macro_valid',False):
                group["matured_unscorable"]+=1
                continue
            target=np.eye(4)[quadrant(features[i+h])]
            group["outcomes"].append(dict(origin=r['market_session'],outcome_session=features[i+h]['date'], outcome_evidence_sha256=fingerprint(features[i+h]),
                                 brier_model=float(np.square(np.array(r['prediction']['probabilities'])-target).sum()),
                                 brier_baseline=float(np.square(np.array(r['prediction']['baseline'])-target).sum())))
        summaries = {}
        for protocol, group in groups.items():
            outcomes = group['outcomes']
            summaries[protocol] = dict(protocol_id=protocol,
                observed_forecasts=group['pending']+len(outcomes)+group['matured_unscorable'],
                pending=group['pending'], matured_unscorable=group['matured_unscorable'],
                matured=len(outcomes), outcomes=outcomes, alpha_established=False, execution_enabled=False)
        summary = summaries[result['protocol_id']]
        summary['archived_protocols'] = [v for k,v in summaries.items() if k != result['protocol_id']]
        atomic_json(root/'latest.json',dict(forecast=result,monitoring=summary))
        return summary


if __name__ == '__main__':
    import json
    pointer=strict_json('var/dashboard-live/latest.json')
    bundle=strict_json(pointer['bundle'])
    result=build(bundle['capture'],bundle['training_report'])
    monitoring=record(result,strict_json(Path(bundle['training_report']).parent/'features.json'),'var/macro-alpha')
    print(json.dumps(dict(status=result['status'],features=result['prediction']['feature_names'],monitoring=monitoring),indent=2))
