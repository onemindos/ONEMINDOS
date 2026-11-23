# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for #126's owner-approved offline bundle orchestration."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('offline_bundle', ROOT / 'apps/_bundles/offline-knowledge/install.py')
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class OfflineBundleTests(unittest.TestCase):
    def catalog(self):
        return [{'id': a['id'], 'tier': 'verified', 'status': 'not_installed',
                 'scan': {'result': 'pass', 'scanned_at': datetime.now(timezone.utc).isoformat()}}
                for a in json.loads(bundle.BUNDLE.read_text())['apps']]

    def run_install(self, replies, **kwargs):
        replies = [(200, kwargs.get('catalog', self.catalog())), *replies]
        with patch.dict(os.environ, {'ONEMIND_TOKEN': 'test-token'}), \
                patch.object(bundle, 'call', side_effect=replies) as call, \
                patch.object(bundle.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            result = bundle.main(['--gateway', 'https://box.example', *kwargs.get('args', [])])
        return result, call

    def test_profiles_use_declared_names_and_types(self):
        data = json.loads(bundle.BUNDLE.read_text())
        for profile in data['profiles']:
            steps = bundle.plan(data, profile, set())
            for app_id, settings, _ in steps:
                if app_id == 'kiwix':
                    self.assertIn('zims', settings)
                    if 'reserve_mb' in settings:
                        self.assertIsInstance(settings['reserve_mb'], int)
                if app_id == 'library-chat':
                    self.assertIn('model', settings)
                    self.assertIsInstance(settings['sources'], int)
                self.assertTrue(all(k == k.lower() for k in settings))

    def test_install_then_configure_and_never_approve(self):
        result, call = self.run_install([(201, {'id': 'install', 'state': 'awaiting_approval'}),
                                       (200, {'id': 'install', 'state': 'succeeded'}),
                                       (201, {'id': 'configure', 'state': 'succeeded'})],
                                      args=['--skip', 'offline-maps', '--skip', 'kolibri', '--skip', 'ollama', '--skip', 'library-chat'])
        self.assertEqual(result, 0)
        posted = [c.args[4] for c in call.call_args_list if c.args[2] == 'POST']
        self.assertEqual([p['type'] for p in posted], ['app.install', 'app.configure'])
        self.assertEqual(posted[0]['params'], {'app_id': 'kiwix'})
        self.assertIn('zims', posted[1]['params']['settings'])
        self.assertTrue(all('reason' not in p for p in posted))
        self.assertFalse(any('approve' in c.args[3] for c in call.call_args_list))

    def test_required_refusal_stops_before_configure(self):
        result, call = self.run_install([(409, {'message': 'scan blocked'})])
        self.assertEqual(result, 1)
        self.assertEqual(call.call_count, 2)

    def test_optional_failure_continues(self):
        result, call = self.run_install([(409, {'message': 'blocked'}),
                                       (201, {'id': 'next', 'state': 'succeeded'})],
                                      args=['--skip', 'kiwix', '--skip', 'offline-maps', '--skip', 'library-chat'])
        self.assertEqual(result, 0)
        self.assertEqual([c.args[4]['params']['app_id'] for c in call.call_args_list if c.args[2] == 'POST'], ['kolibri', 'ollama'])

    def test_required_configure_failure_stops(self):
        result, call = self.run_install([(201, {'id': 'install', 'state': 'succeeded'}),
                                       (201, {'id': 'configure', 'state': 'failed'})])
        self.assertEqual(result, 1)
        self.assertEqual(call.call_count, 3)

    def test_polling_server_error_keeps_original_id(self):
        with patch.object(bundle, 'call', side_effect=[(201, {'id': 'a', 'state': 'awaiting_approval'}),
                                                       (503, {'message': 'retry'}),
                                                       (200, {'id': 'a', 'state': 'succeeded'})]) as call, \
                patch.object(bundle.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(bundle.request_action('https://box.example', 'test', 'app.install', {'app_id': 'kiwix'}, 1, None))
        self.assertEqual([c.args[3] for c in call.call_args_list[1:]], ['/v1/actions/a', '/v1/actions/a'])

    def test_polling_auth_error_fails(self):
        result, _ = self.run_install([(201, {'id': 'a', 'state': 'awaiting_approval'}), (401, {})])
        self.assertEqual(result, 1)

    def test_unknown_outcome_is_terminal(self):
        result, call = self.run_install([(201, {'id': 'a', 'state': 'outcome_unknown'})])
        self.assertEqual(result, 1)
        self.assertEqual(call.call_count, 2)

    def test_timeout_does_not_request_next_app(self):
        with patch.object(bundle.time, 'monotonic', side_effect=[0, 3601]):
            result, call = self.run_install([(201, {'id': 'a', 'state': 'awaiting_approval'})], args=['--wait-hours', '1'])
        self.assertEqual(result, 1)
        self.assertEqual(call.call_count, 2)

    def test_dry_run_files_no_requests(self):
        with patch.object(bundle, 'call') as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bundle.main(['--gateway', 'https://box.example', '--dry-run']), 0)
        call.assert_not_called()

    def test_invalid_wait_rejected(self):
        for value in ('0', '-1', 'nan', 'inf', '169'):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                bundle.main(['--gateway', 'https://box.example', '--wait-hours', value])

    def test_preflight_rejects_required_problems_before_any_actions(self):
        for problem in ('missing', 'blocked', 'unscanned', 'failed_scan', 'stale', 'future', 'invalid', 'stopped'):
            with self.subTest(problem=problem):
                catalog = self.catalog()
                row = catalog[0]
                if problem == 'missing':
                    catalog.pop(0)
                elif problem == 'blocked':
                    row['tier'] = 'blocked'
                elif problem == 'unscanned':
                    row['scan'] = None
                elif problem == 'failed_scan':
                    row['scan']['result'] = 'fail'
                elif problem in ('stale', 'future'):
                    row['scan']['scanned_at'] = (datetime.now(timezone.utc) + timedelta(days=-8 if problem == 'stale' else 1)).isoformat()
                elif problem == 'invalid':
                    row['scan']['scanned_at'] = '2026-01-01T00:00:00'
                else:
                    row['status'] = 'stopped'
                result, call = self.run_install([], catalog=catalog)
                self.assertEqual(result, 1)
                self.assertEqual(call.call_count, 1)

    def test_preflight_skips_optional_blocked_without_creating_action(self):
        catalog = self.catalog()
        next(row for row in catalog if row['id'] == 'kolibri')['tier'] = 'blocked'
        result, call = self.run_install([(201, {'id': 'a', 'state': 'succeeded'})], catalog=catalog,
                                       args=['--skip', 'kiwix', '--skip', 'offline-maps', '--skip', 'library-chat'])
        self.assertEqual(result, 0)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args_list[1].args[4]['params'], {'app_id': 'ollama'})

    def test_already_installed_is_configured_without_reinstall(self):
        catalog = self.catalog()
        for row in catalog:
            row['status'] = 'installed'
        result, call = self.run_install([(201, {'id': 'a', 'state': 'succeeded'}),
                                       (201, {'id': 'b', 'state': 'succeeded'})], catalog=catalog)
        self.assertEqual(result, 0)
        self.assertEqual([c.args[4]['type'] for c in call.call_args_list[1:]], ['app.configure', 'app.configure'])

    def test_catalog_api_failure_files_no_actions(self):
        with patch.dict(os.environ, {'ONEMIND_TOKEN': 'test-token'}), \
                patch.object(bundle, 'call', return_value=(401, {})) as call, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(bundle.main(['--gateway', 'https://box.example']), 2)
        self.assertEqual(call.call_count, 1)

    def test_redirect_never_forwards_owner_token(self):
        received = []
        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')
            def log_message(self, *args):
                pass
        destination = ThreadingHTTPServer(('127.0.0.1', 0), Destination)
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', f'http://127.0.0.1:{destination.server_port}/stolen')
                self.end_headers()
            do_POST = do_GET
            def log_message(self, *args):
                pass
        origin = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        workers = [threading.Thread(target=server.serve_forever, daemon=True) for server in (origin, destination)]
        for worker in workers:
            worker.start()
        try:
            for method in ('GET', 'POST'):
                code, _ = bundle.call(f'http://127.0.0.1:{origin.server_port}', 'test-owner-token', method, '/v1/actions')
                self.assertEqual(code, 302)
            self.assertEqual(received, [])
        finally:
            for server in (origin, destination):
                server.shutdown()
                server.server_close()
            for worker in workers:
                worker.join(timeout=2)
