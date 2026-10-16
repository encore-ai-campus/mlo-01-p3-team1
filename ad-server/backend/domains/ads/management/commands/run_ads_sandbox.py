"""공유 설정과 분리된 광고 확인 도구·5분 작업을 loopback에만 실행합니다."""

import shutil
import subprocess
import time
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.uri_parser import parse_uri

from domains.ads import sandbox_runtime
from domains.ads.mongo import local_client, require_primary


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        # 기본 access log의 query string에 이미지 proof가 포함될 수 있습니다.
        pass


class LocalServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def start_mongo(executable, state_dir):
    parsed = parse_uri(settings.ADS_MONGODB_URI)
    nodes = parsed["nodelist"]
    if len(nodes) != 1 or nodes[0][0] != "127.0.0.1":
        raise CommandError("자동 기동 URI는 단일 127.0.0.1 주소여야 합니다.")
    port = nodes[0][1]
    # 이미 실행 중인 서버는 소유하거나 중단하지 않습니다.
    with MongoClient(f"mongodb://127.0.0.1:{port}/", serverSelectionTimeoutMS=700) as probe:
        try:
            probe.admin.command("ping")
            return None
        except PyMongoError:
            pass
    candidate = Path(executable).resolve()
    if not candidate.is_file():
        raise CommandError("mongod 실행 파일이 없습니다. --mongod 경로를 지정하세요.")
    database_dir = (state_dir / "mongo").resolve()
    if not database_dir.is_relative_to(state_dir.resolve()):
        raise CommandError("시험 MongoDB 자료 경로가 올바르지 않습니다.")
    database_dir.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [
            str(candidate),
            "--dbpath",
            str(database_dir),
            "--bind_ip",
            "127.0.0.1",
            "--port",
            str(port),
            "--replSet",
            "ads-rs",
            "--wiredTigerCacheSizeGB",
            "0.25",
            "--logpath",
            str(state_dir / "mongo.log"),
            "--logappend",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        with MongoClient(
            f"mongodb://127.0.0.1:{port}/?directConnection=true",
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
            socketTimeoutMS=2000,
            tz_aware=True,
        ) as client:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise CommandError(
                        "시험 MongoDB 기동 실패: .local/ads-sandbox/mongo.log를 확인하세요."
                    )
                try:
                    hello = client.admin.command("hello")
                    if not hello.get("setName"):
                        client.admin.command(
                            "replSetInitiate",
                            {"_id": "ads-rs", "members": [{"_id": 0, "host": f"127.0.0.1:{port}"}]},
                        )
                    elif hello.get("setName") == "ads-rs" and hello.get("isWritablePrimary"):
                        return process
                except OperationFailure as exc:
                    if exc.code not in {23, 94}:
                        raise CommandError(
                            f"시험 replica set 초기화 실패: code={exc.code}"
                        ) from None
                except PyMongoError:
                    pass
                time.sleep(0.15)
        raise CommandError("시험 MongoDB primary 준비 시간이 초과됐습니다.")
    except BaseException:
        process.terminate()
        process.wait(timeout=10)
        raise


class Command(BaseCommand):
    help = "로컬 광고 시험 관리 화면과 5분 검증을 실행합니다. sandbox.py로 사용하세요."

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=8001)
        parser.add_argument("--start-mongo", action="store_true")
        parser.add_argument("--mongod", default="")

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "config.sandbox_settings":
            raise CommandError("운영 설정으로 실행할 수 없습니다. python sandbox.py를 사용하세요.")
        sandbox_runtime.require_sandbox()
        port = options["port"]
        if not 1 <= port <= 65535:
            raise CommandError("port는 1~65535 정수여야 합니다.")
        settings.ADS_PUBLIC_BASE_URL = f"https://127.0.0.1:{port}"
        workspace = Path(__file__).resolve().parents[6]
        state_dir = workspace / ".local" / "ads-sandbox"
        state_dir.mkdir(parents=True, exist_ok=True)
        mongod = (
            options["mongod"]
            or shutil.which("mongod")
            or str(workspace / ".tools" / "mongodb-test" / "mongod.exe")
        )
        process = None
        try:
            if options["start_mongo"]:
                # local_client는 URI·_dev 경계를 먼저 검사합니다.
                with local_client():
                    pass
                process = start_mongo(mongod, state_dir)
            with local_client() as client:
                require_primary(client)
            for name in ("apply_ads_schema", "apply_ads_public_schema", "apply_ads_policy_schema"):
                call_command(name, apply=True, stdout=self.stdout)
            access_path = state_dir / "access.txt"
            access_path.write_text(settings.ADS_SANDBOX_ACCESS_TOKEN + "\n", encoding="utf-8")
            sandbox_runtime.start_worker()
            with make_server(
                "127.0.0.1",
                port,
                get_wsgi_application(),
                server_class=LocalServer,
                handler_class=QuietHandler,
            ) as server:
                self.stdout.write(f"광고 로컬 관리: http://127.0.0.1:{port}/dev/ads/")
                self.stdout.write(f"접근 코드 파일: {access_path}")
                self.stdout.write("시험 DB ads_sandbox_dev · 5분 검증 실행 · 공유 인증/PG 미연결")
                self.stdout.write("Ctrl+C로 종료합니다. 자신이 기동한 MongoDB만 함께 종료합니다.")
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        except PyMongoError as exc:
            raise CommandError(f"로컬 MongoDB 연결 실패: {type(exc).__name__}") from None
        finally:
            sandbox_runtime.stop_worker()
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
