import importlib.util, sys, time, shutil
spec = importlib.util.spec_from_file_location("rt", sys.argv[1]); rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)
shutil.copy("/usr/share/AAVMF/AAVMF_VARS.fd", "/var/lab/run/AAVMF_VARS.fd")
vm = rt.VM("/var/lab/run/disk.img", "/var/lab/run/AAVMF_VARS.fd", open(sys.argv[2], "w"))
try:
    vm.start(); vm.wait_gate(); vm.shell_ready()
    time.sleep(int(sys.argv[3]))
    for c in sys.argv[4:]:
        rc, out = vm.run(c, 300); print("$", c); print(out[-6000:])
finally:
    vm.kill()
