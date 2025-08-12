frappe.ui.form.on('Project', {
    refresh: function(frm) {
        frm.add_custom_button(__('Sync Members from Repository'), function() {
            let repo = frm.doc.repository;
            if (!repo) {
                frappe.msgprint(__('Please link a Repository record to this Project first.'));
                return;
            }
            frappe.call({
                method: 'erpnext_github_integration.github_api.sync_repo_members',
                args: {repo_full_name: repo},
                callback: function(r) {
                    frappe.msgprint(__('Repository members synced to Project users.'));
                    frm.reload_doc();
                }
            });
        });
        frm.add_custom_button(__('Sync Repository Data'), function() {
            let repo = frm.doc.repository;
            if (!repo) {
                frappe.msgprint(__('Please link a Repository record to this Project first.'));
                return;
            }
            frappe.call({
                method: 'erpnext_github_integration.github_api.sync_repo',
                args: {repo_full_name: repo},
                callback: function(r) {
                    frappe.msgprint(__('Repository sync completed.'));
                    frm.reload_doc();
                },
                error: function(err) {
                    frappe.msgprint(__('Error during sync: {0}').format(err.responseText || JSON.stringify(err)));
                }
            });
        });
    }
});
