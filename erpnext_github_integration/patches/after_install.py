import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def create_custom_fields_and_scripts():
    custom_fields = {
        'User': [
            dict(fieldname='github_username', label='GitHub Username', fieldtype='Data', insert_after='email')
        ],
        'Project': [
            dict(fieldname='repository', label='Repository', fieldtype='Link', options='Repository', insert_after='project_name')
        ],
        'Task': [
            dict(fieldname='github_repo', label='GitHub Repo', fieldtype='Link', options='Repository', insert_after='project'),
            dict(fieldname='github_issue_number', label='GitHub Issue Number', fieldtype='Int', insert_after='github_repo'),
            dict(fieldname='github_pr_number', label='GitHub PR Number', fieldtype='Int', insert_after='github_issue_number'),
        ]
    }
    try:
        create_custom_fields(custom_fields)
    except Exception:
        pass
    # create minimal client scripts
    try:
        frappe.get_doc({'doctype':'Custom Script','dt':'Task','script_type':'Client','script':"frappe.ui.form.on('Task',{refresh:function(frm){}})"}).insert(ignore_permissions=True)
    except Exception:
        pass
    try:
        frappe.get_doc({'doctype':'Custom Script','dt':'Project','script_type':'Client','script':"frappe.ui.form.on('Project',{refresh:function(frm){}})"}).insert(ignore_permissions=True)
    except Exception:
        pass


# import frappe

# def create_custom_fields_and_scripts():
#     custom_fields = {
#         'User': [
#             dict(fieldname='github_username', label='GitHub Username', fieldtype='Data', insert_after='email')
#         ],
#         'Project': [
#             dict(fieldname='repository', label='Repository', fieldtype='Link', options='Repository', insert_after='project_name')
#         ],
#         'Task': [
#             dict(fieldname='github_repo', label='GitHub Repo', fieldtype='Link', options='Repository', insert_after='project'),
#             dict(fieldname='github_issue_number', label='GitHub Issue Number', fieldtype='Int', insert_after='github_repo'),
#             dict(fieldname='github_pr_number', label='GitHub PR Number', fieldtype='Int', insert_after='github_issue_number'),
#         ]
#     }

#     for dt, fields in custom_fields.items():
#         for f in fields:
#             try:
#                 frappe.get_doc({
#                     'doctype':'Custom Field',
#                     'dt': dt,
#                     'fieldname': f['fieldname'],
#                     'label': f['label'],
#                     'fieldtype': f['fieldtype'],
#                     'options': f.get('options'),
#                     'insert_after': f.get('insert_after')
#                 }).insert(ignore_permissions=True)
#             except Exception:
#                 pass

#     # Create lightweight Custom Script records to ensure client js loads
#     task_script = """frappe.ui.form.on('Task', { refresh: function(frm){} });"""
#     try:
#         frappe.get_doc({
#             'doctype':'Custom Script',
#             'dt':'Task',
#             'script_type':'Client',
#             'script': task_script
#         }).insert(ignore_permissions=True)
#     except Exception:
#         pass

#     project_script = """frappe.ui.form.on('Project', { refresh: function(frm){} });"""
#     try:
#         frappe.get_doc({
#             'doctype':'Custom Script',
#             'dt':'Project',
#             'script_type':'Client',
#             'script': project_script
#         }).insert(ignore_permissions=True)
#     except Exception:
#         pass
