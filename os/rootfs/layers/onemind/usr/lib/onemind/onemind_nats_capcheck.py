# SPDX-License-Identifier: Apache-2.0
"""onemind-nats-capcheck NATS_CONF: refuse a hub nats.conf that turns JetStream on without a cap (#601).

Run as root by onemind-nats-files (through the onemind-nats-capcheck wrapper) before every start and
reload of onemind-nats.service; exit 1 fails the unit, so nats-server never runs. Without a cap
nats-server takes the free disk and 75 % of RAM (nats-server v2.15.3 server/jetstream.go,
dynJetStreamConfig), and memory streams are lost on a restart.

The file is read the way nats-server v2.15.3 reads it (conf/lex.go, conf/parse.go, server/opts.go
parseJetStream), not line by line, because nats-server:
- lowercases every key before it looks at it, so `JetStream` and `MAX_FILE_STORE` count;
- turns JetStream on for the bare words true/yes/on in any case and the strings enabled/enable;
- reads `max_mem_store`/`max_mem` and `max_file` as the same limits, and only inside the block;
- keeps the last of two keys written the same way, but walks two keys that differ only in case in
  random order (a Go map), so neither can be trusted;
- reads `include` files relative to the including file.

Pass: no top-level `jetstream` key (a box set up before JetStream), or one that is off (false/no/off,
disabled/disable). Refuse: on as a plain value (no block, no cap); a block without exactly one
`max_file_store` above 0 and exactly one `max_memory_store` equal to 0 (file storage only); a short
alias; and anything this check cannot read with certainty (a variable, a block string, an escape in a
bare word, a missing include, a parse error). It fails closed: when in doubt, NATS does not start.
"""

from __future__ import annotations

import os
import re
import sys

SPACE = " \t"           # conf/lex.go isWhitespace
NEWLINE = "\r\n"        # conf/lex.go isNL
BOOLS = {"true": True, "yes": True, "on": True, "false": False, "no": False, "off": False}
JS_ON, JS_OFF = ("enabled", "enable"), ("disabled", "disable")         # opts.go parseJetStream
MEM_KEYS = ("max_memory_store", "max_mem_store", "max_mem")
FILE_KEYS = ("max_file_store", "max_file")
INT64_MAX = (1 << 63) - 1
MAX_INCLUDE_DEPTH = 8
# conf/parse.go itemInteger suffixes (lowercased) and their multipliers.
_UNITS = {"": 1}
for _i, _s in enumerate("kmgtpe", start=1):
    _UNITS[_s] = 1000 ** _i
    for _bin in ("b", "i", "ib"):
        _UNITS[_s + _bin] = 1024 ** _i


class Refused(Exception):
    """The conf turns JetStream on without a cap, or cannot be read with certainty."""


class Bare(str):
    """An unquoted value as written (a bool, a number with a unit, a word or a $variable)."""


class Quoted(str):
    """A quoted string value."""


