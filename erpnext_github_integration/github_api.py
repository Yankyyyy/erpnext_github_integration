import frappe, json
from frappe import _
from .github_client import github_request

def _require_github_admin():
    if not frappe.has_role('GitHub Admin'):
        frappe.throw(_('Only users with the GitHub Admin role can perform this action.'))

def _can_sync_repo(repo_full_name):
    """Return True if current user can sync the repo:
       - GitHub Admins can always sync
       - Project Manager of any Project linked to this repo can sync
    """
    if frappe.has_role('GitHub Admin'):
        return True
    projects = frappe.get_all('Project', filters={'repository': repo_full_name}, fields=['name', 'project_manager'])
    user = frappe.session.user
    for p in projects:
        if p.get('project_manager') and p.get('project_manager') == user:
            return True
    return False

@frappe.whitelist()
def can_user_sync_repo(repo_full_name):
    return {'can_sync': _can_sync_repo(repo_full_name)}

@frappe.whitelist()
def list_repositories(organization=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
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
    token = settings.personal_access_token
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    path = f"/repos/{repo_full_name}/branches"
    return github_request('GET', path, token, params={'per_page': per_page})

@frappe.whitelist()
def list_teams(org_name, per_page=100):
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    path = f"/orgs/{org_name}/teams"
    return github_request('GET', path, token, params={'per_page': per_page})

@frappe.whitelist()
def list_repo_members(repo_full_name, per_page=100):
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    try:
        members = github_request('GET', f"/repos/{repo_full_name}/collaborators", token, params={'per_page': per_page})
    except Exception as e:
        frappe.throw(_('GitHub list repo members failed: {0}').format(str(e)))
    return members

@frappe.whitelist()
def create_issue(repo_full_name, title, body=None, assignees=None, labels=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
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
    try:
        resp = github_request('POST', f"/repos/{repo_full_name}/issues", token, data=payload)
    except Exception as e:
        frappe.throw(_('GitHub create issue failed: {0}').format(str(e)))
    if resp:
        doc = frappe.get_doc({
            'doctype': 'Repository Issue',
            'repo_full_name': repo_full_name,
            'issue_number': resp.get('number'),
            'title': resp.get('title'),
            'body': resp.get('body') or '',
            'state': resp.get('state'),
            'labels': ','.join([l.get('name') if isinstance(l, dict) else str(l) for l in resp.get('labels', [])]) if resp.get('labels') else '',
            'assignees': ','.join([a.get('login') for a in resp.get('assignees', [])]) if resp.get('assignees') else '',
            'url': resp.get('html_url'),
            'github_id': resp.get('id'),
            'created_at': resp.get('created_at'),
            'updated_at': resp.get('updated_at')
        })
        doc.insert(ignore_permissions=True)
        return {'issue': resp, 'local_doc': doc.name}
    return resp
@frappe.whitelist()
def assign_issue(repo_full_name, issue_number, assignees):
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    if isinstance(assignees, str):
        try:
            assignees = json.loads(assignees)
        except Exception:
            assignees = [a.strip() for a in assignees.split(',') if a.strip()]
    payload = {'assignees': assignees}
    try:
        resp = github_request('PATCH', f"/repos/{repo_full_name}/issues/{issue_number}", token, data=payload)
    except Exception as e:
        frappe.throw(_('GitHub assign issue failed: {0}').format(str(e)))
    if resp:
        try:
            local = frappe.get_doc('Repository Issue', {'repo_full_name': repo_full_name, 'issue_number': int(issue_number)})
            local.assignees = ','.join(assignees) if assignees else ''
            local.save(ignore_permissions=True)
        except Exception:
            pass
        return resp
    return resp

@frappe.whitelist()
def create_pull_request(repo_full_name, title, head, base, body=None):
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))
    payload = {'title': title, 'head': head, 'base': base}
    if body:
        payload['body'] = body
    try:
        resp = github_request('POST', f"/repos/{repo_full_name}/pulls", token, data=payload)
    except Exception as e:
        frappe.throw(_('GitHub create PR failed: {0}').format(str(e)))
    if resp:
        doc = frappe.get_doc({
            'doctype': 'Repository Pull Request',
            'repo_full_name': repo_full_name,
            'pr_number': resp.get('number'),
            'title': resp.get('title'),
            'body': resp.get('body') or '',
            'state': resp.get('state'),
            'head_branch': resp.get('head',{}).get('ref'),
            'base_branch': resp.get('base',{}).get('ref'),
            'reviewers': ','.join([r.get('login') for r in resp.get('requested_reviewers', [])]) if resp.get('requested_reviewers') else '',
            'mergeable_state': resp.get('mergeable_state'),
            'url': resp.get('html_url'),
            'github_id': resp.get('id'),
            'created_at': resp.get('created_at'),
            'updated_at': resp.get('updated_at')
        })
        doc.insert(ignore_permissions=True)
        return {'pull_request': resp, 'local_doc': doc.name}
    return resp

