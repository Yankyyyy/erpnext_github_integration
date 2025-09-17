import frappe, json
from frappe import _
import datetime
from datetime import datetime, timedelta
from dateutil import parser
import pytz
from .github_client import github_request
from frappe.desk.form.assign_to import add, clear
import time

def has_role(role):
    """Compatibility function for different Frappe versions"""
    try:
        # For older Frappe versions
        return frappe.has_role(role)
    except AttributeError:
        # For Frappe v15+
        return role in frappe.get_roles()
    
# Helper function to convert GitHub datetime to MySQL format
def convert_github_datetime(dt_string):
    if not dt_string:
        return None
    try:
        # Parse ISO 8601 format
        dt = parser.parse(dt_string)
        
        # Ensure it's treated as UTC if no timezone info
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        elif dt.tzinfo.utcoffset(dt) == pytz.utc.utcoffset(dt):
            pass  # Already UTC
        
        # Convert to IST
        ist_tz = pytz.timezone('Asia/Kolkata')
        local_dt = dt.astimezone(ist_tz)
        
        # Return without timezone info for MySQL
        return local_dt.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
        
    except (ValueError, TypeError) as e:
        frappe.log_error(f'Error parsing datetime {dt_string}: {str(e)}', 'DateTime Parse Error')
        return None

# Helper function to convert MySQL (IST) datetime to GitHub UTC ISO
def convert_to_github_datetime(local_dt_str):
    if not local_dt_str:
        return None
    try:
        dt = datetime.strptime(local_dt_str, '%Y-%m-%d %H:%M:%S')
        ist_tz = pytz.timezone('Asia/Kolkata')
        local_dt = ist_tz.localize(dt)
        utc_dt = local_dt.astimezone(pytz.utc)
        return utc_dt.isoformat()
    except Exception as e:
        frappe.log_error(f'Error converting datetime {local_dt_str}: {str(e)}', 'DateTime Convert Error')
        return None
        
# Usage
# if not has_role('GitHub Admin'):
#     frappe.throw("Permission required")

def _require_github_admin():
    if not has_role('GitHub Admin'):
        frappe.throw(_('Only users with the GitHub Admin role can perform this action.'))

def _can_sync_repo(repo_full_name):
    """Return True if current user can sync the repo:
       - GitHub Admins can always sync
       - Project Manager of any Project linked to this repo can sync
    """
    if has_role('GitHub Admin'):
        return True
    projects = frappe.get_all('Project', filters={'repository': repo_full_name}, fields=['name', 'project_manager'])
    user = frappe.session.user
    for p in projects:
        if p.get('project_manager') and p.get('project_manager') == user:
            return True
    return False

