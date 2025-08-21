// Copyright (c) 2025, Yanky and contributors
// For license information, please see license.txt

frappe.ui.form.on("Repository", {
    refresh(frm) {
        // Sync Repository Data button
        if (frm.doc.full_name) {
            frm.add_custom_button(__('Sync Repository Data'), function() {
                frappe.call({
                    method: 'erpnext_github_integration.github_api.sync_repo',
                    args: {repository: frm.doc.full_name},
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint(__('Sync completed: {0} branches, {1} issues, {2} PRs, {3} members', 
                                [r.message.branches, r.message.issues, r.message.pulls, r.message.members]));
                            frm.reload_doc();
                        }
                    },
                    error: function(err) {
                        // frappe.msgprint(__('Sync failed: {0}', [err.responseText || JSON.stringify(err)]));
                        frappe.msgprint(__('Sync failed. Please check the console for details.'));
                    }
                });
            }, __('GitHub'));

            // Sync Members button
            frm.add_custom_button(__('Sync Members'), function() {
                frappe.call({
                    method: 'erpnext_github_integration.github_api.sync_repo_members',
                    args: {repo_full_name: frm.doc.full_name},
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint(__('Synced {0} members', [r.message.members]));
                            frm.reload_doc();
                        }
                    }
                });
            }, __('GitHub'));

            // Create Issue button
            frm.add_custom_button(__('Create Issue'), function() {
                frappe.prompt([
                    {fieldname: 'title', fieldtype: 'Data', label: 'Issue Title', reqd: 1},
                    {fieldname: 'body', fieldtype: 'Text', label: 'Issue Body'},
                    {fieldname: 'assignees', fieldtype: 'Data', label: 'Assignees (comma separated)'},
                    {fieldname: 'labels', fieldtype: 'Data', label: 'Labels (comma separated)'}
                ], function(values) {
                    frappe.call({
                        method: 'erpnext_github_integration.github_api.create_issue',
                        args: {
                            repository: frm.doc.full_name,
                            title: values.title,
                            body: values.body,
                            assignees: values.assignees,
                            labels: values.labels
                        },
                        callback: function(r) {
                            if (r.message) {
                                frappe.msgprint(__('Issue created: #{0}', [r.message.issue.number]));
                                frm.reload_doc();
                            }
                        }
                    });
                }, __('Create GitHub Issue'));
            }, __('Actions'));

            // Create Pull Request button
            frm.add_custom_button(__('Create Pull Request'), function() {
                frappe.prompt([
                    {fieldname: 'title', fieldtype: 'Data', label: 'PR Title', reqd: 1},
                    {fieldname: 'head', fieldtype: 'Data', label: 'Head Branch', reqd: 1},
                    {fieldname: 'base', fieldtype: 'Data', label: 'Base Branch', reqd: 1, default: frm.doc.default_branch || 'main'},
                    {fieldname: 'body', fieldtype: 'Text', label: 'PR Body'}
                ], function(values) {
                    frappe.call({
                        method: 'erpnext_github_integration.github_api.create_pull_request',
                        args: {
                            repository: frm.doc.full_name,
                            title: values.title,
                            head: values.head,
                            base: values.base,
                            body: values.body
                        },
                        callback: function(r) {
                            if (r.message) {
                                frappe.msgprint(__('Pull Request created: #{0}', [r.message.pull_request.number]));
                                frm.reload_doc();
                            }
                        }
                    });
                }, __('Create Pull Request'));
            }, __('Actions'));

            // Manage Access button
            frm.add_custom_button(__('Manage Access'), function() {
                let d = new frappe.ui.Dialog({
                    title: __('Manage Repository Access'),
                    fields: [
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
                                repo_full_name: frm.doc.full_name,
                                action: action_map[values.action],
                                identifier: values.identifier,
                                permission: values.permission
                            },
                            callback: function(r) {
                                frappe.msgprint(__('Repository access updated successfully'));
                                d.hide();
                                frm.reload_doc();
                            }
                        });
                    }
                });
                d.show();
            }, __('Actions'));

            // Show Activity button
            frm.add_custom_button(__('Show Activity'), function() {
                frappe.call({
                    method: 'erpnext_github_integration.github_api.get_repository_activity',
                    args: {repository: frm.doc.full_name, days: 30},
                    callback: function(r) {
                        if (r.message && !r.message.error) {
                            let activity = r.message;
                            let html = '<div style="max-height: 400px; overflow-y: auto;">';
                            
                            // Summary statistics
                            html += `<div class="alert alert-info">
                                <strong>Activity Summary (Last ${activity.period_days} days):</strong><br>
                                Commits: ${activity.commits} | Issues: ${activity.issues} | Pull Requests: ${activity.pulls}
                            </div>`;
                            
                            // Recent commits
                            if (activity.details && activity.details.commits && activity.details.commits.length) {
                                html += '<h5>Recent Commits</h5><ul>';
                                activity.details.commits.forEach(commit => {
                                    const message = commit.commit ? commit.commit.message : commit.message;
                                    const author = commit.commit && commit.commit.author ? commit.commit.author.name : 
                                                commit.author ? commit.author.login : 'Unknown';
                                    const date = commit.commit && commit.commit.author ? commit.commit.author.date : 
                                            commit.commit ? commit.commit.committer.date : '';
                                    
                                    html += `<li><strong>${(message || '').split('\n')[0]}</strong><br>
                                            <small>by ${author} on ${date ? frappe.datetime.str_to_user(date) : 'unknown date'}</small></li>`;
                                });
                                html += '</ul>';
                            } else {
                                html += '<p>No recent commits</p>';
                            }
                            
                            // Recent issues
                            if (activity.details && activity.details.issues && activity.details.issues.length) {
                                html += '<h5>Recent Issues</h5><ul>';
                                activity.details.issues.forEach(issue => {
                                    html += `<li><strong>#${issue.number}: ${issue.title}</strong> - ${issue.state}<br>
                                            <small>by ${issue.user ? issue.user.login : 'Unknown'} on ${frappe.datetime.str_to_user(issue.created_at)}</small></li>`;
                                });
                                html += '</ul>';
                            }
                            
                            // Recent pull requests
                            if (activity.details && activity.details.pulls && activity.details.pulls.length) {
                                html += '<h5>Recent Pull Requests</h5><ul>';
                                activity.details.pulls.forEach(pr => {
                                    html += `<li><strong>#${pr.number}: ${pr.title}</strong> - ${pr.state}<br>
                                            <small>by ${pr.user ? pr.user.login : 'Unknown'} on ${frappe.datetime.str_to_user(pr.created_at)}</small></li>`;
                                });
                                html += '</ul>';
                            }
                            
                            html += '</div>';
                            
                            let d = new frappe.ui.Dialog({
                                title: __('Repository Activity (Last {0} days)', [activity.period_days]),
                                fields: [{
                                    fieldname: 'activity',
                                    fieldtype: 'HTML',
                                    options: html
                                }],
                                size: 'large'
                            });
                            d.show();
                        } else {
                            frappe.msgprint(__('Failed to load activity: {0}', [r.message ? r.message.error : 'Unknown error']));
                        }
                    }
                });
            }, __('View'));

            // Webhook Management
            frm.add_custom_button(__('Manage Webhooks'), function() {
                frappe.call({
                    method: 'erpnext_github_integration.github_api.list_repository_webhooks',
                    args: {repo_full_name: frm.doc.full_name},
                    callback: function(r) {
                        if (r.message) {
                            let webhooks = r.message;
                            let html = '<div style="max-height: 300px; overflow-y: auto;">';
                            
                            if (webhooks.length) {
                                html += '<table class="table table-bordered"><thead><tr><th>ID</th><th>URL</th><th>Events</th><th>Active</th></tr></thead><tbody>';
                                webhooks.forEach(webhook => {
                                    html += `<tr>
                                        <td>${webhook.id}</td>
                                        <td>${webhook.config.url}</td>
                                        <td>${webhook.events.join(', ')}</td>
                                        <td>${webhook.active ? 'Yes' : 'No'}</td>
                                    </tr>`;
                                });
                                html += '</tbody></table>';
                            } else {
                                html += '<p>No webhooks configured for this repository.</p>';
                            }
                            
                            html += '</div>';
                            html += '<button class="btn btn-primary btn-sm" onclick="create_webhook()">Create New Webhook</button>';
                            
                            let d = new frappe.ui.Dialog({
                                title: __('Repository Webhooks'),
                                fields: [{
                                    fieldname: 'webhooks',
                                    fieldtype: 'HTML',
                                    options: html
                                }],
                                size: 'large'
                            });
                            
                            window.create_webhook = function() {
                                frappe.call({
                                    method: 'erpnext_github_integration.github_api.create_repository_webhook',
                                    args: {repo_full_name: frm.doc.full_name},
                                    callback: function(r) {
                                        frappe.msgprint(__('Webhook created successfully'));
                                        d.hide();
                                    }
                                });
                            };
                            
                            d.show();
                        }
                    }
                });
            }, __('Actions'));
        }

        // Open in GitHub button
        if (frm.doc.url) {
            frm.add_custom_button(__('Open in GitHub'), function() {
                window.open(frm.doc.url, '_blank');
            }, __('View'));
        }
    },

    full_name(frm) {
        if (frm.doc.full_name && frm.doc.full_name.includes('/')) {
            let parts = frm.doc.full_name.split('/');
            frm.set_value('repo_owner', parts[0]);
            frm.set_value('repo_name', parts[1]);
            
            if (!frm.doc.url) {
                frm.set_value('url', `https://github.com/${frm.doc.full_name}`);
            }
        }
    }
});