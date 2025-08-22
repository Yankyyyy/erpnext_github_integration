import frappe
from frappe import _
from .github_api import has_role

def validate_repository(doc, method):
    """Validation function for Repository doctype"""
    if doc.full_name and '/' not in doc.full_name:
        frappe.throw(_('Repository Full Name must be in owner/repo format'))
    
    # Auto-populate fields from full_name
    if doc.full_name and '/' in doc.full_name:
        parts = doc.full_name.split('/')
        doc.repo_owner = parts[0]
        doc.repo_name = parts[1]
        
        # Auto-populate URL if not set
        if not doc.url:
            doc.url = f"https://github.com/{doc.full_name}"

def get_repository_dashboard_data(data):
    """Get dashboard data for Repository doctype"""
    return {
        "fieldname": "repository",  # main link field for connections
        "non_standard_fieldnames": {
            "Task": "github_repo"
        },
        "transactions": [
            {
                "label": _("Issues & PRs"),
                "items": ["Repository Issue", "Repository Pull Request"]
            },
            {
                "label": _("Project Management"),
                "items": ["Project", "Task"]
            }
        ]
    }

@frappe.whitelist()
def get_user_repositories():
    """Get repositories accessible by the current user"""
    user = frappe.session.user
    
    # If user is GitHub Admin, return all repositories
    if has_role('GitHub Admin'):
        return frappe.get_all('Repository', fields=['name', 'full_name', 'repo_name', 'url', 'visibility', 'last_synced'])
    
    # Otherwise, return repositories where user is project manager or team member
    user_repos = []
    
    # Get repositories from projects where user is project manager
    projects = frappe.get_all('Project', 
                            filters={'project_manager': user}, 
                            fields=['repository'])
    
    for project in projects:
        if project.get('repository'):
            try:
                repo = frappe.get_doc('Repository', {'full_name': project.get('repository')})
                user_repos.append({
                    'name': repo.name,
                    'full_name': repo.full_name,
                    'repo_name': repo.repo_name,
                    'url': repo.url,
                    'visibility': repo.visibility,
                    'last_synced': repo.last_synced
                })
            except:
                pass
    
    # Get repositories where user is a member using SQL query
    github_username = frappe.db.get_value('User', user, 'github_username')
    if github_username:
        # Use SQL to search for the github_username in the members JSON field
        repos_with_member = frappe.db.sql("""
            SELECT name, full_name, repo_name, url, visibility, last_synced
            FROM `tabRepository`
            WHERE members LIKE %s
        """, f'%"github_username": "{github_username}"%', as_dict=True)
        
        for repo in repos_with_member:
            if repo.name not in [r['name'] for r in user_repos]:
                user_repos.append(repo)
    
    return user_repos

@frappe.whitelist()
def sync_user_github_profile():
    """Sync current user's GitHub profile information"""
    user = frappe.session.user
    user_doc = frappe.get_doc('User', user)
    
    if not user_doc.github_username:
        frappe.throw(_('GitHub username not set for current user'))
    
    github_info = get_github_user_info(user_doc.github_username)
    if not github_info:
        frappe.throw(_('Failed to fetch GitHub user information'))
    
    # Update user profile with GitHub info
    if github_info.get('name') and not user_doc.full_name:
        user_doc.full_name = github_info.get('name')
    
    if github_info.get('bio') and not user_doc.bio:
        user_doc.bio = github_info.get('bio')
    
    if github_info.get('location') and not user_doc.location:
        user_doc.location = github_info.get('location')
    
    user_doc.save(ignore_permissions=True)
    return {'success': True, 'github_info': github_info}

