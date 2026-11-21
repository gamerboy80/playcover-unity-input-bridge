#!/usr/bin/env python3
"""Summarize a local probe capture; compare controlled source IDs and observed hits."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

PHASES = {0: 'unlabelled', 1: 'agent_a_direct', 2: 'agent_b_direct',
          3: 'agent_a_off_field', 4: 'other_sources'}


def summarize(records, expected=None):
    if any(not isinstance(record, dict) for record in records):
        raise ValueError('Capture records must be JSON objects')
    sessions = [r for r in records if r.get('type') == 'session']
    if len(sessions) != 1 or sessions[0].get('schema') != 1:
        raise ValueError('Use one complete schema-1 probe capture')
    events = [r for r in records if r.get('type') == 'damage_candidate']
    indexed = {}
    for event in events:
        sequence = event.get('sequence')
        if type(sequence) is not int or sequence <= 0 or sequence in indexed:
            raise ValueError('Invalid or duplicate event sequence')
        for field in ['source_id', 'target_id', 'phase']:
            value = event.get(field)
            if type(value) is not int or not 0 <= value <= 0xffffffff:
                raise ValueError(f'Invalid event {field}')
        if event['phase'] not in PHASES:
            raise ValueError('Unknown training phase')
        indexed[sequence] = event

    def positive(event):
        amount = event.get('amount')
        return type(amount) in (int, float) and math.isfinite(amount) and amount > 0

    def resolved(event, role):
        lookup = event.get(role + '_lookup', {})
        return (isinstance(lookup, dict) and event[role + '_id'] != 0 and lookup.get('observed') is True and
                lookup.get('matches') is True and lookup.get('id') == event[role + '_id'])

    marked = {r.get('phase') for r in records if r.get('type') == 'marker'}
    phases, sources = {}, {}
    for phase, label in PHASES.items():
        selected = [e for e in events if e['phase'] == phase]
        hits = [e for e in selected if positive(e)]
        counts = Counter(e['source_id'] for e in hits)
        sources[phase] = set(counts)
        phases[label] = {
            'marked': phase in marked, 'events': len(selected), 'positive_events': len(hits),
            'unresolved_sources': sum(not resolved(e, 'source') for e in hits),
            'unresolved_targets': sum(not resolved(e, 'target') for e in hits),
            'sources': [{'id': source, 'hits': counts[source],
                         'amount_sum_candidate': sum(e['amount'] for e in hits if e['source_id'] == source)}
                        for source in sorted(counts)],
        }
    ready = any(r.get('type') == 'hooks' and r.get('ready') is True for r in records)
    truncated = any(r.get('type') == 'limit' for r in records)
    enough = all(phases[PHASES[p]]['marked'] and phases[PHASES[p]]['positive_events'] >= 3 and
                 phases[PHASES[p]]['unresolved_sources'] == phases[PHASES[p]]['unresolved_targets'] == 0
                 for p in [1, 2, 3])
    consistent = (ready and not truncated and enough and len(sources[1]) == len(sources[2]) == 1 and
                  sources[1].isdisjoint(sources[2]) and sources[3] == sources[1])
    checks = []
    for sequence, observed in (expected or {}).items():
        if type(sequence) is not int or sequence <= 0 or not math.isfinite(observed) or observed <= 0:
            raise ValueError('Expected hits need positive sequence numbers and finite positive amounts')
        event = indexed.get(sequence)
        amount = event.get('amount') if event else None
        checks.append({'sequence': sequence, 'observed': observed, 'captured': amount,
                       'matches_display_rounding': bool(event and positive(event) and
                           math.isclose(amount, observed, rel_tol=1e-6, abs_tol=0.51))})
    return {'hooks_ready': ready, 'capture_truncated': truncated, 'events': len(events),
            'phases': phases, 'attribution_check': 'consistent' if consistent else 'inconclusive',
            'amount_checks': checks, 'coverage_verified': False,
            'limitations': 'Display-event candidates only. Phase labels are operator expectations. '
                           'Source consistency does not establish agent config IDs, summon ownership, '
                           'anomaly ownership, effective HP loss or complete damage coverage.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--expect-hit', action='append', default=[], metavar='SEQUENCE=AMOUNT',
                        help='Compare a captured hit with a manually observed, unmerged damage number')
    args = parser.parse_args()
    records = [json.loads(line) for line in args.capture.read_text().splitlines() if line.strip()]
    expected = {}
    for item in args.expect_hit:
        sequence, amount = item.split('=', 1)
        sequence = int(sequence)
        if sequence in expected:
            raise ValueError('Duplicate expected hit')
        expected[sequence] = float(amount)
    print(json.dumps(summarize(records, expected), indent=2, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError) as error:
        sys.exit(f'ZZZ damage report: {error}')