class _Parser:
    def __init__(self, text: str, path: str, depth: int):
        self.s, self.i, self.path, self.depth = text, 0, path, depth

    def _c(self, k: int = 0) -> str:
        j = self.i + k
        return self.s[j] if j < len(self.s) else ""

    def _at(self, chars: str) -> bool:
        c = self._c()
        return c != "" and c in chars

    def fail(self, msg: str):
        raise Refused(f"{self.path} line {self.s.count(chr(10), 0, self.i) + 1}: {msg}")

    def _comment(self) -> bool:
        """Skip a # or // comment up to (not over) the end of the line."""
        if self._c() == "#" or (self._c() == "/" and self._c(1) == "/"):
            while self._c() and not self._at(NEWLINE):
                self.i += 1
            return True
        return False

    def _skip_lines(self) -> None:
        """Skip spaces, new lines and comments, where a key or an array value may start."""
        while True:
            if self._c().isspace():
                self.i += 1
            elif not self._comment():
                return

    def body(self, in_block: bool) -> dict:
        d: dict = {}
        while True:
            self._skip_lines()
            c = self._c()
            if c == "":
                if in_block:
                    self.fail("the file ends inside a block")
                return d
            if c == "}":
                if not in_block:
                    self.fail("'}' without a block")
                self.i += 1
                return d
            if c in ":=":
                self.fail(f"unexpected {c!r}")
            if c == "{" or c == "]":
                self.fail(f"unexpected {c!r} where a key should be")
            key = self._key()
            if key.lower() == "include" and self._c().isspace():
                d.update(self._include())
                self._value_end(in_block)
                continue
            while self._c().isspace():  # lexKeyEnd: any space, new lines too
                self.i += 1
            if self._c() == "":
                self.fail(f"{key!r} has no value")
            if self._at(":="):
                self.i += 1
            d[key] = self.value()  # the same key written the same way: the last one wins (parse.go)
            self._value_end(in_block)

    def _key(self) -> str:
        q = self._c()
        if q in ("\"", "'"):
            j = self.s.find(q, self.i + 1)
            if j < 0:
                self.fail("unterminated quoted key")
            key, self.i = self.s[self.i + 1:j], j + 1
            return key
        j = self.i
        while self._c() and not self._c().isspace() and not self._at(":="):
            self.i += 1
        return self.s[j:self.i]  # lexKey: a bare key ends at a space or a separator, nothing else

    def _include(self) -> dict:
        while self._at(SPACE):
            self.i += 1
        q = self._c()
        if q in ("\"", "'"):
            j = self.s.find(q, self.i + 1)
            if j < 0:
                self.fail("unterminated include")
            name, self.i = self.s[self.i + 1:j], j + 1
        else:
            j = self.i
            while self._c() and not self._at(NEWLINE + SPACE + ";}'"):
                self.i += 1
            name = self.s[j:self.i]
        if not name:
            self.fail("include without a file")
        if self.depth >= MAX_INCLUDE_DEPTH:
            self.fail("includes nested too deep")
        # Go filepath.Join(dir, name): an absolute name stays under dir, unlike os.path.join.
        return parse_file(os.path.normpath(os.path.dirname(self.path) + "/" + name), self.depth + 1)

    def _value_end(self, in_block: bool) -> None:
        while self._at(SPACE):
            self.i += 1
        self._comment()
        c = self._c()
        if c in (";", ","):
            self.i += 1
        elif c == "}" and in_block:
            pass  # body() closes the block
        elif not (c == "" or c in NEWLINE):
            self.fail(f"a value must end with a new line, ',' or ';', not {c!r}")

    def value(self):
        while self._at(SPACE):
            self.i += 1
        c = self._c()
        if c == "" or c in NEWLINE:
            self.fail("a key without a value")
        if c == "{":
            self.i += 1
            return self.body(in_block=True)
        if c == "[":
            self.i += 1
            return self._array()
        if c == "'":
            j = self.s.find("'", self.i + 1)
            if j < 0:
                self.fail("unterminated string")
            v, self.i = self.s[self.i + 1:j], j + 1
            return Quoted(v)
        if c == "\"":
            return self._dq()
        if c == "(":
            self.fail("block strings are not read by this check")
        j = self.i
        while self._c() and not self._at(NEWLINE + SPACE + ";,]}'\\"):
            self.i += 1
        if self._at("'\\"):
            self.fail("a quote or an escape inside a bare word is not read by this check")
        return Bare(self.s[j:self.i])

    def _dq(self) -> Quoted:
        self.i += 1
        out = []
        esc = {"t": "\t", "n": "\n", "r": "\r", "\"": "\"", "\\": "\\"}
        while True:
            c = self._c()
            if c == "":
                self.fail("unterminated string")
            self.i += 1
            if c == "\"":
                return Quoted("".join(out))
            if c != "\\":
                out.append(c)
                continue
            e = self._c()
            self.i += 1
            if e != "" and e in esc:
                out.append(esc[e])
            elif e == "x" and re.fullmatch(r"[0-9A-Fa-f]{2}", self.s[self.i:self.i + 2]):
                out.append(chr(int(self.s[self.i:self.i + 2], 16)))
                self.i += 2
            else:
                self.fail("invalid escape in a string")

    def _array(self) -> list:
        out: list = []
        while True:
            self._skip_lines()
            if self._c() == "]":
                self.i += 1
                return out
            if self._c() in ("", ","):
                self.fail("bad array")
            out.append(self.value())
            while self._at(SPACE):
                self.i += 1
            self._comment()
            if self._c() == "]":
                self.i += 1
                return out
            if not self._at("," + NEWLINE):
                self.fail("an array value must end with ',', a new line or ']'")
            self.i += 1


