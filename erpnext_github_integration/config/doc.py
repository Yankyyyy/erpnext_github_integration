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