@frappe.whitelist()
def create_task_from_github_issue(issue_name, task_title=None):
    """Create a Task from a GitHub Issue"""
    if not frappe.has_permission('Task', 'create'):
        frappe.throw(_('You do not have permission to create tasks'))
    
    try:
        issue = frappe.get_doc('Repository Issue', issue_name)
        
        if not task_title:
            task_title = issue.title
        
        # Check if task already exists for this issue
        existing_task = frappe.db.exists('Task', {
            'github_repo': issue.repository,
            'github_issue_number': issue.issue_number
        })
        
        if existing_task:
            frappe.throw(_('A task already exists for this GitHub issue'))
        
        # Find project linked to repository
        project = frappe.db.get_value('Project', {'repository': issue.repository}, 'name')
        
        task_doc = frappe.get_doc({
            'doctype': 'Task',
            'subject': task_title,
            'description': issue.body,
            'project': project,
            'github_repo': issue.repository,
            'github_issue_number': issue.issue_number,
            'status': 'Open' if issue.state == 'open' else 'Completed'
        })
        
        task_doc.insert()
        return {'success': True, 'task': task_doc.name}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def bulk_import_github_data(repo_full_name, import_type, force_update=False):
    """Bulk import GitHub data for a repository"""
    if not has_role('GitHub Admin'):
        frappe.throw(_('Only GitHub Admins can perform bulk import'))
    
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        frappe.throw(_('GitHub Personal Access Token not configured'))
    
    from .github_client import github_request
    results = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    
    try:
        if import_type == 'issues':
            # Import all issues (including closed ones)
            issues = github_request('GET', f'/repos/{repo_full_name}/issues', token, 
                                  params={'state': 'all', 'per_page': 100})
            
            for issue in issues or []:
                if issue.get('pull_request'):  # Skip pull requests
                    continue
                
                try:
                    existing = frappe.db.exists('Repository Issue', {
                        'repository': repo_full_name,
                        'issue_number': issue.get('number')
                    })
                    
                    if existing and not force_update:
                        results['skipped'] += 1
                        continue
                    
                    if existing:
                        # Update existing
                        doc = frappe.get_doc('Repository Issue', existing)
                        doc.title = issue.get('title')
                        doc.body = issue.get('body') or ''
                        doc.state = issue.get('state')
                        doc.labels = ','.join([l.get('name') for l in issue.get('labels', [])])
                        doc.updated_at = issue.get('updated_at')
                        doc.save(ignore_permissions=True)
                        results['updated'] += 1
                    else:
                        # Create new
                        doc = frappe.get_doc({
                            'doctype': 'Repository Issue',
                            'repository': repo_full_name,
                            'issue_number': issue.get('number'),
                            'title': issue.get('title'),
                            'body': issue.get('body') or '',
                            'state': issue.get('state'),
                            'labels': ','.join([l.get('name') for l in issue.get('labels', [])]),
                            'url': issue.get('html_url'),
                            'github_id': str(issue.get('id', '')),
                            'created_at': issue.get('created_at'),
                            'updated_at': issue.get('updated_at')
                        })
                        doc.insert(ignore_permissions=True)
                        results['imported'] += 1
                
                except Exception as e:
                    frappe.log_error(f"Error importing issue {issue.get('number')}: {str(e)}")
                    results['errors'] += 1
        
        elif import_type == 'pull_requests':
            # Import all pull requests
            pulls = github_request('GET', f'/repos/{repo_full_name}/pulls', token,
                                 params={'state': 'all', 'per_page': 100})
            
            for pr in pulls or []:
                try:
                    existing = frappe.db.exists('Repository Pull Request', {
                        'repository': repo_full_name,
                        'pr_number': pr.get('number')
                    })
                    
                    if existing and not force_update:
                        results['skipped'] += 1
                        continue
                    
                    if existing:
                        # Update existing
                        doc = frappe.get_doc('Repository Pull Request', existing)
                        doc.title = pr.get('title')
                        doc.body = pr.get('body') or ''
                        doc.state = pr.get('state')
                        doc.head_branch = pr.get('head', {}).get('ref')
                        doc.base_branch = pr.get('base', {}).get('ref')
                        doc.author = pr.get('user', {}).get('login')
                        doc.mergeable_state = pr.get('mergeable_state')
                        doc.updated_at = pr.get('updated_at')
                        doc.save(ignore_permissions=True)
                        results['updated'] += 1
                    else:
                        # Create new
                        doc = frappe.get_doc({
                            'doctype': 'Repository Pull Request',
                            'repository': repo_full_name,
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
                            'created_at': pr.get('created_at'),
                            'updated_at': pr.get('updated_at')
                        })
                        doc.insert(ignore_permissions=True)
                        results['imported'] += 1
                
                except Exception as e:
                    frappe.log_error(f"Error importing PR {pr.get('number')}: {str(e)}")
                    results['errors'] += 1
    
    except Exception as e:
        frappe.throw(_('Bulk import failed: {0}').format(str(e)))
    
    return results
