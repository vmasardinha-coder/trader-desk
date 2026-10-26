"""Gera pior_dia_10a.json: maior queda em 1 pregao (fechamento a fechamento) de cada papel,
ate 10 anos de historico (Yahoo). Backlog #38 (26/10/2026). Rodar de tempos em tempos:
    python3 gerar_pior_dia.py
Somente % -- nenhum valor em R$."""
import json, requests, datetime, concurrent.futures as cf
H = {'User-Agent': 'Mozilla/5.0'}

def tickers():
    ts = set()
    try:
        for a in json.load(open('analises.json')):
            if isinstance(a, dict) and a.get('ticker'): ts.add(a['ticker'])
    except Exception: pass
    try:
        d = json.load(open('positions.json'))
        for a in d.get('ativas', []) + d.get('encerradas', []):
            if a.get('ticker'): ts.add(a['ticker'])
    except Exception: pass
    try:
        pb = json.load(open('papeis_br.json'))
        it = pb.values() if isinstance(pb, dict) else pb
        for p in it:
            t = p.get('ticker') if isinstance(p, dict) else None
            if t: ts.add(t)
    except Exception: pass
    return sorted(t if t.endswith('.SA') else t + '.SA' for t in ts)

def pior(t):
    try:
        j = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1d&range=10y',
                         headers=H, timeout=25).json()['chart']['result'][0]
        ts = j['timestamp']; c = j['indicators']['quote'][0]['close']
        s = [(datetime.datetime.fromtimestamp(a, datetime.timezone(datetime.timedelta(hours=-3))).strftime('%Y-%m-%d'), b)
             for a, b in zip(ts, c) if b]
        if len(s) < 60: return t, None
        r = [(s[i][0], s[i][1] / s[i - 1][1] - 1) for i in range(1, len(s))]
        d, v = min(r, key=lambda x: x[1])
        return t, {'pior_dia_pct': round(v * 100, 1), 'data': d, 'anos': round(len(s) / 252, 1)}
    except Exception:
        return t, None

if __name__ == '__main__':
    out = {}
    with cf.ThreadPoolExecutor(8) as ex:
        for t, r in ex.map(pior, tickers()):
            if r: out[t] = r
    json.dump({'gerado_em': datetime.date.today().isoformat(), 'papeis': out}, open('pior_dia_10a.json', 'w'),
              ensure_ascii=False, indent=1)
    print(len(out), 'papeis')
