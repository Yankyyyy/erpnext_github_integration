### ERPNext GitHub Integration – Technical Documentation

## Overview
- Purpose: Synchronize GitHub repositories, issues, pull requests, branches, collaborators, and related activities into ERPNext, with UI actions and webhooks for near-real-time updates.
- Platform: Frappe/ERPNext app.
- Key components:
  - Server modules: `github_client.py`, `github_api.py`, `api.py`, `webhooks.py`, `hooks.py`
  - Data models (DocTypes): `GitHub Settings`, `Repository`, `Repository Issue`, `Repository Pull Request`, child tables for branches, members, assignees, reviewers
  - Client scripts: `public/js/project_client.js`, `public/js/task_client.js`, `repository.js` (form UI actions)
  - Patches and setup: `patches/after_install.py`, `patches/add_github_username.py`
  - Scheduler: hourly sync

## Installation and Packaging
- Standard Python packaging:
  - `pyproject.toml`: uses `flit_core` for build; Python 3.10+; linter config via Ruff.
  - `setup.py`: defines package metadata; `include_package_data=True`.
- App metadata:
  - `modules.txt`: declares module: “Erpnext Github Integration”.
  - `hooks.py` registers assets, events, scheduled jobs.

## Configuration and Setup

### Prerequisites
- ERPNext v14+/Frappe v14+ (compatible code includes `frappe.has_role` fallbacks).
- GitHub Personal Access Token (PAT) or OAuth app (project implements PAT-driven flows; OAuth fields available in settings).
- Webhook secret (optional but recommended).

### After-install patch
- `erpnext_github_integration.patches.after_install.create_custom_fields_and_scripts`:
  - Creates role `GitHub Admin`.
  - Creates custom fields:
    - `Project.repository` (Link → `Repository`)
    - `Task.github_repo` (Link → `Repository`)
    - `Task.github_issue_number` (Int)
    - `Task.github_pr_number` (Int)
  - Creates or updates `Custom Script` for `Task` and `Project` with GitHub actions.
  - Seeds default `GitHub Settings` single if missing.
  - Grants `GitHub Admin` CRUD on GitHub DocTypes via `Custom DocPerm`.
  - Creates sample workflow states.
- Patch `patches/add_github_username.py`:
  - Adds `User.github_username` field if missing.

### App Hooks
- Assets:
  - `app_include_js`: injects `/assets/erpnext_github_integration/js/project_client.js` and `/assets/erpnext_github_integration/js/task_client.js`.
- Doc Events:
  - `Repository.validate` → `erpnext_github_integration.api.validate_repository`: validates `full_name` and backfills `repo_owner`, `repo_name`, `url`.
- Dashboard:
  - `override_doctype_dashboards["Repository"]` → `api.get_repository_dashboard_data`.
- Scheduler:
  - Hourly: `github_api.sync_all_repositories`.

## Data Model (DocTypes)

### GitHub Settings (Single)
- Fields:
  - `auth_type` (Select: PAT/OAuth)
  - `personal_access_token` (Password)
  - `oauth_client_id` (Data)
  - `oauth_client_secret` (Password)
  - `webhook_secret` (Password)
  - `default_organization` (Data)
  - `default_visibility` (Select: Public/Private)
  - `last_sync` (Datetime)
  - `enabled` (Check)
- Permissions: `System Manager` (R/W/C/D), `GitHub Admin` (R/W).

### Repository
- Naming: `autoname: field:full_name`.
- Core fields:
  - `full_name` (owner/repo, unique, required), `repo_name`, `repo_owner`
  - `github_id`, `url`, `visibility` (Public/Private), `default_branch`
  - `is_synced` (Check), `last_synced` (Datetime)
  - Tables:
    - `branches_table` → child `Repository Branch`
    - `members_table` → child `Repository Member`
- Permissions: `System Manager` (R/W/C/D), `GitHub Admin` (R/W).

### Repository Branch (Child)
- Fields: `repo_full_name`, `branch_name`, `commit_sha`, `protected` (Check), `last_updated` (Datetime).
- `istable = 1`.

### Repository Member (Child)
- Fields: `repo_full_name`, `github_username`, `github_id`, `role` (member/maintainer), `email`.
- `istable = 1`.

### Repository Issue
- Naming: `autoname: format:{repository}-#{issue_number}`.
- Fields: `repository` (Link → `Repository`), `issue_number` (Int, required), `title`, `body` (Text), `state` (open/closed), `labels`, `url`, `github_id`, `created_at`, `updated_at`.
- Table: `assignees_table` → child `Repository Issue Assignee`.

