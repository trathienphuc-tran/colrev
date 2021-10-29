#! /usr/bin/env python3
import os
import sys

import git
import yaml

from review_template import repo_setup
from review_template import utils

repo = None
SHARE_STAT_REQ, MAIN_REFERENCES = None, None


class colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    ORANGE = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


def lsremote(url):
    remote_refs = {}
    g = git.cmd.Git()
    for ref in g.ls_remote(url).split('\n'):
        hash_ref_list = ref.split('\t')
        remote_refs[hash_ref_list[1]] = hash_ref_list[0]
    return remote_refs


def get_bib_files():
    bib_files = []
    search_dir = os.path.join(os.getcwd(), 'search/')
    bib_files = [os.path.join(search_dir, x)
                 for x in os.listdir(search_dir) if x.endswith('.bib')]
    return bib_files


def get_nr_in_bib(file_path):

    number_in_bib = 0
    with open(file_path) as f:
        line = f.readline()
        while line:
            # Note: the '﻿' occured in some bibtex files
            # (e.g., Publish or Perish exports)
            if line.replace('﻿', '').lstrip()[:1] == '@':
                if not '@comment' == \
                        line.replace('﻿', '').lstrip()[:8].lower():
                    number_in_bib += 1
            line = f.readline()

    return number_in_bib


def get_nr_search():
    number_search = 0
    for search_file in get_bib_files():
        number_search += get_nr_in_bib(search_file)
    return number_search


def get_status_freq():
    MAIN_REFERENCES = repo_setup.paths['MAIN_REFERENCES']

    md_imported = 0
    md_prepared = 0
    md_need_man_prep = 0
    md_need_man_dedupe = 0
    md_processed = 0

    pdfs_need_retrieval = 0
    pdfs_imported = 0
    pdfs_need_man_prep = 0
    pdfs_overall_prepared = 0
    pdfs_not_available = 0

    rev_retrieved = 0
    rev_prescreen_included = 0
    rev_prescreen_excluded = 0
    rev_screen_included = 0
    rev_screen_excluded = 0
    rev_coded = 0

    entry_links = 0
    md_duplicates_removed = 0

    if os.path.exists(MAIN_REFERENCES):
        with open(MAIN_REFERENCES) as f:
            line = f.readline()
            while line:
                if ' rev_status ' in line:
                    if '{retrieved}' in line:
                        rev_retrieved += 1
                    if '{prescreen_included}' in line:
                        rev_prescreen_included += 1
                    if '{prescreen_excluded}' in line:
                        rev_prescreen_excluded += 1
                    if '{included}' in line:
                        rev_screen_included += 1
                    if '{excluded}' in line:
                        rev_screen_excluded += 1
                    if '{coded}' in line:
                        rev_coded += 1
                if ' md_status ' in line:
                    if '{imported}' in line:
                        md_imported += 1
                    if '{needs_manual_preparation}' in line:
                        md_need_man_prep += 1
                    if '{prepared}' in line:
                        md_prepared += 1
                    if '{needs_manual_merging}' in line:
                        md_need_man_dedupe += 1
                    if '{processed}' in line:
                        md_processed += 1
                if ' pdf_status ' in line:
                    if '{needs_retrieval}' in line:
                        pdfs_need_retrieval += 1
                    if '{imported}' in line:
                        pdfs_imported += 1
                    if '{needs_manual_preparation}' in line:
                        pdfs_need_man_prep += 1
                    if '{prepared}' in line:
                        pdfs_overall_prepared += 1
                    if '{not_available}' in line:
                        pdfs_not_available += 1
                if ' origin ' in line:
                    nr_entry_links = line.count(';')
                    entry_links += nr_entry_links + 1
                    md_duplicates_removed += nr_entry_links

                line = f.readline()

    # Reverse order (overall_x means x or later status)
    md_overall_processed = md_processed
    md_overall_prepared = md_overall_processed + \
        md_need_man_dedupe + md_duplicates_removed + md_prepared
    md_overall_imported = \
        md_overall_prepared + md_need_man_prep + md_imported
    md_overall_retrieved = get_nr_search()

    md_non_imported = md_overall_retrieved - entry_links

    # Reverse order (overall_x means x or later status)
    pdfs_overall_prepared = pdfs_overall_prepared
    pdfs_overall_retrieved = \
        pdfs_overall_prepared + pdfs_need_man_prep + pdfs_imported
    pdfs_overall_required = \
        pdfs_overall_retrieved + pdfs_need_retrieval + pdfs_not_available

    # Reverse order (overall_x means x or later status)
    rev_overall_coded = rev_coded
    rev_overall_included = rev_screen_included + rev_coded
    rev_overall_excluded = rev_screen_excluded
    rev_overall_screen = pdfs_overall_prepared
    rev_overall_prescreen_included = \
        rev_prescreen_included + rev_overall_excluded + rev_overall_included
    rev_overall_prescreen = md_processed

    rev_need_prescreen = rev_overall_prescreen - \
        rev_overall_prescreen_included - rev_prescreen_excluded
    rev_need_screen = \
        rev_overall_screen - rev_overall_included - rev_screen_excluded
    rev_overall_coding = rev_screen_included
    rev_need_coding = rev_screen_included - rev_coded

    non_bw_searched = 0

    if os.path.exists('pdfs/'):
        pdf_files = [x for x in os.listdir('pdfs/')]
        search_files = [x for x in os.listdir('search/') if '.bib' == x[-4:]]
        non_bw_searched = len([x for x in pdf_files
                               if not x.replace('.pdf', 'bw_search.bib')
                               in search_files])
    freqs = {'md_non_imported': md_non_imported,
             'md_imported': md_imported,
             'md_prepared': md_prepared,
             'md_need_man_prep': md_need_man_prep,
             'md_duplicates_removed': md_duplicates_removed,
             'md_need_man_dedupe': md_need_man_dedupe,
             'md_processed': md_processed,
             'md_overall_retrieved': md_overall_retrieved,
             'md_overall_imported': md_overall_imported,
             'md_overall_prepared': md_overall_prepared,
             'md_overall_processed': md_overall_processed,
             \
             'pdfs_need_retrieval': pdfs_need_retrieval,
             'pdfs_not_available': pdfs_not_available,
             'pdfs_imported': pdfs_imported,
             'pdfs_need_man_prep': pdfs_need_man_prep,
             'pdfs_overall_required': pdfs_overall_required,
             'pdfs_overall_retrieved': pdfs_overall_retrieved,
             'pdfs_overall_prepared': pdfs_overall_prepared,
             \
             'rev_retrieved': rev_retrieved,
             'rev_need_prescreen': rev_need_prescreen,
             'rev_prescreen_excluded': rev_prescreen_excluded,
             'rev_prescreen_included': rev_prescreen_included,
             'rev_need_screen': rev_need_screen,
             'rev_screen_excluded': rev_screen_excluded,
             'rev_screen_included': rev_screen_included,
             'rev_need_coding': rev_need_coding,
             'rev_coded': rev_coded,
             'rev_overall_prescreen': rev_overall_prescreen,
             'rev_overall_prescreen_included': rev_overall_prescreen_included,
             'rev_overall_screen': rev_overall_screen,
             'rev_overall_coded': rev_overall_coded,
             'rev_overall_coding': rev_overall_coding,
             \
             'non_bw_searched': non_bw_searched,
             }

    return freqs


