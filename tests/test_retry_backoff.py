"""Exercise actual retry callbacks with camera failures and a controlled clock."""
import ast
import asyncio
import datetime
import logging
import os
import pathlib
import tempfile
from typing import Optional, Callable
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).parents[1] / "custom_components/tapo_control"


def load(name, filename, env):
    tree = ast.parse((ROOT / filename).read_text())
    node = next(n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT / filename), "exec"), env)
    return env[name]


class Unresolvable(Exception):
    pass


class RetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = Mock(return_value=1000)
        self.controller = SimpleNamespace(getRecordingsList=Mock(return_value=[]))
        self.device = {
            "name": "Test camera", "controller": self.controller,
            "enabled": True, "runningMediaSync": False, "isDownloadingStream": False,
            "initialMediaScanDone": False, "initialMediaScanRunning": False,
            "isChild": False, "mediaScanResult": {}, "lastTimeSync": 0,
        }
        async def executor(fn, *args):
            return fn(*args)
        self.hass = SimpleNamespace(
            data={"tapo": {"test": self.device}}, async_add_executor_job=executor)
        self.entry = SimpleNamespace(entry_id="test", data={"hours": ""},
                                     async_create_background_task=Mock())
        self.env = dict(asyncio=asyncio, datetime=datetime, time=SimpleNamespace(monotonic=self.clock),
                        LOGGER=logging.getLogger("test_retry"), DOMAIN="tapo",
                        ENABLE_MEDIA_SYNC="enabled", MEDIA_SYNC_HOURS="hours",
                        hass=self.hass, entry=self.entry, host="test-camera", timeCorrection=0,
                        TIME_SYNC_PERIOD=3600, Unresolvable=Unresolvable,
                        async_update_sync_sensors=AsyncMock(), getRecordings=AsyncMock(),
                        getRecording=AsyncMock(), findMedia=AsyncMock(),
                        preloadRecordingThumbnails=AsyncMock(), mediaCleanup=AsyncMock())
        self.delay = load("retryDelay", "utils.py", self.env)
        self.sync = load("mediaSync", "__init__.py", self.env)
        self.scan = load("scheduleAll", "utils.py", self.env)
        self.clock_error = load("handleTimeSyncError", "__init__.py", self.env)

    def test_delays_grow_and_cap(self):
        self.assertEqual([self.delay(n) for n in (1, 2, 3, 4, 5, 9999)],
                         [300, 600, 1200, 2400, 3600, 3600])

    async def test_catalog_failure_skips_polls_then_success_resets(self):
        self.controller.getRecordingsList.side_effect = TimeoutError("catalog")
        await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertEqual(self.device["mediaSyncFailures"], 1)
        self.assertFalse(self.device["runningMediaSync"])
        self.assertNotIn("lastMediaSyncSuccess", self.device)
        self.clock.return_value = 1299
        await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertEqual(self.controller.getRecordingsList.call_count, 1)
        self.clock.return_value = 1300
        await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertEqual(self.device["mediaSyncRetryAt"], 1900)
        self.controller.getRecordingsList.side_effect = None
        self.clock.return_value = 1900
        await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertEqual(self.device["mediaSyncFailures"], 0)
        self.assertEqual(self.device["mediaSyncRetryAt"], 0)
        self.assertGreater(self.device["lastMediaSyncSuccess"], 0)

    def recordings(self):
        self.controller.getRecordingsList.return_value = [{"day": {"date": "20261029"}}]
        self.env["getRecordings"].return_value = [
            {"clip": {"startTime": 1, "endTime": 2}},
            {"clip": {"startTime": 3, "endTime": 4}},
        ]

    async def test_download_failure_aborts_pass_and_keeps_running_until_cleanup(self):
        self.recordings()
        async def fail(*args):
            self.assertTrue(self.device["runningMediaSync"])
            raise TimeoutError("download")
        self.env["getRecording"].side_effect = fail
        await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertEqual(self.env["getRecording"].await_count, 1)
        self.assertNotIn("lastMediaSyncSuccess", self.device)
        self.assertEqual(self.device["mediaSyncFailures"], 1)
        self.assertFalse(self.device["runningMediaSync"])

    async def test_in_progress_recording_does_not_back_off(self):
        self.recordings()
        self.env["getRecording"].side_effect = Unresolvable("Recording is currently in progress.")
        await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertEqual(self.env["getRecording"].await_count, 2)
        self.assertEqual(self.device["mediaSyncFailures"], 0)

    async def test_unavailable_clip_does_not_starve_later_recordings(self):
        self.recordings()
        self.env["getRecording"].side_effect = [Unresolvable("File missing"), None]
        await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertEqual(self.env["getRecording"].await_count, 2)
        self.assertEqual(self.device["mediaSyncFailures"], 0)

    async def test_cancellation_propagates_and_clears_running(self):
        self.recordings()
        self.env["getRecording"].side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertFalse(self.device["runningMediaSync"])
        self.assertNotIn("lastMediaSyncSuccess", self.device)
        self.assertNotIn("mediaSyncFailures", self.device)

    async def test_disabling_during_sync_does_not_record_success(self):
        self.recordings()
        async def disable(*args):
            self.device["enabled"] = False
        self.env["getRecording"].side_effect = disable
        await asyncio.create_task(self.sync(None, self.entry, self.device))
        self.assertEqual(self.env["getRecording"].await_count, 1)
        self.assertNotIn("lastMediaSyncSuccess", self.device)

    async def test_initial_catalog_failure_backs_off_from_end_of_request(self):
        def fail():
            self.clock.return_value += 30
            raise TimeoutError("initial catalog")
        self.controller.getRecordingsList.side_effect = fail
        await self.scan(self.hass, self.device, self.entry, self.sync)
        self.assertEqual(self.device["mediaScanFailures"], 1)
        self.assertEqual(self.device["lastMediaScanAttempt"], 1030)
        self.clock.return_value = 1329
        await self.scan(self.hass, self.device, self.entry, self.sync)
        self.assertEqual(self.controller.getRecordingsList.call_count, 1)
        self.clock.return_value = 1330
        await self.scan(self.hass, self.device, self.entry, self.sync)
        self.assertEqual(self.device["mediaScanFailures"], 2)
        self.assertFalse(self.device["initialMediaScanRunning"])

    async def test_find_media_failure_and_success_update_retry_state(self):
        find = load("findMedia", "utils.py", self.env)
        self.controller.getRecordingsList.side_effect = TimeoutError("catalog")
        await find(self.hass, self.device, self.entry)
        self.assertEqual(self.device["mediaScanFailures"], 1)
        self.assertFalse(self.device["initialMediaScanDone"])
        self.env["mediaCleanup"].assert_not_awaited()
        self.controller.getRecordingsList.side_effect = None
        await find(self.hass, self.device, self.entry)
        self.assertTrue(self.device["initialMediaScanDone"])
        self.assertEqual(self.device["mediaScanFailures"], 0)

    async def test_full_playback_service_aborts_scan_before_retrying_other_dates(self):
        find = load("findMedia", "utils.py", self.env)
        self.env["getRecordings"].side_effect = Exception("USER_ID_FULL (-71101)")
        await find(self.hass, self.device, self.entry,
                   [{"day": {"date": "20261028"}}, {"day": {"date": "20261029"}}])
        self.assertEqual(self.env["getRecordings"].await_count, 1)
        self.assertEqual(self.device["mediaScanFailures"], 1)
        self.assertFalse(self.device["initialMediaScanDone"])
        self.env["mediaCleanup"].assert_not_awaited()

    async def test_capacity_error_on_day_retry_also_aborts_scan(self):
        self.env["asyncio"] = SimpleNamespace(sleep=AsyncMock())
        find = load("findMedia", "utils.py", self.env)
        self.env["getRecordings"].side_effect = [TimeoutError("day"), Exception("USER_ID_FULL")]
        await find(self.hass, self.device, self.entry,
                   [{"day": {"date": "20261028"}}, {"day": {"date": "20261029"}}])
        self.assertEqual(self.env["getRecordings"].await_count, 2)
        self.assertEqual(self.device["mediaScanFailures"], 1)
        self.env["mediaCleanup"].assert_not_awaited()

    async def check_download_failure(self, action, expected_error):
        with tempfile.TemporaryDirectory() as folder:
            self.controller.getTimeCorrection = Mock(return_value=0)
            self.controller.getRecordings = Mock(return_value=[])
            self.hass.bus = SimpleNamespace(fire=Mock())
            downloader = SimpleNamespace(downloadFile=AsyncMock(return_value={
                "currentAction": action, "fileName": folder + "/1-2.mp4", "errorCode": -71101}))
            self.env.update(HomeAssistant=object, Tapo=object, Optional=Optional, Callable=Callable,
                            os=os, pathlib=pathlib, partial=__import__('functools').partial,
                            getColdDirPathForEntry=lambda *args: folder,
                            getFileName=lambda *args, **kwargs: "1-2",
                            getColdFile=lambda *args, **kwargs: folder + "/1-2.mp4",
                            Downloader=Mock(return_value=downloader), processDownloadStatus=Mock(),
                            processDownload=AsyncMock())
            download = load("getRecording", "utils.py", self.env)
            with self.assertRaises(expected_error):
                await download(self.hass, self.controller, "test", self.device, "20261029", 1, 2)
            self.hass.bus.fire.assert_not_called()
            self.env["processDownload"].assert_not_awaited()
            self.assertFalse(self.device["isDownloadingStream"])

    async def test_busy_transfer_is_not_reported_as_a_download(self):
        await self.check_download_failure("Camera busy", RuntimeError)

    async def test_incomplete_transfer_is_not_reported_as_a_download(self):
        await self.check_download_failure("Giving up", TimeoutError)

    def test_blank_onvif_fault_backs_off_and_preserves_last_success(self):
        fault = type("Fault", (Exception,), {"__module__": "zeep.exceptions"})
        self.clock_error(fault(""))
        self.assertEqual(self.device["timeSyncRetryAt"], 1300)
        self.clock_error(fault(""))
        self.assertEqual(self.device["timeSyncRetryAt"], 1600)
        self.assertEqual(self.device["lastTimeSync"], 0)
        self.clock_error(fault("error time"))
        self.assertEqual(self.device["timeSyncRetryAt"], 87400)

    def test_time_sync_update_gate_respects_retry_deadline(self):
        tree = ast.parse((ROOT / "__init__.py").read_text())
        gate = next(n.test for n in ast.walk(tree) if isinstance(n, ast.If)
                    and "TIME_SYNC_PERIOD" in ast.unparse(n.test))
        expression = compile(ast.Expression(gate), "time-sync-gate", "eval")
        self.env["ts"] = 10000
        self.device["timeSyncRetryAt"] = 1300
        self.assertFalse(eval(expression, self.env))
        self.clock.return_value = 1300
        self.assertTrue(eval(expression, self.env))
        self.device["lastTimeSync"] = 9999
        self.assertFalse(eval(expression, self.env))

    def test_startup_clock_sync_respects_an_earlier_coordinator_failure(self):
        tree = ast.parse((ROOT / "__init__.py").read_text())
        gate = next(n.test for n in ast.walk(tree) if isinstance(n, ast.If)
                    and ast.unparse(n.test).startswith("enableTimeSync and"))
        expression = compile(ast.Expression(gate), "startup-time-sync-gate", "eval")
        self.env["enableTimeSync"] = True
        self.clock_error(TimeoutError("coordinator sync"))
        self.assertFalse(eval(expression, self.env))
        self.clock.return_value = self.device["timeSyncRetryAt"]
        self.assertTrue(eval(expression, self.env))
        self.env["enableTimeSync"] = False
        self.assertFalse(eval(expression, self.env))

    async def test_watchdog_defers_retry_without_releasing_running_guard(self):
        self.env.update(ts=2000, MEDIA_SYNC_WATCHDOG_SECONDS=300)
        self.hass.async_create_task = lambda coro: asyncio.create_task(coro)
        watchdog = load("_check_media_sync_watchdog", "__init__.py", self.env)
        task = Mock()
        task.done.return_value = False
        task.cancelling.return_value = False
        self.device.update(runningMediaSync=True, mediaSyncTask=task,
                           lastMediaSyncActivity=1000)
        await watchdog(self.device)
        task.cancel.assert_called_once()
        self.assertTrue(self.device["runningMediaSync"])
        self.assertEqual(self.device["mediaSyncRetryAt"], 1300)
        self.assertEqual(self.device["mediaSyncStallCount"], 1)
        await asyncio.sleep(0)

    async def test_successful_clock_sync_resets_retry_state(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        local = Mock(); local.dst.return_value = datetime.timedelta(0)
        self.env.update(TIME_SYNC_DST="dst", TIME_SYNC_NDST="ndst",
                        dt_util=SimpleNamespace(now=lambda: local, utcnow=lambda: now,
                                                as_local=lambda value: value))
        self.device.update(onvifManagement=SimpleNamespace(
            create_type=lambda name: SimpleNamespace(), SetSystemDateAndTime=AsyncMock()),
            timezoneOffset=0, dst=0, ndst=0, timeSyncFailures=3, timeSyncRetryAt=3000)
        sync_time = load("syncTime", "utils.py", self.env)
        await sync_time(self.hass, "test")
        self.assertEqual(self.device["timeSyncFailures"], 0)
        self.assertEqual(self.device["timeSyncRetryAt"], 0)
        self.assertEqual(self.device["lastTimeSync"], now.timestamp())
