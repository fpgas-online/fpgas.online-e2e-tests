import time

from tests.shared.test_bitstream_upload import _recently_written


def test_a_file_written_just_now_counts_as_fresh():
    text = f"2026-09-13T11:02\n{int(time.time())}\n"
    fresh, detail = _recently_written(text)
    assert fresh, detail


def test_yesterdays_file_does_not_count():
    """The identical bitstream from a previous run satisfies a size check.

    Only the timestamp distinguishes "this upload landed" from "a file with
    the right size is sitting there", which is what the test claims to prove.
    """
    text = f"2026-09-13T11:02\n{int(time.time()) - 86400}\n"
    fresh, detail = _recently_written(text)
    assert not fresh
    assert "old" in detail


def test_an_unreadable_listing_is_not_fresh():
    fresh, detail = _recently_written("ls: cannot access: No such file or directory")
    assert not fresh
    assert "could not read an mtime" in detail
