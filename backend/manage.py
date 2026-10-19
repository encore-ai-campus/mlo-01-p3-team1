import os
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.cafe.settings')
from django.core.management import execute_from_command_line

execute_from_command_line(sys.argv)
