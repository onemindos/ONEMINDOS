# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock

from onemind_app_sdk import AppClient, define_app


def test_a_hello_app_has_a_narrow_sdk():
    gateway = Mock()
    gateway.actions.request.return_value = {"state": "awaiting_approval"}
    app = AppClient(gateway, {"api": "fixture"})
    assert define_app({"notifications": [{"id": "hello"}]}) == {"notifications": [{"id": "hello"}]}
    assert not hasattr(app, "approve") and not hasattr(app, "gateway")
    assert app.own_secret("api") == "fixture" and app.own_secret("other-app/api") is None
    assert app.request_action("app.install", "hello")["state"] == "awaiting_approval"
    app.file_roots()
    assert gateway.call.call_args.args[0].path == "/v1/files/roots"