@frappe.whitelist()
def test_connection():
    """Test GitHub API connection"""
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        return {'success': False, 'error': 'GitHub Personal Access Token not configured'}
    
    try:
        user_info = github_request('GET', '/user', token)
        if user_info and user_info.get('login'):
            return {'success': True, 'user': user_info.get('login')}
        else:
            return {'success': False, 'error': 'Invalid response from GitHub API'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    
@frappe.whitelist()
def get_github_username_by_email(email):
    """Fetch GitHub username from GitHub API using email"""
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    
    if not token:
        return {'success': False, 'error': 'GitHub Personal Access Token not configured'}
    
    try:
        # Use github_request to search for users by email
        search_results = github_request('GET', f'/search/users?q={email}+in:email', token)
        
        if search_results and search_results.get('total_count', 0) > 0 and search_results.get('items'):
            # Return the first matching username
            return {
                'success': True,
                'github_username': search_results['items'][0]['login'],
                'total_results': search_results['total_count']
            }
        else:
            return {
                'success': False, 
                'error': f'No GitHub user found with email: {email}'
            }
            
    except Exception as e:
        return {'success': False, 'error': str(e)}
    
@frappe.whitelist()
def fetch_all_repositories(organization=None):
    """Fetch all repositories from GitHub and create/update them in ERPNext"""
    try:
        settings = frappe.get_single('GitHub Settings')
        token = settings.get_password('personal_access_token')
        
        if not token:
            frappe.throw('GitHub Personal Access Token not configured')
        
        # Get repositories from GitHub
        if organization:
            repos = github_request('GET', f'/orgs/{organization}/repos', token, params={'per_page': 100})
        else:
            repos = github_request('GET', '/user/repos', token, params={'per_page': 100, 'affiliation': 'owner'})
        
        if not repos:
            return {'success': False, 'message': 'No repositories found'}
        
        created_count = 0
        updated_count = 0
        
        for repo in repos:
            # Check if repository already exists
            repo_name = repo.get('full_name')
            existing_repo = frappe.db.exists('Repository', {'full_name': repo_name})
            
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
            
            if existing_repo:
                # Update existing repository
                doc = frappe.get_doc('Repository', existing_repo)
                doc.update(repo_data)
                doc.save()
                updated_count += 1
                frappe.logger().info(f"Updated repository: {repo_name}")
            else:
                # Create new repository
                doc = frappe.get_doc({
                    'doctype': 'Repository',
                    **repo_data
                })
                doc.insert()
                created_count += 1
                frappe.logger().info(f"Created repository: {repo_name}")
        
        return {
            'success': True,
            'message': f'Successfully fetched {len(repos)} repositories. Created: {created_count}, Updated: {updated_count}'
        }
        
    except Exception as e:
        frappe.logger().error(f"Error fetching repositories: {str(e)}")
        return {'success': False, 'message': f'Error: {str(e)}'}

@frappe.whitelist()
def get_sync_statistics():
    """Get synchronization statistics"""
    stats = {
        'repositories': frappe.db.count('Repository'),
        'issues': frappe.db.count('Repository Issue'),
        'pull_requests': frappe.db.count('Repository Pull Request'),
        'members': frappe.db.count('Repository Member'),
        'branches': frappe.db.count('Repository Branch')
    }
    return stats

@frappe.whitelist()
def can_user_sync_repo(repo_full_name):
    return {'can_sync': _can_sync_repo(repo_full_name)}

@frappe.whitelist()
def list_repositories(organization=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    if organization:
        path = f"/orgs/{organization}/repos"
    else:
        path = "/user/repos"
    return github_request('GET', path, token, params={'per_page': 100})

@frappe.whitelist()
def list_branches(repo_full_name, per_page=100):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    path = f"/repos/{repo_full_name}/branches"
    return github_request('GET', path, token, params={'per_page': per_page})

@frappe.whitelist()
def list_teams(org_name, per_page=100):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    path = f"/orgs/{org_name}/teams"
    return github_request('GET', path, token, params={'per_page': per_page})

@frappe.whitelist()
def list_repo_members(repo_full_name, per_page=100):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    try:
        members = github_request('GET', f"/repos/{repo_full_name}/collaborators", token, params={'per_page': per_page})
    except Exception as e:
        frappe.throw(_('GitHub list repo members failed: {0}').format(str(e)))
    return members

@frappe.whitelist()
def assign_issue(repo_full_name, issue_number, assignees):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))

    # normalize assignees input
    if isinstance(assignees, str):
        try:
            assignees = json.loads(assignees)
        except Exception:
            assignees = [a.strip() for a in assignees.split(',') if a.strip()]

    github_usernames = []

    try:
        local = frappe.get_doc('Repository Issue', {
            'repository': repo_full_name,
            'issue_number': int(issue_number)
        })

        # Find linked Task (if any)
        task = frappe.db.get_value(
            'Task',
            {
                'github_repo': repo_full_name,
                'github_issue_number': int(issue_number)
            },
            ['name', 'subject'],
            as_dict=1
        )

        # Reset assignees table
        local.set('assignees_table', [])

        # Clear existing assignments
        clear("Repository Issue", local.name)
        if task:
            clear("Task", task.name)

        for user_id in assignees:
            # map ERPNext user → GitHub username
            gh_username = frappe.db.get_value("User", user_id, "github_username")

            if not gh_username:
                frappe.log_error(
                    f"User {user_id} has no GitHub username set",
                    "GitHub Assignee Mapping"
                )
                continue  # skip if no GitHub username

            github_usernames.append(gh_username)

            # store ERPNext user (email / id) in local doc
            local.append('assignees_table', {
                'issue': local.name,
                'user': user_id
            })

            # also create ERPNext assignments
            try:
                if task:
                    add({
                        "assign_to": [user_id],
                        "doctype": "Task",
                        "name": task.name,
                        "description": task.subject
                    })
                add({
                    "assign_to": [user_id],
                    "doctype": "Repository Issue",
                    "name": local.name,
                    "description": _("Assigned from GitHub Issue #{0}".format(issue_number))
                })
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Failed to create Frappe assignment")

        local.save(ignore_permissions=True)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Failed to update local Repository Issue assignees")

    # send to GitHub (GitHub API needs GitHub usernames)
    payload = {'assignees': github_usernames}
    try:
        resp = github_request(
            'PATCH',
            f"/repos/{repo_full_name}/issues/{issue_number}",
            token,
            data=payload
        )
    except Exception as e:
        frappe.throw(_('GitHub assign issue failed: {0}').format(str(e)))

    return resp

