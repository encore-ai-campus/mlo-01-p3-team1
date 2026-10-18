#!/usr/bin/env python3
"""Offline deterministic 96h estimate from an observed AWS Price List snapshot."""
import argparse,json,sys
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from project import account_budget_cap

def money(x):return str(x.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
def rate(snapshot,name,operation=None):
 values=next(x for x in snapshot['prices'] if x['name']==name)['rates']
 if operation:values=[r for r in values if r['attributes'].get('operation')==operation]
 if len(values)!=1:raise ValueError('Expected exactly one selected product rate: '+name)
 return Decimal(values[0]['usd'])
def estimate(c,snapshot):
 h=Decimal(str(c['budget']['duration_hours']));month=Decimal(730);rows=[];totals=[]
 for a in c['accounts']:
  if c['budget'].get('estimate_accepted') is True and any(n['instance_type'].startswith('t3.') and n.get('credit_mode')!='standard' for n in a['nodes']):
   raise ValueError('Selected T3 estimate requires explicit standard credit mode')
  ec2=sum(rate(snapshot,n['instance_type'])*h for n in a['nodes'])
  storage=sum(n['root_gib']+n['data_gib'] for n in a['nodes'])
  ebs=Decimal(storage)*rate(snapshot,'ebs_gp3')*h/month
  nat=rate(snapshot,'nat_hour')*h;ip=rate(snapshot,'ipv4')*h
  alb=rate(snapshot,'alb_hour','LoadBalancing:Application')*h if a['profile']=='encore1' else Decimal(0)
  alb_ip=rate(snapshot,'ipv4')*h*2 if a['profile']=='encore1' else Decimal(0)
  base=ec2+ebs+nat+ip+alb+alb_ip;cap=Decimal(str(account_budget_cap(c,a['profile'])))
  totals.append(base)
  rows.append({'profile':a['profile'],'node_count':len(a['nodes']),'ebs_gib':storage,'ec2_usd':money(ec2),'ebs_usd':money(ebs),
   'nat_usd':money(nat),'nat_ipv4_usd':money(ip),'alb_usd':money(alb),'alb_min_ipv4_usd':money(alb_ip),
   'base_usd':money(base),'cap_usd':money(cap),'remaining_before_variable_costs_usd':money(cap-base),'base_within_cap':base<=cap})
 return {'kind':'selected estimate' if c['budget'].get('estimate_accepted') is True else 'proposal estimate',
  'actual_bill_or_deployment_evidence':False,'duration_hours':int(h),'source':'AWS Price List Query API',
  'price_observed_at':snapshot['retrieved_at'],'monthly_proration_hours':int(month),'accounts':rows,
  'base_total_usd':money(sum(totals)),
  'total_cap_usd':c['budget']['total_usd_cap'],'variable_rates':{'nat_processing_usd_per_gb':str(rate(snapshot,'nat_gb')),
  'alb_lcu_usd_per_lcu_hour':str(rate(snapshot,'alb_lcu','LoadBalancing:Application'))},
  'excluded':['NAT processed bytes','cross-AZ peering/NAT traffic','Internet transfer','ALB LCU and additional public IPs','S3 storage/requests/version retention','CloudWatch logs','extra gp3 IOPS/throughput','tax','reinstallation overlap','other-account resources'],
  'assumptions':['All 14 EC2, 5 NAT and planned ALB retained for 96h','Standard On-Demand Linux x86_64, no credits/discounts','T3 CPU-credit Standard mode; exhaustion reduces CPU to baseline','EBS gp3 base 3000 IOPS/125 MiBps; storage prorated with 730h approximation','2 public IPv4 for a future ALB minimum estimate; scaling can add addresses','Not a billing cap enforcement or auto-destroy scheduler']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--pricing',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 result=estimate(json.loads(Path(a.config).read_text()),json.loads(Path(a.pricing).read_text()));Path(a.out).write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
