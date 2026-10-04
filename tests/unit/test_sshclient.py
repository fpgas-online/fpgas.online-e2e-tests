import pytest

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
