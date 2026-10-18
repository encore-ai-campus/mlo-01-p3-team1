#!/usr/bin/env python3
"""Initialize only a proven empty Nitro data EBS volume, with generation identity."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def run(*args):return subprocess.check_output(args,text=True).strip()


def find_disk(devices,volume):
    wanted=volume.replace('-','')
    found=[d for d in devices if d.get('type')=='disk' and (d.get('serial') or '').strip()==wanted]
    if len(found)!=1:raise ValueError('Cannot identify exactly one Nitro EBS data volume by VolumeId serial')
    disk=found[0]
    if disk.get('children'):raise ValueError('Data disk has partitions; automatic formatting is forbidden')
    return disk


def initialize(c,check_only=False):
    node=c['node'];identity={'project':c['aws']['project'],'environment':c['aws']['environment'],
                           'generation':c['aws']['generation'],'node':node['name']}
    target=Path('/var/lib/music-cluster');marker=target/'.aws-volume-identity.json'
    devices=json.loads(run('lsblk','-J','-o','NAME,TYPE,SERIAL,FSTYPE,MOUNTPOINTS'))['blockdevices']
    disk=find_disk(devices,node['data_volume_id']);device='/dev/'+disk['name']
    mounts=[m for m in (disk.get('mountpoints') or []) if m]
    if mounts:
        if mounts!=[str(target)] or not marker.exists() or json.loads(marker.read_text())!=identity:
            raise ValueError('Mounted disk identity differs; never reset automatically')
        return
    if check_only:raise ValueError('Data volume is not mounted with the expected generation identity')
    if disk.get('fstype') or run('wipefs','--no-act','--noheadings',device):
        raise ValueError('Existing filesystem/signature found; refuses to format or reset it')
    if target.exists() and any(target.iterdir()):raise ValueError('Data directory already contains files')
    target.mkdir(parents=True,exist_ok=True)
    subprocess.run(['mkfs.ext4','-q',device],check=True)
    uuid=run('blkid','-s','UUID','-o','value',device)
    entry=f'UUID={uuid} {target} ext4 defaults,nofail 0 2\n'
    with Path('/etc/fstab').open('a') as f:f.write(entry)
    subprocess.run(['mount',str(target)],check=True)
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(identity,f)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runtime');p.add_argument('--check-only',action='store_true');a=p.parse_args()
    try:initialize(json.loads(Path(a.runtime).read_text()),a.check_only)
    except (ValueError,OSError,subprocess.SubprocessError) as e:raise SystemExit('[FAIL] '+str(e))
    print('[PASS] Data volume generation identity verified')
