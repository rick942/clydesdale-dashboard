#!/usr/bin/env python3
"""Price the club watchlist -> watchlist.json.

Reads the picks from Supabase (public view, anon key - read only), quotes each
ticker, and writes watchlist.json for the dashboard to render.

Deliberately independent of the Schwab feed: that token expires weekly, and the
watchlist should not die every time it does. Equally, this script must never be
able to break the holdings feed - it runs as its own job and exits 0 on any
failure, leaving the previous watchlist.json in place.

Entry prices are captured once, on the first run after a pick is added, and then
carried forward untouched so the "since you added it" number cannot drift.
"""
import json, os, re, sys, time, urllib.request, urllib.error

SB_URL = 'https://nvhsvcesvkudgttmbpvg.supabase.co'
OUT = 'watchlist.json'
UA = 'Mozilla/5.0 (compatible; clydesdale-dashboard/1.0)'


def anon_key():
    """Single source of truth: the key the page already ships with."""
    key = os.environ.get('SUPABASE_ANON_KEY')
    if key:
        return key
    with open('index.html', encoding='utf-8') as f:
        m = re.search(r"const SB_KEY='([^']+)'", f.read())
    if not m:
        raise SystemExit('anon key not found in index.html')
    return m.group(1)


def get_json(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def quote(ticker):
    """Last price for a ticker, or None. Never raises."""
    sym = urllib.parse.quote(ticker.replace('/', '-'))
    url = ('https://query1.finance.yahoo.com/v8/finance/chart/'
           f'{sym}?interval=1d&range=1d')
    try:
        d = get_json(url, {'User-Agent': UA})
        res = (d.get('chart') or {}).get('result') or []
        if not res:
            return None
        meta = res[0].get('meta') or {}
        px = meta.get('regularMarketPrice')
        return round(float(px), 4) if px is not None else None
    except Exception as e:
        print(f'  {ticker}: quote failed ({type(e).__name__})')
        return None


def main():
    import urllib.parse  # noqa: F401  (used by quote())
    key = anon_key()
    hdr = {'apikey': key, 'Authorization': 'Bearer ' + key}
    picks = get_json(f'{SB_URL}/rest/v1/watchlist_public?select=id,ticker,note,added_at,name', hdr)
    print(f'{len(picks)} pick(s) on the watchlist')

    prev = {}
    if os.path.exists(OUT):
        try:
            for it in json.load(open(OUT)).get('items', []):
                prev[it['id']] = it
        except Exception:
            pass  # corrupt or first run; rebuild from scratch

    # One quote per distinct ticker, however many members picked it.
    prices = {t: quote(t) for t in sorted({p['ticker'] for p in picks})}

    items, now = [], time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    for p in picks:
        old = prev.get(p['id'], {})
        last = prices.get(p['ticker'])
        entry = old.get('entryPrice')
        entry_at = old.get('entryAt')
        if entry is None and last is not None:   # first pricing of a new pick
            entry, entry_at = last, now
        pct = None
        if entry and last is not None and entry > 0:
            pct = round((last - entry) / entry * 100, 2)
        items.append({
            'id': p['id'], 'ticker': p['ticker'], 'name': p['name'],
            'note': p['note'], 'addedAt': p['added_at'],
            'entryPrice': entry, 'entryAt': entry_at,
            'lastPrice': last if last is not None else old.get('lastPrice'),
            'pct': pct,
        })

    items.sort(key=lambda i: (i['pct'] is None, -(i['pct'] or 0)))
    json.dump({'updated': now, 'items': items}, open(OUT, 'w'), indent=1)
    priced = sum(1 for i in items if i['pct'] is not None)
    print(f'WROTE {OUT} | {len(items)} pick(s), {priced} priced')


if __name__ == '__main__':
    import urllib.parse
    try:
        main()
    except Exception as e:
        # Never fail the workflow: a broken watchlist must not look like a broken club.
        print(f'watchlist update skipped: {type(e).__name__}: {e}')
        sys.exit(0)
