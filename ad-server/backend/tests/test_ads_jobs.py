"""실패 격리·재시도·종료·기존 claim 경계를 운영 DB 없이 검증합니다."""

import json
import threading
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from domains.ads.errors import DatabaseUnavailable, DomainError
from workers.ads_jobs import AdsJob, AdsJobRunner, AdsWorkerGroup, configured_jobs


class AdsJobsTests(SimpleTestCase):
    def test_failed_job_recovers_without_leaking_exception_text(self):
        callback = Mock(
            side_effect=[DatabaseUnavailable("mongodb://secret@host"), {"ads_checked": 1}]
        )
        runner = AdsJobRunner(AdsJob("policy", callback, 300))
        failed = runner.run_once()
        self.assertEqual(failed["status"], "ERROR")
        self.assertIsNone(failed["last_succeeded_at"])
        self.assertNotIn("secret", json.dumps(failed))
        recovered = runner.run_once()
        self.assertEqual(recovered["status"], "OK")
        self.assertIsNone(recovered["error"])
        self.assertIsNotNone(recovered["last_succeeded_at"])
        self.assertEqual(callback.call_count, 2)

    def test_unknown_result_payload_is_not_exposed(self):
        runner = AdsJobRunner(AdsJob("policy", lambda: {"password": "secret"}, 300))
        result = runner.run_once()
        self.assertEqual(result["status"], "ERROR")
        self.assertNotIn("secret", json.dumps(result))
        result["error"]["type"] = "changed"
        self.assertEqual(runner.snapshot()["error"]["type"], "ValueError")

    def test_blocked_log_thread_does_not_delay_policy_and_shutdown_is_bounded(self):
        started, release, policy_ran = threading.Event(), threading.Event(), threading.Event()

        def slow_log():
            started.set()
            release.wait(3)
            return {"ads_checked": 0}

        def policy():
            policy_ran.set()
            return {"ads_checked": 0}

        group = AdsWorkerGroup(
            [AdsJob("other_policy", slow_log, 30), AdsJob("policy", policy, 300)]
        )
        try:
            group.start()
            self.assertTrue(started.wait(1))
            self.assertTrue(policy_ran.wait(1))
            with self.assertRaises(RuntimeError):
                group.start()
            with self.assertRaises(RuntimeError):
                group.run_once()
            self.assertFalse(group.stop(timeout=0))
        finally:
            release.set()
            self.assertTrue(group.stop(timeout=2))

    def test_watch_retries_after_failure_without_catchup_burst(self):
        runner = AdsJobRunner(
            AdsJob(
                "policy",
                Mock(
                    side_effect=[
                        RuntimeError("private-uri"),
                        {"ads_checked": 0},
                    ]
                ),
                300,
            )
        )
        stop = Mock()
        stop.is_set.return_value = False
        stop.wait.side_effect = [False, True]
        with patch("workers.ads_jobs.time.monotonic", side_effect=[0, 350, 800]):
            runner.watch(stop)
        self.assertEqual(runner.job.callback.call_count, 2)
        self.assertEqual(runner.snapshot()["status"], "OK")
        self.assertEqual([call.args[0] for call in stop.wait.call_args_list], [300, 150])

    def test_successful_command_outputs_safe_counts(self):
        with patch(
            "domains.ads.management.commands.run_ads_workers.configured_jobs",
            return_value=[
                AdsJob("policy", lambda: {"ads_checked": 0}, 300),
            ],
        ):
            output = StringIO()
            call_command("run_ads_workers", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["policy"]["status"], "OK")

    def test_unavailable_error_code_and_text_are_sanitized(self):
        def callback():
            raise DomainError("postgresql://credential@host", "password", 503)

        result = AdsJobRunner(AdsJob("policy", callback, 30)).run_once()
        self.assertEqual(result["error"], {"type": "DomainError", "code": None})

    @override_settings(ADS_LOG_SINK="unused.never.imported")
    def test_only_policy_runs_without_external_log_dependency(self):
        with patch("workers.ads_jobs.refresh_policy", return_value={"ads_checked": 0}) as policy:
            jobs = configured_jobs()
            self.assertEqual([(job.name, job.interval_seconds) for job in jobs], [("policy", 300)])
            report = AdsWorkerGroup(jobs).run_once()
        policy.assert_called_once_with()
        self.assertEqual(set(report), {"policy"})
        self.assertEqual(report["policy"]["status"], "OK")

    def test_failed_policy_command_has_nonzero_exit_semantics(self):
        with patch("workers.ads_jobs.refresh_policy", side_effect=DatabaseUnavailable()):
            output = StringIO()
            with self.assertRaises(CommandError):
                call_command("run_ads_workers", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["policy"]["status"], "ERROR")
