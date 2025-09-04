// Copyright (c) 2025, Yanky and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitHub Settings", {
    refresh(frm) {
        // Update on form refresh
        update_auth_fields_visibility(frm);
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

        frm.add_custom_button(__('Bulk Update Github Username'), function() {
            if (!frm.doc.personal_access_token) {
                frappe.msgprint({
                    title: __('Personal Access Token Required'),
                    indicator: 'red',
                    message: __('Please set Personal Access Token first in the Personal Access Token field.')
                });
                return;
            }
            
            frappe.confirm(
                __('This will update GitHub usernames for all users based on their email addresses. This may take several minutes. Continue?'),
                function() {
                    // Proceed with bulk update
                    update_all_users_github_usernames();
                },
                function() {
                    frappe.show_alert({
                        message: __('Bulk update cancelled'),
                        indicator: 'blue'
                    });
                }
            );
        }, __('Actions'));

        // Fetch All Repositories button
        frm.add_custom_button(__('Fetch All Repositories'), function() {
                frappe.call({
                    method: 'erpnext_github_integration.github_api.fetch_all_repositories',
                    args: {
                        organization: '' // Optional: pass organization name
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint({
                                title: __('Success'),
                                indicator: 'green',
                                message: r.message.message
                            });
                            frappe.set_route('List', 'Repository');
                        } else {
                            frappe.msgprint({
                                title: __('Error'),
                                indicator: 'red',
                                message: r.message.message || __('Failed to fetch repositories')
                            });
                        }
                    }
                });
            }, __('Sync'));

        // List Repositories button
        frm.add_custom_button(__('List Repositories'), function() {
            frappe.call({
                method: 'erpnext_github_integration.github_api.list_repositories',
                args: {
                    organization: frm.doc.default_organization
                },
                callback: function(r) {
                    if (r.message && r.message.length) {
                        let repos_html = '<div style="max-height: 400px; overflow-y: auto;"><table class="table table-bordered" id="github-repos-table"><thead><tr><th>Repository</th><th>Visibility</th><th>Action</th></tr></thead><tbody>';
                        
                        r.message.forEach(repo => {
                            repos_html += `<tr>
                                <td><a href="${repo.html_url}" target="_blank">${repo.full_name}</a></td>
                                <td>${repo.private ? 'Private' : 'Public'}</td>
                                <td><button class="btn btn-xs btn-primary sync-btn" data-repo="${repo.full_name}">Sync</button></td>
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
                        
                        d.show();
                        
                        // Add event listener after dialog is rendered
                        setTimeout(() => {
                            const table = d.body.querySelector('#github-repos-table');
                            if (table) {
                                table.addEventListener('click', function(e) {
                                    if (e.target.classList.contains('sync-btn')) {
                                        const repoFullName = e.target.getAttribute('data-repo');
                                        frappe.call({
                                            method: 'erpnext_github_integration.github_api.sync_repo',
                                            args: {repository: repoFullName},
                                            callback: function(r) {
                                                frappe.msgprint(__('Repository {0} synced successfully', [repoFullName]));
                                                d.hide();
                                            },
                                            error: function(err) {
                                                frappe.msgprint(__('Error syncing repository: {0}', [err.responseText || JSON.stringify(err)]));
                                            }
                                        });
                                    }
                                });
                            }
                        }, 100);
                        
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
                        if (r.message) {
                            frappe.msgprint({
                                title: __('Repositories Sync'),
                                indicator: r.message.failed > 0 ? 'red' : 'green',
                                message: __(`Success: ${r.message.success}<br>Failed: ${r.message.failed}`)
                            });
                        }
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
            let users = [];

            // Fetch repositories first
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Repository',
                    fields: ['name', 'full_name']
                },
                callback: function(r) {
                    if (r.message && r.message.length) {
                        r.message.forEach(repo => {
                            repos.push({ label: repo.full_name, value: repo.full_name });
                        });
                    }

                    // Fetch users after repos
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'User',
                            filters: { enabled: 1 },
                            fields: ['name', 'full_name']
                        },
                        callback: function(r2) {
                            if (r2.message && r2.message.length) {
                                r2.message.forEach(user => {
                                    users.push({
                                        label: user.full_name || user.name,
                                        value: user.name
                                    });
                                });
                            }

                            // Now show the dialog
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
                                        fieldtype: 'Select',
                                        label: 'Username',
                                        options: users,
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
                    });
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
    onload: function(frm) {
        // Set initial state
        update_auth_fields_visibility(frm);
    },
    
    auth_type: function(frm) {
        // Update when auth_type changes
        update_auth_fields_visibility(frm);
    }
});

function update_auth_fields_visibility(frm) {
    // Default to PAT if not set
    const auth_type = frm.doc.auth_type || 'Personal Access Token';
    
    if (auth_type === 'Personal Access Token') {
        frm.set_df_property('personal_access_token', 'hidden', false);
        frm.set_df_property('oauth_client_id', 'hidden', true);
        frm.set_df_property('oauth_client_secret', 'hidden', true);
    } else if (auth_type === 'OAuth App') {
        frm.set_df_property('personal_access_token', 'hidden', true);
        frm.set_df_property('oauth_client_id', 'hidden', false);
        frm.set_df_property('oauth_client_secret', 'hidden', false);
    }
    
    // Refresh the form to apply changes
    frm.refresh_fields();
}

// Script to bulk update GitHub usernames for all users
function update_all_users_github_usernames() {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'User',
            fields: ['name', 'email', 'github_username', 'full_name'],
            filters: [
                ['email', '!=', ''],
                ['github_username', '=', ''],
                ['enabled', '=', 1]
            ],
            limit_page_length: 0
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                let users = r.message;
                let processed = 0;
                let successCount = 0;
                let errorCount = 0;
                
                // Show progress dialog
                let progress_dialog = new frappe.ui.Dialog({
                    title: __('Updating GitHub Usernames'),
                    fields: [
                        {
                            fieldname: 'progress',
                            fieldtype: 'HTML',
                            options: `<div class="progress-area">
                                <div class="progress-text">${__('Processing 0 of ' + users.length + ' users...')}</div>
                                <div class="progress-bar" style="height: 20px; background: #f0f0f0; border-radius: 3px;">
                                    <div class="progress-fill" style="height: 100%; width: 0%; background: #5e64ff; border-radius: 3px;"></div>
                                </div>
                            </div>`
                        }
                    ]
                });
                
                progress_dialog.show();
                
                // Process users with delay to avoid rate limiting
                users.forEach((user, index) => {
                    setTimeout(() => {
                        frappe.call({
                            method: 'erpnext_github_integration.github_api.get_github_username_by_email',
                            args: {
                                email: user.email
                            },
                            callback: function(response) {
                                processed++;
                                
                                // Update progress
                                let progressPercent = (processed / users.length) * 100;
                                progress_dialog.fields_dict.progress.$wrapper.html(`
                                    <div class="progress-area">
                                        <div class="progress-text">${__('Processing ' + processed + ' of ' + users.length + ' users...')}</div>
                                        <div class="progress-bar" style="height: 20px; background: #f0f0f0; border-radius: 3px;">
                                            <div class="progress-fill" style="height: 100%; width: ${progressPercent}%; background: #5e64ff; border-radius: 3px;"></div>
                                        </div>
                                        <div style="margin-top: 10px;">
                                            ${__('Success:')} ${successCount} | ${__('Errors:')} ${errorCount}
                                        </div>
                                    </div>
                                `);
                                
                                if (response.message && response.message.success) {
                                    frappe.call({
                                        method: 'erpnext_github_integration.api.link_github_user_to_erp',
                                        args: {
                                            erp_user: user.name,
                                            github_username: response.message.github_username
                                        },
                                        callback: function(linkResponse) {
                                            if (linkResponse.message && linkResponse.message.success) {
                                                console.log(`Updated ${user.name} with GitHub username: ${response.message.github_username}`);
                                                successCount++;
                                            } else {
                                                console.error(__('Failed to update {0}: {1}', [user.name, linkResponse.message?.error || 'Unknown error']));
                                                errorCount++;
                                            }
                                            
                                            checkCompletion();
                                        }
                                    });
                                } else {
                                    console.error(__('Failed to fetch GitHub username for {0}: {1}', [user.email, response.message?.error || 'Unknown error']));
                                    errorCount++;
                                    checkCompletion();
                                }
                                
                                function checkCompletion() {
                                    if (processed === users.length) {
                                        progress_dialog.hide();
                                        frappe.msgprint({
                                            title: __('Update Complete'),
                                            indicator: 'green',
                                            message: __(`
                                                Processed: ${processed} users<br>
                                                Success: ${successCount}<br>
                                                Errors: ${errorCount}
                                            `)
                                        });
                                    }
                                }
                            }
                        });
                    }, index * 1500); // 1.5 second delay between requests to avoid GitHub rate limiting
                });
            } else {
                frappe.msgprint(__('No users found without GitHub usernames'));
            }
        }
    });
}