def get_status():
    status_of_records = []

    with open(repo_setup.paths['MAIN_REFERENCES']) as f:
        line = f.readline()
        while line:
            if line.lstrip().startswith('status'):
                status_of_records.append(line.replace('status', '')
                                             .replace('=', '')
                                             .replace('{', '')
                                             .replace('}', '')
                                             .replace(',', '')
                                             .lstrip().rstrip())
            line = f.readline()
        status_of_records = list(set(status_of_records))

    return status_of_records


def get_remote_commit_differences(repo):
    nr_commits_behind, nr_commits_ahead = -1, -1

    if repo.active_branch.tracking_branch() is not None:

        branch_name = str(repo.active_branch)
        tracking_branch_name = str(repo.active_branch.tracking_branch())
        print(f'{branch_name} - {tracking_branch_name}')
        behind_operation = branch_name + '..' + tracking_branch_name
        commits_behind = repo.iter_commits(behind_operation)
        ahead_operation = tracking_branch_name + '..' + branch_name
        commits_ahead = repo.iter_commits(ahead_operation)
        nr_commits_behind = (sum(1 for c in commits_behind))
        nr_commits_ahead = (sum(1 for c in commits_ahead))

        # TODO: check whether this also considers non-pulled changes!? (fetch?)

    return nr_commits_behind, nr_commits_ahead


def is_git_repo(path):
    try:
        _ = git.Repo(path).git_dir
        return True
    except git.exc.InvalidGitRepositoryError:
        return False


