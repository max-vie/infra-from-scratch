import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


COMPONENT = Path(__file__).resolve().parents[1]


class TestRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build_dir.cleanup)
        cls.binary = Path(os.environ.get(
            "CONTAINER_RUNTIME_TEST_BINARY", str(Path(cls.build_dir.name) / "runtime")
        )).resolve()
        cls.probe = Path(cls.build_dir.name) / "probe"
        for source, output in (
            (COMPONENT / "runtime.c", cls.binary),
            (COMPONENT / "tests" / "probe.c", cls.probe),
        ):
            subprocess.run(
                ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                 "-O2", "-o", str(output), str(source)],
                check=True,
            )
        # Inspect only the locally compiled, trusted test program.
        linked = subprocess.run(
            ["ldd", str(cls.probe)], capture_output=True, text=True, check=True,
            env={**os.environ, "LC_ALL": "C"},
        ).stdout
        cls.libraries = set(re.findall(r"(/[\w/+.\-]+)", linked))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.rootfs = Path(self.directory.name) / "rootfs"
        (self.rootfs / "proc").mkdir(parents=True)
        (self.rootfs / "marker").write_text("inside")
        self.outside = Path(self.directory.name) / "outside"
        self.outside.write_text("outside")
        shutil.copy2(self.probe, self.rootfs / "probe")
        for library in self.libraries:
            destination = self.rootfs / library.lstrip("/")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(library, destination)

    def run_command(self, *arguments, **kwargs):
        return subprocess.run(
            [str(self.binary), str(self.rootfs), *arguments],
            capture_output=True, text=True, timeout=5, **kwargs,
        )

    def start_command(self, mode):
        process = subprocess.Popen(
            [str(self.binary), str(self.rootfs), "/probe", mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop_process, process)
        with selectors.DefaultSelector() as ready:
            ready.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(ready.select(timeout=5), "container did not become ready")
        line = process.stdout.readline()
        if line != "ready\n":
            _, stderr = process.communicate(timeout=5)
            self.fail(f"container startup failed: {line!r} {stderr}")
        return process

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)

    @staticmethod
    def descendants(pid):
        children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
        result = []
        for child in map(int, children):
            result.append(child)
            result.extend(TestRuntime.descendants(child))
        return result

    def assert_processes_stopped(self, pids, allow_zombies=False):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            running = []
            for pid in pids:
                try:
                    state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
                except FileNotFoundError:
                    continue
                if not allow_zombies or state != "Z":
                    running.append(pid)
            if not running:
                return
            time.sleep(0.01)
        self.fail(f"container processes still running: {running}")

    def test_isolates_root_processes_and_inherited_descriptors(self):
        with self.outside.open() as outside_file:
            result = self.run_command(
                "/probe", "inspect", str(self.outside), str(os.getpid()),
                str(outside_file.fileno()), pass_fds=(outside_file.fileno(),),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        for key, expected in (
            ("pid", "2"), ("ppid", "1"), ("uid", "0"), ("cwd", "/"),
            ("rootfs_marker", "1"), ("host_marker_hidden", "1"),
            ("host_process_hidden", "1"), ("inherited_fd_closed", "1"),
            ("init_fds_closed", "1"),
        ):
            self.assertEqual(values[key], expected, result.stdout)
        self.assertNotEqual(int(values["pid_namespace"]), os.stat("/proc/self/ns/pid").st_ino)
        self.assertNotEqual(int(values["mount_namespace"]), os.stat("/proc/self/ns/mnt").st_ino)
        for capability in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
            self.assertRegex(result.stdout, rf"{capability}:\s+0+\n")
        self.assertRegex(result.stdout, r"NoNewPrivs:\s+1\n")
        self.assertEqual(self.outside.read_text(), "outside")
        self.assertFalse(os.path.ismount(self.rootfs))
        self.assertEqual(list((self.rootfs / "proc").iterdir()), [])

    def test_preserves_status_and_reuses_rootfs_after_exec_failure(self):
        (self.rootfs / "not-executable").write_text("no execute permission")
        for command, expected in (
            (["/missing"], 127), (["/not-executable"], 126), (["/probe", "exit", "37"], 37),
        ):
            with self.subTest(command=command):
                result = self.run_command(*command)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertFalse(os.path.ismount(self.rootfs))
                self.assertEqual(list((self.rootfs / "proc").iterdir()), [])

    def test_reaps_orphans_while_command_runs(self):
        result = self.run_command("/probe", "orphan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "orphan reaped\n")

    def test_preserves_exit_status_when_caller_ignores_sigchld(self):
        result = self.run_command(
            "/probe", "exit", "37",
            preexec_fn=lambda: signal.signal(signal.SIGCHLD, signal.SIG_IGN),
        )
        self.assertEqual(result.returncode, 37, result.stderr)

    def test_command_exit_removes_descendant_in_another_session(self):
        process = self.start_command("tree")
        pids = self.descendants(process.pid)
        self.assertEqual(len(pids), 3)
        _, stderr = process.communicate("x\n", timeout=5)
        self.assertEqual(process.returncode, 37, stderr)
        self.assert_processes_stopped(pids)

    def test_forwards_signals_to_command_group(self):
        for number in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=number):
                process = self.start_command("signal")
                pids = self.descendants(process.pid)
                self.assertEqual(len(pids), 3)
                process.send_signal(number)
                _, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 128 + number, stderr)
                self.assertEqual((self.rootfs / "child-signal").read_text(), f"{number}\n")
                self.assert_processes_stopped(pids)

    def test_launcher_death_removes_namespace_processes(self):
        process = self.start_command("tree")
        pids = self.descendants(process.pid)
        self.assertEqual(len(pids), 3)
        process.kill()
        process.wait(timeout=5)
        self.assertEqual(process.returncode, -signal.SIGKILL)
        # The host's init process now owns reaping the dead namespace init.
        self.assert_processes_stopped(pids, allow_zombies=True)
        process.communicate(timeout=5)

    def test_reports_unhandled_signal_exit_status(self):
        process = self.start_command("tree")
        pids = self.descendants(process.pid)
        process.terminate()
        process.wait(timeout=5)
        _, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 143, stderr)
        self.assert_processes_stopped(pids)

    def test_rejects_invalid_roots_and_commands(self):
        cases = (
            [], [str(self.rootfs)], [str(self.rootfs), "probe"],
            ["/", "/bin/true"], [str(self.outside), "/probe"],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [str(self.binary), *arguments], capture_output=True, timeout=5,
                )
                self.assertEqual(result.returncode, 125)
        (self.rootfs / "proc").rmdir()
        result = self.run_command("/probe", "exit", "0")
        self.assertEqual(result.returncode, 125)
        (self.rootfs / "proc").symlink_to("/proc", target_is_directory=True)
        result = self.run_command("/probe", "exit", "0")
        self.assertEqual(result.returncode, 125)
        self.assertIn("real proc directory", result.stderr)


if __name__ == "__main__":
    unittest.main()
