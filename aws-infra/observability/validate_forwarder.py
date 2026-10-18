"""Isolated real-Filebeat integration test; never sends fixtures to the live cluster.

Checks disk-queue recovery after SIGKILL, bulk 503/partial 429 retry, rotation and redaction.
"""
import datetime
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time


def wait_for(predicate, seconds=45):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(0.5)
    raise AssertionError('test_condition_timeout')


def main():
    state={'accept':False,'requests':0,'partial':False,'accepted':{},'failed_ids':set()}
    class Sink(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,code,body):
            data=json.dumps(body).encode();self.send_response(code)
            self.send_header('Content-Type','application/json');self.send_header('X-Elastic-Product','Elasticsearch')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if 'license' in self.path:self.reply(200,{'license':{'status':'active','type':'basic'}})
            else:self.reply(200,{'name':'isolated-test','cluster_name':'isolated-test','cluster_uuid':'test',
                 'version':{'number':'8.19.23','build_flavor':'default','build_type':'tar','build_hash':'test','build_date':'2026-10-01T00:00:00Z','build_snapshot':False,'lucene_version':'9.12.2','minimum_wire_compatibility_version':'7.17.0','minimum_index_compatibility_version':'7.0.0'},'tagline':'You Know, for Search'})
        def do_POST(self):
            data=self.rfile.read(int(self.headers['Content-Length']))
            if self.headers.get('Content-Encoding')=='gzip':data=gzip.decompress(data)
            lines=data.splitlines();state['requests']+=1
            if not state['accept']:
                self.reply(503,{'error':{'type':'unavailable','reason':'isolated retry test'},'status':503});return
            items=[];errors=False
            for index in range(0,len(lines),2):
                action=json.loads(lines[index]);kind=next(iter(action));meta=action[kind];doc=json.loads(lines[index+1])
                if not state['partial']:
                    state['partial']=True;state['failed_ids'].add(meta['_id']);errors=True
                    items.append({kind:{'_index':meta['_index'],'_id':meta['_id'],'status':429,'error':{'type':'es_rejected_execution_exception','reason':'isolated partial retry'}}})
                else:
                    state['accepted'][meta['_id']]=doc
                    items.append({kind:{'_index':meta['_index'],'_id':meta['_id'],'status':201}})
            self.reply(200,{'took':1,'errors':errors,'items':items})
    server=ThreadingHTTPServer(('127.0.0.1',0),Sink)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=Path(tempfile.mkdtemp(prefix='forwarder-validation-',dir='/var/lib/music-cluster/observability'))
    config=json.loads(Path('/etc/music-cluster/observability/filebeat.yml').read_text())
    config['path.data']=str(base/'state');config['path.logs']=str(base/'logs')
    config['http.enabled']=False
    config['output.elasticsearch']={'hosts':['http://127.0.0.1:'+str(server.server_port)],'index':'ops-mlo-validation',
      'bulk_max_size':10,'backoff.init':'1s','backoff.max':'2s','compression_level':0}
    config['filebeat.inputs']=[{'type':'filestream','id':'isolated-test-v1','paths':[str(base/'source*.jsonl')],
      'prospector.scanner.check_interval':'1s','prospector.scanner.fingerprint.length':64,
      'parsers':[{'ndjson':{'target':'payload'}}],'fields':{'event':{'dataset':'validation'}},'fields_under_root':True}]
    config['queue.disk']['max_size']='16MB';config['queue.disk']['segment_size']='1MB'
    c=base/'filebeat.yml';c.write_text(json.dumps(config));c.chmod(0o600)
    source=base/'source.jsonl'
    def fixtures(start,count):
        return [json.dumps({'event_id':'validation-'+str(i),'dataset':'validation','@timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           'message':'password=IsolatedCanaryOnly https://example.invalid/a?token=IsolatedCanaryOnly','is_test':True})+'\n' for i in range(start,start+count)]
    source.write_text(''.join(fixtures(0,50)))
    binary='/opt/music-observability/filebeat-8.19.23/filebeat'
    log=(base/'process.log').open('wb')
    def start():return subprocess.Popen([binary,'-e','-c',str(c),'--path.home','/opt/music-observability/filebeat-8.19.23'],stdout=log,stderr=log)
    process=start()
    try:
        wait_for(lambda:state['requests']>0)
        # The disk queue owns the unacknowledged batch when the publisher receives 503.
        process.kill();process.wait(timeout=10)
        state['accept']=True
        process=start()
        wait_for(lambda:len(state['accepted'])==50,75)
        source.rename(base/'source.old.jsonl')
        source.write_text(''.join(fixtures(50,3)))
        wait_for(lambda:len(state['accepted'])==53,30)
        assert state['partial'] and state['failed_ids'].issubset(state['accepted'])
        for doc in state['accepted'].values():
            assert 'IsolatedCanaryOnly' not in json.dumps(doc)
            assert doc['event']['dataset']=='validation' and doc['ops']['is_test'] is True
        print(json.dumps({'passed':True,'unique_events':len(state['accepted']),'bulk_requests':state['requests'],
                          'sigkill_recovery':True,'partial_429_retry':True,'rotation':True,'redaction':True,
                          'live_cluster_test_writes':0}))
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=15)
        server.shutdown();log.close()


if __name__=='__main__':main()