def repository_validation():
    global repo
    if not is_git_repo(os.getcwd()):
        print('No git repository. Use '
              f'{colors.GREEN}review_template init{colors.END}')
        sys.exit()

    repo = git.Repo('')

    required_paths = ['search', 'private_config.ini',
                      'shared_config.ini', '.pre-commit-config.yaml',
                      '.gitignore']
    if not all(os.path.exists(x) for x in required_paths):
        print('No review_template repository\n  Missing: ' +
              ', '.join([x for x in required_paths if not os.path.exists(x)]) +
              '\n  To retrieve a shared repository, use ' +
              f'{colors.GREEN}review_template init{colors.END}.' +
              '\n  To initalize a new repository, execute the command ' +
              'in an empty directory.\nExit.')
        sys.exit()

    with open('.pre-commit-config.yaml') as pre_commit_y:
        pre_commit_config = yaml.load(pre_commit_y, Loader=yaml.FullLoader)
    installed_hooks = []
    remote_pv_hooks_repo = \
        'https://github.com/geritwagner/pipeline-validation-hooks'
    for repository in pre_commit_config['repos']:
        if repository['repo'] == remote_pv_hooks_repo:
            local_hooks_version = repository['rev']
            installed_hooks = [hook['id'] for hook in repository['hooks']]
    if not installed_hooks == ['consistency-checks', 'formatting']:
        print(f'{colors.RED}Pre-commit hooks not installed{colors.END}.'
              '\n See '
              'https://github.com/geritwagner/pipeline-validation-hooks'
              '#using-the-pre-commit-hook for details')
        sys.exit()

    try:
        refs = lsremote(remote_pv_hooks_repo)
        remote_sha = refs['HEAD']

        if not remote_sha == local_hooks_version:
            # Default: automatically update hooks
            print('Updating pre-commit hooks...')
            os.system('pre-commit autoupdate')

            print('Commit updated pre-commit hooks')
            repo.index.add(['.pre-commit-config.yaml'])
            repo.index.commit(
                'Update pre-commit-config' + utils.get_version_flag() +
                utils.get_commit_report(),
                author=git.Actor('script:' + os.path.basename(__file__), ''),
                committer=git.Actor(repo_setup.config['GIT_ACTOR'],
                                    repo_setup.config['EMAIL']),
            )
        # we could offer a parameter to disable autoupdates (warn accordingly)
        #     print('  pipeline-validation-hooks version outdated.\n  use ',
        #           f'{colors.RED}pre-commit autoupdate{colors.END}')
        #     sys.exit()
        #     # once we use tags, we may consider recommending
        #     # pre-commit autoupdate --bleeding-edge
    except git.exc.GitCommandError:
        print('  Warning: No Internet connection, cannot check remote '
              'pipeline-validation-hooks repository for updates.')
        pass

    return


def repository_load():
    global repo

    # TODO: check whether it is a valid git repo

    # Notify users when changes in bib files are not staged
    # (this may raise unexpected errors)
    non_tracked = [item.a_path for item in repo.index.diff(None)
                   if '.bib' == item.a_path[-4:]]
    if len(non_tracked) > 0:
        print('Warning: Non-tracked files that may cause failing checks: '
              + ','.join(non_tracked))
    return


def stat_print(field1, val1, connector=None, field2=None, val2=None):
    if field2 is None:
        field2 = ''
    if val2 is None:
        val2 = ''
    if field1 != '':
        stat = ' |  - ' + field1
    else:
        stat = ' | '
    rjust_padd = 35-len(stat)
    stat = stat + str(val1).rjust(rjust_padd, ' ')
    if connector is not None:
        stat = stat + '  ' + connector + '  '
    if val2 != '':
        rjust_padd = 45-len(stat)
        stat = stat + str(val2).rjust(rjust_padd, ' ') + ' '
    if field2 != '':
        stat = stat + str(field2) + '.'
    print(stat)
    return


