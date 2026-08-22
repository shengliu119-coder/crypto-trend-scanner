import concurrent.futures, json, math, os, statistics, time, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

NOW_MS = int(time.time() * 1000)
UA = {"User-Agent": "CodexTrendScanner/1.0"}\nOKX_BASES = ("https://www.okx.com", "https://app.okx.com")

def get_json(url, timeout=20):
    error=None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:
            error=exc
            if attempt<2: time.sleep(2**attempt)
    raise error

def okx_json(path):
    error=None
    for base in OKX_BASES:
        try:
            payload=get_json(base+path)
            if payload.get("code") != "0": raise RuntimeError(payload.get("msg") or payload.get("code"))
            return payload["data"]
        except Exception as exc: error=exc
    raise error

def ema(values, n):
    a = 2 / (n + 1); out = [values[0]]
    for v in values[1:]: out.append(a*v + (1-a)*out[-1])
    return out

def atr(rows, n=14):
    tr=[]
    for i,r in enumerate(rows):
        h,l,c=r[2],r[3],r[4]; pc=rows[i-1][4] if i else c
        tr.append(max(h-l, abs(h-pc), abs(l-pc)))
    return ema(tr,n)

def klines(symbol, interval, limit):
    bar="1Dutc" if interval=="1d" else "4H"
    q=urllib.parse.urlencode({"instId":symbol,"bar":bar,"limit":min(limit,300)})
    raw=okx_json("/api/v5/market/candles?"+q)
    span=86400000 if interval=="1d" else 14400000
    rows=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5]),int(x[0])+span-1] for x in raw if x[8]=="1"]
    return sorted(rows,key=lambda x:x[0])

STABLE={"usdt","usdc","dai","usde","fdusd","tusd","usds","pyusd","usdd","frax","susds","usdtb","usdx","rlusd","gusd","lusd","crvusd"}
WRAP_WORDS=("wrapped ","bridged ","staked ","restaked ")

def universe():
    coins=[]
    for page in (1,2):
        q=urllib.parse.urlencode({"vs_currency":"usd","order":"market_cap_desc","per_page":250,"page":page,"sparkline":"false"})
        coins += get_json("https://api.coingecko.com/api/v3/coins/markets?"+q)
    out=[]
    for c in coins[:300]:
        name=c["name"].lower(); sym=c["symbol"].lower()
        if sym in STABLE or any(name.startswith(w) for w in WRAP_WORDS): continue
        out.append(c)
    return out

def scan_one(item, symbols):
    c=item; pair=c["symbol"].upper()+"-USDT"
    if pair not in symbols: return {"status":"no_pair"}
    try:
        h4=klines(pair,"4h",140); d1=klines(pair,"1d",140)
        if len(h4)<80 or len(d1)<80: return {"status":"short"}
        dc=[r[4] for r in d1]; e24=ema(dc,24); e52=ema(dc,52)
        trend=(dc[-1]>e24[-1]>e52[-1] and e52[-1]>e52[-6]) or (dc[-1]>e52[-1] and e52[-1]>=e52[-10]*0.995)
        last=h4[-1]; prior=h4[:-1]; ac=atr(h4); vol20=statistics.mean(r[5] for r in prior[-20:]); vr=last[5]/vol20 if vol20 else 0
        loc=(last[4]-last[3])/(last[2]-last[3]) if last[2]>last[3] else 0
        best=None
        for w in (10,15,20,30,40):
            base=prior[-w:]; level=max(r[2] for r in base); base_low=min(r[3] for r in base)
            width=(level-base_low)/level
            contract=statistics.mean(atr(prior)[-14:]) < statistics.mean(atr(prior)[-42:-14])
            broke=last[4]>level
            stop=max(base_low, min(r[3] for r in prior[-10:]))
            risk=(last[4]-stop)/last[4]
            old_highs=[r[2] for r in d1[-120:-1] if r[2]>last[4]]
            resistance=min(old_highs) if old_highs else max(last[4]+3*(last[4]-stop), last[2])
            rr=(resistance-last[4])/(last[4]-stop) if last[4]>stop else 0
            ok=trend and broke and vr>=1.5 and loc>=0.7 and risk<=0.08 and rr>=2 and width<=0.22 and contract
            score=(20 if trend else 0)+(20 if broke else 0)+min(20,vr/1.5*15)+(15 if loc>=.7 else 5)+(15 if contract else 0)+(10 if rr>=2 else 0)
            cand={"signalType":"breakout","window":w,"breakout":level,"stop":stop,"riskPct":risk*100,"resistance":resistance,"rr":rr,"volumeMultiple":vr,"closeLocation":loc,"contract":contract,"score":round(score,1),"ok":ok}
            if best is None or (cand["ok"],cand["score"])>(best["ok"],best["score"]): best=cand
        # First pullback after a qualified breakout in one of the prior six closed bars.
        for j in range(max(25, len(h4)-7), len(h4)-1):
            hist=h4[:j]; base=hist[-20:]; level=max(r[2] for r in base)
            b=h4[j]; bvol=statistics.mean(r[5] for r in hist[-20:]); bloc=(b[4]-b[3])/(b[2]-b[3]) if b[2]>b[3] else 0
            qualified=b[4]>level and b[5]>=1.5*bvol and bloc>=0.7
            touched=last[3]<=level*1.03 and last[4]>=level and last[4]>last[1]
            quiet=last[5]<b[5]
            stop=min(r[3] for r in h4[j+1:]) if h4[j+1:] else last[3]
            risk=(last[4]-stop)/last[4] if last[4]>stop else 1
            old_highs=[r[2] for r in d1[-120:-5] if r[2]>last[4]]
            resistance=min(old_highs) if old_highs else last[4]+3*(last[4]-stop)
            rr=(resistance-last[4])/(last[4]-stop) if last[4]>stop else 0
            ok=trend and qualified and touched and quiet and risk<=0.08 and rr>=2
            score=(25 if trend else 0)+(25 if qualified else 0)+(15 if touched else 0)+(10 if quiet else 0)+(15 if risk<=.08 else 0)+(10 if rr>=2 else 0)
            cand={"signalType":"first_pullback","window":20,"breakout":level,"stop":stop,"riskPct":risk*100,"resistance":resistance,"rr":rr,"volumeMultiple":b[5]/bvol if bvol else 0,"closeLocation":bloc,"contract":quiet,"score":round(score,1),"ok":ok}
            if (cand["ok"],cand["score"])>(best["ok"],best["score"]): best=cand
        return {"status":"ok","id":c["id"],"name":c["name"],"symbol":c["symbol"].upper(),"rank":c.get("market_cap_rank"),"price":last[4],"closeTime":datetime.fromtimestamp(last[6]/1000,timezone.utc).isoformat(),"trend":trend,"metrics":best}
    except Exception as e: return {"status":"error","error":type(e).__name__}

