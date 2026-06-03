#!/usr/bin/env python3
"""Pull Schwab account -> build dashboard-shaped data -> ENCRYPT -> data.enc.json.
Creds + passcode from env (GitHub Action) or ~/.config/clydesdale (local)."""
import os, json, base64, time, hashlib, urllib.parse, urllib.request, urllib.error

def load_local():
    sec={}; p=os.path.expanduser('~/.config/clydesdale/secrets.env')
    if os.path.exists(p):
        for ln in open(p):
            ln=ln.strip()
            if '=' in ln and not ln.startswith('#'): k,v=ln.split('=',1); sec[k]=v
    tp=os.path.expanduser('~/.config/clydesdale/token.json'); rt=None
    if os.path.exists(tp): rt=json.load(open(tp)).get('refresh_token')
    return sec, rt

env=os.environ
sec,localrt=load_local()
KEY=env.get('SCHWAB_APP_KEY') or sec.get('SCHWAB_APP_KEY')
SECRET=env.get('SCHWAB_APP_SECRET') or sec.get('SCHWAB_APP_SECRET')
RT=env.get('SCHWAB_REFRESH_TOKEN') or localrt
PASS=env.get('CLUB_PASSCODE') or sec.get('CLUB_PASSCODE')
if not (KEY and SECRET and RT): raise SystemExit('Missing Schwab credentials')

auth=base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
def token_post(data):
    req=urllib.request.Request('https://api.schwabapi.com/v1/oauth/token',
        data=urllib.parse.urlencode(data).encode(),
        headers={'Authorization':f'Basic {auth}','Content-Type':'application/x-www-form-urlencoded','Accept-Encoding':'identity'})
    return json.load(urllib.request.urlopen(req))
try:
    tok=token_post({'grant_type':'refresh_token','refresh_token':RT})
except urllib.error.HTTPError as e:
    raise SystemExit('REFRESH_FAILED %d %s (run the weekly Reconnect)'%(e.code,e.read().decode('utf-8','replace')))

req=urllib.request.Request('https://api.schwabapi.com/trader/v1/accounts?fields=positions',
    headers={'Authorization':'Bearer '+tok['access_token'],'Accept-Encoding':'identity'})
accts=json.load(urllib.request.urlopen(req))

ETF={'SPY','VOO','VTI','QQQ','QQQM','SCHD','SCHG','SCHB','SCHX','PAVE','XLK','XLF','XLE','XLV','XLY','XLI','XLP','XLU','XLB','XLRE','IWM','DIA','VUG','VTV','VIG','VYM','VGT','SMH','SOXX','ARKK','JEPI','JEPQ','IVV','VXUS','VEA','VWO','BND','AGG','TLT','GLD','SLV','EEM','EFA','RSP','MGK','COWZ','VOOG','IJR','IJH','VB','VO','MOAT','QUAL','USMV','DGRO','SCHF','VT','BRKB'}

def r2(x):
    try: return round(float(x),2)
    except (TypeError,ValueError): return 0.0

holdings=[]; mv_total=cb_total=day_total=0.0; cash=0.0; acct_type=None
for a in accts:
    sa=a.get('securitiesAccount',{}); acct_type=sa.get('type')
    cash += float(sa.get('currentBalances',{}).get('cashBalance') or 0)
    for p in sa.get('positions',[]):
        inst=p.get('instrument',{}); sym=inst.get('symbol') or '?'
        qty=float(p.get('longQuantity') or 0)-float(p.get('shortQuantity') or 0)
        mv=float(p.get('marketValue') or 0)
        avg=float(p.get('averagePrice') or 0)
        cb=avg*qty
        gl=float(p.get('longOpenProfitLoss') or (mv-cb))
        atype=inst.get('assetType','')
        is_etf = sym in ETF or atype in ('COLLECTIVE_INVESTMENT','MUTUAL_FUND')
        holdings.append({
            'symbol':sym,'qty':r2(qty),'price':r2(mv/qty) if qty else 0.0,'mktVal':r2(mv),
            'dayPct':r2(p.get('currentDayProfitLossPercentage')),
            'costBasis':r2(cb),'glDollar':r2(gl),'glPct':r2(gl/cb*100) if cb else 0.0,
            'weight':0.0,'type':'ETF' if is_etf else 'Equity','tag':'Delisted' if mv==0 else ''})
        mv_total+=mv; cb_total+=cb; day_total+=float(p.get('currentDayProfitLoss') or 0)

total=mv_total+cash
for h in holdings: h['weight']=r2(h['mktVal']/total*100) if total else 0.0
holdings.sort(key=lambda x:-x['mktVal'])
eq=sum(h['mktVal'] for h in holdings if h['type']=='Equity')
ef=sum(h['mktVal'] for h in holdings if h['type']=='ETF')
alloc=[]
if eq>0: alloc.append({'label':'Equities','value':r2(eq),'pct':r2(eq/total*100)})
if ef>0: alloc.append({'label':'ETFs / CEFs','value':r2(ef),'pct':r2(ef/total*100)})
alloc.append({'label':'Cash','value':r2(cash),'pct':r2(cash/total*100)})
et=time.gmtime(time.time()-4*3600)  # EDT
DATA={'asOf':time.strftime('%b %-d, %Y %-I:%M %p ET',et),'totalValue':r2(total),
      'marketValue':r2(mv_total),'cash':r2(cash),'costBasis':r2(cb_total),
      'dayChange':r2(day_total),'dayChangePct':r2(day_total/total*100) if total else 0.0,
      'totalGain':r2(mv_total-cb_total),'totalGainPct':r2((mv_total-cb_total)/cb_total*100) if cb_total else 0.0,
      'alloc':alloc,'holdings':holdings}
plaintext=json.dumps(DATA,separators=(',',':')).encode()

if PASS:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    norm=PASS.strip().lower().encode(); salt=os.urandom(16); iters=200000
    keyb=hashlib.pbkdf2_hmac('sha256',norm,salt,iters,32); iv=os.urandom(12)
    ct=AESGCM(keyb).encrypt(iv,plaintext,None)
    enc={'v':1,'iter':iters,'salt':base64.b64encode(salt).decode(),
         'iv':base64.b64encode(iv).decode(),'ct':base64.b64encode(ct).decode()}
    json.dump(enc,open('data.enc.json','w'))
    # roundtrip self-test
    k2=hashlib.pbkdf2_hmac('sha256',norm,salt,iters,32)
    assert json.loads(AESGCM(k2).decrypt(iv,ct,None))['totalValue']==DATA['totalValue']
    print('WROTE data.enc.json (encrypted) | total=%.2f cash=%.2f holdings=%d | roundtrip OK'%(total,cash,len(holdings)))
else:
    json.dump(DATA,open('data.json','w'),indent=2)
    print('WROTE data.json (PLAINTEXT - no passcode set) | total=%.2f holdings=%d'%(total,len(holdings)))