@frappe.whitelist()
def add_pr_reviewer(repo_full_name, pr_number, reviewers):
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
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
            local = frappe.get_doc('Repository Pull Request', {'repo_full_name': repo_full_name, 'pr_number': int(pr_number)})
            local.reviewers = ','.join(reviewers) if reviewers else ''
            local.save(ignore_permissions=True)
        except Exception:
            pass
        return resp
    return resp

@frappe.whitelist()
def sync_repo(repo_full_name, per_page=100):
    if not _can_sync_repo(repo_full_name):
        frappe.throw(_('You do not have permission to sync this repository.'))
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))

    try:
        branches = github_request('GET', f"/repos/{repo_full_name}/branches", token, params={'per_page': per_page})
        issues = github_request('GET', f"/repos/{repo_full_name}/issues", token, params={'state':'all','per_page': per_page})
        pulls = github_request('GET', f"/repos/{repo_full_name}/pulls", token, params={'state':'all','per_page': per_page})
    except Exception as e:
        frappe.throw(_('GitHub sync failed: {0}').format(str(e)))

    repo_doc = None
    try:
        repo_doc = frappe.get_doc('Repository', {'full_name': repo_full_name})
    except Exception:
        repo_doc = None

    if not repo_doc:
        rd = frappe.get_doc({
            'doctype': 'Repository',
            'repo_name': repo_full_name.split('/')[-1],
            'full_name': repo_full_name,
            'url': f"https://github.com/{repo_full_name}"
        })
        rd.insert(ignore_permissions=True)
        repo_doc = rd

    if issues:
        for issue in issues:
            if issue.get('pull_request'):
                continue
            identifier = {'repo_full_name': repo_full_name, 'issue_number': issue.get('number')}
            try:
                local = frappe.get_doc('Repository Issue', identifier)
                local.title = issue.get('title')
                local.body = issue.get('body') or ''
                local.state = issue.get('state')
                local.labels = ','.join([l.get('name') if isinstance(l, dict) else str(l) for l in issue.get('labels',[])]) if issue.get('labels') else ''
                local.assignees = ','.join([a.get('login') for a in issue.get('assignees',[])]) if issue.get('assignees') else ''
                local.url = issue.get('html_url')
                local.github_id = issue.get('id')
                local.updated_at = issue.get('updated_at')
                local.save(ignore_permissions=True)
            except Exception:
                doc = frappe.get_doc({
                    'doctype': 'Repository Issue',
                    'repo_full_name': repo_full_name,
                    'issue_number': issue.get('number'),
                    'title': issue.get('title'),
                    'body': issue.get('body') or '',
                    'state': issue.get('state'),
                    'labels': ','.join([l.get('name') if isinstance(l, dict) else str(l) for l in issue.get('labels',[])]) if issue.get('labels') else '',
                    'assignees': ','.join([a.get('login') for a in issue.get('assignees',[])]) if issue.get('assignees') else '',
                    'url': issue.get('html_url'),
                    'github_id': issue.get('id'),
                    'created_at': issue.get('created_at'),
                    'updated_at': issue.get('updated_at')
                })
                doc.insert(ignore_permissions=True)

    if pulls:
        for pr in pulls:
            identifier = {'repo_full_name': repo_full_name, 'pr_number': pr.get('number')}
            try:
                local = frappe.get_doc('Repository Pull Request', identifier)
                local.title = pr.get('title')
                local.body = pr.get('body') or ''
                local.state = pr.get('state')
                local.head_branch = pr.get('head',{}).get('ref')
                local.base_branch = pr.get('base',{}).get('ref')
                local.reviewers = ','.join([r.get('login') for r in pr.get('requested_reviewers',[])]) if pr.get('requested_reviewers') else ''
                local.mergeable_state = pr.get('mergeable_state')
                local.url = pr.get('html_url')
                local.github_id = pr.get('id')
                local.updated_at = pr.get('updated_at')
                local.save(ignore_permissions=True)
            except Exception:
                doc = frappe.get_doc({
                    'doctype': 'Repository Pull Request',
                    'repo_full_name': repo_full_name,
                    'pr_number': pr.get('number'),
                    'title': pr.get('title'),
                    'body': pr.get('body') or '',
                    'state': pr.get('state'),
                    'head_branch': pr.get('head',{}).get('ref'),
                    'base_branch': pr.get('base',{}).get('ref'),
                    'reviewers': ','.join([r.get('login') for r in pr.get('requested_reviewers',[])]) if pr.get('requested_reviewers') else '',
                    'mergeable_state': pr.get('mergeable_state'),
                    'url': pr.get('html_url'),
                    'github_id': pr.get('id'),
                    'created_at': pr.get('created_at'),
                    'updated_at': pr.get('updated_at')
                })
                doc.insert(ignore_permissions=True)

    return {'branches': len(branches or []), 'issues': len(issues or []), 'pulls': len(pulls or [])}

