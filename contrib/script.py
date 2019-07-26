#!/usr/bin/env python3
"""A script to set up COMMITTERS.rst according to gitlab committers."""

import os
import subprocess
import argparse
import json
import urllib.request
from collections import OrderedDict


MASTER = 'https://gitlab.com/api/v4/projects/BuildStream%2Fbuildstream/protected_branches/master'
USERS = 'https://gitlab.com/api/v4/users/{}'

def get_committers(token: str) -> OrderedDict:
    res = urllib.request.Request(MASTER)
    res.add_header('PRIVATE-TOKEN', token)
    contributors = json.loads(urllib.request.urlopen(res).read().decode('utf-8'))['merge_access_levels']
    names_usernames_dictionary = OrderedDict()
    names_usernames_dictionary['Tristan Van Berkom'] = 'tristanvb'
    names_usernames_dictionary['Juerg Biletter'] = 'juergbi'
    names_usernames_dictionary['Laurence Urhegyi'] = 'LaurenceUrhegyi'
    names_usernames_dictionary['Tristan Maat'] = 'tlater'
    for contributor in contributors:
        if contributor['access_level_description'] not in ['Maintainers', 'bst-marge-bot']:
            user_id = contributor['user_id']
            res = urllib.request.Request(USERS.format(user_id))
            res.add_header('PRIVATE-TOKEN', token)
            user_info = json.loads(urllib.request.urlopen(res).read().decode('utf-8'))
            names_usernames_dictionary[user_info['name']] = user_info['username']

    return names_usernames_dictionary

def get_table_entry(entry: str, max_len: int) -> str:
    res = entry
    for i in range(max_len - len(entry)):
        res = res + ' '
    return res

def find_repository_root() -> str:
    root = os.getcwd()
    while not '.git' in os.listdir(root):
        root_parent = os.path.abspath(os.path.join(root, '..'))
        if root == root_parent:
            raise Exception('Reached root. This is not a git repository')
        else:
            root = root_parent
    return root

def create_committers_file(committers: OrderedDict):
    contrib_directory = os.path.join(find_repository_root(), 'contrib')
    subprocess.call(['cp',
                    os.path.join(contrib_directory, '.COMMITTERS_template.rst'),
                    os.path.join(contrib_directory, 'COMMITTERS.rst')])
    with open(os.path.join(contrib_directory, 'COMMITTERS.rst'), 'a') as f:
        max_len = len('Full Name                         ')
        for name, username in committers.items():
            table_name = get_table_entry(name, max_len)
            table_username = get_table_entry(username, max_len)
            f.write('| {}| {}|\n'.format(table_name, table_username))
            f.write('+-----------------------------------+-----------------------------------+\n')

def commit_changes_if_needed():
    committers_file = os.path.join(find_repository_root(), 'contrib/COMMITTERS.rst')
    git_diff_output = subprocess.check_output('git diff {}'.format(committers_file), shell=True)
    if git_diff_output:
        commit_message = 'contrib: Update COMMITTERS.rst'
        subprocess.call('git add {}'.format(committers_file), shell=True)
        subprocess.call('git commit -m {}'.format(commit_message), shell=True)

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
    commit_changes_if_needed()

if __name__ == '__main__':
    main()
