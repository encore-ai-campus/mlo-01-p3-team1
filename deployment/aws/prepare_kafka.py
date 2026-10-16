"""Prepare only the application's two topics and scoped pipeline ACLs.

Run on the identified existing Kafka node as EC2 root. Credentials remain in
native admin.properties; never grant topic-creation privileges to the app user.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--generation',required=True)
    parser.add_argument('--instance-id',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:raise RuntimeError('EC2_root_required')
    runtime=json.loads(Path('/etc/music-cluster/runtime.json').read_text())
    if runtime['aws']['generation']!=args.generation or runtime['node']['role']!='kafka':
        raise RuntimeError('generation_or_role_mismatch')
    token=urlopen(Request('http://169.254.169.254/latest/api/token',method='PUT',headers={'X-aws-ec2-metadata-token-ttl-seconds':'60'}),timeout=3).read().decode()
    instance=urlopen(Request('http://169.254.169.254/latest/meta-data/instance-id',headers={'X-aws-ec2-metadata-token':token}),timeout=3).read().decode()
    if instance!=args.instance_id:raise RuntimeError('instance_mismatch')
    hosts=[n['address'] for n in runtime['inventory']['nodes'] if set(n['roles'])&{'control','spark'}]
    def cli(script,*options):
        argv=['runuser','-u','kafka','--','env','JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64','LOG_DIR=/var/lib/music-cluster/kafka/log',
              '/opt/music-cluster/kafka/bin/'+script,'--bootstrap-server',runtime['derived']['kafka_bootstrap'],'--command-config','/etc/music-cluster/kafka/admin.properties',*options]
        result=subprocess.run(argv,capture_output=True,text=True,timeout=120)
        if result.returncode:raise RuntimeError('native_kafka_admin_failed:'+script)
        return result.stdout
    if not args.apply:
        print(json.dumps({'apply':False,'topics':['weather.v1','feedback.v1'],'replication':3,'partitions':3,'allowed_hosts':len(hosts)}));return
    host_args=[part for host in hosts for part in ['--allow-host',host]]
    for topic in ['weather.v1','feedback.v1']:
        cli('kafka-topics.sh','--create','--if-not-exists','--topic',topic,'--partitions','3','--replication-factor','3','--config','min.insync.replicas=2')
        value=cli('kafka-topics.sh','--describe','--topic',topic)
        if not re.search(r'PartitionCount:\s*3\b',value) or not re.search(r'ReplicationFactor:\s*3\b',value) or 'min.insync.replicas=2' not in value:
            raise RuntimeError('existing_topic_contract_conflict_preserved')
        cli('kafka-acls.sh','--add','--allow-principal','User:pipeline',*host_args,'--operation','Read','--operation','Write','--operation','Describe','--topic',topic)
    cli('kafka-acls.sh','--add','--allow-principal','User:pipeline',*host_args,'--operation','Read','--group','feedback-projection-aws-v1')
    cli('kafka-acls.sh','--add','--allow-principal','User:pipeline',*host_args,'--operation','Read','--group','spark-kafka-source-','--resource-pattern-type','prefixed')
    for operation in ['Describe','IdempotentWrite']:
        cli('kafka-acls.sh','--add','--allow-principal','User:pipeline',*host_args,'--operation',operation,'--cluster')
    print(json.dumps({'applied':True,'topics':2,'partitions_each':3,'replication_factor':3,'minimum_isr':2,'group_access':'exact_feedback_and_spark_prefix','app_can_create_topics':False}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__,'reason':str(error) if isinstance(error,RuntimeError) else 'see_private_service_logs'}))
        raise SystemExit(1)