def parse_file(path: str, depth: int = 0) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise Refused(f"cannot read {path}: {e.strerror}") from None
    except UnicodeDecodeError:
        raise Refused(f"{path} is not UTF-8") from None
    return _Parser(text, path, depth).body(in_block=False)


def storage_size(v) -> int | None:
    """What nats-server makes of a JetStream size (parse.go itemInteger; opts.go getStorageSize), or
    None when it would fail or this check cannot tell."""
    if isinstance(v, Bare):
        m = re.fullmatch(r"(-?\d+)([kKmMgGtTpPeE][bBiI]*)?", v)
        if not m or (m.group(2) or "").lower() not in _UNITS:
            return None
        n = int(m.group(1)) * _UNITS[(m.group(2) or "").lower()]
    elif isinstance(v, Quoted):
        if v == "":
            return 0
        m = re.fullmatch(r"([+-]?\d+)([KMGT])", v)
        if not m:
            return None
        n = int(m.group(1)) << {"K": 10, "M": 20, "G": 30, "T": 40}[m.group(2)]
    else:
        return None
    return n if -INT64_MAX - 1 <= n <= INT64_MAX else None  # Go would wrap around: refuse


def _one(d: dict, names: tuple[str, ...], what: str):
    hits = [(k, v) for k, v in d.items() if k.lower() in names]
    if len(hits) > 1:
        raise Refused(f"{what} is set more than once ({', '.join(k for k, _ in hits)}); "
                      "nats-server would pick one at random")
    return hits[0] if hits else None


def check(conf: str) -> None:
    """Raise Refused when the conf would start JetStream without a cap."""
    top = parse_file(conf)
    js = _one(top, ("jetstream",), "jetstream")
    if js is None:
        return
    v = js[1]
    if isinstance(v, dict):
        _check_block(conf, v)
        return
    word = v.lower() if isinstance(v, str) else None
    if isinstance(v, Bare) and word in BOOLS:
        if BOOLS[word]:
            raise Refused(f"{conf} turns JetStream on ({js[0]}: {v}) without a block, so with no cap")
        return
    if word in JS_OFF:
        return
    if word in JS_ON:
        raise Refused(f"{conf} turns JetStream on ({js[0]}: {v}) without a block, so with no cap")
    raise Refused(f"{conf}: cannot read the jetstream value {v!r}")


def _check_block(conf: str, block: dict) -> None:
    for k in block:
        if k.lower() in MEM_KEYS + FILE_KEYS and k.lower() not in ("max_memory_store", "max_file_store"):
            raise Refused(f"{conf} uses a short alias ({k}) for a JetStream limit; "
                          "write max_file_store and max_memory_store")
    f = _one(block, FILE_KEYS, "max_file_store")
    if f is None:
        raise Refused(f"{conf} turns JetStream on without max_file_store")
    size = storage_size(f[1])
    if size is None or size <= 0:
        raise Refused(f"{conf}: max_file_store {f[1]!r} is not a size above 0")
    m = _one(block, MEM_KEYS, "max_memory_store")
    if m is None:
        raise Refused(f"{conf} has no max_memory_store: 0 (file storage only)")
    if storage_size(m[1]) != 0:
        raise Refused(f"{conf}: max_memory_store is {m[1]!r}, not 0 (file storage only)")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: onemind-nats-capcheck NATS_CONF", file=sys.stderr)
        return 2
    if not os.path.isfile(args[0]):
        return 0  # no conf: onemind-nats has nothing to start
    try:
        check(args[0])
    except Refused as e:
        print(f"onemind-nats: {e}; refusing to start (#601)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