@frappe.whitelist()
def add_pr_reviewer(repo_full_name, pr_number, reviewers):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    if isinstance(reviewers, str):
        try:
            reviewers = json.loads(reviewers)
        except Exception:
            reviewers = [r.strip() for r in reviewers.split(',') if r.strip()]
    payload = {'reviewers': reviewers}
    try:
        resp = github_request('POST', f"/repos/{repo_full_name}/pulls/{pr_number}/requested_reviewers", token, data=payload)
    except Exception as e:
        frappe.throw(_('GitHub add PR reviewer failed: {0}').format(str(e)))
    if resp:
        try:
            local = frappe.get_doc('Repository Pull Request', {'repository': repo_full_name, 'pr_number': int(pr_number)})
            # Update reviewers table
            local.set('reviewers_table', [])
            for reviewer in reviewers:
                local.append('reviewers_table', {
                    'user': reviewer
                })
            local.save(ignore_permissions=True)
        except Exception:
            pass
        return resp
    return resp

@frappe.whitelist()
def sync_repo(repository):
    repo_full = repository
    if not _can_sync_repo(repo_full):
        frappe.throw(_('You do not have permission to sync this repository.'))
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    
    # Get repository info
    repo_info = github_request('GET', f'/repos/{repo_full}', token) or {}
    branches = github_request('GET', f'/repos/{repo_full}/branches', token) or []
    members = github_request('GET', f'/repos/{repo_full}/collaborators', token) or []
    
    # Upsert repo doc (without last_synced yet)
    existing = frappe.db.exists('Repository', {'full_name': repo_full})
    if existing:
        repo_doc = frappe.get_doc('Repository', existing)
        is_new = False
    else:
        repo_doc = frappe.get_doc({
            'doctype': 'Repository',
            'full_name': repo_full,
            'repo_name': repo_full.split('/')[-1],
            'repo_owner': repo_full.split('/')[0],
            'url': f'https://github.com/{repo_full}',
            'github_id': str(repo_info.get('id', '')),
            'visibility': 'Private' if repo_info.get('private') else 'Public',
            'default_branch': repo_info.get('default_branch', 'main'),
            'is_synced': 1
        })
        is_new = True
    
    repo_doc.github_id = str(repo_info.get('id', ''))
    repo_doc.visibility = 'Private' if repo_info.get('private') else 'Public'
    repo_doc.default_branch = repo_info.get('default_branch', 'main')
    
    last_synced_local = getattr(repo_doc, 'last_synced', None) if not is_new else None
    since_utc = convert_to_github_datetime(last_synced_local)
    
    params = {'state': 'all'}
    if since_utc:
        params['since'] = since_utc
    
    issues = github_request('GET', f'/repos/{repo_full}/issues', token, params=params) or []
    pulls = github_request('GET', f'/repos/{repo_full}/pulls', token, params=params) or []
    
    if is_new:
        repo_doc.insert(ignore_permissions=True)
    else:
        repo_doc.save(ignore_permissions=True)
    
    # Collect all GitHub logins for assignees/reviewers to batch query ERP users
    all_github_logins = set()
    for issue in issues:
        if issue.get('pull_request'):
            continue
        for a in issue.get('assignees', []):
            all_github_logins.add(a.get('login'))
    for pr in pulls:
        for r in pr.get('requested_reviewers', []):
            all_github_logins.add(r.get('login'))
    
    gh_to_erp = {}
    if all_github_logins:
        users = frappe.get_all(
            'User',
            filters={'github_username': ['in', list(all_github_logins)]},
            fields=['name', 'github_username']
        )
        gh_to_erp = {u['github_username']: u['name'] for u in users}
    
    # Clear and update branches
    repo_doc.set('branches_table', [])
    for b in branches:
        branch_name = b.get('name')
        commit_sha = b.get('commit', {}).get('sha')
        
        # Get the commit details for last updated date
        commit_date = ''
        if commit_sha:
            commit = github_request('GET', f'/repos/{repo_full}/commits/{commit_sha}', token)
            if isinstance(commit, dict):
                commit_date_str = commit.get('commit', {}).get('author', {}).get('date', '')
                commit_date = convert_github_datetime(commit_date_str) if commit_date_str else ''
            else:
                print(f"Unexpected commit response for {repo_full}, branch {branch_name}, SHA {commit_sha}: {commit}")
                commit_date = ''
                
        repo_doc.append('branches_table', {
            'repo_full_name': repo_full,
            'branch_name': branch_name,
            'commit_sha': commit_sha or '',
            'protected': b.get('protected', False),
            'last_updated': commit_date
        })
    
    # Clear and update members
    repo_doc.set('members_table', [])
    for m in members:
        user_info = github_request('GET', f"/users/{m.get('login')}", token)
        m_email = user_info.get("email") or ""
        repo_doc.append('members_table', {
            'repo_full_name': repo_full,
            'github_username': m.get('login'),
            'github_id': str(m.get('id', '')),
            'role': 'maintainer' if m.get('permissions', {}).get('admin') else 'member',
            'email': m_email or ''
        })
    
    repo_doc.save(ignore_permissions=True)
    
    # Sync issues
    for issue in issues:
        if issue.get('pull_request'):
            continue  # Skip pull requests (they're handled separately)
        
        # Check if issue exists
        issue_filters = {'repository': repo_full, 'issue_number': issue.get('number')}
        existing_issue = frappe.db.exists('Repository Issue', issue_filters)
        
        assignees_gh = issue.get('assignees', [])
        labels_list = [lab.get('name') for lab in issue.get('labels', [])]
        
        if existing_issue:
            # Update existing issue
            local = frappe.get_doc('Repository Issue', issue_filters)
            local.title = issue.get('title')
            local.body = issue.get('body') or ''
            local.state = issue.get('state')
            local.labels = ','.join(labels_list)
            local.url = issue.get('html_url')
            local.github_id = str(issue.get('id', ''))
            local.updated_at = convert_github_datetime(issue.get('updated_at'))
            
            # Update assignees
            local.set('assignees_table', [])
            for assignee in assignees_gh:
                erp_user = gh_to_erp.get(assignee.get('login'), assignee.get('login'))
                local.append('assignees_table', {
                    'user': erp_user,
                    'issue': local.name
                })
            
            local.save(ignore_permissions=True)
        else:
            # Create new issue
            issue_doc = frappe.get_doc({
                'doctype': 'Repository Issue',
                'repository': repo_full,
                'issue_number': issue.get('number'),
                'title': issue.get('title'),
                'body': issue.get('body') or '',
                'state': issue.get('state'),
                'labels': ','.join(labels_list),
                'url': issue.get('html_url'),
                'github_id': str(issue.get('id', '')),
                'created_at': convert_github_datetime(issue.get('created_at')),
                'updated_at': convert_github_datetime(issue.get('updated_at'))
            })
            issue_doc.insert(ignore_permissions=True)
            
            # Add assignees after insert
            for assignee in assignees_gh:
                erp_user = gh_to_erp.get(assignee.get('login'), assignee.get('login'))
                issue_doc.append('assignees_table', {
                    'user': erp_user,
                    'issue': issue_doc.name
                })
            issue_doc.save(ignore_permissions=True)
    
    # Sync pull requests
    for pr in pulls:
        # Check if PR exists
        pr_filters = {'repository': repo_full, 'pr_number': pr.get('number')}
        existing_pr = frappe.db.exists('Repository Pull Request', pr_filters)
        
        reviewers_gh = pr.get('requested_reviewers', [])
        
        if existing_pr:
            # Update existing PR
            local = frappe.get_doc('Repository Pull Request', pr_filters)
            local.title = pr.get('title')
            local.body = pr.get('body') or ''
            local.state = pr.get('state')
            local.head_branch = pr.get('head', {}).get('ref')
            local.base_branch = pr.get('base', {}).get('ref')
            local.author = pr.get('user', {}).get('login')
            local.mergeable_state = pr.get('mergeable_state')
            local.github_id = str(pr.get('id', ''))
            local.url = pr.get('html_url')
            local.updated_at = convert_github_datetime(pr.get('updated_at'))
            
            # Update reviewers
            local.set('reviewers_table', [])
            for reviewer in reviewers_gh:
                gh_login = reviewer.get('login')
                erp_user = gh_to_erp.get(gh_login, gh_login)
                local.append('reviewers_table', {
                    'user': erp_user,
                    'pull_request': local.name
                })
            
            local.save(ignore_permissions=True)
        else:
            # Create new PR
            pr_doc = frappe.get_doc({
                'doctype': 'Repository Pull Request',
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
            pr_doc.insert(ignore_permissions=True)
            
            # Add reviewers after insert
            for reviewer in reviewers_gh:
                gh_login = reviewer.get('login')
                erp_user = gh_to_erp.get(gh_login, gh_login)
                pr_doc.append('reviewers_table', {
                    'user': erp_user,
                    'pull_request': pr_doc.name
                })
            pr_doc.save(ignore_permissions=True)
    
    # Update last_synced at the end
    repo_doc.last_synced = frappe.utils.now()
    repo_doc.save(ignore_permissions=True)
    
    return {
        'success': True,
        'message': f'Synced repository {repo_full}',
        'branches': len(branches), 
        'issues': len(issues), 
        'pulls': len(pulls), 
        'members': len(members)
    }

@frappe.whitelist()
def create_issue(repository, title, body=None, assignees=None, labels=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    
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
            doc = frappe.get_doc({
                'doctype': 'Repository Issue',
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
            
            # Add assignees after insert
            for assignee in resp.get('assignees', []):
                gh_login = assignee.get('login')
                erp_user = frappe.db.get_value("User", {"github_username": gh_login}, "name") or gh_login
                doc.append('assignees_table', {
                    'user': erp_user,
                    'issue': doc.name
                })
            doc.save(ignore_permissions=True)
            return {'issue': resp, 'local_doc': doc.name}
        except Exception:
            pass
    return resp

@frappe.whitelist()
def bulk_create_issues(repository, issues):
    """Bulk create multiple issues in a repository"""
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    
    if isinstance(issues, str):
        issues = json.loads(issues)
    
    created_issues = []
    for issue_data in issues:
        try:
            resp = github_request('POST', f'/repos/{repository}/issues', token, data=issue_data)
            if resp:
                created_issues.append(resp)
                # Create local record
                doc = frappe.get_doc({
                    'doctype': 'Repository Issue',
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
                doc.insert(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(f"Error creating issue: {str(e)}", "Bulk Create Issues")
    
    return {'created': len(created_issues), 'issues': created_issues}

@frappe.whitelist()
def create_pull_request(repository, title, head, base, body=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    
    payload = {'title': title, 'head': head, 'base': base}
    if body: 
        payload['body'] = body
        
    resp = github_request('POST', f'/repos/{repository}/pulls', token, data=payload)
    if resp:
        try:
            doc = frappe.get_doc({
                'doctype': 'Repository Pull Request',
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
            return {'pull_request': resp, 'local_doc': doc.name}
        except Exception:
            pass
    return resp

@frappe.whitelist()
def sync_repo_members(repo_full_name):
    if not _can_sync_repo(repo_full_name):
        frappe.throw(_('You do not have permission to sync this repository.'))
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))

    try:
        members = list_repo_members(repo_full_name)
    except Exception as e:
        frappe.throw(str(e))

    # Update repository members table
    try:
        repo_doc = frappe.get_doc('Repository', {'full_name': repo_full_name})
        repo_doc.set('members_table', [])
        for m in members or []:
            user_info = github_request('GET', f"/users/{m.get('login')}", token)
            m_email = user_info.get("email") or ""
            repo_doc.append('members_table', {
                'repo_full_name': repo_full_name,
                'github_username': m.get('login'),
                'github_id': str(m.get('id', '')),
                'role': 'maintainer' if m.get('permissions', {}).get('admin') else 'member',
                'email': m_email or ''
            })
        
        repo_doc.save(ignore_permissions=True)
    except Exception:
        pass

    # Update linked projects
    projects = frappe.get_all('Project', filters={'repository': repo_full_name}, fields=['name'])
    for p in projects:
        try:
            proj = frappe.get_doc('Project', p.get('name'))
            proj.set('project_users', [])
            
            for m in members or []:
                user_info = github_request('GET', f"/users/{m.get('login')}", token)
                m_email = user_info.get("email") or ""
                username = m.get('login')
                erp_user = None
                
                # Try to find matching ERP user
                try:
                    user_name = frappe.db.get_value("User", {"github_username": username}, "name")
                    erp_user = user_name
                except Exception:
                    # Try to find by email if available
                    if m_email:
                        try:
                            user_name = frappe.db.get_value("User", {"email": m_email}, "name")
                            if user_name:
                                user_doc = frappe.get_doc("User", user_name)
                                user_doc.github_username = username
                                user_doc.save(ignore_permissions=True)
                        except Exception:
                            pass
                
                proj.append('project_users', {
                    'user': erp_user or username,
                    'role': 'Project User'
                })
            
            proj.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(f"Error updating project {p.get('name')}: {str(e)}")

    return {'members': len(members or [])}

@frappe.whitelist()
def manage_repo_access(repo_full_name, action, identifier, permission='push'):
    _require_github_admin()
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))

    parts = repo_full_name.split('/')
    if len(parts) != 2:
        frappe.throw(_('repo_full_name must be in owner/repo format'))
    owner, repo = parts

    try:
        if action == 'add_collaborator':
            resp = github_request('PUT', f"/repos/{owner}/{repo}/collaborators/{identifier}", token, 
                                data={'permission': permission})
            return resp
        elif action == 'remove_collaborator':
            resp = github_request('DELETE', f"/repos/{owner}/{repo}/collaborators/{identifier}", token)
            return resp
        elif action == 'add_team':
            resp = github_request('PUT', f"/orgs/{owner}/teams/{identifier}/repos/{owner}/{repo}", token, 
                                data={'permission': permission})
            return resp
        elif action == 'remove_team':
            resp = github_request('DELETE', f"/orgs/{owner}/teams/{identifier}/repos/{owner}/{repo}", token)
            return resp
        else:
            frappe.throw(_('Unknown action: {0}').format(action))
    except Exception as e:
        frappe.throw(_('manage_repo_access failed: {0}').format(str(e)))

def background_sync_all_repositories():
    """Background job for syncing all repositories with progress updates"""
    _require_github_admin()
    repos = frappe.get_all('Repository', fields=['full_name'])
    total = len(repos)
    progress = 0
    results = {'success': 0, 'failed': 0}
    start_time = time.time()
    
    for r in repos:
        repo_name = r.get('full_name')
        frappe.publish_realtime(
            event='github_sync_progress',
            message={
                'progress': progress,
                'total': total,
                'repo': repo_name,
                'phase': 'syncing',
                'time_s': round(time.time() - start_time, 1)
            }
        )
        
        try:
            sync_repo(repo_name)
            results['success'] += 1
            status = 'success'
        except Exception as e:
            results['failed'] += 1
            status = 'failed'
            frappe.log_error(message=str(e), title=f'GitHub Sync Error - {repo_name}')
        
        progress += 1
        frappe.publish_realtime(
            event='github_sync_progress',
            message={
                'progress': progress,
                'total': total,
                'repo': repo_name,
                'status': status,
                'success': results['success'],
                'failed': results['failed'],
                'time_s': round(time.time() - start_time, 1)
            }
        )
    
    settings = frappe.get_single("GitHub Settings")
    settings.last_sync = frappe.utils.now()
    settings.save(ignore_permissions=True)
    
    frappe.publish_realtime(
        event='github_sync_progress',
        message={
            'progress': total,
            'total': total,
            'msg': 'completed',
            'success': results['success'],
            'failed': results['failed'],
            'time_s': round(time.time() - start_time, 1)
        }
    )

@frappe.whitelist()
def start_sync_all_repositories():
    """Start background sync of all repositories"""
    frappe.enqueue('erpnext_github_integration.github_api.background_sync_all_repositories')
    return {'status': 'queued'}

@frappe.whitelist()
def get_repository_activity(repository, days=30):
    """Get recent activity for a repository"""
    try:
        settings = frappe.get_single('GitHub Settings')
        token = settings.get_password('personal_access_token')
        
        # Validate and convert days
        try:
            days_int = int(days)
        except (ValueError, TypeError):
            days_int = 30  # Default fallback
        
        # Ensure days is within reasonable bounds
        days_int = max(1, min(days_int, 365))  # Between 1 and 365 days
        
        # Calculate since date
        since = (datetime.now() - timedelta(days=days_int)).isoformat()
        
        # Get activity data
        commits = github_request(
            'GET', 
            f'/repos/{repository}/commits', 
            token, 
            params={'since': since, 'per_page': 50}
        ) or []
        
        issues = github_request(
            'GET',
            f'/repos/{repository}/issues',
            token,
            params={'since': since, 'state': 'all', 'per_page': 20}
        ) or []
        
        pulls = github_request(
            'GET',
            f'/repos/{repository}/pulls',
            token,
            params={'since': since, 'state': 'all', 'per_page': 20}
        ) or []
        
        # Filter out pull requests from issues (GitHub API returns PRs in issues)
        actual_issues = [issue for issue in issues if 'pull_request' not in issue]
        
        return {
            'commits': len(commits),
            'issues': len(actual_issues),
            'pulls': len(pulls),
            'period_days': days_int,
            'details': {
                'commits': commits[:10],  # Return first 10 for preview
                'issues': actual_issues[:10],
                'pulls': pulls[:10]
            }
        }
        
    except Exception as e:
        frappe.logger().error(f"Error getting repository activity: {str(e)}")
        return {'error': str(e)}

@frappe.whitelist()
def create_repository_webhook(repo_full_name, webhook_url=None, events=None):
    """Create a webhook for the repository"""
    _require_github_admin()
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    
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
    """List all webhooks for a repository"""
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    
    try:
        webhooks = github_request('GET', f"/repos/{repo_full_name}/hooks", token)
        return webhooks or []
    except Exception as e:
        frappe.throw(_('Failed to list webhooks: {0}').format(str(e)))