def get_github_user_info(github_username):
    """Get GitHub user information"""
    if not github_username:
        return None
    
    settings = frappe.get_single('GitHub Settings')
    token = settings.get_password('personal_access_token')
    if not token:
        return None
    
    try:
        from .github_client import github_request
        user_info = github_request('GET', f'/users/{github_username}', token)
        return user_info
    except Exception:
        return None

@frappe.whitelist()
def link_github_user_to_erp(github_username, erp_user):
    """Link a GitHub user to an ERP user"""
    if not frappe.has_permission('User', 'write'):
        frappe.throw(_('You do not have permission to modify users'))
    
    try:
        user_doc = frappe.get_doc('User', erp_user)
        user_doc.github_username = github_username
        user_doc.save(ignore_permissions=True)
        return {
            'success': True, 
            'message': _('GitHub username {0} linked successfully to user {1}').format(
                github_username, erp_user)
        }
    except frappe.ValidationError as e:
        return {'success': False, 'error': str(e)}
    except Exception as e:
        frappe.log_error(f'Error linking GitHub user: {str(e)}')
        return {'success': False, 'error': _('An error occurred while updating the user')}

@frappe.whitelist()
def get_repository_statistics(repo_full_name):
    """Get statistics for a specific repository"""
    stats = {
        'issues': {
            'total': frappe.db.count('Repository Issue', {'repository': repo_full_name}),
            'open': frappe.db.count('Repository Issue', {'repository': repo_full_name, 'state': 'open'}),
            'closed': frappe.db.count('Repository Issue', {'repository': repo_full_name, 'state': 'closed'})
        },
        'pull_requests': {
            'total': frappe.db.count('Repository Pull Request', {'repository': repo_full_name}),
            'open': frappe.db.count('Repository Pull Request', {'repository': repo_full_name, 'state': 'open'}),
            'closed': frappe.db.count('Repository Pull Request', {'repository': repo_full_name, 'state': 'closed'}),
            'merged': frappe.db.count('Repository Pull Request', {'repository': repo_full_name, 'state': 'merged'})
        },
        'branches': frappe.db.count('Repository Branch', {'repo_full_name': repo_full_name}),
        'members': frappe.db.count('Repository Member', {'repo_full_name': repo_full_name})
    }
    return stats

@frappe.whitelist()
def create_project_from_repository(repo_full_name, project_name=None):
    """Create a new Project linked to a repository"""
    if not frappe.has_permission('Project', 'create'):
        frappe.throw(_('You do not have permission to create projects'))
    
    try:
        repo_doc = frappe.get_doc('Repository', {'full_name': repo_full_name})
        
        if not project_name:
            project_name = f"{repo_doc.repo_name} Project"
        
        # Check if project already exists
        if frappe.db.exists('Project', {'repository': repo_full_name}):
            frappe.throw(_('A project is already linked to this repository'))
        
        project_doc = frappe.get_doc({
            'doctype': 'Project',
            'project_name': project_name,
            'repository': repo_full_name,
            'status': 'Open'
        })
        
        project_doc.insert()
        return {'success': True, 'project': project_doc.name}
    except Exception as e:
        return {'success': False, 'error': str(e)}