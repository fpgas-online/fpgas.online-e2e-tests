"""Do the ssh instructions printed on the board page actually work?

The page says: user pi, this host, this port, password in the login banner.
A person copies that, pastes it into a terminal, reads the banner, and logs
in. So does this test. The ground truth is a shell on the Pi that agrees with
the page about which board it is.
"""

import paramiko
import pytest

from e2e.sshbanner import (
    parse_instructions,
    password_from_banner,
    read_login_banner,
    read_version_string,
)


@pytest.mark.live
def test_ssh_instructions_on_the_page_let_you_log_in(board_page, evidence):
    session = board_page()
    board, page, terminal = session.board, session.page, session.terminal

    instructions = parse_instructions(page.inner_text("body"))
    evidence.ground_truth(
        "the page tells the user how to ssh in",
        bool(instructions.ssh_command),
        detail=f"page says: {instructions}",
    )

    version = read_version_string(instructions.host, instructions.port)
    evidence.ground_truth(
        f"{instructions.host}:{instructions.port} answers ssh",
        version.startswith("SSH-"),
        detail=f"server identified itself as {version.strip()!r}",
    )

    # What a person sees before the password prompt. OpenSSH sends it during
    # authentication, so it never appears on the raw socket.
    banner = read_login_banner(instructions.host, instructions.port, instructions.user)
    password = password_from_banner(banner)
    evidence.ground_truth(
        "the login banner contains the password, as the page promises",
        password is not None,
        detail=f"banner was: {banner[:400]!r}",
    )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            instructions.host,
            port=instructions.port,
            username=instructions.user,
            password=password,
            timeout=20,
            allow_agent=False,
            look_for_keys=False,
        )
        _, stdout, _ = client.exec_command("hostname", timeout=20)
        remote_hostname = stdout.read().decode().strip()
    finally:
        client.close()

    evidence.ground_truth(
        "the credentials from the banner log in",
        bool(remote_hostname),
        detail=f"`hostname` returned {remote_hostname!r}",
    )
    evidence.ground_truth(
        "ssh reached the board the page said it would",
        remote_hostname == board.hostname,
        detail=f"page said {board.hostname!r}, ssh reached {remote_hostname!r}",
    )

    via_web = terminal.run("hostname")
    shown, detail = via_web.shows(remote_hostname)
    evidence.ground_truth("the web terminal and direct ssh reach the same board", shown, detail=detail)
