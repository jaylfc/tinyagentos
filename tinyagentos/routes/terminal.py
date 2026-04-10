from __future__ import annotations

import asyncio
import json
import os
import pty
import signal
import struct
import fcntl
import termios
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/terminal")
async def terminal_ws(ws: WebSocket):
    await ws.accept()

    shell = os.environ.get("SHELL", "/bin/bash")

    # Create PTY pair
    master_fd, slave_fd = pty.openpty()

    # Fork child process
    pid = os.fork()
    if pid == 0:
        # Child: become session leader, attach to slave PTY
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        os.execvpe(shell, [shell, "-l"], env)
        # Never reaches here

    # Parent: close slave, work with master
    os.close(slave_fd)

    # Non-blocking reads from master
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    async def pty_reader():
        try:
            while True:
                await asyncio.sleep(0.02)
                try:
                    data = os.read(master_fd, 65536)
                    if data:
                        await ws.send_text(data.decode("utf-8", errors="replace"))
                except BlockingIOError:
                    pass
                except OSError:
                    break
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(pty_reader())

    try:
        while True:
            msg = await ws.receive_text()
            # Check for resize command
            try:
                cmd = json.loads(msg)
                if isinstance(cmd, dict) and cmd.get("type") == "resize":
                    winsize = struct.pack(
                        "HHHH", cmd.get("rows", 24), cmd.get("cols", 80), 0, 0
                    )
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                    continue
            except (json.JSONDecodeError, ValueError):
                pass
            os.write(master_fd, msg.encode("utf-8"))
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        try:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        except OSError:
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
