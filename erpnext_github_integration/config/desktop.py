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