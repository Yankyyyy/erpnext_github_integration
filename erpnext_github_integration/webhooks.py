import frappe, hmac, hashlib, json
from frappe import _
from .github_api import convert_github_datetime


def get_github_event_header():
    """Get GitHub event header in a more robust way"""
    # Try different ways to get the event header
    event = None
    
    # Method 1: Standard header access
    if hasattr(frappe.request, 'headers'):
        headers = frappe.request.headers
        event = headers.get('X-GitHub-Event') or headers.get('x-github-event')
    
    # Method 2: Direct environ access
    if not event and hasattr(frappe.local, 'request') and hasattr(frappe.local.request, 'environ'):
        environ = frappe.local.request.environ
        # HTTP headers are prefixed with HTTP_ and converted to uppercase with dashes as underscores
        event = environ.get('HTTP_X_GITHUB_EVENT')
    
    # Method 3: Frappe's header helper
    if not event:
        event = frappe.get_request_header("X-GitHub-Event") or frappe.get_request_header("x-github-event")
    
    return event


@frappe.whitelist(allow_guest=True)
def github_webhook():
    """Handle GitHub webhook events"""
    try:
        settings = frappe.get_single('GitHub Settings')
        secret = settings.get_password('webhook_secret') or frappe.conf.get('github_webhook_secret')
        payload = frappe.request.get_data()
        signature = frappe.request.headers.get('X-Hub-Signature-256') or ''

        # Verify signature if secret is configured
        if secret:
            expected_signature = 'sha256=' + hmac.new(
                secret.encode(),
                msg=payload,
                digestmod=hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(expected_signature, signature):
                frappe.log_error('Invalid webhook signature', 'GitHub Webhook')
                frappe.throw(_('Invalid webhook signature'), exc=frappe.PermissionError)

        # Get event name with robust header extraction
        event = get_github_event_header()
        data = json.loads(payload.decode('utf-8'))
        
        # If event header is missing, try to infer from payload
        if not event:
            if 'commits' in data and 'ref' in data and 'before' in data and 'after' in data:
                event = 'push'
            elif 'issue' in data:
                event = 'issues'
            elif 'pull_request' in data:
                event = 'pull_request'
            elif 'member' in data:
                event = 'member'
            elif 'action' in data and 'repository' in data and data.get('repository'):
                event = 'repository'

        # Get repository info
        repo_info = data.get('repository', {}) or {}
        repo_full_name = repo_info.get('full_name')

        if not repo_full_name:
            frappe.log_error('No repository information in webhook payload', 'GitHub Webhook')
            return 'ok'
        
        # Log the event for debugging
        frappe.log_error(f'Processing webhook event: {event} for repo: {repo_full_name}', 'GitHub Webhook Debug')

        # Check if repo exists in system
        if not frappe.db.exists('Repository', {'full_name': repo_full_name}):
            frappe.log_error(f'Repository {repo_full_name} not found in system', 'GitHub Webhook')
            return 'ok'

        # Process webhook immediately to avoid background job issues
        # You can change this back to background processing once it's working
        _process_github_webhook(event=event, data=data, repo_full_name=repo_full_name)

        return 'ok'

    except Exception as e:
        frappe.log_error(f'Webhook processing error: {frappe.get_traceback()}', 'GitHub Webhook Error')
        return {'error': str(e)}


def _process_github_webhook(event=None, data=None, repo_full_name=None):
    """Process GitHub webhook events in background"""
    try:
        if not event:
            frappe.log_error(f"Missing event parameter. Data: {json.dumps(data, indent=2)}", "GitHub Webhook Missing Event")
            return

        event = event.lower().strip()
        frappe.log_error(f"Processing event: {event} for repo: {repo_full_name}", "GitHub Webhook Processing")

        if event == "issues":
            _handle_issues_event(data, repo_full_name)
        elif event == "pull_request":
            _handle_pull_request_event(data, repo_full_name)
        elif event == "push":
            _handle_push_event(data, repo_full_name)
        elif event == "member":
            _handle_member_event(data, repo_full_name)
        elif event == "repository":
            _handle_repository_event(data, repo_full_name)
        else:
            frappe.log_error(f"Unhandled webhook event: {event}", "GitHub Webhook")
    
    except Exception as e:
        frappe.log_error(f"Error processing {event} webhook: {str(e)}", "GitHub Webhook Handler")
        
def _handle_issues_event(data, repo_full_name):
    """Handle GitHub issues webhook events"""
    action = data.get('action')
    issue = data.get('issue', {})
    
    if not issue:
        frappe.log_error('No issue data in webhook payload', 'GitHub Issues Webhook')
        return
    
    issue_number = issue.get('number')
    if not issue_number:
        frappe.log_error('No issue number in webhook payload', 'GitHub Issues Webhook')
        return
    
    try:
        # Try to get existing issue
        existing = frappe.db.exists('Repository Issue', {
            'repository': repo_full_name,
            'issue_number': issue_number
        })
        
        if action in ['opened', 'edited', 'reopened', 'closed']:
            if existing:
                # Update existing issue
                doc = frappe.get_doc('Repository Issue', existing)
                doc.title = issue.get('title', '')
                doc.body = issue.get('body', '')
                doc.state = issue.get('state', 'open')
                doc.labels = ','.join([l.get('name', '') for l in issue.get('labels', [])])
                doc.url = issue.get('html_url', '')
                doc.updated_at = convert_github_datetime(issue.get('updated_at'))
                
                # Clear and update assignees
                doc.set('assignees_table', [])
                for assignee in issue.get('assignees', []):
                    doc.append('assignees_table', {
                        'user': assignee.get('login', '')
                    })
                
                doc.flags.ignore_permissions = True
                doc.save()
                frappe.db.commit()
                
            else:
                # Create new issue
                doc = frappe.get_doc({
                    'doctype': 'Repository Issue',
                    'repository': repo_full_name,
                    'issue_number': issue_number,
                    'title': issue.get('title', ''),
                    'body': issue.get('body', ''),
                    'state': issue.get('state', 'open'),
                    'labels': ','.join([l.get('name', '') for l in issue.get('labels', [])]),
                    'url': issue.get('html_url', ''),
                    'github_id': str(issue.get('id', '')),
                    'created_at': convert_github_datetime(issue.get('created_at')),
                    'updated_at': convert_github_datetime(issue.get('updated_at'))
                })
                
                # Add assignees
                for assignee in issue.get('assignees', []):
                    doc.append('assignees_table', {
                        'user': assignee.get('login', '')
                    })
                
                doc.flags.ignore_permissions = True
                doc.insert()
                frappe.db.commit()
        
        elif action == 'deleted' and existing:
            # Delete issue
            frappe.delete_doc('Repository Issue', existing, ignore_permissions=True)
            frappe.db.commit()
    
    except Exception as e:
        frappe.log_error(f'Error handling issue event: {frappe.get_traceback()}', 'GitHub Issues Webhook')

def _handle_pull_request_event(data, repo_full_name):
    """Handle GitHub pull request webhook events"""
    action = data.get('action')
    pr = data.get('pull_request', {})
    
    if not pr:
        frappe.log_error('No pull request data in webhook payload', 'GitHub PR Webhook')
        return
    
    pr_number = pr.get('number')
    if not pr_number:
        frappe.log_error('No PR number in webhook payload', 'GitHub PR Webhook')
        return
    
    try:
        # Try to get existing PR
        existing = frappe.db.exists('Repository Pull Request', {
            'repository': repo_full_name,
            'pr_number': pr_number
        })
        
        if action in ['opened', 'edited', 'reopened', 'closed', 'merged']:
            if existing:
                # Update existing PR
                doc = frappe.get_doc('Repository Pull Request', existing)
                doc.title = pr.get('title', '')
                doc.body = pr.get('body', '')
                doc.state = pr.get('state', 'open')
                doc.head_branch = pr.get('head', {}).get('ref', '')
                doc.base_branch = pr.get('base', {}).get('ref', '')
                doc.author = pr.get('user', {}).get('login', '')
                doc.mergeable_state = pr.get('mergeable_state', '')
                doc.url = pr.get('html_url', '')
                doc.updated_at = convert_github_datetime(pr.get('updated_at'))
                
                # Clear and update reviewers
                doc.set('reviewers_table', [])
                for reviewer in pr.get('requested_reviewers', []):
                    doc.append('reviewers_table', {
                        'user': reviewer.get('login', '')
                    })
                
                doc.flags.ignore_permissions = True
                doc.save()
                frappe.db.commit()
                
            else:
                # Create new PR
                doc = frappe.get_doc({
                    'doctype': 'Repository Pull Request',
                    'repository': repo_full_name,
                    'pr_number': pr_number,
                    'title': pr.get('title', ''),
                    'body': pr.get('body', ''),
                    'state': pr.get('state', 'open'),
                    'head_branch': pr.get('head', {}).get('ref', ''),
                    'base_branch': pr.get('base', {}).get('ref', ''),
                    'author': pr.get('user', {}).get('login', ''),
                    'mergeable_state': pr.get('mergeable_state', ''),
                    'github_id': str(pr.get('id', '')),
                    'url': pr.get('html_url', ''),
                    'created_at': convert_github_datetime(pr.get('created_at')),
                    'updated_at': convert_github_datetime(pr.get('updated_at'))
                })
                
                # Add reviewers
                for reviewer in pr.get('requested_reviewers', []):
                    doc.append('reviewers_table', {
                        'user': reviewer.get('login', '')
                    })
                
                doc.flags.ignore_permissions = True
                doc.insert()
                frappe.db.commit()
    
    except Exception as e:
        frappe.log_error(f'Error handling PR event: {frappe.get_traceback()}', 'GitHub PR Webhook')

def _handle_push_event(data, repo_full_name):
    """Handle GitHub push webhook events"""
    try:
        ref = data.get('ref', '')
        branch_name = ref.replace('refs/heads/', '') if ref.startswith('refs/heads/') else None
        
        if not branch_name:
            frappe.log_error(f'Invalid ref format: {ref}', 'GitHub Push Webhook')
            return
        
        # Get repository document
        repo_filters = {'full_name': repo_full_name}
        if not frappe.db.exists('Repository', repo_filters):
            frappe.log_error(f'Repository {repo_full_name} not found', 'GitHub Push Webhook')
            return
            
        repo_doc = frappe.get_doc('Repository', repo_filters)
        
        # Update repository last sync time
        repo_doc.last_synced = frappe.utils.now()
        
        # Update branch information if it exists in the branches table
        branch_updated = False
        if hasattr(repo_doc, 'branches_table') and repo_doc.branches_table:
            for branch in repo_doc.branches_table:
                if branch.branch_name == branch_name:
                    branch.commit_sha = data.get('after', '')
                    branch.last_updated = frappe.utils.now()
                    branch_updated = True
                    break
        
        # If branch doesn't exist in table, add it
        if not branch_updated and hasattr(repo_doc, 'branches_table'):
            repo_doc.append('branches_table', {
                'branch_name': branch_name,
                'commit_sha': data.get('after', ''),
                'last_updated': frappe.utils.now()
            })
        
        repo_doc.flags.ignore_permissions = True
        repo_doc.save()
        frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(f'Error handling push event: {frappe.get_traceback()}', 'GitHub Push Webhook')

def _handle_member_event(data, repo_full_name):
    """Handle GitHub member webhook events"""
    try:
        action = data.get('action')
        member = data.get('member', {})
        
        if not member:
            frappe.log_error('No member data in webhook payload', 'GitHub Member Webhook')
            return
        
        username = member.get('login')
        if not username:
            frappe.log_error('No username in member data', 'GitHub Member Webhook')
            return
        
        # Get repository document
        repo_filters = {'full_name': repo_full_name}
        if not frappe.db.exists('Repository', repo_filters):
            frappe.log_error(f'Repository {repo_full_name} not found', 'GitHub Member Webhook')
            return
            
        repo_doc = frappe.get_doc('Repository', repo_filters)
        
        if action == 'added':
            # Check if member already exists
            existing_member = None
            if hasattr(repo_doc, 'members_table') and repo_doc.members_table:
                for mem in repo_doc.members_table:
                    if mem.github_username == username:
                        existing_member = mem
                        break
            
            if not existing_member:
                repo_doc.append('members_table', {
                    'repo_full_name': repo_full_name,
                    'github_username': username,
                    'github_id': str(member.get('id', '')),
                    'role': 'member'
                })
        
        elif action == 'removed':
            # Remove member from repository
            if hasattr(repo_doc, 'members_table') and repo_doc.members_table:
                for mem in repo_doc.members_table[:]:  # Create a copy to iterate over
                    if mem.github_username == username:
                        repo_doc.remove(mem)
                        break
        
        repo_doc.flags.ignore_permissions = True
        repo_doc.save()
        frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(f'Error handling member event: {frappe.get_traceback()}', 'GitHub Member Webhook')

def _handle_repository_event(data, repo_full_name):
    """Handle GitHub repository webhook events"""
    try:
        action = data.get('action')
        repository = data.get('repository', {})
        
        if not repository:
            frappe.log_error('No repository data in webhook payload', 'GitHub Repository Webhook')
            return
        
        if action in ['edited', 'renamed']:
            # Get repository document
            repo_filters = {'full_name': repo_full_name}
            if not frappe.db.exists('Repository', repo_filters):
                frappe.log_error(f'Repository {repo_full_name} not found', 'GitHub Repository Webhook')
                return
                
            repo_doc = frappe.get_doc('Repository', repo_filters)
            
            # Update basic repository information
            repo_doc.visibility = 'Private' if repository.get('private') else 'Public'
            repo_doc.default_branch = repository.get('default_branch', 'main')
            repo_doc.description = repository.get('description', '')
            
            # Handle repository rename
            if action == 'renamed':
                new_full_name = repository.get('full_name')
                if new_full_name and new_full_name != repo_full_name:
                    repo_doc.full_name = new_full_name
                    repo_doc.repo_name = repository.get('name')
                    repo_doc.repo_owner = repository.get('owner', {}).get('login', '')
                    repo_doc.url = repository.get('html_url', '')
            
            repo_doc.flags.ignore_permissions = True
            repo_doc.save()
            frappe.db.commit()
    
    except Exception as e:
        frappe.log_error(f'Error handling repository event: {frappe.get_traceback()}', 'GitHub Repository Webhook')