@frappe.whitelist()
def sync_repo_members(repo_full_name):
    if not _can_sync_repo(repo_full_name):
        frappe.throw(_('You do not have permission to sync this repository.'))
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))

    try:
        members = list_repo_members(repo_full_name)
    except Exception as e:
        frappe.throw(str(e))

    for m in members or []:
        username = m.get('login')
        gh_id = m.get('id')
        role = m.get('role_name') or m.get('permissions') or ''
        try:
            doc = frappe.get_doc('Repository Member', {'repo_full_name': repo_full_name, 'github_username': username})
            doc.github_id = gh_id
            doc.role = str(role)
            doc.save(ignore_permissions=True)
        except Exception:
            frappe.get_doc({
                'doctype':'Repository Member',
                'repo_full_name': repo_full_name,
                'github_username': username,
                'github_id': gh_id,
                'role': str(role)
            }).insert(ignore_permissions=True)

    projects = frappe.get_all('Project', filters={'repository': repo_full_name}, fields=['name'])
    for p in projects:
        proj = frappe.get_doc('Project', p.get('name'))
        proj.set('project_users', [])
        for m in members or []:
            username = m.get('login')
            erp_user = None
            try:
                user_doc = frappe.get_doc('User', {'github_username': username})
                erp_user = user_doc.name
            except Exception:
                erp_user = None
            proj.append('project_users', {
                'user': erp_user or username,
                'role': 'Project User'
            })
        proj.save(ignore_permissions=True)

    return {'members': len(members or [])}

@frappe.whitelist()
def manage_repo_access(repo_full_name, action, identifier, permission='push'):
    _require_github_admin()
    settings = frappe.get_single('GitHub Settings')
    token = settings.personal_access_token
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured in GitHub Settings'))

    owner_repo = repo_full_name
    parts = owner_repo.split('/')
    if len(parts) != 2:
        frappe.throw(_('repo_full_name must be in owner/repo format'))
    owner, repo = parts

    try:
        if action == 'add_collaborator':
            resp = github_request('PUT', f"/repos/{owner}/{repo}/collaborators/{identifier}", token, data={'permission': permission})
            return resp
        elif action == 'remove_collaborator':
            resp = github_request('DELETE', f"/repos/{owner}/{repo}/collaborators/{identifier}", token)
            return resp
        elif action == 'add_team':
            resp = github_request('PUT', f"/orgs/{owner}/teams/{identifier}/repos/{owner}/{repo}", token, data={'permission': permission})
            return resp
        elif action == 'remove_team':
            resp = github_request('DELETE', f"/orgs/{owner}/teams/{identifier}/repos/{owner}/{repo}", token)
            return resp
        else:
            frappe.throw(_('Unknown action: {0}').format(action))
    except Exception as e:
        frappe.throw(_('manage_repo_access failed: {0}').format(str(e)))

@frappe.whitelist()
def sync_all_repositories():
    _require_github_admin()
    repos = frappe.get_all('Repository', fields=['full_name'])
    for r in repos:
        try:
            sync_repo(r.get('full_name'))
        except Exception as e:
            frappe.log_error(message=str(e), title='GitHub Sync Error')
