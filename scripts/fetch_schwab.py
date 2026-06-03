#!/usr/bin/env python3
"""Refresh access token, pull Schwab account, write a SCRUBBED data.json.
Reads creds from env (GitHub Action) or local files (Mac test)."""
import os, json, base64, time, urllib.parse, urllib.request, urllib.error

def load_local():
    sec={}
    p=os.path.expanduser('~/.config/clydesdale/secrets.env')
    if os.path.exists(p):
        for ln in open(p):
            ln=ln.strip()
            if '=' in ln and not ln.startswith('#'):
                k,v=ln.split('=',1); sec[k]=v
    tp=os.path.expanduser('~/.config/clydesdale/token.json')
    rt=None
    if os.path.exists(tp): rt=json.load(open(tp)).get('refresh_token')
    return sec.get('SCHWAB_APP_KEY'), sec.get('SCHWAB_APP_SECRET'), rt

KEY=os.environ.get('SCHWAB_APP_KEY'); SECRET=os.environ.get('SCHWAB_APP_SECRET'); RT=os.environ.get('SCHWAB_REFRESH_TOKEN')
if not (KEY and SECRET and RT):
    lk,ls,lr=load_local(); KEY=KEY or lk; SECRET=SECRET or ls; RT=RT or lr
if not (KEY and SECRET and RT):
    raise SystemExit('Missing credentials')

auth=base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
def post(data):
    req=urllib.request.Request('https://api.schwabapi.com/v1/oauth/token',
        data=urllib.parse.urlencode(data).encode(),
        headers={'Authorization':f'Basic {auth}','Content-Type':'application/x-www-form-urlencoded','Accept-Encoding':'identity'})
    return json.load(urllib.request.urlopen(req))

try:
    tok=post({'grant_type':'refresh_token','refresh_token':RT})
except urllib.error.HTTPError as e:
    raise SystemExit('REFRESH_FAILED %d %s -- (refresh token likely expired; run Reconnect)' % (e.code, e.read().decode('utf-8','replace')))
at=tok['access_token']

req=urllib.request.Request('https://api.schwabapi.com/trader/v1/accounts?fields=positions',
    headers={'Authorization':'Bearer '+at,'Accept-Encoding':'identity'})
accts=json.load(urllib.request.urlopen(req))

def num(x):
    try: return round(float(x),2)
    except (TypeError,ValueError): return None

positions=[]
total=cash=lmv=0.0
acct_type=None
for a in accts:
    sa=a.get('securitiesAccount',{})
    acct_type=sa.get('type')
    bal=sa.get('currentBalances',{})
    total += float(bal.get('liquidationValue') or 0)
    cash  += float(bal.get('cashBalance') or 0)
    lmv   += float(bal.get('longMarketValue') or 0)
    for p in sa.get('positions',[]):
        inst=p.get('instrument',{})
        qty=float(p.get('longQuantity') or 0) - float(p.get('shortQuantity') or 0)
        mv=float(p.get('marketValue') or 0)
        positions.append({
            'symbol': inst.get('symbol'),
            'description': inst.get('description'),
            'asset_type': inst.get('assetType'),
            'quantity': num(qty),
            'avg_price': num(p.get('averagePrice')),
            'price': num(mv/qty) if qty else None,
            'market_value': num(mv),
            'day_pl': num(p.get('currentDayProfitLoss')),
            'day_pl_pct': num(p.get('currentDayProfitLossPercentage')),
            'total_pl': num(p.get('longOpenProfitLoss')),
        })
positions.sort(key=lambda x:-(x['market_value'] or 0))
out={
    'updated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'account_type': acct_type,
    'total_value': round(total,2),
    'cash': round(cash,2),
    'long_market_value': round(lmv,2),
    'positions_count': len(positions),
    'positions': positions,
}
dest=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'data.json')
json.dump(out, open(dest,'w'), indent=2)
print('WROTE', dest, '| total=%.2f cash=%.2f positions=%d' % (total,cash,len(positions)))
