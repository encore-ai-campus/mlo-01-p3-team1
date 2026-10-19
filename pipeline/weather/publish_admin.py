"""python -m pipeline.weather.publish_admin [--once]. 별도 관리자 ES 발행 프로세스."""
import argparse
import json
import os
import time
from pipeline.weather.mongo_current import collection, setting
from pipeline.weather.es_current import publish_pending


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    base, index = setting('ES_URL'), setting('WEATHER_INDEX')
    interval = int(os.environ.get('WEATHER_ADMIN_POLL_SECONDS', '15'))
    if interval < 1:
        raise ValueError('invalid_admin_poll_interval')
    while True:
        count = 0
        try:
            count = publish_pending(collection('publish'), base, index)
            print(json.dumps(dict(stage='admin_projection', ok=True, grids=count)), flush=True)
        except Exception as error:
            print(json.dumps(dict(stage='admin_projection', ok=False,
                                  error_type=type(error).__name__)), flush=True)
            if args.once:
                raise SystemExit(1)
        if args.once:
            return
        # 대기 자료가 한 묶음 이상이면 쉬지 않고 다음 묶음 처리.
        if count < 50:
            time.sleep(interval)


if __name__ == '__main__':
    main()
