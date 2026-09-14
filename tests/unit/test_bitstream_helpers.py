from e2e.journeys import file_is_fresh


def test_a_file_written_just_now_by_the_pis_clock_counts_as_fresh():
    """`date +%s; stat -c %Y` on the Pi: its clock, then the file's mtime."""
    fresh, detail = file_is_fresh("1789358522\n1789358510\n")
    assert fresh, detail
    assert "12s old" in detail


def test_yesterdays_file_does_not_count():
    """The identical bitstream from a previous run satisfies a size check.

    Only the timestamp distinguishes "this upload landed" from "a file with
    the right size is sitting there", which is what the test claims to prove.
    """
    fresh, detail = file_is_fresh(f"1789358522\n{1789358522 - 86400}\n")
    assert not fresh
    assert "86400s old" in detail


def test_the_pis_clock_is_what_counts_not_this_machines():
    """A Pi whose clock is a week behind ours still says its own file is new."""
    fresh, _ = file_is_fresh("1700000000\n1699999990\n")
    assert fresh


def test_a_file_from_the_future_is_not_fresh_either():
    fresh, _ = file_is_fresh("1789358522\n1789358600\n")
    assert not fresh


def test_an_unreadable_listing_is_not_fresh():
    fresh, detail = file_is_fresh("stat: cannot statx '/home/pi/Uploads/top.bit': No such file or directory")
    assert not fresh
    assert "could not read" in detail
