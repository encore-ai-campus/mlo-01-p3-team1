"""Load only Gemini settings; never execute/interpolate a local env file."""
import os

KEYS={'GEMINI_API_KEY','GEMINI_ENABLED','GEMINI_TIMEOUT_MS',
      'GEMINI_MAX_CANDIDATES','GEMINI_MAX_OUTPUT_TOKENS'}


def load(path):
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        name,separator,value=line.strip().partition('=')
        name=name.strip()
        if not separator or name not in KEYS:
            continue
        value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):
            value=value[1:-1]
        if value:
            os.environ.setdefault(name,value)
