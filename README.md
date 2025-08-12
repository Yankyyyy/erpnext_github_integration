# erpnext_github_integration v4

This package provides a Frappe app that integrates GitHub with ERPNext Projects and Tasks.

Features:
- PAT-based authentication and GitHub Settings
- Repository, Repository Issue, Repository Pull Request, Repository Branch, Repository Member doctypes
- Create issues/PRs, assign issues, add PR reviewers
- Manage collaborators and teams (manage_repo_access)
- Granular permission checks: GitHub Admins and Project Managers can sync repositories
- Client-side buttons on Task and Project
- Webhook handler for issues and PR events

Installation:
1. Unzip into bench/apps/
2. `bench --site <site> install-app erpnext_github_integration`
3. Open GitHub Settings and configure Personal Access Token and webhook secret

PAT scopes required (depending on features used): `repo`, `admin:org` (for org/team management)
