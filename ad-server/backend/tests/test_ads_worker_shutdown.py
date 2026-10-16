"""watch의 SIGTERM/키보드 종료와 종료 실패를 실제 OS 신호 전송 없이 검증합니다."""

import signal
import threading
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from domains.ads.management.commands.run_ads_workers import Command


class AdsWorkerShutdownTests(SimpleTestCase):
    def command(self):
        return Command(stdout=StringIO())

    def group(self):
        group = Mock()
        group.snapshot.return_value = {"policy": {"status": "RUNNING"}}
        group.stop.return_value = True
        return group

    def test_sigterm_requests_stop_and_restores_previous_handler(self):
        command, group = self.command(), self.group()
        previous = object()
        with patch(
            "domains.ads.management.commands.run_ads_workers.signal.signal",
            return_value=previous,
        ) as register:
            group.start.side_effect = lambda: register.call_args.args[1](signal.SIGTERM, None)
            command.watch(group)
        group.start.assert_called_once_with()
        group.stop.assert_called_once_with()
        self.assertEqual(register.call_count, 2)
        self.assertEqual(register.call_args.args, (signal.SIGTERM, previous))
        self.assertIn("RUNNING", command.stdout._out.getvalue())

    def test_keyboard_interrupt_stops_group_and_restores_handler(self):
        group = self.group()
        event = Mock()
        event.wait.side_effect = KeyboardInterrupt
        with (
            patch(
                "domains.ads.management.commands.run_ads_workers.threading.Event",
                return_value=event,
            ),
            patch(
                "domains.ads.management.commands.run_ads_workers.signal.signal", return_value="old"
            ) as register,
        ):
            self.command().watch(group)
        event.wait.assert_called_once_with(30)
        group.stop.assert_called_once_with()
        self.assertEqual(register.call_args.args, (signal.SIGTERM, "old"))

    def test_failed_shutdown_is_reported_and_handler_still_restored(self):
        group = self.group()
        group.start.side_effect = KeyboardInterrupt
        group.stop.return_value = False
        with patch(
            "domains.ads.management.commands.run_ads_workers.signal.signal", return_value="old"
        ) as register:
            with self.assertRaises(CommandError):
                self.command().watch(group)
        self.assertEqual(register.call_args.args, (signal.SIGTERM, "old"))

    def test_nonmain_thread_does_not_register_process_signal_handlers(self):
        group = self.group()
        group.start.side_effect = KeyboardInterrupt
        errors = []

        def run():
            try:
                self.command().watch(group)
            except Exception as exc:
                errors.append(exc)

        with patch("domains.ads.management.commands.run_ads_workers.signal.signal") as register:
            thread = threading.Thread(target=run)
            thread.start()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        register.assert_not_called()
        group.stop.assert_called_once_with()

    def test_start_failure_still_stops_and_restores_handler(self):
        group = self.group()
        group.start.side_effect = RuntimeError("fixture-start-failure")
        with patch(
            "domains.ads.management.commands.run_ads_workers.signal.signal", return_value="old"
        ) as register:
            with self.assertRaises(RuntimeError):
                self.command().watch(group)
        group.stop.assert_called_once_with()
        self.assertEqual(register.call_args.args, (signal.SIGTERM, "old"))
