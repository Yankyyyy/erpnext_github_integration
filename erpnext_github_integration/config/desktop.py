from frappe import _

def get_data():
    return [
        {
            "module_name": "Erpnext Github Integration",
            "color": "#24292e",
            "icon": "octicon octicon-mark-github",
            "type": "module",
            "label": _("GitHub Integration"),
            "description": _("Integrate ERPNext with GitHub repositories, issues, and pull requests")
        }
    ]

# File: erpnext_github_integration/config/docs.py  
docs_app = "erpnext_github_integration"

source_link = "https://github.com/yourusername/erpnext_github_integration"

headline = "GitHub Integration for ERPNext"

sub_heading = "Sync repositories, issues, pull requests, and teams"

def get_context(context):
    context.brand_html = "GitHub Integration"
    context.top_bar_items = [
        {"label": "GitHub", "url": "https://github.com"},
        {"label": "Documentation", "url": "/docs"}
    ]