def main():
    uni=universe(); info=okx_json("/api/v5/public/instruments?instType=SPOT")
    symbols={x["instId"] for x in info if x.get("state")=="live" and x.get("quoteCcy")=="USDT"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        results=list(ex.map(lambda x:scan_one(x,symbols),uni))
    covered=[x for x in results if x.get("status")=="ok"]
    hits=sorted([x for x in covered if x["metrics"]["ok"]],key=lambda x:x["metrics"]["score"],reverse=True)
    near=sorted([x for x in covered if not x["metrics"]["ok"] and x["metrics"]["score"]>=65],key=lambda x:x["metrics"]["score"],reverse=True)[:5]
    btc=next((x for x in covered if x.get("id")=="bitcoin"),None)
    report={"generatedAt":datetime.now(timezone.utc).isoformat(),"top300Raw":300,"filteredUniverse":len(uni),"covered":len(covered),"btc":btc,"hits":hits[:10],"near":near,"statusCounts":{s:sum(1 for x in results if x.get("status")==s) for s in {x.get("status") for x in results}}}
    Path("latest_results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    state_path=Path("state.json")
    state=json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"sent":[]}
    sent=set(state.get("sent",[])); fresh=[]; fresh_keys=[]
    for x in report["hits"]:
        m=x["metrics"]; key=f'{x["symbol"]}:{m["signalType"]}:{m["breakout"]:.12g}'
        if key not in sent: fresh.append(x); fresh_keys.append(key)
    hook=os.getenv("FEISHU_TREND_WEBHOOK","").strip()
    if fresh and hook:
        lines=[f'加密趋势扫描｜{report["generatedAt"]}',f'新增信号 {len(fresh)} 个：']
        for x in fresh:
            m=x["metrics"]; grade="A" if m["score"]>=90 else "B"
            lines.append(f'{grade} {x["symbol"]}（市值#{x["rank"]}） {m["signalType"]}｜收盘 {x["price"]:.8g}｜突破 {m["breakout"]:.8g}｜失效 {m["stop"]:.8g}｜风险 {m["riskPct"]:.1f}%｜阻力 {m["resistance"]:.8g}｜R {m["rr"]:.1f}｜量 {m["volumeMultiple"]:.1f}x')
        payload=json.dumps({"msg_type":"text","content":{"text":"\n".join(lines)}},ensure_ascii=False).encode("utf-8")
        req=urllib.request.Request(hook,data=payload,headers={"Content-Type":"application/json; charset=utf-8"},method="POST")
        with urllib.request.urlopen(req,timeout=20) as resp:
            body=json.load(resp)
        if body.get("code")!=0: raise RuntimeError(f'Feishu rejected message: {body.get("code")} {body.get("msg")}')
        sent.update(fresh_keys)
    elif fresh and not hook:
        print("WARNING: fresh signals found but FEISHU_TREND_WEBHOOK is not configured")
    state_path.write_text(json.dumps({"sent":list(sent)[-500:]},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__": main()

