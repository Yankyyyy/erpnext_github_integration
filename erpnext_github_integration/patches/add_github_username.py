import frappe

def execute():
    if not frappe.db.exists("Custom Field", {"dt": "User", "fieldname": "github_username"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "User",
            "fieldname": "github_username",
            "label": "GitHub Username",
            "fieldtype": "Data",
            "insert_after": "username"
        }).insert()
