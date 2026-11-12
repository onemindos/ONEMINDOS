# SPDX-License-Identifier: Apache-2.0
"""Load a hyphenated script from os/update/ as a module (the scripts run with python3 -I)."""
import importlib.util, os

UPDATE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(UPDATE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fixture(name):
    return os.path.join(FIX, name)
