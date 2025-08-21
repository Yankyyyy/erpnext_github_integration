import frappe, hmac, hashlib, json
from frappe import _

@frappe.whitelist(allow_guest=True)
def github_webhook():
    try:
        settings = frappe.get_single('GitHub Settings')
        secret = settings.get_password("webhook_secret") or frappe.conf.get('github_webhook_secret')
        payload = frappe.request.get_data()

        # Normalize all headers to lowercase
        headers = {k.lower(): v for k, v in frappe.request.headers.items()}
        frappe.log_error(json.dumps(headers, indent=2), "GitHub Webhook Headers")

        signature = headers.get('x-hub-signature-256') or headers.get('x-hub-signature') or ''
        
        if secret:
            expected_signature = 'sha256=' + hmac.new(
                secret.encode(),
                msg=payload,
                digestmod=hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected_signature, signature):
                frappe.log_error({'expected': expected_signature, 'got': signature}, 'GitHub Webhook Invalid Signature')
                frappe.throw(_('Invalid webhook signature'), exc=frappe.PermissionError)

        # Check for GitHub event type
        event = headers.get('x-github-event')
        if not event:
            frappe.log_error({"headers": headers}, "GitHub Webhook Missing Event")
            return 'ok'

        data = json.loads(payload.decode('utf-8'))
        repo_info = data.get('repository', {})
        repo_full_name = repo_info.get('full_name')

        if not repo_full_name:
            frappe.log_error('No repository information in webhook payload', 'GitHub Webhook')
            return 'ok'

        if not frappe.db.exists('Repository', {'full_name': repo_full_name}):
            frappe.log_error(f'Repository {repo_full_name} not found in system', 'GitHub Webhook')
            return 'ok'

        frappe.enqueue(
            "erpnext_github_integration.webhooks._process_github_webhook",
            event=event,
            data=data,
            repo_full_name=repo_full_name,
            queue='default'
        )

        return 'ok'

    except Exception as e:
        frappe.log_error(f'Webhook processing error: {str(e)}', 'GitHub Webhook Error')
        return {'error': str(e)}

def _process_github_webhook(event=None, data=None, repo_full_name=None):
    """Process GitHub webhook events in background"""
    try:
        if event == 'issues':
            _handle_issues_event(data, repo_full_name)
        elif event == 'pull_request':
            _handle_pull_request_event(data, repo_full_name)
        elif event == 'push':
            _handle_push_event(data, repo_full_name)
        elif event == 'member':
            _handle_member_event(data, repo_full_name)
        elif event == 'repository':
            _handle_repository_event(data, repo_full_name)
        else:
            frappe.log_error(f'Unhandled webhook event: {event}', 'GitHub Webhook')
    
    except Exception as e:
        frappe.log_error(f'Error processing {event} webhook: {str(e)}', 'GitHub Webhook Handler')

def _handle_issues_event(data, repo_full_name):
    """Handle GitHub issues webhook events"""
    action = data.get('action')
    issue = data.get('issue', {})
    
    if not issue:
        return
    
    issue_number = issue.get('number')
    if not issue_number:
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
                doc.updated_at = issue.get('updated_at')
                
                # Update assignees
                doc.set('assignees_table', [])
                for assignee in issue.get('assignees', []):
                    doc.append('assignees_table', {
                        'user': assignee.get('login', '')
                    })
                
                doc.save(ignore_permissions=True)
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
                    'created_at': issue.get('created_at'),
                    'updated_at': issue.get('updated_at')
                })
                
                # Add assignees
                for assignee in issue.get('assignees', []):
                    doc.append('assignees_table', {
                        'user': assignee.get('login', '')
                    })
                
                doc.insert(ignore_permissions=True)
        
        elif action == 'deleted' and existing:
            # Delete issue
            frappe.delete_doc('Repository Issue', existing, ignore_permissions=True)
    
    except Exception as e:
        frappe.log_error(f'Error handling issue event: {str(e)}', 'GitHub Issues Webhook')

def _handle_pull_request_event(data, repo_full_name):
    """Handle GitHub pull request webhook events"""
    action = data.get('action')
    pr = data.get('pull_request', {})
    
    if not pr:
        return
    
    pr_number = pr.get('number')
    if not pr_number:
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
                doc.updated_at = pr.get('updated_at')
                
                # Update reviewers
                doc.set('reviewers_table', [])
                for reviewer in pr.get('requested_reviewers', []):
                    doc.append('reviewers_table', {
                        'user': reviewer.get('login', '')
                    })
                
                doc.save(ignore_permissions=True)
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
                    'created_at': pr.get('created_at'),
                    'updated_at': pr.get('updated_at')
                })
                
                # Add reviewers
                for reviewer in pr.get('requested_reviewers', []):
                    doc.append('reviewers_table', {
                        'user': reviewer.get('login', '')
                    })
                
                doc.insert(ignore_permissions=True)
    
    except Exception as e:
        frappe.log_error(f'Error handling PR event: {str(e)}', 'GitHub PR Webhook')

def _handle_push_event(data, repo_full_name):
    """Handle GitHub push webhook events"""
    try:
        ref = data.get('ref', '')
        branch_name = ref.replace('refs/heads/', '') if ref.startswith('refs/heads/') else None
        
        if not branch_name:
            return
        
        # Update repository last sync time
        repo_doc = frappe.get_doc('Repository', {'full_name': repo_full_name})
        repo_doc.last_synced = frappe.utils.now()
        
        # Update branch information if it exists in the branches table
        for branch in repo_doc.branches_table:
            if branch.branch_name == branch_name:
                branch.commit_sha = data.get('after', '')
                branch.last_updated = frappe.utils.now()
                break
        
        repo_doc.save(ignore_permissions=True)
    
    except Exception as e:
        frappe.log_error(f'Error handling push event: {str(e)}', 'GitHub Push Webhook')

def _handle_member_event(data, repo_full_name):
    """Handle GitHub member webhook events"""
    try:
        action = data.get('action')
        member = data.get('member', {})
        
        if not member:
            return
        
        username = member.get('login')
        if not username:
            return
        
        repo_doc = frappe.get_doc('Repository', {'full_name': repo_full_name})
        
        if action == 'added':
            # Add member to repository
            existing_member = None
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
                repo_doc.save(ignore_permissions=True)
        
        elif action == 'removed':
            # Remove member from repository
            for mem in repo_doc.members_table:
                if mem.github_username == username:
                    repo_doc.remove(mem)
                    break
            repo_doc.save(ignore_permissions=True)
    
    except Exception as e:
        frappe.log_error(f'Error handling member event: {str(e)}', 'GitHub Member Webhook')

def _handle_repository_event(data, repo_full_name):
    """Handle GitHub repository webhook events"""
    try:
        action = data.get('action')
        repository = data.get('repository', {})
        
        if action in ['edited', 'renamed']:
            repo_doc = frappe.get_doc('Repository', {'full_name': repo_full_name})
            repo_doc.visibility = 'Private' if repository.get('private') else 'Public'
            repo_doc.default_branch = repository.get('default_branch', 'main')
            
            # Handle repository rename
            if action == 'renamed' and repository.get('full_name') != repo_full_name:
                repo_doc.full_name = repository.get('full_name')
                repo_doc.repo_name = repository.get('name')
                repo_doc.repo_owner = repository.get('owner', {}).get('login', '')
                repo_doc.url = repository.get('html_url', '')
            
            repo_doc.save(ignore_permissions=True)
    
    except Exception as e:
        frappe.log_error(f'Error handling repository event: {str(e)}', 'GitHub Repository Webhook')