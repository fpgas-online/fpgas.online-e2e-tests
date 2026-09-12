import pytest

from e2e.sshbanner import parse_instructions, password_from_banner

PAGE = """
      Use your own ssh client. user: pi, host: welland.fpgas.online, port 21622,
      (password is in login banner)
      click to copy:
ssh -p 21622 pi@welland.fpgas.online
scp -P 21622 * pi@welland.fpgas.online:Uploads
"""

# Captured from ps1.fpgas.online:10222 on 2026-09-12 via paramiko's
# Transport.get_banner(). OpenSSH sends this during authentication
# (SSH_MSG_USERAUTH_BANNER), so it is what a real ssh client prints just before
# prompting for a password -- and here it IS the password, nothing else.
REAL_BANNER = "ship7ohT\n"


def test_parse_instructions_reads_user_host_and_port():
    got = parse_instructions(PAGE)
    assert (got.user, got.host, got.port) == ("pi", "welland.fpgas.online", 21622)


def test_parse_instructions_reads_the_copyable_ssh_command():
    assert parse_instructions(PAGE).ssh_command == "ssh -p 21622 pi@welland.fpgas.online"


def test_parse_instructions_raises_when_the_page_says_nothing():
    with pytest.raises(ValueError):
        parse_instructions("no instructions here")


def test_password_from_a_real_banner_that_is_only_the_password():
    assert password_from_banner(REAL_BANNER) == "ship7ohT"


@pytest.mark.parametrize(
    "banner, expected",
    [
        ("Welcome!\nThe password is hunter2\n", "hunter2"),
        ("password: swordfish", "swordfish"),
        ("Login with password 'let me in'", "let me in"),
    ],
)
def test_password_from_a_banner_that_spells_it_out(banner, expected):
    assert password_from_banner(banner) == expected


def test_a_banner_that_is_only_prose_yields_no_password():
    assert password_from_banner("Debian GNU/Linux\nAuthorised users only.\n") is None


def test_an_empty_banner_yields_no_password():
    assert password_from_banner("") is None


def test_a_bare_word_banner_is_not_mistaken_for_a_password_when_it_is_a_sentence():
    """A single line of several words is a notice, not a credential."""
    assert password_from_banner("Unauthorised access is prohibited\n") is None