### Repository Issue Assignee (Child)
- Fields: `issue` (Link → `Repository Issue`), `user` (Link → `User`).
- `istable = 1`.

### Repository Pull Request
- Naming: `autoname: format:{repository}-#{pr_number}`.
- Fields: `repository` (Link → `Repository`), `pr_number` (Int, required), `title`, `body`, `state` (open/closed/merged), `author`, `head_branch`, `base_branch`, `mergeable_state`, `github_id`, `url`, `created_at`, `updated_at`.
- Table: `reviewers_table` → child `Repository PR Reviewer`.

### Repository PR Reviewer (Child)
- Fields: `pull_request` (Link → `Repository Pull Request`), `user` (Link → `User`).
- `istable = 1`.

## Server Modules

### github_client.py (GitHub API client)
- Base URL `https://api.github.com`.
- Headers: Authorization: `token <PAT>`, Accept: `application/vnd.github.v3+json`, User-Agent: `erpnext-github-integration`.
- Rate limiting:
  - Checks `X-RateLimit-Remaining` and `X-RateLimit-Reset`; sleeps until reset if depleted.
- Pagination:
  - Follows RFC5988 `Link` header; `_get_with_pagination` accumulates all pages.
- `github_request(method, path, token, params=None, data=None, retry=2)`:
  - JSON body requests; handles 200/201/204; paginated responses; raises Frappe errors on failures with retries on rate-limit 403.

### github_api.py (Integration logic)
- Role check compatibility: `has_role(role)` supports older/newer Frappe.
- `convert_github_datetime(dt)`: normalizes GitHub ISO timestamps to Asia/Kolkata (IST) timezone and returns MySQL-friendly string without tz.
- Admin guard: `_require_github_admin()`.
- Permission check for sync: `_can_sync_repo(repo_full_name)` (GitHub Admin or project manager of linked `Project`).
- Connection and lookup:
  - `test_connection()`: validates PAT via `/user`.
  - `get_github_username_by_email(email)`: GitHub user search API.
- Listing:
  - `list_repositories(organization=None)`: `/orgs/{org}/repos` or `/user/repos` with pagination.
  - `list_branches(repo_full_name)`, `list_teams(org_name)`, `list_repo_members(repo_full_name)`.
- CRUD/actions:
  - `create_issue(repository, title, body=None, assignees=None, labels=None)` → creates GitHub issue and mirrors a `Repository Issue` record.
  - `bulk_create_issues(repository, issues)` → batch create in GitHub and mirror locally.
  - `assign_issue(repo_full_name, issue_number, assignees)` → PATCH GitHub issue; updates local assignees table.
  - `create_pull_request(repository, title, head, base, body=None)` → creates GitHub PR and mirrors `Repository Pull Request`.
  - `add_pr_reviewer(repo_full_name, pr_number, reviewers)` → request reviewers on GitHub; updates local reviewers.
  - `manage_repo_access(repo_full_name, action, identifier, permission='push')`:
    - `add_collaborator`/`remove_collaborator`
    - `add_team`/`remove_team` on an org repo (requires admin)
- Sync:
  - `sync_repo(repository)`:
    - Fetches repo info, branches (latest commit dates via `/commits?sha=branch&per_page=1`), issues (state=all), PRs (state=all), members.
    - Upserts `Repository`, clears/rebuilds `branches_table` and `members_table`, mirrors issues and PRs with child tables, converts timestamps to IST.
  - `sync_repo_members(repo_full_name)`:
    - Updates `Repository.members_table`.
    - Syncs linked `Project.project_users` by matching `User.github_username` or email fallback; sets role “Project User”.
  - `sync_all_repositories()`:
    - Hourly scheduler job; iterates all `Repository` and calls `sync_repo`.
    - Updates `GitHub Settings.last_sync`.
- Analytics and webhooks:
  - `get_repository_activity(repository, days=30)`:
    - Summaries: commit count, issues count (excluding PRs), pulls count, returns details preview.
  - `create_repository_webhook(repo_full_name, webhook_url=None, events=None)`, `list_repository_webhooks(repo_full_name)`.

### webhooks.py (Inbound GitHub webhooks)
- Entry: `github_webhook()` (guest allowed)
  - Validates HMAC signature with `webhook_secret` if present using `X-Hub-Signature-256`.
  - Robust header extraction `X-GitHub-Event` with fallbacks; infers event if header absent.
  - Ensures `repository.full_name` exists locally; processes events inline (not background) for reliability.
