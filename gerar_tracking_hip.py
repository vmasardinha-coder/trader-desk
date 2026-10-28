"""Gera tracking_hipotetico_snapshot.json (28/10/2026): resultado do tracking hipotetico
guardado no repositorio. O servidor entrega este arquivo na hora quando o cache em memoria
esta frio (deploy/reinicio) e recalcula por tras -- assim o painel 'Aproveitamento realizado'
nunca fica indisponivel. Rodar de vez em quando: python3 gerar_tracking_hip.py"""
import json, os, sys, time, warnings
warnings.filterwarnings('ignore')
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import proxy
def _ler(n):
    try:
        return json.load(open(os.path.join(AQUI, n)))
    except Exception:
        return []
res = proxy._tracking_hip_calcular(_ler('analises.json'), _ler('analises_arquivo.json'))
res['snapshot_gerado_em'] = time.strftime('%Y-%m-%d %H:%M')
json.dump(res, open(os.path.join(AQUI, 'tracking_hipotetico_snapshot.json'), 'w'), ensure_ascii=False)
print('ok', res.get('total_avaliadas'), res['snapshot_gerado_em'])