def review_status():
    global status_freq

    # Principle: first column shows total records/PDFs in each stage
    # the second column shows
    # (blank call)  * the number of records requiring manual action
    #               -> the number of records excluded/merged

    print('\nStatus\n')

    if not os.path.exists(repo_setup.paths['MAIN_REFERENCES']):
        print(' | Search')
        print(' |  - Not initiated')
    else:
        status_freq = get_status_freq()
        # TODO: set all status_freq to str() to avoid frequent str() calls
        # for the Instructions, parse all to int
        # Search

        print(' | Search')
        stat_print('Records retrieved',
                   status_freq['md_overall_retrieved'])
        if status_freq['md_non_imported'] > 0:
            stat_print('', '', '*', 'record(s) not yet imported',
                       status_freq['md_non_imported'])
        stat_print('Records imported', status_freq['md_overall_imported'])
        if status_freq['md_imported'] > 0:
            stat_print('', '', '*', 'record(s) need preparation',
                       status_freq['md_imported'])
        if status_freq['md_need_man_prep'] > 0:
            stat_print('', '', '*', 'record(s) need manual preparation',
                       status_freq['md_need_man_prep'])
        stat_print('Records prepared', status_freq['md_overall_prepared'])
        if status_freq['md_prepared'] > 0:
            stat_print('', '', '*', 'record(s) need merging',
                       status_freq['md_prepared'])
        if status_freq['md_need_man_dedupe'] > 0:
            stat_print('', '', '*', 'record(s) need manual merging',
                       status_freq['md_need_man_dedupe'])
        stat_print('Records processed',
                   status_freq['md_overall_processed'], '->',
                   'duplicates removed',
                   status_freq['md_duplicates_removed'])

        print(' |')
        print(' | Pre-screen')
        if status_freq['rev_overall_prescreen'] == 0:
            stat_print('Not initiated', '')
        else:
            stat_print('Prescreen size', status_freq['rev_overall_prescreen'])
            if 0 != status_freq['rev_need_prescreen']:
                stat_print('', '', '*', 'records to prescreen',
                           status_freq['rev_need_prescreen'])
            stat_print('Included',
                       status_freq['rev_overall_prescreen_included'],
                       '->', 'records excluded',
                       status_freq['rev_prescreen_excluded'])

        print(' |')
        print(' | PDFs')

        stat_print('PDFs required', status_freq['pdfs_overall_required'])
        if 0 != status_freq['pdfs_need_retrieval']:
            stat_print('', '', '*', 'PDFs to retrieve',
                       status_freq['pdfs_need_retrieval'])
        if status_freq['pdfs_not_available'] > 0:
            stat_print('PDFs retrieved',
                       status_freq['pdfs_overall_retrieved'],
                       '*', 'PDFs not available',
                       status_freq['pdfs_not_available'])
        else:
            stat_print('PDFs retrieved',
                       status_freq['pdfs_overall_retrieved'])
        if status_freq['pdfs_need_man_prep'] > 0:
            stat_print('', '', '*', 'PDFs need manual preparation',
                       status_freq['pdfs_need_man_prep'])
        if 0 != status_freq['pdfs_imported']:
            stat_print('', '', '*', 'PDFs to prepare',
                       status_freq['pdfs_imported'])
        stat_print('PDFs prepared', status_freq['pdfs_overall_prepared'])

        print(' |')
        print(' | Screen')
        if status_freq['rev_overall_screen'] == 0:
            stat_print('Not initiated', '')
        else:
            stat_print('Screen size', status_freq['rev_overall_screen'])
            if 0 != status_freq['rev_need_screen']:
                stat_print('', '', '*', 'records to screen',
                           status_freq['rev_need_screen'])
            stat_print('Included', status_freq['rev_screen_included'], '->',
                       'records excluded', status_freq['rev_screen_excluded'])

        print(' |')
        print(' | Data and synthesis')
        if status_freq['rev_need_coding'] == 0:
            stat_print('Not initiated', '')
        else:
            stat_print('Total', status_freq['rev_overall_coding'])
            if 0 != status_freq['rev_need_coding']:
                stat_print('Coded', status_freq['rev_overall_coded'], '*',
                           'need coding', status_freq['rev_need_coding'])

    return


def review_instructions(status_freq=None):
    if status_freq is None:
        status_freq = get_status_freq()

    print('\n\nInstructions\n')
    # Note: review_template init is suggested in repository_validation()
    if not os.path.exists(repo_setup.paths['MAIN_REFERENCES']):
        print('  To import, copy search results to the search directory. ' +
              'Then use\n     review_template process')
        return

    if status_freq['md_non_imported'] > 0:
        print('  To import, use\n     review_template process')
        return

    if status_freq['md_need_man_prep'] > 0:
        print('  To continue with manual preparation, '
              'use\n     review_template man-prep')
        return

    if status_freq['md_prepared'] > 0:
        print('  To continue with entry preparation, '
              'use\n     review_template process')
        return

    if status_freq['md_need_man_dedupe'] > 0:
        print('  To continue manual processing of duplicates, '
              'use\n     review_template man-dedupe')
        return

    # TODO: if pre-screening activated in template variables
    if status_freq['rev_need_prescreen'] > 0:
        print('  To continue with prescreen, '
              'use\n     review_template prescreen')
        return

    if status_freq['pdfs_need_retrieval'] > 0:
        print('  To continue with pdf acquisition, '
              'use\n     review_template pdfs')
        return

    if status_freq['pdfs_imported'] > 0:
        print('  To continue with pdf preparation, '
              'use\n     review_template pdf-prepare')
        return

    # TBD: how/when should we offer that option?
    # if status_freq['non_bw_searched'] > 0:
    #     print('  To execute backward search, '
    #           'use\n     review_template back-search')
        # no return because backward searches are optional

    if status_freq['rev_need_screen'] > 0:
        print('  To continue with screen, '
              'use\n     review_template screen')
        return

    # TODO: if data activated in template variables
    if status_freq['rev_need_coding'] > 0:
        print('  To continue with data extraction/analysis, '
              'use\n     review_template data')
        return

    print('\n  Nothing to do. To start another review cycle, add '
          'papers to search/ and use\n     review_template process')
    if 'MANUSCRIPT' == repo_setup.config['DATA_FORMAT']:
        print('\n  To build the paper use\n     review_template paper')
    return status_freq


