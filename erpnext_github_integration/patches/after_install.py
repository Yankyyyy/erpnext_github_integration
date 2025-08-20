import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def create_custom_fields_and_scripts():
    """Create custom fields and scripts after installation"""
    
    # Create custom role if it doesn't exist
    if not frappe.db.exists('Role', 'GitHub Admin'):
        frappe.get_doc({
            'doctype': 'Role',
            'role_name': 'GitHub Admin',
            'desk_access': 1
        }).insert(ignore_permissions=True)
    
    # Custom fields to be created
    custom_fields = {
        'User': [
            dict(
                fieldname='github_username',
                label='GitHub Username',
                fieldtype='Data',
                insert_after='email',
                unique=1,
                description='GitHub username for integration purposes'
            )
        ],
        'Project': [
            dict(
                fieldname='repository',
                label='Repository',
                fieldtype='Link',
                options='Repository',
                insert_after='project_name',
                description='Link to GitHub repository'
            )
        ],
        'Task': [
            dict(
                fieldname='github_repo',
                label='GitHub Repository',
                fieldtype='Link',
                options='Repository',
                insert_after='project',
                description='GitHub repository this task belongs to'
            ),
            dict(
                fieldname='github_issue_number',
                label='GitHub Issue Number',
                fieldtype='Int',
                insert_after='github_repo',
                description='GitHub issue number if this task is linked to an issue'
            ),
            dict(
                fieldname='github_pr_number',
                label='GitHub PR Number',
                fieldtype='Int',
                insert_after='github_issue_number',
                description='GitHub pull request number if this task is linked to a PR'
            )
        ]
    }
    
    try:
        create_custom_fields(custom_fields)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Error creating custom fields: {str(e)}", "GitHub Integration Install")
    
    # Create custom scripts for enhanced functionality
    scripts = [
        {
            'dt': 'Task',
            'script_type': 'Client',
            'script': """
frappe.ui.form.on('Task', {
    refresh: function(frm) {
        // Add GitHub integration buttons
        if (frm.doc.github_repo) {
            // Create GitHub Issue button
            if (!frm.doc.github_issue_number) {
                frm.add_custom_button(__('Create GitHub Issue'), function() {
                    frappe.prompt([
                        {fieldname: 'title', fieldtype: 'Data', label: 'Issue Title', reqd: 1, default: frm.doc.subject},
                        {fieldname: 'body', fieldtype: 'Text', label: 'Issue Body', default: frm.doc.description}
                    ], function(values) {
                        frappe.call({
                            method: 'erpnext_github_integration.github_api.create_issue',
                            args: {
                                repository: frm.doc.github_repo,
                                title: values.title,
                                body: values.body
                            },
                            callback: function(r) {
                                if (r.message && r.message.issue) {
                                    frm.set_value('github_issue_number', r.message.issue.number);
                                    frm.save();
                                    frappe.msgprint(__('GitHub issue created: #{0}', [r.message.issue.number]));
                                }
                            }
                        });
                    }, __('Create GitHub Issue'));
                }, __('GitHub'));
            }
            
            // View in GitHub button
            if (frm.doc.github_issue_number) {
                frm.add_custom_button(__('View GitHub Issue'), function() {
                    let repo_name = frm.doc.github_repo;
                    window.open(`https://github.com/${repo_name}/issues/${frm.doc.github_issue_number}`, '_blank');
                }, __('GitHub'));
            }
            
            if (frm.doc.github_pr_number) {
                frm.add_custom_button(__('View GitHub PR'), function() {
                    let repo_name = frm.doc.github_repo;
                    window.open(`https://github.com/${repo_name}/pull/${frm.doc.github_pr_number}`, '_blank');
                }, __('GitHub'));
            }
        }
    }
});
            """
        },
        {
            'dt': 'Project',
            'script_type': 'Client',
            'script': """
frappe.ui.form.on('Project', {
    refresh: function(frm) {
        if (frm.doc.repository) {
            // Sync from GitHub button
            frm.add_custom_button(__('Sync from GitHub'), function() {
                frappe.call({
                    method: 'erpnext_github_integration.github_api.sync_repo',
                    args: {repository: frm.doc.repository},
                    callback: function(r) {
                        frappe.msgprint(__('GitHub sync completed'));
                        frm.reload_doc();
                    }
                });
            }, __('GitHub'));
            
            // View in GitHub button
            frm.add_custom_button(__('View in GitHub'), function() {
                window.open(`https://github.com/${frm.doc.repository}`, '_blank');
            }, __('GitHub'));
        }
    }
});
            """
        }
    ]
    
    # Create or update custom scripts
    for script_data in scripts:
        try:
            # Check if script already exists
            existing_script = frappe.db.exists('Custom Script', {
                'dt': script_data['dt'],
                'script_type': script_data['script_type']
            })
            
            if existing_script:
                # Update existing script
                script_doc = frappe.get_doc('Custom Script', existing_script)
                script_doc.script = script_data['script']
                script_doc.save(ignore_permissions=True)
            else:
                # Create new script
                frappe.get_doc({
                    'doctype': 'Custom Script',
                    'dt': script_data['dt'],
                    'script_type': script_data['script_type'],
                    'script': script_data['script']
                }).insert(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(f"Error creating custom script for {script_data['dt']}: {str(e)}", "GitHub Integration Install")
    
    # Create default GitHub Settings document if it doesn't exist
    if not frappe.db.exists('GitHub Settings'):
        try:
            frappe.get_doc({
                'doctype': 'GitHub Settings',
                'auth_type': 'Personal Access Token',
                'default_visibility': 'Private',
                'sync_interval_minutes': 60,
                'rate_limit_threshold': 100,
                'enabled': 0
            }).insert(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(f"Error creating GitHub Settings: {str(e)}", "GitHub Integration Install")
    
    # Set up permissions for GitHub Admin role
    try:
        github_doctypes = [
            'GitHub Settings',
            'Repository',
            'Repository Issue',
            'Repository Pull Request',
            'Repository Branch',
            'Repository Member',
            'Repository Issue Assignee',
            'Repository PR Reviewer'
        ]
        
        for doctype in github_doctypes:
            if frappe.db.exists('DocType', doctype):
                # Check if permission already exists
                existing_perm = frappe.db.exists('Custom DocPerm', {
                    'parent': doctype,
                    'role': 'GitHub Admin'
                })
                
                if not existing_perm:
                    frappe.get_doc({
                        'doctype': 'Custom DocPerm',
                        'parent': doctype,
                        'parenttype': 'DocType',
                        'parentfield': 'permissions',
                        'role': 'GitHub Admin',
                        'read': 1,
                        'write': 1,
                        'create': 1,
                        'delete': 1
                    }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Error setting up permissions: {str(e)}", "GitHub Integration Install")
    
    # Create sample workflow states for GitHub integration
    try:
        workflow_states = [
            {'state': 'Draft', 'style': ''},
            {'state': 'Open', 'style': 'Success'},
            {'state': 'In Progress', 'style': 'Warning'},
            {'state': 'In Review', 'style': 'Info'},
            {'state': 'Merged', 'style': 'Primary'},
            {'state': 'Closed', 'style': 'Danger'}
        ]

        for state_data in workflow_states:
            if not frappe.db.exists('Workflow State', state_data['state']):
                frappe.get_doc({
                    'doctype': 'Workflow State',
                    'workflow_state_name': state_data['state'],
                    'style': state_data['style']
                }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Error creating workflow states: {str(e)}", "GitHub Integration Install")
    
    frappe.db.commit()
    print("GitHub Integration setup completed successfully!")