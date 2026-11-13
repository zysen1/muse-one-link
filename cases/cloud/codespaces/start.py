#!/usr/bin/env python3
"""Manage the adjacent app.py on loopback; Python standard library only.

Usage: python start.py [start|status|stop] [--port 8000] [--timeout 10]
PORT supplies the default port. Runtime files stay in .runtime beside this file.
Stopping this application does not stop the Codespace or its resource usage.
"""

import argparse
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


SCRIPT = Path(__file__).resolve()
APP = SCRIPT.with_name("app.py")
NOTICE = "停止本工具不等于停止 Codespace；不用云环境时请另外在 GitHub 停止它。"
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ServiceError(Exception):
    pass


def private_open(path, flags):
    """Refuse symlinks, shared files, and files owned by another user."""
    fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise ServiceError("运行文件必须属于当前用户且仅本人可读写：" + str(path))
    return fd


def atomic_write(path, content):
    if path.exists() or path.is_symlink():
        os.close(private_open(path, os.O_RDONLY))
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def process_identity(pid):
    """Start time plus full command prevents trusting a recycled PID."""
    try:
        if sys.platform.startswith("linux"):
            proc = Path("/proc") / str(pid)
            fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] == "Z":
                return None
            argv = [os.fsdecode(x) for x in (proc / "cmdline").read_bytes().split(b"\0") if x]
            if not argv:
                return None
            return {
                "backend": "proc",
                "started": fields[19],
                "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                "command": argv,
                "session": os.getsid(pid),
            }
        # macOS ps is an OS utility, not an installed Python dependency.
        result = subprocess.run(
            ["/bin/ps", "-ww", "-p", str(pid), "-o", "lstart=", "-o", "command="],
            capture_output=True, text=True, timeout=3,
            env=dict(os.environ, LC_ALL="C"),
        )
        if result.returncode == 1 and not result.stdout.strip():
            return None
        match = re.match(
            r"^\s*(\w{3}\s+\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+(.+)$",
            result.stdout.strip(),
        )
        if result.returncode or not match:
            raise ServiceError("无法可靠读取进程身份；没有向该进程发送信号。")
        return {
            "backend": "ps", "started": " ".join(match[1].split()),
            "command": match[2], "session": os.getsid(pid),
        }
    except (FileNotFoundError, ProcessLookupError):
        return None


def owns_process(state):
    identity = process_identity(state["pid"])
    return identity is not None and identity == state["identity"]


def port_busy(port):
    # Binding tests occupancy even if an existing listener is not accepting yet.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def health(port, timeout=0.8):
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:%s/api/status" % port,
            headers={"Accept": "application/json"},
        )
        with HTTP.open(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read(65537))
        if not isinstance(data, dict):
            return None
        if not all(isinstance(data.get(k), str) and data[k] for k in ("system", "python", "utc")):
            return None
        cpu = data.get("cpu_visible")
        return data if isinstance(cpu, int) and not isinstance(cpu, bool) and cpu > 0 else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


