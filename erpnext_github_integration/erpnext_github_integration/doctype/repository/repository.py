import frappe
from frappe.model.document import Document

class Repository(Document):
    def validate(self):
        if self.full_name and '/' not in self.full_name:
            frappe.throw('Repository Full Name must be in owner/repo format')
