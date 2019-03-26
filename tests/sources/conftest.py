from buildstream.plugintestutils import sourcetests_collection_hook


# This hook enables pytest to collect the templated source tests from
# buildstream.plugintestutils
def pytest_sessionstart(session):
    sourcetests_collection_hook(session)
