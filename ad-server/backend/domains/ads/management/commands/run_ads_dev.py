from wsgiref.simple_server import make_server

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application


class Command(BaseCommand):
    help = "광고 API 개발용 loopback 서버입니다. 관리 요청은 공유 ADMIN 검증이 필요합니다."

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=8000)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("이 명령은 DEBUG 로컬 개발에서만 사용할 수 있습니다.")
        port = options["port"]
        if not 1 <= port <= 65535:
            raise CommandError("port는 1~65535 정수여야 합니다.")
        self.stdout.write(f"개발 준비 서버: http://127.0.0.1:{port}/api/health")
        self.stdout.write(
            "공유 ADMIN 연결 없이 관리 요청을 허용하지 않습니다. 공통 migration은 별도입니다."
        )
        with make_server("127.0.0.1", port, get_wsgi_application()) as server:
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
