import pytest

from e2e import sshclient
from e2e.sshclient import banner_from, printed_command_argv

# What OpenSSH prints, first connection to ps1 pi7, up to the password prompt.
FIRST_CONNECTION = (
    "The authenticity of host '[ps1.fpgas.online]:10722 ([203.0.113.7]:10722)' can't be established.\r\n"
    "ED25519 key fingerprint is SHA256:abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG.\r\n"
    "This key is not known by any other names.\r\n"
    "Are you sure you want to continue connecting (yes/no/[fingerprint])? yes\r\n"
    "Warning: Permanently added '[ps1.fpgas.online]:10722' (ED25519) to the list of known hosts.\r\n"
    "ship7ohT\r\n"
    "pi@ps1.fpgas.online's password:"
)


def test_the_page_command_is_run_as_printed():
    assert printed_command_argv("ssh -p 10722 pi@ps1.fpgas.online") == ["ssh", "-p", "10722", "pi@ps1.fpgas.online"]


@pytest.mark.parametrize("bad", ["scp -P 10722 * pi@ps1.fpgas.online:Uploads", "ssh pi@host", "rm -rf /", ""])
def test_anything_but_the_printed_ssh_command_is_refused(bad):
    with pytest.raises(ValueError):
        printed_command_argv(bad)


def test_the_banner_is_what_the_server_said_and_nothing_the_client_added():
    assert banner_from(FIRST_CONNECTION) == "ship7ohT"


def test_the_banner_survives_a_known_host_with_no_question():
    assert banner_from("ship7ohT\r\npi@ps1.fpgas.online's password:") == "ship7ohT"


def test_an_empty_banner_is_empty():
    assert banner_from("pi@ps1.fpgas.online's password:") == ""


def test_an_empty_prompt_line_after_login_is_free():
    from e2e.sshclient import refuse_if_line_busy

    refuse_if_line_busy("Last login: Sat Sep 12 from 10.21.0.1\r\n06:25:33 pi@pi2:~/Demos $ \r\n")


def test_a_half_typed_command_after_login_is_refused_before_anything_is_sent():
    from e2e.sshclient import refuse_if_line_busy
    from e2e.terminal import TerminalBusy

    with pytest.raises(TerminalBusy, match="sudo apt install pipx"):
        refuse_if_line_busy("06:25:33 pi@pi2:~/Demos $ sudo apt install pipx\r\n")


class _FakeChild:
    """A pexpect child that is a shell behind ssh: `login_screen` is what tmux paints after the password."""

    def __init__(self, login_screen):
        self.login_screen = login_screen
        self.sent = []
        self.pending = []
        self.before = "ship7ohT\r\npi@ps1.fpgas.online's "
        self.after = "password:"

    def expect(self, patterns, **_kwargs):
        return 1  # the password prompt

    def sendline(self, line):
        self.sent.append(line)
        if line == "ship7ohT":
            self.pending.append(self.login_screen)
        elif line == "hostname":
            self.pending.append("hostname\r\npi7\r\n03:30:00 pi@pi7:~ $ ")

    def read_nonblocking(self, size=4096, timeout=0.5):
        if self.pending:
            return self.pending.pop(0)
        raise sshclient.pexpect.TIMEOUT("nothing more")

    def close(self, force=False):
        pass


def _login(monkeypatch, tmp_path, login_screen):
    child = _FakeChild(login_screen)
    monkeypatch.setattr(sshclient.pexpect, "spawn", lambda *args, **kwargs: child)
    result = sshclient.log_in_with_the_printed_command(
        "ssh -p 10722 pi@ps1.fpgas.online", ["hostname"], tmp_path / "known_hosts", timeout=5
    )
    return child, result


def test_login_sends_the_command_when_the_line_is_free(monkeypatch, tmp_path):
    child, result = _login(monkeypatch, tmp_path, "Last login: Sat\r\n03:29:00 pi@pi7:~ $ \r\n")
    assert child.sent == ["ship7ohT", "hostname"]
    assert result.outputs["hostname"] == "pi7"


def test_login_checks_the_line_before_its_first_sendline(monkeypatch, tmp_path):
    """Delete the refuse_if_line_busy call in log_in_with_the_printed_command and this fails."""
    from e2e.terminal import TerminalBusy

    child = _FakeChild("Last login: Sat\r\n03:29:00 pi@pi7:~ $ sudo apt install pipx\r\n")
    monkeypatch.setattr(sshclient.pexpect, "spawn", lambda *args, **kwargs: child)

    with pytest.raises(TerminalBusy, match="a visitor is using the terminal: 'sudo apt install pipx'"):
        sshclient.log_in_with_the_printed_command(
            "ssh -p 10722 pi@ps1.fpgas.online", ["hostname"], tmp_path / "known_hosts", timeout=5
        )

    assert child.sent == ["ship7ohT"]  # only the password; the command never reached the shared shell


def test_a_login_that_reaches_no_prompt_at_all_is_still_an_ssh_failure_not_a_busy_skip(monkeypatch, tmp_path):
    from e2e.terminal import TerminalBusy

    child = _FakeChild("Permission denied, please try again.\r\n")
    monkeypatch.setattr(sshclient.pexpect, "spawn", lambda *args, **kwargs: child)

    with pytest.raises(sshclient.SshFailed) as caught:
        sshclient.log_in_with_the_printed_command(
            "ssh -p 10722 pi@ps1.fpgas.online", ["hostname"], tmp_path / "known_hosts", timeout=2
        )

    assert not isinstance(caught.value, TerminalBusy)
    assert child.sent == ["ship7ohT"]


@pytest.mark.parametrize("under", ["Connection to pi7 closed.", "bash: /usr/bin/ls: Stale file handle"])
def test_a_login_that_lands_on_a_fault_under_the_prompt_fails_and_sends_nothing(monkeypatch, tmp_path, under):
    from e2e.terminal import TerminalBusy, TerminalLost

    child = _FakeChild(f"03:29:00 pi@pi7:~ $ \r\n{under}\r\n")
    monkeypatch.setattr(sshclient.pexpect, "spawn", lambda *args, **kwargs: child)

    with pytest.raises(TerminalLost, match=under.split(":")[-1].strip()) as caught:
        sshclient.log_in_with_the_printed_command(
            "ssh -p 10722 pi@ps1.fpgas.online", ["hostname"], tmp_path / "known_hosts", timeout=5
        )

    assert not isinstance(caught.value, TerminalBusy)
    assert child.sent == ["ship7ohT"]
