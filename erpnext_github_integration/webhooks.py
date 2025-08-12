import frappe, hmac, hashlib, json
from frappe import _

@frappe.whitelist(allow_guest=True)
def handle_event():
    settings = frappe.get_single('GitHub Settings')
    secret = settings.webhook_secret or None
    payload = frappe.request.get_data().decode('utf-8')
    signature = frappe.request.headers.get('X-Hub-Signature-256')
    if secret and signature:
        mac = 'sha256=' + hmac.new(secret.encode(), msg=payload.encode(), digestmod=hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, signature):
            frappe.throw(_('Invalid webhook signature'), exc=frappe.PermissionError)
    event = frappe.request.headers.get('X-GitHub-Event')
    data = json.loads(payload)
    frappe.enqueue('erpnext_github_integration.webhooks._handle_event', event=event, data=data)
    return 'ok'

def _handle_event(event, data):
    try:
        if event == 'issues':
            repo = data.get('repository',{}).get('full_name')
            issue = data.get('issue')
            identifier = {'repo_full_name': repo, 'issue_number': issue.get('number')}
            try:
                doc = frappe.get_doc('Repository Issue', identifier)
                doc.title = issue.get('title')
                doc.body = issue.get('body') or ''
                doc.state = issue.get('state')
                doc.url = issue.get('html_url')
                doc.github_id = issue.get('id')
                doc.save(ignore_permissions=True)
            except Exception:
                frappe.get_doc({
                    'doctype':'Repository Issue',
                    'repo_full_name': repo,
                    'issue_number': issue.get('number'),
                    'title': issue.get('title'),
                    'body': issue.get('body') or '',
                    'state': issue.get('state'),
                    'url': issue.get('html_url'),
                    'github_id': issue.get('id')
                }).insert(ignore_permissions=True)
        elif event == 'pull_request':
            repo = data.get('repository',{}).get('full_name')
            pr = data.get('pull_request')
            identifier = {'repo_full_name': repo, 'pr_number': pr.get('number')}
            try:
                doc = frappe.get_doc('Repository Pull Request', identifier)
                doc.title = pr.get('title')
                doc.body = pr.get('body') or ''
                doc.state = pr.get('state')
                doc.head_branch = pr.get('head',{}).get('ref')
                doc.base_branch = pr.get('base',{}).get('ref')
                doc.url = pr.get('html_url')
                doc.github_id = pr.get('id')
                doc.save(ignore_permissions=True)
            except Exception:
                frappe.get_doc({
                    'doctype':'Repository Pull Request',
                    'repo_full_name': repo,
                    'pr_number': pr.get('number'),
                    'title': pr.get('title'),
                    'body': pr.get('body') or '',
                    'state': pr.get('state'),
                    'head_branch': pr.get('head',{}).get('ref'),
                    'base_branch': pr.get('base',{}).get('ref'),
                    'url': pr.get('html_url'),
                    'github_id': pr.get('id')
                }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(message=str(e), title='GitHub Webhook Handler Error')
