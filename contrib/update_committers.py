#!/usr/bin/env python3
"""A script to set up COMMITTERS.rst according to gitlab committers."""

import os
import subprocess
import argparse
import json
import urllib.request
import urllib.parse
from jinja2 import Environment, FileSystemLoader
from collections import OrderedDict

GIT_ERROR = 1
MERGE_REQUEST = 'https://gitlab.com/api/v4/projects/1975139/merge_requests'
ALL_MEMBERS = 'https://gitlab.com/api/v4/projects/1975139/members/all'
PROTECTED = 'https://gitlab.com/api/v4/projects/1975139/protected_branches/master'
USERS = 'https://gitlab.com/api/v4/users/{}'
MAX_LEN = len('Full Name                         ')


def get_committers(token: str) -> OrderedDict:
    request = urllib.request.Request(PROTECTED)
    request.add_header('PRIVATE-TOKEN', token)
    response = urllib.request.urlopen(request).read().decode('utf-8')
    named_developers = [x['user_id'] for x in json.loads(response)['merge_access_levels']]
    request = urllib.request.Request(ALL_MEMBERS)
    request.add_header('PRIVATE-TOKEN', token)
    all_members = json.loads(urllib.request.urlopen(request).read().decode('utf-8'))
    names_usernames_dictionary = OrderedDict()
    for contributor in all_members:
        if contributor['access_level'] >= 40:
            names_usernames_dictionary[contributor['name']] = contributor['username']
    for contributor in named_developers:
        if contributor:
            request = urllib.request.Request(USERS.format(contributor))
            response = json.loads(urllib.request.urlopen(request).read().decode('utf-8'))
            if response['name'] != 'bst-marge-bot':
                names_usernames_dictionary[response['name']] = response['username']
    return names_usernames_dictionary


def get_table_entry(entry: str) -> str:
    res = entry
    for _ in range(MAX_LEN - len(entry)):
        res = res + ' '
    return res


def find_repository_root() -> str:
    root = os.getcwd()
    try:
        root = subprocess.check_output('git rev-parse --show-toplevel', shell=True)
    except CalledProcessError as e:
        print('The current working directory is not a git repository. \
               \"git rev-parse --show-toplevel\" exited with code {}.'.format(e.returncode))
        sys.exit(GIT_ERROR)
    return root.rstrip().decode('utf-8')


def create_committers_file(committers: OrderedDict):
    contrib_directory = os.path.join(find_repository_root(), 'contrib')
    file_loader = FileSystemLoader(contrib_directory)
    env = Environment(loader=file_loader)
    template = env.get_template('COMITTERS.rst.j2')
    render_output = template.render(committers=committers, get_table_entry=get_table_entry)
    committers_file = os.path.join(contrib_directory, 'COMMITTERS.rst')

    with open(committers_file, 'w') as f:
        f.write(render_output)


def commit_changes_if_needed(token: str):
    committers_file = os.path.join(find_repository_root(), 'contrib/COMMITTERS.rst')
    git_diff = subprocess.call('git diff --quiet {}'.format(committers_file), shell=True)
    if git_diff:
        commit_message = '\'contrib: Update COMMITTERS.rst\''
        branch_name = 'update_committers'
        subprocess.call('git add {}'.format(committers_file), shell=True)
        subprocess.call('git commit -m {}'.format(commit_message), shell=True)
        try:
            subprocess.call('git push -u origin {} 2>&1'.format(branch_name),
                            shell=True)
        except CalledProcessError as e:
            print('Could not push to remote branch. \"git push -u origin {}\" \
                   exited with code {}.'.format(branch_name, e.returncode))
            sys.exit(GIT_ERROR)
        data = urllib.parse.urlencode({'source_branch': 'update_committers',
                                       'target_branch': 'master',
                                       'title': 'Update COMMITTERS.rst file'})
        request = urllib.request.Request(MERGE_REQUEST, data=bytearray(data, 'ASCII'))
        request.add_header('PRIVATE-TOKEN', token)
        response = urllib.request.urlopen(request).read().decode('utf-8')


def main():
    parser = argparse.ArgumentParser(
        description="Update gitlab committers according to COMMITTERS.rst"
    )
    parser.add_argument(
        "token", type=str,
        help="Your private access token. See https://gitlab.com/profile/personal_access_tokens."
    )
    args = parser.parse_args()

    committers = get_committers(args.token)
    create_committers_file(committers)
    commit_changes_if_needed(args.token)


if __name__ == '__main__':
    main()
