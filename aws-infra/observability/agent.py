"""Install pinned Filebeat with durable disk queue, source registry and redaction."""
import glob
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from bootstrap import CONF, DATA, HERE, distribution, installation_lock, run, write


def install(c):
    CONF.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    CONF.chmod(0o751)
    shutil.copyfile(HERE / 'sanitize.js', CONF / 'sanitize.js')
    shutil.copyfile(HERE / 'metrics.py', CONF / 'metrics.py')
    shutil.copyfile(HERE / 'app_metrics.py', CONF / 'app_metrics.py')
    for name in ['sanitize.js','metrics.py','app_metrics.py']:
        (CONF / name).chmod(0o644)
    shutil.copyfile(HERE / 'ca.crt', CONF / 'ca.crt')
    (CONF / 'ca.crt').chmod(0o644)
    binary = distribution('filebeat')
    units = subprocess.run(['systemctl','list-unit-files','--no-legend','--plain','music-*.service'],capture_output=True,text=True,check=True).stdout
    units = [line.split()[0] for line in units.splitlines() if line.startswith('music-') and not line.startswith(('music-filebeat','music-ops-metrics'))]
    units += ['nginx.service']
    inputs = [{'type':'journald','id':'music-journal-v3','seek':'head','units':units,
               'fields':{'event':{'dataset':'service'}},'fields_under_root':True},
              {'type':'journald','id':'music-kernel-errors-v3','seek':'head','transports':['kernel'],
               'fields':{'event':{'dataset':'kernel'}},'fields_under_root':True,
               'processors':[{'drop_event':{'when':{'range':{'log.syslog.priority':{'gte':4}}}}}]}]
    sources = [('weather',['/var/lib/music-cluster/control/weather/collector/requests.jsonl','/var/lib/music-cluster/control/logs/weather-process.jsonl'],True),
               ('operations',['/var/lib/music-cluster/observability/events-*.jsonl'],True),
               ('kafka',['/var/lib/music-cluster/kafka/log/server.log*','/var/lib/music-cluster/kafka/log/controller.log*','/var/lib/music-cluster/kafka/log/state-change.log*','/var/lib/music-cluster/kafka/log/kafka-authorizer.log*'],False),
               ('elasticsearch',['/var/lib/music-cluster/elasticsearch/log/*_server.json','/var/lib/music-cluster/elasticsearch/log/*_deprecation.json','/var/lib/music-cluster/elasticsearch/log/*_slowlog.json'],True),
               ('nginx_access',['/var/log/nginx/access.log*'],False),('nginx_error',['/var/log/nginx/error.log*'],False),
               ('mongodb',['/var/lib/music-cluster/mongodb/mongod.log*','/var/lib/music-cluster/mongodb/log/*.log','/var/log/mongodb/*.log'],True),
               ('spark_executor',['/var/lib/music-cluster/spark/work/*/*/stderr','/var/lib/music-cluster/spark/work/*/*/stdout'],False)]
    roles={'weather':['control'],'operations':[c['role']],'kafka':['kafka'],'elasticsearch':['es'],
           'nginx_access':['control','advertising'],'nginx_error':['control','advertising'],
           'mongodb':['mongodb'],'spark_executor':['spark']}
    for dataset, paths, structured in sources:
        # Keep known role inputs even before their first file is created (rotation/failover/new executor).
        if c['role'] not in roles[dataset]:
            continue
        item={'type':'filestream','id':'music-'+dataset+'-v3','paths':paths,
              'prospector.scanner.check_interval':'5s','prospector.scanner.fingerprint.length':64,
              'message_max_bytes':8192,'exclude_files':['\\.gz$'],
              'fields':{'event':{'dataset':dataset}},'fields_under_root':True}
        if structured:item['parsers']=[{'ndjson':{'target':'payload','add_error_key':True}}]
        inputs.append(item)
    secrets=[]
    for p in Path('/etc/music-cluster').glob('**/runtime.json'):
        for k,v in json.loads(p.read_text()).get('env',{}).items():
            if re.search('PASSWORD|SECRET|TOKEN|KEY',k) and isinstance(v,str):secrets.append(v)
    for p in Path('/etc/music-cluster').glob('*/application.env'):
        import shlex
        for line in p.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and re.search('PASSWORD|SECRET|TOKEN|KEY|URI|URL',key):
                try:values=shlex.split(value)
                except ValueError:continue
                if values:secrets.append(values[0])
    config={'name':c['node'],'path.data':str(DATA/'filebeat'),'path.logs':str(DATA/'filebeat-logs'),
            'filebeat.inputs':inputs,'filebeat.registry.flush':'1s',
            'queue.disk':{'max_size':'512MB','segment_size':'16MB','read_ahead':64,'write_ahead':64},
            'setup.ilm.enabled':False,'setup.template.enabled':False,
            'output.elasticsearch':{'hosts':['https://'+c['hub_ip']+':8444'],'path':'/elastic',
              'username':'ops_ingest','password':c['writer_password'],'ssl.certificate_authorities':[str(CONF/'ca.crt')],
              'index':'ops-mlo-%{[event.dataset]}-%{+yyyy.MM.dd}','bulk_max_size':100,'worker':1,'compression_level':1},
            'processors':[{'add_fields':{'target':'host','fields':{'name':c['node']}}},
                          {'script':{'lang':'javascript','file':str(CONF/'sanitize.js'),'params':{'secrets':secrets},'timeout':'100ms'}},
                          {'drop_event':{'when':{'contains':{'tags':'_js_exception'}}}},
                          {'timestamp':{'field':'ops_timestamp','layouts':['2006-01-02T15:04:05.999999999Z07:00'],'ignore_missing':True,'ignore_failure':True}},
                          {'fingerprint':{'when':{'has_fields':['event.id']},
                                          'fields':['host.name','event.dataset','event.id'],
                                          'ignore_missing':False,'target_field':'@metadata._id','method':'sha256'}},
                          {'fingerprint':{'when':{'not':{'has_fields':['event.id']}},
                                          'fields':['host.name','@timestamp','event.dataset','log.file.path','log.offset','message','ops_fingerprint'],
                                          'ignore_missing':True,'target_field':'@metadata._id','method':'sha256'}},
                          # @timestamp is automatically retained; listing it duplicates the serialized field in 8.19.
                          {'include_fields':{'fields':['host.name','message','event','service.name','log.level','log.file.path','log.offset','ops','tags']}}],
            'http.enabled':True,'http.host':'127.0.0.1','http.port':5066,
            'logging.level':'warning','logging.to_files':False,'logging.to_stderr':True}
    # kernel selection uses journal PRIORITY rather than a non-existent range processor condition.
    inputs[1].pop('processors')
    inputs[1]['include_matches.match']=['PRIORITY=0','PRIORITY=1','PRIORITY=2','PRIORITY=3']
    write(CONF/'filebeat.yml',json.dumps(config,indent=2))
    write(CONF/'node.json',json.dumps({'node':c['node'],'role':c['role']}))
    run([str(binary/'filebeat'),'test','config','-c',str(CONF/'filebeat.yml'),'--path.home',str(binary)])
    write('/etc/systemd/system/music-filebeat.service',f'''[Unit]
Description=Music durable sanitized log forwarding
After=network-online.target
[Service]
ExecStart={binary}/filebeat -e -c {CONF}/filebeat.yml --path.home {binary}
Restart=on-failure
RestartSec=10
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
MemoryMax=256M
CPUQuota=20%
[Install]
WantedBy=multi-user.target
''',0o644)
    write('/etc/systemd/system/music-ops-metrics.service',f'''[Unit]
Description=Music read-only operations metrics
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {CONF}/metrics.py
TimeoutStartSec=50
UMask=0077
Nice=10
MemoryMax=192M
''',0o644)
    write('/etc/systemd/system/music-ops-metrics.timer','''[Unit]
Description=Music operations metrics every minute
[Timer]
OnBootSec=30
OnUnitActiveSec=60
Persistent=true
[Install]
WantedBy=timers.target
''',0o644)
    run(['systemctl','daemon-reload'])
    run(['systemctl','enable','--now','music-filebeat','music-ops-metrics.timer'])
    run(['systemctl','restart','music-filebeat'])
    run(['systemctl','start','music-ops-metrics'])
    print(json.dumps({'node':c['node'],'filebeat_installed':True,'inputs':len(inputs),'units':units,'redaction_secrets_count':len(secrets)}))


if __name__=='__main__':
    with installation_lock():
        install(json.loads(Path(sys.argv[1]).read_text()))
