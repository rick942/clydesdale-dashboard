#!/usr/bin/env python3
import os,sys,json,base64,time,subprocess,webbrowser,urllib.parse,urllib.request,urllib.error
CFG=os.path.expanduser('~/.config/clydesdale')
sec={}
for ln in open(os.path.join(CFG,'secrets.env')):
    ln=ln.strip()
    if '=' in ln and not ln.startswith('#'): k,v=ln.split('=',1); sec[k]=v
KEY,SECRET=sec['SCHWAB_APP_KEY'],sec['SCHWAB_APP_SECRET']
url='https://api.schwabapi.com/v1/oauth/authorize?client_id=%s&redirect_uri=https://127.0.0.1'%KEY
print('\n=== Clydesdale Capital — weekly reconnect ===\n')
print('Opening the Schwab login in your browser...')
try: webbrowser.open(url)
except Exception: pass
print('\nIf it did not open, paste this link into your browser:\n'+url)
print('\nLog in + approve. Your browser will show a "site cannot be reached" page — that is normal.')
redir=input('\nPaste the FULL https://127.0.0.1/... address from the bar, then Enter:\n> ').strip()
try: code=urllib.parse.parse_qs(urllib.parse.urlparse(redir).query)['code'][0]
except Exception: print('\nThat did not look like the right URL. Run this again.'); input('Press Enter to close.'); sys.exit(1)
auth=base64.b64encode(('%s:%s'%(KEY,SECRET)).encode()).decode()
body=urllib.parse.urlencode({'grant_type':'authorization_code','code':code,'redirect_uri':'https://127.0.0.1'}).encode()
req=urllib.request.Request('https://api.schwabapi.com/v1/oauth/token',data=body,headers={'Authorization':'Basic '+auth,'Content-Type':'application/x-www-form-urlencoded','Accept-Encoding':'identity'})
try: tok=json.load(urllib.request.urlopen(req))
except urllib.error.HTTPError as e:
    print('\nThat code expired or failed (%d). Just run this again.'%e.code); input('Press Enter to close.'); sys.exit(1)
tok['_obtained_at']=int(time.time())
tp=os.path.join(CFG,'token.json'); json.dump(tok,open(tp,'w')); os.chmod(tp,0o600)
r=subprocess.run(['gh','secret','set','SCHWAB_REFRESH_TOKEN','--repo','rick942/clydesdale-dashboard','--body',tok['refresh_token']],capture_output=True,text=True)
print('GitHub vault updated.' if r.returncode==0 else ('WARN updating vault: '+r.stderr))
subprocess.run(['gh','workflow','run','update.yml','--repo','rick942/clydesdale-dashboard'],capture_output=True,text=True)
print('\n  Reconnected! Dashboard refreshes within a minute. Good for another 7 days.')
input('\nPress Enter to close.')
