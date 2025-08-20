// Copyright (c) 2025, Yanky and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitHub Settings", {
    refresh(frm) {
        // Test Connection button
        frm.add_custom_button(__('Test Connection'), function() {
            if (!frm.doc.personal_access_token) {
                frappe.msgprint(__('Please set Personal Access Token first'));
                return;
            }
            
            frappe.call({
                method: 'erpnext_github_integration.github_api.test_connection',
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.msgprint(__('GitHub connection successful! User: {0}', [r.message.user]));
                    } else {
                        frappe.msgprint(__('GitHub connection failed: {0}', [r.message.error || 'Unknown error']));
                    }
                }
            });
        }, __('Actions'));

        // List Repositories button
        frm.add_custom_button(__('List Repositories'), function() {
            frappe.call({
                method: 'erpnext_github_integration.github_api.list_repositories',
                args: {
                    organization: frm.doc.default_organization
                },
                callback: function(r) {
                    if (r.message && r.message.length) {
                        let repos_html = '<div style="max-height: 400px; overflow-y: auto;"><table class="table table-bordered"><thead><tr><th>Repository</th><th>Visibility</th><th>Action</th></tr></thead><tbody>';
                        
                        r.message.forEach(repo => {
                            repos_html += `<tr>
                                <td><a href="${repo.html_url}" target="_blank">${repo.full_name}</a></td>
                                <td>${repo.private ? 'Private' : 'Public'}</td>
                                <td><button class="btn btn-xs btn-primary" onclick="sync_repo('${repo.full_name}')">Sync</button></td>
                            </tr>`;
                        });
                        
                        repos_html += '</tbody></table></div>';
                        
                        let d = new frappe.ui.Dialog({
                            title: __('GitHub Repositories'),
                            fields: [{
                                fieldname: 'repos',
                                fieldtype: 'HTML',
                                options: repos_html
                            }],
                            size: 'large'
                        });
                        
                        // Add sync function to window
                        window.sync_repo = function(repo_full_name) {
                            frappe.call({
                                method: 'erpnext_github_integration.github_api.sync_repo',
                                args: {repository: repo_full_name},
                                callback: function(r) {
                                    frappe.msgprint(__('Repository {0} synced successfully', [repo_full_name]));
                                    d.hide();
                                },
                                error: function(err) {
                                    frappe.msgprint(__('Error syncing repository: {0}', [err.responseText || JSON.stringify(err)]));
                                }
                            });
                        };
                        
                        d.show();
                    } else {
                        frappe.msgprint(__('No repositories found'));
                    }
                }
            });
        }, __('Sync'));

        // Sync All Repositories button
        frm.add_custom_button(__('Sync All Repositories'), function() {
            frappe.confirm(__('This will sync all existing repositories. Continue?'), function() {
                frappe.call({
                    method: 'erpnext_github_integration.github_api.sync_all_repositories',
                    callback: function(r) {
                        frappe.msgprint(__('All repositories sync initiated. Check background jobs for progress.'));
                    },
                    error: function(err) {
                        frappe.msgprint(__('Error initiating sync: {0}', [err.responseText || JSON.stringify(err)]));
                    }
                });
            });
        }, __('Sync'));

        // Sync Repository Members button
        frm.add_custom_button(__('Sync Repository Members'), function() {
            let repos = [];
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Repository',
                    fields: ['name', 'full_name']
                },
                callback: function(r) {
                    if (r.message && r.message.length) {
                        r.message.forEach(repo => {
                            repos.push({label: repo.full_name, value: repo.full_name});
                        });
                        
                        frappe.prompt([{
                            fieldname: 'repository',
                            fieldtype: 'Select',
                            label: 'Select Repository',
                            options: repos,
                            reqd: 1
                        }], function(values) {
                            frappe.call({
                                method: 'erpnext_github_integration.github_api.sync_repo_members',
                                args: {repo_full_name: values.repository},
                                callback: function(r) {
                                    frappe.msgprint(__('Repository members synced successfully'));
                                }
                            });
                        }, __('Sync Repository Members'));
                    } else {
                        frappe.msgprint(__('No repositories found. Please sync repositories first.'));
                    }
                }
            });
        }, __('Sync'));

        // Bulk Create Issues button
        frm.add_custom_button(__('Bulk Create Issues'), function() {
            let repos = [];
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Repository',
                    fields: ['name', 'full_name']
                },
                callback: function(r) {
                    if (r.message && r.message.length) {
                        r.message.forEach(repo => {
                            repos.push({label: repo.full_name, value: repo.full_name});
                        });
                        
                        let d = new frappe.ui.Dialog({
                            title: __('Bulk Create GitHub Issues'),
                            fields: [
                                {
                                    fieldname: 'repository',
                                    fieldtype: 'Select',
                                    label: 'Repository',
                                    options: repos,
                                    reqd: 1
                                },
                                {
                                    fieldname: 'issues_data',
                                    fieldtype: 'Code',
                                    label: 'Issues JSON Data',
                                    description: 'Format: [{"title": "Issue 1", "body": "Description"}, {"title": "Issue 2", "body": "Description"}]',
                                    reqd: 1
                                }
                            ],
                            primary_action_label: __('Create Issues'),
                            primary_action: function(values) {
                                try {
                                    let issues = JSON.parse(values.issues_data);
                                    frappe.call({
                                        method: 'erpnext_github_integration.github_api.bulk_create_issues',
                                        args: {
                                            repository: values.repository,
                                            issues: issues
                                        },
                                        callback: function(r) {
                                            frappe.msgprint(__('Issues created successfully'));
                                            d.hide();
                                        }
                                    });
                                } catch (e) {
                                    frappe.msgprint(__('Invalid JSON format'));
                                }
                            }
                        });
                        d.show();
                    }
                }
            });
        }, __('Actions'));

        // Manage Repository Access button
        frm.add_custom_button(__('Manage Repository Access'), function() {
            let repos = [];
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Repository',
                    fields: ['name', 'full_name']
                },
                callback: function(r) {
                    if (r.message && r.message.length) {
                        r.message.forEach(repo => {
                            repos.push({label: repo.full_name, value: repo.full_name});
                        });
                        
                        let d = new frappe.ui.Dialog({
                            title: __('Manage Repository Access'),
                            fields: [
                                {
                                    fieldname: 'repository',
                                    fieldtype: 'Select',
                                    label: 'Repository',
                                    options: repos,
                                    reqd: 1
                                },
                                {
                                    fieldname: 'action',
                                    fieldtype: 'Select',
                                    label: 'Action',
                                    options: 'Add Collaborator\nRemove Collaborator\nAdd Team\nRemove Team',
                                    reqd: 1
                                },
                                {
                                    fieldname: 'identifier',
                                    fieldtype: 'Data',
                                    label: 'Username/Team Name',
                                    reqd: 1
                                },
                                {
                                    fieldname: 'permission',
                                    fieldtype: 'Select',
                                    label: 'Permission Level',
                                    options: 'pull\npush\nadmin\nmaintain\ntriage',
                                    default: 'push'
                                }
                            ],
                            primary_action_label: __('Execute'),
                            primary_action: function(values) {
                                let action_map = {
                                    'Add Collaborator': 'add_collaborator',
                                    'Remove Collaborator': 'remove_collaborator',
                                    'Add Team': 'add_team',
                                    'Remove Team': 'remove_team'
                                };
                                
                                frappe.call({
                                    method: 'erpnext_github_integration.github_api.manage_repo_access',
                                    args: {
                                        repo_full_name: values.repository,
                                        action: action_map[values.action],
                                        identifier: values.identifier,
                                        permission: values.permission
                                    },
                                    callback: function(r) {
                                        frappe.msgprint(__('Repository access updated successfully'));
                                        d.hide();
                                    }
                                });
                            }
                        });
                        d.show();
                    }
                }
            });
        }, __('Actions'));

        // Show sync statistics
        if (frm.doc.last_sync) {
            frm.add_custom_button(__('Show Sync Statistics'), function() {
                frappe.call({
                    method: 'erpnext_github_integration.github_api.get_sync_statistics',
                    callback: function(r) {
                        if (r.message) {
                            let stats = r.message;
                            let stats_html = `
                                <div class="row">
                                    <div class="col-md-3">
                                        <div class="card text-center">
                                            <div class="card-body">
                                                <h5 class="card-title">${stats.repositories}</h5>
                                                <p class="card-text">Repositories</p>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="card text-center">
                                            <div class="card-body">
                                                <h5 class="card-title">${stats.issues}</h5>
                                                <p class="card-text">Issues</p>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="card text-center">
                                            <div class="card-body">
                                                <h5 class="card-title">${stats.pull_requests}</h5>
                                                <p class="card-text">Pull Requests</p>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="card text-center">
                                            <div class="card-body">
                                                <h5 class="card-title">${stats.members}</h5>
                                                <p class="card-text">Members</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            `;
                            
                            let d = new frappe.ui.Dialog({
                                title: __('GitHub Integration Statistics'),
                                fields: [{
                                    fieldname: 'stats',
                                    fieldtype: 'HTML',
                                    options: stats_html
                                }],
                                size: 'large'
                            });
                            d.show();
                        }
                    }
                });
            }, __('Statistics'));
        }
    },
    
    auth_type(frm) {
        // Toggle field visibility based on auth type
        if (frm.doc.auth_type === 'Personal Access Token') {
            frm.toggle_display('personal_access_token', true);
            frm.toggle_display('oauth_client_id', false);
            frm.toggle_display('oauth_client_secret', false);
        } else if (frm.doc.auth_type === 'OAuth App') {
            frm.toggle_display('personal_access_token', false);
            frm.toggle_display('oauth_client_id', true);
            frm.toggle_display('oauth_client_secret', true);
        }
    }
});