def collaboration_instructions(status_freq):

    print('\n\nVersioning and collaboration\n')

    if repo.is_dirty():
        print(f'  {colors.RED}Uncommitted changes{colors.END}'
              '\n  To add, use\n     git add .'
              '\n  To commit, use\n     git commit -m')
    print('\n  To inspect changes, use\n     gitk')

    print()
    nr_commits_behind, nr_commits_ahead = get_remote_commit_differences(repo)

    if nr_commits_behind == -1 and nr_commits_ahead == -1:
        print('  Not connected to a shared repository '
              '(tracking a remote branch).\n  Create remote repository and '
              'use\n     git remote add origin https://github.com/user/repo\n'
              f'     git push origin {repo.active_branch.name}')
    else:
        print(f' Requirement: {SHARE_STAT_REQ}')

        if nr_commits_behind > 0:
            print('Remote changes available on the server.\n'
                  'Once you have committed your changes, get the latest '
                  'remote changes. Use \n   git pull')
        if nr_commits_ahead > 0:
            print('Local changes not yet on the server.\n'
                  'Once you have committed your changes, upload them '
                  'to the remote server. Use \n   git push')

        if SHARE_STAT_REQ == 'NONE':
            print(f' Currently: '
                  f'{colors.GREEN}ready for sharing{colors.END}'
                  f' (if consistency checks pass)')

        # TODO all the following: should all search results be imported?!
        if SHARE_STAT_REQ == 'PROCESSED':
            non_processed = status_freq['md_non_imported'] + \
                status_freq['md_imported'] + \
                status_freq['md_prepared'] + \
                status_freq['md_need_man_prep'] + \
                status_freq['md_duplicates_removed'] + \
                status_freq['md_need_man_dedupe']
            if len(non_processed) == 0:
                print(f' Currently: '
                      f'{colors.GREEN}ready for sharing{colors.END}'
                      f' (if consistency checks pass)')
            else:
                print(f' Currently: '
                      f'{colors.RED}not ready for sharing{colors.END}\n'
                      f'  All records should be processed before sharing '
                      '(see instructions above).')

        # Note: if we use all(...) in the following,
        # we do not need to distinguish whether
        # a PRE_SCREEN or INCLUSION_SCREEN is needed
        if SHARE_STAT_REQ == 'SCREENED':
            non_screened = status_freq['rev_retrieved'] + \
                status_freq['rev_need_prescreen'] + \
                status_freq['rev_need_screen']

            if len(non_screened) == 0:
                print(f' Currently:'
                      f' {colors.GREEN}ready for sharing{colors.END}'
                      f' (if consistency checks pass)')
            else:
                print(f' Currently: '
                      f'{colors.RED}not ready for sharing{colors.END}\n'
                      f'  All records should be screened before sharing '
                      '(see instructions above).')

        if SHARE_STAT_REQ == 'COMPLETED':
            non_completed = status_freq['rev_retrieved'] + \
                status_freq['rev_need_prescreen'] + \
                status_freq['rev_need_screen'] + \
                status_freq['rev_overall_included']
            if len(non_completed) == 0:
                print(f' Currently: '
                      f'{colors.GREEN}ready for sharing{colors.END}'
                      f' (if consistency checks pass)')
            else:
                print(f' Currently: '
                      f'{colors.RED}not ready for sharing{colors.END}\n'
                      f'  All records should be completed before sharing '
                      '(see instructions above).')

    print('\n')

    return


def main():

    repository_validation()
    repository_load()
    status_freq = review_status()
    review_instructions(status_freq)
    collaboration_instructions(status_freq)

    print('Documentation\n\n   '
          'See https://github.com/geritwagner/review_template/docs\n')

    return


if __name__ == '__main__':
    main()
