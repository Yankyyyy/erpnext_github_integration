import frappe, json
from frappe import _
from frappe.model.meta import get_table_columns
import datetime
import time
from datetime import datetime, timedelta
from dateutil import parser
import pytz
from concurrent.futures import ThreadPoolExecutor
import requests
from .github_client import github_request

def has_role(role):
    """Compatibility function for different Frappe versions"""
    try:
        return frappe.has_role(role)
    except AttributeError:
        return role in frappe.get_roles()

def convert_github_datetime(dt_string):
    if not dt_string:
        return None
    try:
        dt = parser.parse(dt_string)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        ist_tz = pytz.timezone('Asia/Kolkata')
        local_dt = dt.astimezone(ist_tz)
        return local_dt.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError) as e:
        frappe.log_error(f'Error parsing datetime {dt_string}: {str(e)}', 'DateTime Parse Error')
        return None

def _require_github_admin():
    if not has_role('GitHub Admin'):
        frappe.throw(_('Only users with the GitHub Admin role can perform this action.'))

def _can_sync_repo(repo_full_name):
    if has_role('GitHub Admin'):
        return True
    projects = frappe.get_all('Project', filters={'repository': repo_full_name}, fields=['name', 'project_manager'])
    user = frappe.session.user
    for p in projects:
        if p.get('project_manager') and p.get('project_manager') == user:
            return True
    return False

def _publish_progress(event='github_sync_progress', data=None, user=None):
    try:
        frappe.publish_realtime(event, data or {}, user=user)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Failed to publish realtime progress")

def _replace_child_table_rows_multi_insert(parent_doctype, parent_name, child_table_fieldname, rows):
    """
    Replace child table rows with a single multi-row INSERT (fast, DB-level).
    Ensure docstatus is included and set to 0 for all child table rows.
    """
    meta = frappe.get_meta(parent_doctype)
    child_meta = frappe.get_meta(meta.get_field(child_table_fieldname).options)
    valid_columns = child_meta.get_valid_columns()
    base_columns = ["name", "owner", "creation", "modified", "modified_by", 
                    "parent", "parentfield", "parenttype", "idx", "docstatus"]
    insert_columns = base_columns + [c for c in valid_columns if c not in base_columns]

    # Delete existing rows
    frappe.db.sql(f"""
        DELETE FROM `tab{child_meta.name}`
        WHERE parent=%s AND parentfield=%s AND parenttype=%s
    """, (parent_name, child_table_fieldname, parent_doctype))

    if not rows:
        return

    now = frappe.utils.now_datetime()
    values = []
    for idx, row in enumerate(rows, start=1):
        base_vals = {
            "name": frappe.generate_hash("", 10),
            "owner": frappe.session.user,
            "creation": now,
            "modified": now,
            "modified_by": frappe.session.user,
            "parent": parent_name,
            "parentfield": child_table_fieldname,
            "parenttype": parent_doctype,
            "idx": idx,
            "docstatus": 0  # Explicitly set docstatus to 0
        }
        vals = []
        for col in insert_columns:
            vals.append(base_vals.get(col, row.get(col)))
        values.append(vals)

    placeholders = "(" + ", ".join(["%s"] * len(insert_columns)) + ")"
    insert_sql = f"""
        INSERT INTO `tab{child_meta.name}` ({", ".join(f"`{c}`" for c in insert_columns)})
        VALUES {", ".join([placeholders] * len(values))}
    """
    flat_values = [val for row_vals in values for val in row_vals]
    frappe.db.sql(insert_sql, tuple(flat_values))

def fetch_paginated_data(path, token, params=None):
    params = params or {}
    params['per_page'] = 100
    results = []
    page = 1
    while True:
        params['page'] = page
        data = github_request('GET', path, token, params=params) or []
        results.extend(data)
        if len(data) < 100:
            break
        page += 1
    return results

