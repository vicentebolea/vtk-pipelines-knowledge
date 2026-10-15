from pipelines_knowledge.convert import _error_key, add_rates
from pipelines_watch import entries


def _entry(job_id, snippet, outcome):
    return entries.Entry(project="g/p", job_id=job_id, pipeline_id=1, ref="r", job_name="j", platform="linux",
                         error_type="git", snippet=snippet, outcome=outcome)


def test_error_key_blanks_numbers_and_paths():
    a = _entry(1, "fatal: bad signature 0x00000000 in C:/ci/builds/42/.git/index", "retry_passed")
    b = _entry(2, "fatal: bad signature 0xdeadbeef in /home/ci/7/.git/index", "retry_passed")
    assert _error_key(a) == _error_key(b)


def test_add_rates(tmp_path):
    for e in (_entry(1, "fatal: index 1", "retry_passed"), _entry(2, "fatal: index 2", "retry_failed"),
              _entry(3, "fatal: index 3", "retry_passed"), _entry(4, "other error", "retry_failed")):
        entries.save(tmp_path, e)
    add_rates(tmp_path)
    got = {e.job_id: (e.similar, e.success_rate) for e, _ in entries.load_all(tmp_path)}
    assert got == {1: (3, 2 / 3), 2: (3, 2 / 3), 3: (3, 2 / 3), 4: (1, 0.0)}
