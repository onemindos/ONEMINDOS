# SPDX-License-Identifier: Apache-2.0
"""onemind-nats-reload (#620): a reload cannot change the NATS system account, so a changed system_account
line must restart NATS, or every later accounts change is ignored until the next reboot. Real nats-server."""
import os, shutil, signal, socket, stat, subprocess, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind-nats-reload")
UNIT = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-nats-reload.service")

PLAIN = 'accounts { ONEMIND { users: [{user: u1, password: p1}] } }\n'
WITH_SYS = ('accounts {\n ONEMIND { users: [{user: u1, password: p1}] }\n SYS { users: [{user: s, password: sp}] }\n}\n'
            'system_account: SYS\n')
WITH_SYS_AND_U2 = WITH_SYS.replace("{user: u1, password: p1}", "{user: u1, password: p1}, {user: u2, password: p2}")


def can_sign_in(port, user, pw):
    s = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        s.recv(4096)
        s.sendall(f'CONNECT {{"user":"{user}","pass":"{pw}","verbose":false}}\r\nPING\r\n'.encode())
        s.settimeout(2)
        return b"PONG" in s.recv(4096)
    except OSError:
        return False
    finally:
        s.close()


@unittest.skipUnless(shutil.which("nats-server"), "needs nats-server on PATH")
class NatsReload(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.t, True)
        self.run_dir = os.path.join(self.t, "run")
        os.makedirs(self.run_dir)
        self.src = os.path.join(self.t, "accounts.conf")
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        with open(os.path.join(self.run_dir, "nats.conf"), "w") as f:
            f.write(f'listen: 127.0.0.1:{self.port}\nserver_name: t\ninclude "nats-accounts.conf"\n')
        self.log = os.path.join(self.t, "calls")
        self.shim = os.path.join(self.t, "systemctl")
        with open(self.shim, "w") as f:  # records which verb the script chose
            f.write(f'#!/bin/sh\necho "$1" >> "{self.log}"\n')
        os.chmod(self.shim, os.stat(self.shim).st_mode | stat.S_IXUSR)
        self.proc = None
        self.addCleanup(self.stop)

    def stop(self):
        if self.proc:
            self.proc.kill()
            self.proc.wait()
            self.proc = None

    def start(self):
        self.proc = subprocess.Popen(["nats-server", "-c", os.path.join(self.run_dir, "nats.conf")],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.1)
        self.fail("nats-server did not start")

    def put(self, path, text):
        with open(path, "w") as f:
            f.write(text)

    def copy_in(self):  # what onemind-nats-files does at start and reload
        shutil.copy(self.src, os.path.join(self.run_dir, "nats-accounts.conf"))

    def hup(self):
        self.proc.send_signal(signal.SIGHUP)
        time.sleep(0.7)

    def verb(self):
        env = dict(os.environ, ONEMIND_NATS_RUN=self.run_dir, ONEMIND_NATS_ACCOUNTS_SRC=self.src, ONEMIND_SYSTEMCTL=self.shim)
        if os.path.exists(self.log):
            os.remove(self.log)
        subprocess.run(["sh", SCRIPT], env=env, check=True)
        return open(self.log).read().split()

    def test_the_premise_a_hup_cannot_add_the_system_account_and_then_ignores_later_changes(self):
        self.put(self.src, PLAIN)
        self.copy_in()
        self.start()
        self.put(self.src, WITH_SYS)
        self.copy_in()
        self.hup()
        self.put(self.src, WITH_SYS_AND_U2)
        self.copy_in()
        self.hup()
        self.assertTrue(can_sign_in(self.port, "u1", "p1"))
        self.assertFalse(can_sign_in(self.port, "u2", "p2"), "this nats-server applied the reload: the restart is not needed")

    def test_a_new_system_account_restarts_and_the_next_change_is_applied_by_a_reload(self):
        self.put(self.src, PLAIN)
        self.copy_in()
        self.start()
        self.put(self.src, WITH_SYS)
        self.assertEqual(self.verb(), ["try-restart"])
        self.copy_in()
        self.stop()
        self.start()                       # what the restart does
        self.put(self.src, WITH_SYS_AND_U2)
        self.assertEqual(self.verb(), ["try-reload-or-restart"])
        self.copy_in()
        self.hup()
        self.assertTrue(can_sign_in(self.port, "u2", "p2"))

    def test_the_reverse_removing_the_system_account_restarts_too(self):
        self.put(self.src, WITH_SYS)
        self.copy_in()
        self.put(self.src, PLAIN)
        self.assertEqual(self.verb(), ["try-restart"])

    def test_no_change_in_the_system_account_reloads(self):
        self.put(self.src, PLAIN)
        self.copy_in()
        self.put(self.src, PLAIN + "# a node joined\n")
        self.assertEqual(self.verb(), ["try-reload-or-restart"])

    def test_the_unit_runs_the_script_and_the_script_is_executable(self):
        self.assertIn("ExecStart=/usr/lib/onemind/onemind-nats-reload", open(UNIT).read())
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
