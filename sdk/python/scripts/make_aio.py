# SPDX-License-Identifier: Apache-2.0
"""Derive src/onemind_sdk/aio.py from client.py: the same surface with `await`.

    python3 scripts/make_aio.py           # rewrite aio.py
    python3 scripts/make_aio.py --check   # exit 1 when aio.py is stale (CI)
"""

import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "src" / "onemind_sdk"

SIMPLE = [
    ('"""The synchronous client. `onemind_sdk.aio.Client` is the same surface with `await`."""',
     '"""The asyncio client: the same surface as onemind_sdk.Client, with `await`.\n\n'
     'Derived from client.py by sdk/python/scripts/make_aio.py; edit client.py and rerun it."""'),
    ("import time\n", "import asyncio\nimport time\n"),
    ("from collections.abc import Callable, Iterator", "from collections.abc import AsyncIterator, Awaitable, Callable"),
    ("sleep: Callable[[float], None] = time.sleep", "sleep: Callable[[float], Awaitable[None]] = asyncio.sleep"),
    ("refresh: Callable[[], str | None] | None", "refresh: Callable[[], Awaitable[str | None]] | None"),
    ("transport: httpx.BaseTransport | None", "transport: httpx.AsyncBaseTransport | None"),
    ("httpx.Client(", "httpx.AsyncClient("),
    ("    def __enter__(self) -> Client:\n        return self\n\n    def __exit__(self, *exc: object) -> None:\n"
     "        self.close()\n\n    def close(self) -> None:\n        self._http.close()",
     "    async def __aenter__(self) -> Client:\n        return self\n\n    async def __aexit__(self, *exc: object) -> None:\n"
     "        await self.close()\n\n    async def close(self) -> None:\n        await self._http.aclose()"),
    ("    def subscribe(", "    async def subscribe("),
    ("-> Iterator[dict]:", "-> AsyncIterator[dict]:"),
    ("return self._once(r)", "return await self._once(r)"),
    ("return self.request(r)[0]", "return (await self.request(r))[0]"),
    ("resp = self._http.request(", "resp = await self._http.request("),
    ("self._sleep(core.backoff", "await self._sleep(core.backoff"),
    ("new = self._refresh()", "new = await self._refresh()"),
    ("self.c.instance.get()", "await self.c.instance.get()"),
    ("return self._decide(", "return await self._decide("),
    ("got = self.get(action_id)", "got = await self.get(action_id)"),
    ("a = self.get(action_id)", "a = await self.get(action_id)"),
    ("self.c._sleep(every)", "await self.c._sleep(every)"),
    ("self.c._sleep(delay", "await self.c._sleep(delay"),
    ("bool((self.call(", "bool((await self.call("),
    ("with self.c._http.stream(", "async with self.c._http.stream("),
    ("resp.read()", "await resp.aread()"),
    ("for text in resp.iter_text():", "async for text in resp.aiter_text():"),
]
ASYNC_DEFS = ["healthz", "_once", "request", "call", "get", "list", "approve", "deny", "_decide", "wait", "verify"]


def derive(src: str) -> str:
    for a, b in SIMPLE:
        if a not in src:
            raise SystemExit(f"make_aio: pattern not found in client.py: {a[:60]!r}")
        src = src.replace(a, b)
    for name in ASYNC_DEFS:
        src = re.sub(rf"(\n    )def {name}\(", rf"\1async def {name}(", src)
    src = src.replace("self.c.call(", "await self.c.call(").replace("self.c.request(", "await self.c.request(")
    return src


def main() -> int:
    out = derive((PKG / "client.py").read_text())
    target = PKG / "aio.py"
    if "--check" in sys.argv:
        if not target.exists() or target.read_text() != out:
            print("sdk/python/src/onemind_sdk/aio.py is stale: run `make -C sdk gen`", file=sys.stderr)
            return 1
        return 0
    target.write_text(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
