import pytest

from e2e.sshbanner import parse_instructions, password_from_banner

PAGE = """
      Use your own ssh client. user: pi, host: welland.fpgas.online, port 21622,
      (password is in login banner)
      click to copy:
ssh -p 21622 pi@welland.fpgas.online
scp -P 21622 * pi@welland.fpgas.online:Uploads
"""


def test_parse_instructions_reads_user_host_and_port():
    got = parse_instructions(PAGE)
    assert (got.user, got.host, got.port) == ("pi", "welland.fpgas.online", 21622)


def test_parse_instructions_reads_the_copyable_ssh_command():
    assert parse_instructions(PAGE).ssh_command == "ssh -p 21622 pi@welland.fpgas.online"


def test_parse_instructions_raises_when_the_page_says_nothing():
    with pytest.raises(ValueError):
        parse_instructions("no instructions here")


@pytest.mark.parametrize(
    "banner, expected",
    [
        ("Welcome!\nThe password is hunter2\n", "hunter2"),
        ("password: swordfish", "swordfish"),
        ("Login with password 'let me in'", "let me in"),
    ],
)
def test_password_from_banner_finds_the_password(banner, expected):
    assert password_from_banner(banner) == expected


def test_password_from_banner_returns_none_when_there_is_none():
    assert password_from_banner("Debian GNU/Linux\n") is None
