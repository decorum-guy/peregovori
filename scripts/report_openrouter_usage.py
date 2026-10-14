#!/usr/bin/env python3
"""Export content-free local OpenRouter accounting; makes no network/model calls."""
import argparse
import json
from pathlib import Path

from _demo import ROOT
from app.config import Settings
from app.usage import UsageLedger


def summarize(rows):
    result = {}
    for category in sorted({row['category'] for row in rows}):
        items = [row for row in rows if row['category'] == category]
        result[category] = {
            'requests': len(items), 'repeat_requests': sum(row['retry_index'] > 0 for row in items),
            'reported_cost_usd': round(sum(row['cost_usd'] for row in items if row['cost_usd'] is not None), 9),
            'cost_not_reported_requests': sum(row['cost_usd'] is None for row in items),
            'duration_seconds': round(sum(row['duration_seconds'] for row in items), 3),
        }
        for field in ('prompt_tokens', 'completion_tokens', 'reasoning_tokens', 'visible_output_tokens', 'total_tokens'):
            result[category][field + '_reported_sum'] = sum(row[field] for row in items if row[field] is not None)
            result[category][field + '_not_reported_requests'] = sum(row[field] is None for row in items)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', action='append', help='Limit export to specified session ID; repeat for multiple games')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    rows = UsageLedger(Settings.from_env().database_path).rows(args.session)
    result = {'categories': summarize(rows), 'reported_total_cost_usd': round(sum(row['cost_usd'] for row in rows if row['cost_usd'] is not None), 9),
              'cost_not_reported_requests': sum(row['cost_usd'] is None for row in rows), 'requests': rows}
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
