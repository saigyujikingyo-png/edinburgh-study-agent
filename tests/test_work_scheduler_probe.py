"""Portable failure cases for the opt-in scheduler probe's cleanup selection."""
from dataclasses import replace
from pathlib import Path

import pytest

from edinburgh_study_agent.work_runtime import Process, Profile
from scripts.verify_work_scheduler import observe_fixture


@pytest.mark.parametrize('fault', ['owner_pid_reused', 'job_pid_reused', 'job_wrong_parent', 'job_older_than_owner', 'none'])
def test_cleanup_never_adopts_an_unverified_pid(tmp_path, fault):
    profile = Profile(tmp_path, tmp_path, 'fixture', str(tmp_path/'profiles'),
                      'unused.exe', str(tmp_path/'python.exe'), tmp_path/'unused.dpapi', 'fixture')
    # The wrapper test is already covered against the exact Windows command. This
    # portable boundary keeps the subject here the additional parent/job checks.
    wrapper = Process(10, 1, 'wrapper', 1.0, ('wrapper',))
    owner = Process(11, 10, profile.python, 2.0, (profile.python, '-m',
                    'edinburgh_study_agent.work_runtime', 'run', '--connection-directory', str(tmp_path)))
    job = Process(12, 11, profile.python, 3.0, (profile.python, '-m', 'edinburgh_study_agent.school'))
    if fault == 'owner_pid_reused':
        owner = replace(owner, argv=(profile.python, '-m', 'unrelated'))
    if fault == 'job_pid_reused':
        job = replace(job, executable=str(tmp_path/'different.exe'))
    if fault == 'job_wrong_parent':
        job = replace(job, parent=999)
    if fault == 'job_older_than_owner':
        job = replace(job, born=1.5)
    class FixtureProfile:
        def __getattr__(self, key): return getattr(profile, key)
        def wrapper(self, item): return item == wrapper
    observed = []
    if fault == 'none':
        assert observe_fixture(FixtureProfile(), [wrapper, owner, job],
                               {'supervisor': 11, 'job': 12}, observed) == (wrapper, owner, job)
        assert observed == [wrapper, owner, job]
    else:
        with pytest.raises(ValueError):
            observe_fixture(FixtureProfile(), [wrapper, owner, job],
                            {'supervisor': 11, 'job': 12}, observed)
        assert job not in observed
        assert (owner in observed) == (fault != 'owner_pid_reused')
