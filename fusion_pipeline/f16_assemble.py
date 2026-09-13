"""Alles in data.json zusammenfuehren: Achsen, Tragfaehigkeit, Hebel, Schweigen-Tests."""
import json, numpy as np, pandas as pd
from pathlib import Path
T=Path('team'); OUT=Path('team_out'); D=json.loads(Path('dashboard/data.json').read_text())
d=pd.read_parquet(T/'dataset_long.parquet'); M=json.loads((T/'metrics.json').read_text())
w=d.dropna(subset=['value']).sort_values('year').drop_duplicates(['ticker','metric'],keep='last')
piv=w.pivot(index='ticker',columns='metric',values='value').apply(pd.to_numeric,errors='coerce')
sec=d.drop_duplicates('ticker').set_index('ticker').gics_sector

# --- Tragfaehigkeit
V=pd.read_csv(OUT/'axis_viability.csv').set_index('ticker')
lvl={'tragfaehig':'tragfähig','angespannt':'angespannt','gefaehrdet':'gefährdet','nicht bewertbar':'nicht bewertbar'}
D['axes']['V']='Tragfähigkeit'; n=0
for f in D['firms']:
    t=f['ticker']
    if t in V.index and V.loc[t,'level']!='nicht bewertbar':
        r=V.loc[t]; f['viability']=dict(level=lvl[r['level']],index=float(r['index']),weakest=str(r['weakest_dim']),provisional=True); n+=1
    else: f['viability']=dict(level='nicht bewertbar',index=None,weakest=None,provisional=True)
D['n_viability']=n
C=pd.read_csv(OUT/'axis_correlation_5.csv',index_col=0); D['axis_corr']={}
for i,a in enumerate(C.columns):
    for b in list(C.columns)[i+1:]: D['axis_corr'][f'{a} vs {b}']=float(C.loc[a,b])
D['resistance']=pd.read_csv(OUT/'manipulationsresistenz.csv').to_dict('records')
D['viability_note']=("Vorläufig: aus einem Geschäftsjahr rekonstruiert. Die volle Fassung stresst gegen das eigene "
  "schlechteste Jahr aus zehn Jahren Historie. Unser Nachbau korreliert mit ρ = 0,52 zur Gewinnmarge, die volle "
  "Fassung mit 0,12 — er belohnt also noch Profit. Wird ersetzt, sobald die Historie vorliegt.")

# --- Hebel
CORE={'A':('co2_intensity','CO₂-Intensität','t CO₂ je Mio. USD Umsatz'),'S':('dart_rate','Unfallrate','Unfälle je 100 Vollzeitkräfte'),
      'G':('echo_nc_quarters_per_site','Verstoßquartale je Anlage','Quartale'),'B':('sbti_validated','SBTi-geprüftes Ziel','ja/nein')}
def lever(t,ax):
    m,label,unit=CORE[ax]
    if m not in piv or pd.isna(piv.at[t,m]): return None
    peers=piv.loc[sec[sec==sec[t]].index,m].dropna()
    if len(peers)<5: return None
    v=float(piv.at[t,m]); lower=M[m]['direction']<0; thr=float(peers.quantile(0.333 if lower else 0.667))
    if m=='sbti_validated': return dict(text=('hat ein geprüftes Klimaziel' if v>=1 else 'ein wissenschaftlich geprüftes Klimaziel setzen'),already=bool(v>=1))
    if (v<=thr) if lower else (v>=thr): return dict(text=f'liegt bereits im oberen Drittel ({label})',already=True)
    pct=abs(v-thr)/abs(v)*100 if v else 0
    return dict(text=f'{label} um {round(pct)} % {"senken" if lower else "anheben"} (von {round(v,2)} auf {round(thr,2)} {unit})',already=False)
hist=d.dropna(subset=['value']); yp=hist.groupby(['ticker','metric']).year.agg(['min','max']); ly=hist.groupby('metric').year.max()
for f in D['firms']:
    t=f['ticker']; f['levers']={ax:lever(t,ax) for ax in ['A','S','G','B'] if ax in f['axes']}; f['levers']={k:v for k,v in f['levers'].items() if v}
    ret=[]
    if t in yp.index.get_level_values(0):
        for m,(mn,mx) in yp.loc[t].iterrows():
            if m in M and M[m]['axis'] in 'ASGB' and M[m]['source_id']!='eigene_berechnung' and (ly[m]-mx)>=2:
                ret.append(dict(metric=M[m]['label'],last=int(mx)))
    f['retreat']=ret

# --- Schweigen-Tests
R=pd.read_csv(OUT/'silence_test.csv'); S=pd.read_csv(OUT/'silence_cost.csv').set_index('ticker')
D['silence_test']=R.to_dict('records')
for f in D['firms']:
    t=f['ticker']
    f['silence_cost']=float(S.loc[t,'spanne_durch_schweigen']) if t in S.index else None
D['silence_summary']=dict(n_tests=len(R), n_sig=int((R.p<0.05).sum()), n_worse=int(((R.p<0.05)&(R.differenz<0)).sum()),
    median_cost=float(S.spanne_durch_schweigen.median()), n_firms=len(S))
Path('dashboard/data.json').write_text(json.dumps(D,ensure_ascii=False))
print('assembled | viability',n,'| silence tests',len(R),'| firms with silence cost',len(S))
