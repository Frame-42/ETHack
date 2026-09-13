"""Exercise the executable workflow on synthetic cached data; never touch shipped outputs."""
import contextlib,importlib,io,json,pkgutil,runpy,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np,pandas as pd
REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
import pipeline
for info in pkgutil.walk_packages(pipeline.__path__,'pipeline.'):
 importlib.import_module(info.name)
from pipeline.scoring import montecarlo
original_cfg=montecarlo.MonteCarloConfig

def fast_cfg(*args,**kwargs):
 kwargs['n_draws']=20
 return original_cfg(*args,**kwargs)

with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);raw=root/'data/raw';out=root/'data/out';raw.mkdir(parents=True);out.mkdir()
 for name,module in list(sys.modules.items()):
  if name.startswith('pipeline'):
   for key,value in [('ROOT',root),('RAW',raw),('OUT',out),('DATA',root/'data')]:
    if hasattr(module,key):setattr(module,key,value)
 master=pd.DataFrame([{'ticker':f'T{i:02}','company':f'Synthetic Plant {i:02}','cik':i+1,'gics_sector':'Utilities','gics_sub_industry':'Electric Utilities'} for i in range(12)])
 master.to_parquet(raw/'sp500_master.parquet',index=False)
 master.rename(columns={'ticker':'Symbol','company':'Security','cik':'CIK','gics_sector':'GICS Sector','gics_sub_industry':'GICS Sub-Industry'}).to_csv(root/'constituents.csv',index=False)
 fac=[];emi=[];rev=[]
 for i,r in master.iterrows():
  for year in range(2018,2026):
   fac.append(dict(facility_id=i+100,year=year,parent_company=r.company,frs_id=str(i+100),facility_types='Direct'))
   emi.append(dict(facility_id=i+100,year=year,scope1_t=(i+1)*100*(1+.01*i)**(year-2018),supplied_t=0))
   rev.append(dict(cik=r.cik,year=year,revenue_musd=100+i+year-2018))
 pd.DataFrame(fac).to_parquet(raw/'epa_facility.parquet',index=False)
 pd.DataFrame(emi).to_parquet(raw/'epa_emission.parquet',index=False)
 pd.DataFrame(rev).to_parquet(raw/'sec_revenue.parquet',index=False)
 pd.DataFrame({'ticker':master.ticker,'esg_risk_total':np.arange(12)+10,'esg_risk_env':np.arange(12)+3}).to_parquet(raw/'esg_snapshot.parquet',index=False)
 pd.DataFrame({'plant_name':master.company,'operator_name':master.company,'utility_name':master.company,'co2_t':np.arange(12)+100,'net_generation_mwh':np.arange(12)+200,'year':2022}).to_parquet(raw/'egrid_plant.parquet',index=False)
 pd.DataFrame({'standard_parent_co_name':master.company,'total_releases':np.arange(12)+1,'carcinogen':'N','frs_id':np.arange(12)+100}).to_parquet(raw/'epa_tri.parquet',index=False)
 pd.DataFrame({'company_name':master.company,'establishment_name':master.company,'total_hours_worked':20000,'annual_average_employees':10,'total_dafw_cases':1,'total_djtr_cases':1,'total_deaths':0}).to_parquet(raw/'osha_ita.parquet',index=False)
 pd.DataFrame({'registry_id':np.arange(12)+100,'fac_3yr_compliance_history':'V___________','fac_compliance_status':'No violation','fac_total_penalties':100,'fac_inspection_count':1}).to_parquet(raw/'epa_echo.parquet',index=False)
 pd.DataFrame(columns=['legal_name','trade_nm','case_id','case_violtn_cnt','bw_atp_amt','ee_atp_cnt','cmp_assd']).to_parquet(raw/'dol_whd.parquet',index=False)
 with patch.object(montecarlo,'MonteCarloConfig',fast_cfg),patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected network call')):
  for name in ['02_analyze.py','03_aggregate.py','04_dataset.py','06_review.py','05_reliability.py']:
   capture=io.StringIO()
   with contextlib.redirect_stdout(capture):
    runpy.run_path(str(REPOSITORY / 'scripts' / name), run_name='__main__')
   print('PASS',name)
 data=pd.read_csv(out/'dataset_long.csv')
 assert set(data.loc[data.metric=='egrid_mwh','year'])=={2022},'eGRID year was relabeled'
 assert set(data.quality_status)<= {'ok','review','error'}
 assert len(pd.read_csv(out/'reliability.csv'))==12
 assert not (root/'web').exists() and not (root/'report').exists()
 print('PASS complete synthetic workflow, correct eGRID year, no web/report side effects')
