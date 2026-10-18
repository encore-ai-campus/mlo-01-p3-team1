"""Bounded local health/metric export; SQLite cache prevents duplicate terminal records.

The Filebeat registry/disk queue owns delivery; this writer fsyncs before committing its cache.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import urllib.request

BASE=Path('/var/lib/music-cluster/observability')
CONF=Path('/etc/music-cluster/observability')


def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()


def stamp(value):return datetime.datetime.fromisoformat(value.replace('Z','+00:00'))


def write(records,db):
    path=BASE/('events-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')+'.jsonl')
    accepted=[]
    for item in records:
        identity=item.get('event_id')
        digest=hashlib.sha256(json.dumps(item,sort_keys=True,default=str).encode()).hexdigest()
        if identity and db.execute('SELECT digest FROM sent WHERE id=?',(identity,)).fetchone()==(digest,):continue
        accepted.append((item,identity,digest))
    with path.open('a') as stream:
        for item,_,_ in accepted:stream.write(json.dumps(item,default=str,separators=(',',':'))+'\n')
        stream.flush();os.fsync(stream.fileno())
    for _,identity,digest in accepted:
        if identity:db.execute('INSERT OR REPLACE INTO sent VALUES (?,?)',(identity,digest))
    db.commit()


def weather(db):
    records=[]
    sources=[('collection',Path('/var/lib/music-cluster/control/weather/collector/requests.jsonl')),
             ('projection',Path('/var/lib/music-cluster/control/logs/weather-process.jsonl'))]
    for kind,path in sources:
        if not path.exists():continue
        inode=str(path.stat().st_ino)
        saved=db.execute('SELECT inode,offset FROM cursors WHERE path=?',(str(path),)).fetchone()
        offset=saved[1] if saved and saved[0]==inode and saved[1]<=path.stat().st_size else 0
        with path.open('rb') as stream:
            stream.seek(offset)
            for _ in range(10000):
                line=stream.readline(1024*1024)
                if not line or not line.endswith(b'\n'):break
                offset=stream.tell()
                try:item=json.loads(line)
                except ValueError:continue
                if kind=='collection' and item.get('ok') and item.get('request_id') and item.get('requested_at'):
                    db.execute('INSERT OR REPLACE INTO weather_requests VALUES (?,?)',(item['request_id'],item['requested_at']))
                if kind=='projection' and item.get('ok'):
                    for request_id in item.get('request_ids',[]):
                        row=db.execute('SELECT started FROM weather_requests WHERE id=?',(request_id,)).fetchone()
                        if row:
                            try:latency=(stamp(item['requested_at'])-stamp(row[0])).total_seconds()
                            except (KeyError,ValueError,TypeError):continue
                            if latency>=0:
                                records.append({'dataset':'pipeline_latency','event_id':'weather-latency:'+str(item.get('log_id'))+':'+request_id,
                                  '@timestamp':item['requested_at'],'request_id':request_id,'pipeline_latency_seconds':latency,
                                  'stage':'es_projection','timestamp_basis':'request_start_to_projection_complete'})
        db.execute('INSERT OR REPLACE INTO cursors VALUES (?,?,?)',(str(path),inode,offset))
    # Commit these cursors only after the correlated records have been fsynced by write().
    return records


def application(role):
    base=Path('/opt/music-apps')/role
    current=base/'current'
    unit='music-app-common' if role=='control' else 'music-app-advertising'
    command=subprocess.run(['systemctl','show',unit,'-p','ExecStart','--value'],capture_output=True,text=True,check=True).stdout
    match=re.search(r'(/opt/music-apps/(?:control|advertising)/venv-[^/\s;]+/bin/)',command)
    if not match:raise RuntimeError('application_interpreter_unresolved')
    env=os.environ.copy()
    for line in (Path('/etc/music-cluster')/role/'application.env').read_text().splitlines():
        key,sep,value=line.partition('=')
        if not sep or key.startswith('#'):continue
        values=shlex.split(value)
        env[key]=values[0] if values else ''
    cwd=current/('backend' if role=='control' else 'ad-server/backend')
    env['PYTHONPATH']=str(cwd)+':'+str(current)
    result=subprocess.run([match.group(1)+'python',str(CONF/'app_metrics.py'),role],cwd=cwd,env=env,capture_output=True,text=True,timeout=25)
    if result.returncode:raise RuntimeError('application_metrics_failed')
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]


def main():
    os.umask(0o077)
    node=json.loads((CONF/'node.json').read_text())
    db=sqlite3.connect(BASE/'metrics.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS sent (id TEXT PRIMARY KEY,digest TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS cursors (path TEXT PRIMARY KEY,inode TEXT,offset INTEGER)')
    db.execute('CREATE TABLE IF NOT EXISTS weather_requests (id TEXT PRIMARY KEY,started TEXT NOT NULL)')
    records=[]
    try:
        with urllib.request.urlopen('http://127.0.0.1:5066/stats',timeout=3) as r:stats=json.load(r)
        events=stats.get('libbeat',{}).get('pipeline',{}).get('events',{})
        output=stats.get('libbeat',{}).get('output',{}).get('events',{})
        records.append({'dataset':'forwarder','@timestamp':now(),'active':1,'queued_events':events.get('active',0),
                        'acked_events':output.get('acked',0),'failed_events':output.get('failed',0),
                        'rss_bytes':stats.get('beat',{}).get('memstats',{}).get('rss',0)})
    except Exception as error:records.append({'dataset':'forwarder','@timestamp':now(),'active':0,'error_type':type(error).__name__})
    units=subprocess.run(['systemctl','list-units','--all','--type=service','--no-legend','--plain','music-*','nginx*'],capture_output=True,text=True,check=True).stdout
    for line in units.splitlines():
        parts=line.split()
        if len(parts)>=4 and parts[0] not in ['music-ops-metrics.service']:
            records.append({'dataset':'service_health','@timestamp':now(),'service':parts[0],'state':parts[2],
                            'active':int(parts[2]=='active')})
    if node['node']=='control-a':
        records+=weather(db)
        try:records+=application('control')
        except Exception as error:records.append({'dataset':'exporter','@timestamp':now(),'ok':False,'source':'postgresql','error_type':type(error).__name__})
    if node['role']=='advertising':
        try:records+=application('advertising')
        except Exception as error:records.append({'dataset':'exporter','@timestamp':now(),'ok':False,'source':'mongodb','error_type':type(error).__name__})
    write(records,db)
    db.close()


if __name__=='__main__':main()