- Handlers:
  - `_handle_issues_event`: upsert/delete `Repository Issue` and assignees based on `action`.
  - `_handle_pull_request_event`: upsert `Repository Pull Request` and reviewers based on `action`.
  - `_handle_push_event`: updates `Repository.last_synced` and branch commit SHA/`last_updated`; adds branch if new.
  - `_handle_member_event`: add/remove collaborators in `members_table`.
  - `_handle_repository_event`: updates repo attributes; handles rename (`full_name`, `repo_name`, `repo_owner`, `url`).

### api.py (ERPNext-facing helpers)
- Form validation and UX:
  - `validate_repository(doc, method)`: validates `full_name` and populates `repo_owner`, `repo_name`, `url`.
  - `get_repository_dashboard_data(data)`: defines dashboard sections for `Repository`.
- User and project flows:
  - `get_user_repositories()`: returns repos accessible to current user:
    - All if `GitHub Admin`
    - Project manager of linked projects
    - Membership match by SQL on `members` JSON (optimizes for string search on `github_username`).
  - `sync_user_github_profile()`: fills `User` fields from GitHub (name/bio/location) via username.
  - `link_github_user_to_erp(github_username, erp_user)`: sets a user’s GitHub username.
  - `get_repository_statistics(repo_full_name)`: counts issues/PRs by state, branches, members.
  - `create_project_from_repository(repo_full_name, project_name=None)`: creates `Project` linked to repo.
- Bulk import:
  - `bulk_import_github_data(repo_full_name, import_type, force_update=False)`:
    - `issues`: imports all non-PR issues (state=all).
    - `pull_requests`: imports all PRs (state=all).
    - Upsert with `force_update` toggle; records import/update/skip/errors.

## Client/UI Behavior

### Repository form actions (`repository.js`)
- Buttons (under “GitHub” or “Actions” groups):
  - Sync Repository Data → `github_api.sync_repo`
  - Sync Members → `github_api.sync_repo_members`
  - Create Issue → `github_api.create_issue` (prompt for title/body/assignees/labels)
  - Create Pull Request → `github_api.create_pull_request` (prompt for title/head/base/body)
  - Manage Access → `github_api.manage_repo_access` (collaborator/team add/remove, permission)
  - Show Activity → `github_api.get_repository_activity` summary dialog
  - Manage Webhooks → list existing hooks; create via `github_api.create_repository_webhook`
  - Open in GitHub → opens `url`
- Auto-fill on `full_name` change: sets `repo_owner`, `repo_name`, `url`.

### Project form (`public/js/project_client.js`)
- Buttons:
  - Sync Members from Repository → `github_api.sync_repo_members`
  - Sync Repository Data → `github_api.sync_repo` (note: the script uses `args: {repo_full_name: repo}` in one place and `sync_repo` expects `repository`; be mindful in use; the `Repository` form uses the correct signature)

### Task form (`public/js/task_client.js`)
- Buttons when `github_repo` set:
  - Create GitHub Issue → `github_api.create_issue` (prompts, sets `github_issue_number`)
  - Create Pull Request → `github_api.create_pull_request` (prompts, sets `github_pr_number`)
  - Assign Issue → `github_api.assign_issue` (prompts for assignees)
  - Add PR Reviewer → `github_api.add_pr_reviewer` (prompts for reviewers)

## Permissions Model
- `GitHub Admin` role:
  - Created during install.
  - Granted CRUD permissions on GitHub DocTypes via `Custom DocPerm`.
  - Elevated actions require this role (bulk import, manage repo access, create/list webhooks, sync all).
- Access in business logic:
  - `_require_github_admin()` guards admin-only endpoints.
  - `_can_sync_repo()` allows either `GitHub Admin` or `Project.project_manager` of a project linked to that repository.
- Repository visibility is informational; actual GitHub API permissions are enforced via token scopes.

## Security
- PAT stored in `GitHub Settings` as Password field; accessed via `get_password`.
- Webhook validation: HMAC-SHA256 using `webhook_secret` if configured; rejects invalid signatures.
- ERPNext permission checks:
  - Creation of `Task`, `Project`, `User` edits guarded with `frappe.has_permission` checks in helpers.

## Error Handling and Logging
- API errors:
  - `github_client.github_request` raises Frappe exceptions on HTTP errors; retries on 403 rate-limit with backoff; paginates automatically.
- Webhooks:
  - Extensive `frappe.log_error` for missing data, unhandled events, processing errors; commits after each upsert to reduce partial failures.
- Bulk import and sync:
  - Records skipped/updated/imported counts; logs individual errors per record.

