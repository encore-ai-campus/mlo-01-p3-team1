"""python sandbox.py --start-mongo 로 실행하는 독립 로컬 도구입니다."""

import os
import sys


def main():
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.sandbox_settings"
    from django.core.management import execute_from_command_line

    execute_from_command_line([sys.argv[0], "run_ads_sandbox", *sys.argv[1:]])


if __name__ == "__main__":
    main()
