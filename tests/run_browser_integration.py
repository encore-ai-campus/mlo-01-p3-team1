"""기존 로컬 DB/서버와 분리한 유한 브라우저 통합 시험. 운영 서비스 호출 없음."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import socket
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]


def main():
    def available_port():
        with socket.socket() as connection:
            connection.bind(('127.0.0.1',0));return connection.getsockname()[1]
    api_port,web_port,ads_port=available_port(),available_port(),available_port()
    with tempfile.TemporaryDirectory(prefix='browser-test-',dir=ROOT/'artifacts') as directory:
        folder=Path(directory).resolve()
        if not folder.is_relative_to(ROOT):raise RuntimeError('test_directory_outside_workspace')
        env={**os.environ,'C_LOCAL_DEMO':'1','INTEGRATION_ENABLED':'1','C_LOCAL_DATABASE':str(folder/'test.sqlite3'),
             'DJANGO_SETTINGS_MODULE':'backend.cafe.settings','GUEST_TTL_SECONDS':'600','ADMIN_SESSION_SECONDS':'600',
             'OWNER_RESOLVER':'backend.common.identity.owner','EVENT_SINK':'backend.common.events.record',
             'WEATHER_PROVIDER':'','SEARCH_SECONDS':'20','SEARCH_MAX_CANDIDATES':'96',
             'VITE_C_DEMO':'1','VITE_RECOMMENDATION_API_TARGET':f'http://127.0.0.1:{api_port}',
             'VITE_ADS_API_TARGET':f'http://127.0.0.1:{ads_port}','SMOKE_BASE_URL':f'http://127.0.0.1:{web_port}',
             'GEMINI_ENABLED':'0'}
        def run(args):
            completed=subprocess.run(args,cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
            if completed.returncode:raise RuntimeError(completed.stderr[-2000:])
        run([sys.executable,'backend/manage.py','migrate','--noinput'])
        run([sys.executable,'backend/manage.py','seed_c_demo'])
        run([sys.executable,'backend/manage.py','shell','-c',
             "from django.contrib.auth import get_user_model; from backend.common.admin_roles import assign_role; "
             "u=get_user_model().objects.create_user('browser-reviewer',password='Browser-test-only-123!',is_staff=True); "
             "assign_role(u,'SUPER_ADMIN')"])
        processes=[]
        # Prebuilt UI avoids development dependency scanning on restricted Windows runners.
        web_command=['node','./node_modules/vite/bin/vite.js']
        if os.environ.get('BROWSER_USE_BUILD')=='1':web_command+=['preview','--configLoader','runner']
        web_command+=['--host','127.0.0.1','--port',str(web_port),'--strictPort']
        with (folder/'process.log').open('w',encoding='utf8') as output:
            try:
                for command,cwd in [([sys.executable,'backend/manage.py','runserver',f'127.0.0.1:{api_port}','--noreload'],ROOT),
                    ([sys.executable,'backend/manage.py','run_recommendations'],ROOT),
                    (web_command,ROOT/'frontend')]:
                    processes.append(subprocess.Popen(command,cwd=cwd,env=env,stdout=output,stderr=output))
                deadline=time.monotonic()+30
                for url in [f'http://127.0.0.1:{api_port}/health/',env['SMOKE_BASE_URL']+'/']:
                    while True:
                        if any(process.poll() is not None for process in processes):raise RuntimeError('isolated_test_process_failed')
                        try:
                            with urlopen(url,timeout=1) as response:
                                if response.status==200:break
                        except OSError:pass
                        if time.monotonic()>deadline:raise RuntimeError('isolated_test_start_timeout')
                        time.sleep(.2)
                for script in ('integration-smoke.cjs','ads-layout-smoke.cjs','ads-banner-smoke.cjs'):
                    completed=subprocess.run(['node','frontend/scripts/'+script],cwd=ROOT,env=env,
                                             capture_output=True,text=True,timeout=90)
                    if completed.returncode:raise RuntimeError(completed.stderr[-2000:])
                    print(completed.stdout.strip())
            finally:
                for process in reversed(processes):
                    if process.poll() is None:process.terminate()
                for process in processes:
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


if __name__=='__main__':
    (ROOT/'artifacts').mkdir(exist_ok=True)
    main()