## Rate Limiting and Performance
- Client handles `X-RateLimit-Remaining` and `X-RateLimit-Reset` with sleep-and-retry.
- Pagination used for list endpoints.
- Scheduler runs hourly `sync_all_repositories`; prefer using webhooks for near real-time updates.
- Activity endpoint returns only small previews in `details`.

## API Endpoints (Whitelisted Methods)
- Connection/lookup:
  - `github_api.test_connection()`
  - `github_api.get_github_username_by_email(email)`
- Listing:
  - `github_api.list_repositories(organization=None)`
  - `github_api.list_branches(repo_full_name, per_page=100)`
  - `github_api.list_teams(org_name, per_page=100)`
  - `github_api.list_repo_members(repo_full_name, per_page=100)`
- Repo lifecycle:
  - `github_api.sync_repo(repository)`
  - `github_api.sync_repo_members(repo_full_name)`
  - `github_api.sync_all_repositories()`
  - `github_api.manage_repo_access(repo_full_name, action, identifier, permission='push')`
  - `github_api.create_repository_webhook(repo_full_name, webhook_url=None, events=None)`
  - `github_api.list_repository_webhooks(repo_full_name)`
  - `github_api.get_repository_activity(repository, days=30)`
- Issues:
  - `github_api.create_issue(repository, title, body=None, assignees=None, labels=None)`
  - `github_api.bulk_create_issues(repository, issues)`
  - `github_api.assign_issue(repo_full_name, issue_number, assignees)`
- Pull requests:
  - `github_api.create_pull_request(repository, title, head, base, body=None)`
  - `github_api.add_pr_reviewer(repo_full_name, pr_number, reviewers)`
- ERP-side helpers (api.py):
  - `api.get_user_repositories()`
  - `api.sync_user_github_profile()`
  - `api.create_task_from_github_issue(issue_name, task_title=None)`
  - `api.bulk_import_github_data(repo_full_name, import_type, force_update=False)` (admin)
  - `api.link_github_user_to_erp(github_username, erp_user)`
  - `api.get_repository_statistics(repo_full_name)`
  - `api.create_project_from_repository(repo_full_name, project_name=None)`
  - `api.can_user_sync_repo(repo_full_name)`

## Webhooks Integration
- Endpoint: `/api/method/erpnext_github_integration.webhooks.github_webhook`
- Events handled:
  - `issues`: open/edit/reopen/close/delete → upsert/delete `Repository Issue` + assignees.
  - `pull_request`: open/edit/reopen/close/merged → upsert `Repository Pull Request` + reviewers.
  - `push`: updates branch commit SHA and `last_updated`.
  - `member`: add/remove collaborator in `members_table`.
  - `repository`: `edited`/`renamed` → update repo attributes and `full_name`.
- Security:
  - Verify `X-Hub-Signature-256` with configured secret.
- Operational note:
  - Processing is synchronous (“immediate”) to avoid background job issues; could be moved to background once stable.

## Desk/UI Highlights
- `Repository` dashboard shows “Issues & PRs” and “Project Management” links.
- Many UI actions are provided as custom buttons on `Repository`, `Project`, and `Task` for convenience.
- `Repository.full_name` drives owner/name/url auto-fill.

## Known Edge Cases and Notes
- Timezone conversion uses IST; adjust if a different local timezone is desired.
- Some client scripts pass `repo_full_name` instead of `repository` for `sync_repo` arguments; ensure to call with `repository=<full_name>` for correctness as per `github_api.sync_repo`.
- GitHub “issues” API includes PRs; code filters PRs out when needed.
- `get_user_repositories()` uses a SQL LIKE on JSON field for members matching; effective but not relationally strict.

## Extensibility
- Add new DocTypes for additional GitHub entities (e.g., labels, milestones) following the same pattern (create list API call, mirror locally in child tables).
- Add background job queues to decouple webhook processing for high volume.
- Extend `GitHub Settings` with rate-limit thresholds, default sync intervals, custom event subscriptions.
- Implement OAuth if needed: settings fields are present; add OAuth flow endpoints to exchange and store tokens per user or app.

## Quick Start
- Install the app via bench; run migrations; ensure `GitHub Settings` has a valid PAT and webhook secret.
- Create `Repository` records with `full_name` values, or use `github_api.fetch_all_repositories(organization=...)` to populate.
- Click “Create Repository Webhook” from a `Repository` form (Manage Webhooks) or configure in GitHub manually to point to the webhook URL.
- Use “Sync Repository Data” to prime local data; rely on webhooks + hourly scheduler for continuous updates.