def check_rate_limit(token):
    response = github_request('GET', '/rate_limit', token)
    remaining = response.get('rate', {}).get('remaining', 0)
    reset_time = response.get('rate', {}).get('reset', 0)
    if remaining < 100:
        reset_dt = datetime.fromtimestamp(reset_time)
        frappe.throw(f"GitHub API rate limit too low ({remaining} requests remaining). Try again after {reset_dt}.")
    return remaining

def github_request(method, path, token, params=None, data=None):
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f"https://api.github.com{path}"
    for attempt in range(3):
        try:
            response = requests.request(method, url, headers=headers, params=params, json=data)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise Exception(f"GitHub API request failed: {str(e)}")
            time.sleep(2 ** attempt)
    return {}

@frappe.whitelist()
def test_connection():
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        return {'success': False, 'error': 'GitHub Personal Access Token not configured'}
    try:
        check_rate_limit(token)
        user_info = github_request('GET', '/user', token)
        if user_info and user_info.get('login'):
            return {'success': True, 'user': user_info.get('login')}
        return {'success': False, 'error': 'Invalid response from GitHub API'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def get_github_username_by_email(email):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        return {'success': False, 'error': 'GitHub Personal Access Token not configured'}
    try:
        check_rate_limit(token)
        search_results = github_request('GET', f'/search/users?q={email}+in:email', token)
        if search_results and search_results.get('total_count', 0) > 0 and search_results.get('items'):
            return {
                'success': True,
                'github_username': search_results['items'][0]['login'],
                'total_results': search_results['total_count']
            }
        return {'success': False, 'error': f'No GitHub user found with email: {email}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def fetch_all_repositories(organization=None):
    try:
        settings = frappe.get_single('GitHub Settings')
        token = settings.get_password('personal_access_token')
        if not token:
            frappe.throw('GitHub Personal Access Token not configured')
        check_rate_limit(token)
        repos = fetch_paginated_data(f'/orgs/{organization}/repos' if organization else '/user/repos', token)
        if not repos:
            return {'success': False, 'message': 'No repositories found'}
        created_count = updated_count = 0
        for repo in repos:
            repo_name = repo.get('full_name')
            repo_data = {
                'full_name': repo_name,
                'repo_name': repo.get('name'),
                'repo_owner': repo.get('owner', {}).get('login'),
                'github_id': str(repo.get('id')),
                'url': repo.get('html_url'),
                'visibility': 'Private' if repo.get('private') else 'Public',
                'default_branch': repo.get('default_branch'),
                'is_synced': 0
            }
            if frappe.db.exists('Repository', {'full_name': repo_name}):
                doc = frappe.get_doc('Repository', {'full_name': repo_name})
                doc.update(repo_data)
                doc.save(ignore_permissions=True)
                updated_count += 1
            else:
                doc = frappe.get_doc({'doctype': 'Repository', **repo_data})
                doc.insert(ignore_permissions=True)
                created_count += 1
            if (created_count + updated_count) % 10 == 0:
                frappe.db.commit()
        frappe.db.commit()
        return {
            'success': True,
            'message': f'Successfully fetched {len(repos)} repositories. Created: {created_count}, Updated: {updated_count}'
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error fetching repositories: {str(e)}", "GitHub Fetch Repos")
        return {'success': False, 'message': f'Error: {str(e)}'}

@frappe.whitelist()
def get_sync_statistics():
    return {
        'repositories': frappe.db.count('Repository'),
        'issues': frappe.db.count('Repository Issue'),
        'pull_requests': frappe.db.count('Repository Pull Request'),
        'members': frappe.db.count('Repository Member'),
        'branches': frappe.db.count('Repository Branch')
    }

@frappe.whitelist()
def can_user_sync_repo(repo_full_name):
    return {'can_sync': _can_sync_repo(repo_full_name)}

@frappe.whitelist()
def list_repositories(organization=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    path = f"/orgs/{organization}/repos" if organization else "/user/repos"
    return fetch_paginated_data(path, token)

@frappe.whitelist()
def list_branches(repo_full_name, per_page=100):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    return fetch_paginated_data(f"/repos/{repo_full_name}/branches", token, params={'per_page': per_page})

@frappe.whitelist()
def list_teams(org_name, per_page=100):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    return fetch_paginated_data(f"/orgs/{org_name}/teams", token, params={'per_page': per_page})

@frappe.whitelist()
def list_repo_members(repo_full_name, per_page=100):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    try:
        return fetch_paginated_data(f"/repos/{repo_full_name}/collaborators", token, params={'per_page': per_page})
    except Exception as e:
        frappe.throw(_('GitHub list repo members failed: {0}').format(str(e)))

@frappe.whitelist()
def assign_issue(repo_full_name, issue_number, assignees):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    if isinstance(assignees, str):
        try:
            assignees = json.loads(assignees)
        except Exception:
            assignees = [a.strip() for a in assignees.split(',') if a.strip()]
    github_usernames = []
    rows = []
    try:
        local = frappe.get_doc('Repository Issue', {'repository': repo_full_name, 'issue_number': int(issue_number)})
        for user_id in assignees:
            gh_username = frappe.db.get_value("User", user_id, "github_username")
            if not gh_username:
                frappe.log_error(f"User {user_id} has no GitHub username set", "GitHub Assignee Mapping")
                continue
            github_usernames.append(gh_username)
            rows.append({'user': user_id, 'issue': local.name})
        _replace_child_table_rows_multi_insert('Repository Issue', local.name, 'assignees_table', rows)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Failed to update local Repository Issue assignees")
    payload = {'assignees': github_usernames}
    try:
        resp = github_request('PATCH', f"/repos/{repo_full_name}/issues/{issue_number}", token, data=payload)
        return resp
    except Exception as e:
        frappe.throw(_('GitHub assign issue failed: {0}').format(str(e)))

@frappe.whitelist()
def add_pr_reviewer(repo_full_name, pr_number, reviewers):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    if isinstance(reviewers, str):
        try:
            reviewers = json.loads(reviewers)
        except Exception:
            reviewers = [r.strip() for r in reviewers.split(',') if r.strip()]
    github_usernames = []
    rows = []
    try:
        local = frappe.get_doc('Repository Pull Request', {'repository': repo_full_name, 'pr_number': int(pr_number)})
        for user_id in reviewers:
            gh_username = frappe.db.get_value("User", user_id, "github_username")
            if not gh_username:
                frappe.log_error(f"User {user_id} has no GitHub username set", "GitHub Reviewer Mapping")
                continue
            github_usernames.append(gh_username)
            rows.append({'user': user_id, 'pull_request': local.name})
        _replace_child_table_rows_multi_insert('Repository Pull Request', local.name, 'reviewers_table', rows)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Failed to update local Repository Pull Request reviewers")
    payload = {'reviewers': github_usernames}
    try:
        resp = github_request('POST', f"/repos/{repo_full_name}/pulls/{pr_number}/requested_reviewers", token, data=payload)
        return resp
    except Exception as e:
        frappe.throw(_('GitHub add PR reviewer failed: {0}').format(str(e)))

@frappe.whitelist()
def sync_repo(repository, user=None):
    repo_full = repository
    _publish_progress(data={'repo': repo_full, 'phase': 'start', 'msg': f'Starting sync for {repo_full}'}, user=user)
    if not _can_sync_repo(repo_full):
        frappe.throw(_('You do not have permission to sync this repository.'))
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    try:
        # Initialize or fetch repository document
        repo_doc = frappe.get_doc('Repository', {'full_name': repo_full}) if frappe.db.exists('Repository', {'full_name': repo_full}) else frappe.get_doc({
            'doctype': 'Repository',
            'full_name': repo_full,
            'repo_name': repo_full.split('/')[-1],
            'repo_owner': repo_full.split('/')[0],
            'url': f'https://github.com/{repo_full}'
        })
        last_synced = repo_doc.last_synced
        params = {'state': 'all', 'per_page': 100}
        if last_synced:
            params['since'] = last_synced.isoformat()

        # Parallel API calls
        def fetch_repo_info():
            return github_request('GET', f'/repos/{repo_full}', token) or {}
        def fetch_branches():
            return fetch_paginated_data(f'/repos/{repo_full}/branches', token)
        def fetch_issues():
            return fetch_paginated_data(f'/repos/{repo_full}/issues', token, params=params)
        def fetch_pulls():
            return fetch_paginated_data(f'/repos/{repo_full}/pulls', token, params=params)
        def fetch_members():
            return fetch_paginated_data(f'/repos/{repo_full}/collaborators', token)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                'repo_info': executor.submit(fetch_repo_info),
                'branches': executor.submit(fetch_branches),
                'issues': executor.submit(fetch_issues),
                'pulls': executor.submit(fetch_pulls),
                'members': executor.submit(fetch_members)
            }
            repo_info = futures['repo_info'].result()
            branches = futures['branches'].result()
            issues = futures['issues'].result()
            pulls = futures['pulls'].result()
            members = futures['members'].result()

        # Update repository fields
        repo_doc.update({
            'github_id': str(repo_info.get('id', '')),
            'visibility': 'Private' if repo_info.get('private') else 'Public',
            'default_branch': repo_info.get('default_branch', 'main'),
            'is_synced': 1,
            'last_synced': frappe.utils.now()
        })

        # Prepare branches
        branch_rows = []
        for b in branches:
            commits = github_request('GET', f'/repos/{repo_full}/commits', token, params={'sha': b.get('name'), 'per_page': 1}) or []
            commit_date = convert_github_datetime(commits[0].get('commit', {}).get('author', {}).get('date')) if commits else None
            branch_rows.append({
                'repo_full_name': repo_full,
                'branch_name': b.get('name'),
                'commit_sha': b.get('commit', {}).get('sha'),
                'protected': b.get('protected', False),
                'last_updated': commit_date or ''
            })

        # Prepare members
        member_rows = []
        for m in members:
            user_info = github_request('GET', f"/users/{m.get('login')}", token) or {}
            member_rows.append({
                'repo_full_name': repo_full,
                'github_username': m.get('login'),
                'github_id': str(m.get('id', '')),
                'role': 'maintainer' if m.get('permissions', {}).get('admin') else 'member',
                'email': user_info.get('email') or ''
            })

        # Update child tables for Repository
        _replace_child_table_rows_multi_insert('Repository', repo_doc.name, 'branches_table', branch_rows)
        _replace_child_table_rows_multi_insert('Repository', repo_doc.name, 'members_table', member_rows)
        repo_doc.save(ignore_permissions=True)

        # Handle issues
        issue_rows = []
        issue_assignee_rows = {}
        for issue in issues:
            if issue.get('pull_request'):
                continue
            issue_name = frappe.generate_hash("", 10)
            issue_rows.append({
                'name': issue_name,
                'repository': repo_full,
                'issue_number': issue.get('number'),
                'title': issue.get('title'),
                'body': issue.get('body') or '',
                'state': issue.get('state'),
                'labels': ','.join([lab.get('name') for lab in issue.get('labels', [])]),
                'url': issue.get('html_url'),
                'github_id': str(issue.get('id', '')),
                'created_at': convert_github_datetime(issue.get('created_at')),
                'updated_at': convert_github_datetime(issue.get('updated_at'))
            })
            issue_assignee_rows[issue_name] = [
                {'user': frappe.db.get_value("User", {"github_username": assignee.get('login')}, "name") or assignee.get('login'), 'issue': issue_name}
                for assignee in issue.get('assignees', [])
            ]

        if issue_rows:
            # Delete existing issues to avoid duplicates
            frappe.db.sql(f"""
                DELETE FROM `tabRepository Issue`
                WHERE repository=%s AND issue_number IN %s
            """, (repo_full, [row['issue_number'] for row in issue_rows]))
            for issue_row in issue_rows:
                issue_doc = frappe.get_doc({
                    'doctype': 'Repository Issue',
                    **issue_row
                })
                issue_doc.insert(ignore_permissions=True)
                if issue_name in issue_assignee_rows:
                    _replace_child_table_rows_multi_insert('Repository Issue', issue_row['name'], 'assignees_table', issue_assignee_rows[issue_row['name']])

        # Handle pull requests
        pr_rows = []
        pr_reviewer_rows = {}
        for pr in pulls:
            pr_name = frappe.generate_hash("", 10)
            pr_rows.append({
                'name': pr_name,
                'repository': repo_full,
                'pr_number': pr.get('number'),
                'title': pr.get('title'),
                'body': pr.get('body') or '',
                'state': pr.get('state'),
                'head_branch': pr.get('head', {}).get('ref'),
                'base_branch': pr.get('base', {}).get('ref'),
                'author': pr.get('user', {}).get('login'),
                'mergeable_state': pr.get('mergeable_state'),
                'github_id': str(pr.get('id', '')),
                'url': pr.get('html_url'),
                'created_at': convert_github_datetime(pr.get('created_at')),
                'updated_at': convert_github_datetime(pr.get('updated_at'))
            })
            pr_reviewer_rows[pr_name] = [
                {'user': frappe.db.get_value("User", {"github_username": reviewer.get('login')}, "name") or reviewer.get('login'), 'pull_request': pr_name}
                for reviewer in pr.get('requested_reviewers', [])
            ]

        if pr_rows:
            # Delete existing pull requests to avoid duplicates
            frappe.db.sql(f"""
                DELETE FROM `tabRepository Pull Request`
                WHERE repository=%s AND pr_number IN %s
            """, (repo_full, [row['pr_number'] for row in pr_rows]))
            for pr_row in pr_rows:
                pr_doc = frappe.get_doc({
                    'doctype': 'Repository Pull Request',
                    **pr_row
                })
                pr_doc.insert(ignore_permissions=True)
                if pr_row['name'] in pr_reviewer_rows:
                    _replace_child_table_rows_multi_insert('Repository Pull Request', pr_row['name'], 'reviewers_table', pr_reviewer_rows[pr_row['name']])

        frappe.db.commit()

        if len(issues) >= 100 or len(pulls) >= 100:
            _publish_progress(data={'repo': repo_full, 'phase': 'done', 'msg': f'Sync complete for {repo_full}', 'issues': len([i for i in issues if not i.get('pull_request')]), 'pulls': len(pulls)}, user=user)
        
        return {
            'success': True,
            'message': f'Synced repository {repo_full}',
            'branches': len(branches),
            'issues': len([i for i in issues if not i.get('pull_request')]),
            'pulls': len(pulls),
            'members': len(members)
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error syncing repository {repo_full}: {str(e)}", "GitHub Sync Error")
        _publish_progress(data={'repo': repo_full, 'phase': 'error', 'msg': str(e)}, user=user)
        raise e

@frappe.whitelist()
def create_issue(repository, title, body=None, assignees=None, labels=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    payload = {'title': title}
    if body:
        payload['body'] = body
    if assignees:
        if isinstance(assignees, str):
            try:
                assignees = json.loads(assignees)
            except Exception:
                assignees = [a.strip() for a in assignees.split(',') if a.strip()]
        payload['assignees'] = assignees
    if labels:
        if isinstance(labels, str):
            try:
                labels = json.loads(labels)
            except Exception:
                labels = [l.strip() for l in labels.split(',') if l.strip()]
        payload['labels'] = labels
    resp = github_request('POST', f'/repos/{repository}/issues', token, data=payload)
    if resp:
        try:
            issue_name = frappe.generate_hash("", 10)
            doc = frappe.get_doc({
                'doctype': 'Repository Issue',
                'name': issue_name,
                'repository': repository,
                'issue_number': resp.get('number'),
                'title': resp.get('title'),
                'body': resp.get('body') or '',
                'state': resp.get('state'),
                'labels': ','.join([l.get('name') if isinstance(l, dict) else str(l) for l in resp.get('labels', [])]),
                'url': resp.get('html_url'),
                'github_id': str(resp.get('id', '')),
                'created_at': convert_github_datetime(resp.get('created_at')),
                'updated_at': convert_github_datetime(resp.get('updated_at'))
            })
            doc.insert(ignore_permissions=True)
            rows = [
                {'user': frappe.db.get_value("User", {"github_username": assignee.get('login')}, "name") or assignee.get('login'), 'issue': issue_name}
                for assignee in resp.get('assignees', [])
            ]
            _replace_child_table_rows_multi_insert('Repository Issue', issue_name, 'assignees_table', rows)
            frappe.db.commit()
            return {'issue': resp, 'local_doc': doc.name}
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(f"Error creating local issue: {str(e)}", "GitHub Create Issue")
    return resp

@frappe.whitelist()
def bulk_create_issues(repository, issues):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    if isinstance(issues, str):
        issues = json.loads(issues)
    created_issues = []
    issue_rows = []
    issue_assignee_rows = {}
    for i, issue_data in enumerate(issues):
        try:
            resp = github_request('POST', f'/repos/{repository}/issues', token, data=issue_data)
            if resp:
                created_issues.append(resp)
                issue_name = frappe.generate_hash("", 10)
                issue_rows.append({
                    'name': issue_name,
                    'repository': repository,
                    'issue_number': resp.get('number'),
                    'title': resp.get('title'),
                    'body': resp.get('body') or '',
                    'state': resp.get('state'),
                    'url': resp.get('html_url'),
                    'github_id': str(resp.get('id', '')),
                    'created_at': convert_github_datetime(resp.get('created_at')),
                    'updated_at': convert_github_datetime(resp.get('updated_at'))
                })
                issue_assignee_rows[issue_name] = [
                    {'user': frappe.db.get_value("User", {"github_username": assignee.get('login')}, "name") or assignee.get('login'), 'issue': issue_name}
                    for assignee in resp.get('assignees', [])
                ]
                if (i + 1) % 10 == 0:
                    frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Error creating issue: {str(e)}", "Bulk Create Issues")
    if issue_rows:
        frappe.get_doc({'doctype': 'Repository Issue', 'repository': repository}).insert(ignore_permissions=True)
        _replace_child_table_rows_multi_insert('Repository Issue', repository, 'issues_table', issue_rows)
        for issue_name, assignees in issue_assignee_rows.items():
            _replace_child_table_rows_multi_insert('Repository Issue', issue_name, 'assignees_table', assignees)
    frappe.db.commit()
    return {'created': len(created_issues), 'issues': created_issues}

@frappe.whitelist()
def create_pull_request(repository, title, head, base, body=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    payload = {'title': title, 'head': head, 'base': base}
    if body:
        payload['body'] = body
    resp = github_request('POST', f'/repos/{repository}/pulls', token, data=payload)
    if resp:
        try:
            pr_name = frappe.generate_hash("", 10)
            doc = frappe.get_doc({
                'doctype': 'Repository Pull Request',
                'name': pr_name,
                'repository': repository,
                'pr_number': resp.get('number'),
                'title': resp.get('title'),
                'body': resp.get('body') or '',
                'state': resp.get('state'),
                'head_branch': resp.get('head', {}).get('ref'),
                'base_branch': resp.get('base', {}).get('ref'),
                'author': resp.get('user', {}).get('login'),
                'mergeable_state': resp.get('mergeable_state'),
                'github_id': str(resp.get('id', '')),
                'url': resp.get('html_url'),
                'created_at': convert_github_datetime(resp.get('created_at')),
                'updated_at': convert_github_datetime(resp.get('updated_at'))
            })
            doc.insert(ignore_permissions=True)
            rows = [
                {'user': frappe.db.get_value("User", {"github_username": reviewer.get('login')}, "name") or reviewer.get('login'), 'pull_request': pr_name}
                for reviewer in resp.get('requested_reviewers', [])
            ]
            _replace_child_table_rows_multi_insert('Repository Pull Request', pr_name, 'reviewers_table', rows)
            frappe.db.commit()
            return {'pull_request': resp, 'local_doc': doc.name}
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(f"Error creating local PR: {str(e)}", "GitHub Create PR")
    return resp

@frappe.whitelist()
def sync_repo_members(repo_full_name):
    try:
        if not _can_sync_repo(repo_full_name):
            frappe.throw(_('You do not have permission to sync this repository.'))
        settings = frappe.get_single('GitHub Settings')
        token = settings.get_password('personal_access_token')
        if not token:
            frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
        check_rate_limit(token)
        members = fetch_paginated_data(f'/repos/{repo_full_name}/collaborators', token)
        repo_doc = frappe.get_doc('Repository', {'full_name': repo_full_name})
        member_rows = []
        for m in members or []:
            user_info = github_request('GET', f"/users/{m.get('login')}", token) or {}
            member_rows.append({
                'repo_full_name': repo_full_name,
                'github_username': m.get('login'),
                'github_id': str(m.get('id', '')),
                'role': 'maintainer' if m.get('permissions', {}).get('admin') else 'member',
                'email': user_info.get('email') or ''
            })
        _replace_child_table_rows_multi_insert('Repository', repo_doc.name, 'members_table', member_rows)
        repo_doc.save(ignore_permissions=True)
        projects = frappe.get_all('Project', filters={'repository': repo_full_name}, fields=['name'])
        for i, p in enumerate(projects):
            try:
                proj = frappe.get_doc('Project', p.get('name'))
                project_user_rows = []
                for m in members or []:
                    user_info = github_request('GET', f"/users/{m.get('login')}", token) or {}
                    m_email = user_info.get('email') or ''
                    username = m.get('login')
                    erp_user = frappe.db.get_value("User", {"github_username": username}, "name")
                    if not erp_user and m_email:
                        erp_user = frappe.db.get_value("User", {"email": m_email}, "name")
                        if erp_user:
                            user_doc = frappe.get_doc("User", erp_user)
                            user_doc.github_username = username
                            user_doc.save(ignore_permissions=True)
                    project_user_rows.append({
                        'user': erp_user or username,
                        'role': 'Project User'
                    })
                _replace_child_table_rows_multi_insert('Project', proj.name, 'project_users', project_user_rows)
                proj.save(ignore_permissions=True)
                if (i + 1) % 5 == 0:
                    frappe.db.commit()
            except Exception as e:
                frappe.log_error(f"Error updating project {p.get('name')}: {str(e)}", "GitHub Sync Project")
        frappe.db.commit()
        return {'members': len(members or [])}
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error syncing repository members: {str(e)}", "GitHub Sync Members")
        raise e

@frappe.whitelist()
def manage_repo_access(repo_full_name, action, identifier, permission='push'):
    _require_github_admin()
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    parts = repo_full_name.split('/')
    if len(parts) != 2:
        frappe.throw(_('repo_full_name must be in owner/repo format'))
    owner, repo = parts
    try:
        if action == 'add_collaborator':
            resp = github_request('PUT', f"/repos/{owner}/{repo}/collaborators/{identifier}", token, data={'permission': permission})
        elif action == 'remove_collaborator':
            resp = github_request('DELETE', f"/repos/{owner}/{repo}/collaborators/{identifier}", token)
        elif action == 'add_team':
            resp = github_request('PUT', f"/orgs/{owner}/teams/{identifier}/repos/{owner}/{repo}", token, data={'permission': permission})
        elif action == 'remove_team':
            resp = github_request('DELETE', f"/orgs/{owner}/teams/{identifier}/repos/{owner}/{repo}", token)
        else:
            frappe.throw(_('Unknown action: {0}').format(action))
        return resp
    except Exception as e:
        frappe.throw(_('manage_repo_access failed: {0}').format(str(e)))

@frappe.whitelist()
def start_sync_all_repositories():
    _require_github_admin()
    user = frappe.session.user
    frappe.enqueue('erpnext_github_integration.github_api.sync_all_repositories', queue='long', timeout=3600, is_async=True, user=user)
    return {'status': 'queued'}

@frappe.whitelist()
def sync_all_repositories(user=None):
    _require_github_admin()
    repos = frappe.get_all('Repository', fields=['full_name'])
    total = len(repos)
    results = {'success': 0, 'failed': 0}
    _publish_progress(data={'progress': 0, 'total': total, 'msg': 'Starting sync_all_repositories'}, user=user)
    for i, r in enumerate(repos):
        repo_name = r.get('full_name')
        try:
            start_ts = time.perf_counter()
            sync_repo(repo_name, user=user)
            results['success'] += 1
            dur = time.perf_counter() - start_ts
            if (i + 1) % 10 == 0 or i == len(repos) - 1:
                _publish_progress(data={
                    'progress': i + 1,
                    'total': total,
                    'repo': repo_name,
                    'status': 'ok',
                    'time_s': round(dur, 2),
                    'success': results['success'],
                    'failed': results['failed'],
                    'msg': f'Synced {repo_name} ({i + 1}/{total})'
                }, user=user)
        except Exception as e:
            results['failed'] += 1
            frappe.db.rollback()
            frappe.log_error(f"Error syncing {repo_name}: {str(e)}", f'GitHub Sync Error - {repo_name}')
            _publish_progress(data={
                'progress': i + 1,
                'total': total,
                'repo': repo_name,
                'status': 'error',
                'success': results['success'],
                'failed': results['failed'],
                'msg': f'Failed {repo_name}: {str(e)[:200]}'
            }, user=user)
        if i < len(repos) - 1:
            time.sleep(1)
    settings = frappe.get_single("GitHub Settings")
    settings.last_sync = frappe.utils.now()
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    _publish_progress(data={'progress': total, 'total': total, 'msg': 'Sync finished', 'success': results['success'], 'failed': results['failed']}, user=user)
    return results

@frappe.whitelist()
def get_repository_activity(repository, days=30):
    try:
        settings = frappe.get_single('GitHub Settings')
        token = settings.get_password('personal_access_token')
        check_rate_limit(token)
        try:
            days_int = int(days)
        except (ValueError, TypeError):
            days_int = 30
        days_int = max(1, min(days_int, 365))
        since = (datetime.now() - timedelta(days=days_int)).isoformat()
        commits = fetch_paginated_data(f'/repos/{repository}/commits', token, params={'since': since, 'per_page': 50})
        issues = fetch_paginated_data(f'/repos/{repository}/issues', token, params={'since': since, 'state': 'all', 'per_page': 20})
        pulls = fetch_paginated_data(f'/repos/{repository}/pulls', token, params={'since': since, 'state': 'all', 'per_page': 20})
        actual_issues = [issue for issue in issues if 'pull_request' not in issue]
        return {
            'commits': len(commits),
            'issues': len(actual_issues),
            'pulls': len(pulls),
            'period_days': days_int,
            'details': {
                'commits': commits[:10],
                'issues': actual_issues[:10],
                'pulls': pulls[:10]
            }
        }
    except Exception as e:
        frappe.log_error(f"Error getting repository activity: {str(e)}", "GitHub Activity")
        return {'error': str(e)}

@frappe.whitelist()
def create_repository_webhook(repo_full_name, webhook_url=None, events=None):
    _require_github_admin()
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    if not webhook_url:
        webhook_url = frappe.utils.get_url('/api/method/erpnext_github_integration.webhooks.github_webhook')
    if not events:
        events = ['push', 'pull_request', 'issues', 'issue_comment']
    payload = {
        'name': 'web',
        'active': True,
        'events': events,
        'config': {
            'url': webhook_url,
            'content_type': 'json'
        }
    }
    if settings.get_password('webhook_secret'):
        payload['config']['secret'] = settings.get_password('webhook_secret')
    try:
        resp = github_request('POST', f"/repos/{repo_full_name}/hooks", token, data=payload)
        return resp
    except Exception as e:
        frappe.throw(_('Failed to create webhook: {0}').format(str(e)))

@frappe.whitelist()
def list_repository_webhooks(repo_full_name):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    check_rate_limit(token)
    try:
        return fetch_paginated_data(f"/repos/{repo_full_name}/hooks", token)
    except Exception as e:
        frappe.throw(_('Failed to list webhooks: {0}').format(str(e)))