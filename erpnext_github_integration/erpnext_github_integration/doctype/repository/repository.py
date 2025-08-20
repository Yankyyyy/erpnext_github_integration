import frappe
from frappe.model.document import Document

class Repository(Document):
    def validate(self):
        if self.full_name and '/' not in self.full_name:
            frappe.throw('Repository Full Name must be in owner/repo format')
        
        # Auto-populate repo_name and repo_owner from full_name
        if self.full_name and '/' in self.full_name:
            parts = self.full_name.split('/')
            self.repo_owner = parts[0]
            self.repo_name = parts[1]
            
        # Auto-populate URL if not set
        if self.full_name and not self.url:
            self.url = f"https://github.com/{self.full_name}"