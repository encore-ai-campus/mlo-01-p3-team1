"""Read service env files as data; never execute shell code or interpolate values."""
import os
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVICES={'common':ROOT/'backend', 'weather':ROOT/'pipeline'/'weather'}


def read(path, allowed=None):
    result={}
    if not path.is_file():return result
    for number,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'):continue
        name,separator,value=line.partition('=');name=name.strip();value=value.strip()
        if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*',name):
            raise ValueError(f'env_format_line_{number}')
        if allowed is not None and name not in allowed:continue
        if value[:1] in ('"',"'"):
            if len(value)<2 or value[-1]!=value[0]:raise ValueError(f'env_quote_line_{number}')
            value=value[1:-1]
        if value:result[name]=value
    return result


def load(service, environ=None):
    directory=SERVICES[service]
    target=os.environ if environ is None else environ
    if not (directory/'.env').is_file():return target
    allowed={line.partition('=')[0].strip() for line in
             (directory/'.env.example').read_text(encoding='utf8').splitlines()
             if '=' in line and not line.lstrip().startswith('#')}
    for name,value in read(directory/'.env',allowed).items():target.setdefault(name,value)
    return target