class Service:
    def __init__(self, args):
        self.port = args.port
        self.timeout = args.timeout
        self.directory = args.state_dir.expanduser().absolute()
        self.state_path = self.directory / ("server-%s.json" % self.port)
        self.pid_path = self.directory / ("server-%s.pid" % self.port)
        self.log_path = self.directory / ("server-%s.log" % self.port)

    @contextlib.contextmanager
    def locked(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ServiceError("状态目录必须属于当前用户且仅本人可访问；请换用私有目录：" + str(self.directory))
        fd = private_open(self.directory / ("server-%s.lock" % self.port), os.O_CREAT | os.O_RDWR)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ServiceError("同一端口已有启动或停止操作正在执行，请稍后重试。")
            yield
        finally:
            os.close(fd)

    def load(self):
        try:
            fd = private_open(self.state_path, os.O_RDONLY)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, encoding="utf-8") as stream:
            try:
                state = json.loads(stream.read(65537))
            except ValueError:
                raise ServiceError("状态文件损坏；未覆盖记录或停止任何进程。")
        if not isinstance(state, dict) or not (
            state.get("manager") == str(SCRIPT) and state.get("app") == str(APP)
            and state.get("port") == self.port and type(state.get("pid")) is int
            and state["pid"] > 1 and isinstance(state.get("identity"), dict)
            and state["identity"].get("session") == state["pid"]
        ):
            raise ServiceError("状态文件不属于此脚本、应用或端口；没有停止任何进程。")
        identity_command = state["identity"].get("command")
        argv = state.get("argv")
        if not isinstance(argv, list) or len(argv) != 3 or argv[1:] != ["-u", str(APP)]:
            raise ServiceError("状态中的应用启动路径不匹配。")
        if identity_command != (argv if state["identity"].get("backend") == "proc" else " ".join(argv)):
            raise ServiceError("状态中的完整进程命令不匹配。")
        return state

    def clear(self):
        for path in (self.state_path, self.pid_path):
            try:
                os.close(private_open(path, os.O_RDONLY))
                path.unlink()
            except FileNotFoundError:
                pass

    def result(self, status, message, **values):
        return dict(
            ok=status not in ("unmanaged", "unhealthy", "stale"), status=status,
            message=message, url="http://127.0.0.1:%s" % self.port,
            access="程序监听回环地址；Codespaces 私有转发状态请在 Ports 中核对。", note=NOTICE, **values,
        )

    def status(self):
        state = self.load()
        if state and owns_process(state):
            api = health(self.port)
            return self.result("running" if api else "unhealthy",
                               "工具正在运行。" if api else "受管进程仍在，但状态 API 未通过检查。",
                               pid=state["pid"], api=api, log=str(self.log_path))
        if port_busy(self.port):
            return self.result("unmanaged", "端口被非本脚本可验证的进程占用；不会接管或停止它。")
        return self.result("stale" if state else "stopped",
                           "旧进程记录已失效；没有向该 PID 发送信号。" if state else "工具未运行。")

    def terminate(self, state):
        # Signal only this recorded process, never a process group or a port owner.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if not owns_process(state):
                return
            try:
                os.kill(state["pid"], sig)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + min(self.timeout, 5.0)
            while time.monotonic() < deadline:
                if not owns_process(state):
                    return
                time.sleep(0.1)
        if owns_process(state):
            raise ServiceError("停止超时，仍保留进程记录以便再次检查。")

    def stop(self):
        state = self.load()
        if not state:
            if port_busy(self.port):
                return self.result("unmanaged", "没有本工具的进程记录；端口上的其他进程未被停止。")
            return self.result("stopped", "工具已经停止。")
        if not owns_process(state):
            return self.result("stale", "记录与实际进程身份不符；没有停止任何进程。")
        self.terminate(state)
        self.clear()
        return self.result("stopped", "已停止本工具的受管进程。", stopped_pid=state["pid"])

    def start(self):
        state = self.load()
        if state and owns_process(state):
            api = health(self.port)
            if not api:
                raise ServiceError("受管进程仍在，但状态 API 不健康；请先查看日志或执行 stop。")
            return self.result("running", "工具已经运行，本次没有重复启动。", pid=state["pid"], api=api)
        if port_busy(self.port):
            raise ServiceError("端口 %s 已被其他进程占用；未启动、未停止任何其他进程。" % self.port)
        if not APP.is_file():
            raise ServiceError("缺少同目录 app.py：" + str(APP))
        if state:
            self.clear()  # Stale records only; never signal the recorded old PID.
        argv = [sys.executable, "-u", str(APP)]
        child = None
        managed = None
        try:
            fd = private_open(self.log_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND)
            with os.fdopen(fd, "ab", buffering=0) as log:
                child = subprocess.Popen(
                    argv, cwd=str(APP.parent), env=dict(os.environ, PORT=str(self.port)),
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True, close_fds=True,
                )
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise ServiceError("程序启动后退出；请查看日志：" + str(self.log_path))
                identity = process_identity(child.pid)
                expected = argv if sys.platform.startswith("linux") else " ".join(argv)
                if identity and identity["command"] == expected and identity["session"] == child.pid:
                    managed = dict(
                        manager=str(SCRIPT), app=str(APP), port=self.port, pid=child.pid,
                        argv=argv, identity=identity,
                        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    break
                time.sleep(0.05)
            if not managed:
                raise ServiceError("未能在时限内核对新进程身份。")
            atomic_write(self.pid_path, str(child.pid) + "\n")
            atomic_write(self.state_path, json.dumps(managed, ensure_ascii=False, indent=2) + "\n")
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise ServiceError("程序启动后退出；请查看日志：" + str(self.log_path))
                api = health(self.port, min(0.8, max(0.05, deadline - time.monotonic())))
                if api and owns_process(managed):
                    return self.result("running", "工具已在后台启动并通过状态 API 检查。",
                                       pid=child.pid, api=api, log=str(self.log_path))
                time.sleep(0.1)
            raise ServiceError("启动健康检查超时；请查看日志：" + str(self.log_path))
        except BaseException:
            if managed:
                self.terminate(managed)
                self.clear()
            elif child is not None and child.poll() is None:
                # This is still our unreaped direct child; its PID cannot be reused.
                child.terminate()
                try:
                    child.wait(timeout=min(self.timeout, 3.0))
                except subprocess.TimeoutExpired:
                    child.kill()
            if child is not None:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    child.wait(timeout=1)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="start", choices=("start", "status", "stop"))
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "8000"))
    parser.add_argument("--state-dir", type=Path, default=SCRIPT.parent / ".runtime")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 < args.timeout <= 120:
        parser.error("端口须为 1–65535，超时须大于 0 且不超过 120 秒。")
    os.umask(0o077)
    try:
        service = Service(args)
        with service.locked():
            result = getattr(service, args.action)()
    except KeyboardInterrupt:
        result = dict(ok=False, status="interrupted", message="操作已中断。", note=NOTICE)
    except (ServiceError, OSError, subprocess.SubprocessError) as exc:
        result = dict(ok=False, status="error", message=str(exc), note=NOTICE)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
