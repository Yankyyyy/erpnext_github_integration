# ERPNext GitHub Integration

A comprehensive GitHub integration app for ERPNext that synchronizes repositories, issues, pull requests, and members between GitHub and ERPNext.

# ERPNext GitHub Integration - Complete File Structure

To create the zip file, create the following directory structure and files:

## Directory Structure
```
erpnext_github_integration/
├── __init__.py
├── hooks.py
├── modules.txt
├── patches.txt
├── github_api.py
├── github_client.py
├── webhooks.py
├── api.py
├── README.md
├── config/
│   ├── __init__.py
│   ├── desktop.py
│   └── docs.py
├── erpnext_github_integration/
│   ├── __init__.py
│   └── doctype/
│       ├── __init__.py
│       ├── github_settings/
│       │   ├── __init__.py
│       │   ├── github_settings.js
│       │   ├── github_settings.json
│       │   ├── github_settings.py
│       │   └── test_github_settings.py
│       ├── repository/
│       │   ├── __init__.py
│       │   ├── repository.js
│       │   ├── repository.json
│       │   ├── repository.py
│       │   └── test_repository.py
│       ├── repository_branch/
│       │   ├── __init__.py
│       │   ├── repository_branch.json
│       │   └── repository_branch.py
│       ├── repository_issue/
│       │   ├── __init__.py
│       │   ├── repository_issue.js
│       │   ├── repository_issue.json
│       │   ├── repository_issue.py
│       │   └── test_repository_issue.py
│       ├── repository_issue_assignee/
│       │   ├── __init__.py
│       │   ├── repository_issue_assignee.json
│       │   └── repository_issue_assignee.py
│       ├── repository_member/
│       │   ├── __init__.py
│       │   ├── repository_member.json
│       │   └── repository_member.py
│       ├── repository_pull_request/
│       │   ├── __init__.py
│       │   ├── repository_pull_request.js
│       │   ├── repository_pull_request.json
│       │   ├── repository_pull_request.py
│       │   └── test_repository_pull_request.py
│       └── repository_pr_reviewer/
│           ├── __init__.py
│           ├── repository_pr_reviewer.json
│           └── repository_pr_reviewer.py
├── patches/
│   ├── __init__.py
│   └── after_install/
│       ├── __init__.py
│       └── create_custom_fields_and_scripts.py
├── public/
│   ├── .gitkeep
│   └── js/
│       ├── project_client.js
│       └── task_client.js
└── templates/
    ├── __init__.py
    └── pages/
        └── __init__.py
```

## Features

### 🔧 Repository Management
- Sync GitHub repositories with ERPNext
- Track repository branches, members, and metadata
- Manage repository access and permissions
- Real-time webhook integration

### 📋 Issue Management
- Sync GitHub issues with ERPNext
- Create issues from ERPNext tasks
- Track assignees and labels
- Bulk import/export capabilities

### 🔄 Pull Request Tracking
- Monitor pull request status
- Track reviewers and merge status
- Link PRs to ERPNext tasks
- Automated status updates via webhooks

### 👥 Team Management
- Sync repository collaborators
- Link GitHub users to ERPNext users
- Project team synchronization
- Role-based access control

### 📊 Dashboard & Analytics
- Repository activity tracking
- Sync statistics and reports
- GitHub profile integration
- Comprehensive dashboard views

## Installation

### Prerequisites
- ERPNext v13+ or Frappe v13+
- GitHub Personal Access Token or OAuth App
- Python 3.7+

### Install Steps

1. **Install the app:**
   ```bash
   bench get-app https://github.com/yourusername/erpnext_github_integration.git
   bench --site your-site.com install-app erpnext_github_integration
   ```

2. **Run migrations:**
   ```bash
   bench --site your-site.com migrate
   ```

3. **Restart services:**
   ```bash
   bench restart
   ```

## Configuration

### 1. GitHub Settings

Navigate to **Setup > GitHub Settings** and configure:

#### Authentication
- **Auth Type**: Choose "Personal Access Token" or "OAuth App"
- **Personal Access Token**: Your GitHub PAT with required scopes:
  - `repo` (for private repositories)
  - `public_repo` (for public repositories)
  - `read:org` (for organization access)
  - `read:user` (for user information)

#### Repository Settings
- **Default Organization**: Your GitHub organization name
- **Default Visibility**: Public or Private
- **Sync Interval**: How often to sync (in minutes)

#### Webhook Configuration
- **Webhook Secret**: Secret key for webhook validation
- Configure webhooks for real-time updates

### 2. User Setup

#### Link GitHub Users
1. Go to **User** doctype
2. Set **GitHub Username** field for each user
3. Users can sync their GitHub profile information

#### Role Assignment
- Assign **GitHub Admin** role to users who need full access
- Project Managers can sync repositories they manage

## Usage Guide

### Repository Management

#### Sync Repositories
1. **From GitHub Settings:**
   - Click "List Repositories" to see available repos
   - Select repositories to sync individually
   - Use "Sync All Repositories" for bulk sync

2. **From Repository Form:**
   - Open any Repository record
   - Use "Sync Repository Data" button
   - View synced branches, issues, PRs, and members

#### Create New Repository
```python
# Via API
frappe.call({
    method: 'erpnext_github_integration.github_api.create_repository',
    args: {
        name: 'my-new-repo',
        description: 'Repository description',
        private: true
    }
})
```

### Issue Management

#### Create Issues from Tasks
1. Open a Task record
2. Set **GitHub Repository** field
3. Click "Create GitHub Issue" button
4. Issue will be created and linked automatically

#### Sync Issues
- Issues are automatically synced during repository sync
- Use webhooks for real-time updates
- Bulk import available for historical data

### Pull Request Workflow

#### Create PRs from Tasks
1. Set GitHub repository in Task
2. Use "Create Pull Request" button
3. Specify head and base branches
4. PR is created and linked to task

#### Track PR Status
- PR status updates automatically via webhooks
- View merge status and reviews
- Link multiple PRs to single task

### Project Integration

#### Link Projects to Repositories
1. Open Project form
2. Set **Repository** field
3. Use "Sync from GitHub" to sync team members
4. Team members are automatically added to project

#### Automated Task Creation
```python
# Create task from GitHub issue
frappe.call({
    method: 'erpnext_github_integration.api.create_task_from_github_issue',
    args: {
        issue_name: 'REPO-ISSUE-001',
        task_title: 'Fix bug in authentication'
    }
})
```

## API Reference

### Repository Operations

#### List Repositories
```python
frappe.call({
    method: 'erpnext_github_integration.github_api.list_repositories',
    args: {organization: 'my-org'}
})
```

#### Sync Repository
```python
frappe.call({
    method: 'erpnext_github_integration.github_api.sync_repo',
    args: {repository: 'owner/repo-name'}
})
```

### Issue Operations

#### Create Issue
```python
frappe.call({
    method: 'erpnext_github_integration.github_api.create_issue',
    args: {
        repository: 'owner/repo',
        title: 'Issue title',
        body: 'Issue description',
        assignees: ['username1', 'username2'],
        labels: ['bug', 'priority-high']
    }
})
```

#### Assign Issue
```python
frappe.call({
    method: 'erpnext_github_integration.github_api.assign_issue',
    args: {
        repo_full_name: 'owner/repo',
        issue_number: 123,
        assignees: ['username']
    }
})
```

### Pull Request Operations

#### Create Pull Request
```python
frappe.call({
    method: 'erpnext_github_integration.github_api.create_pull_request',
    args: {
        repository: 'owner/repo',
        title: 'PR title',
        head: 'feature-branch',
        base: 'main',
        body: 'PR description'
    }
})
```

#### Add Reviewers
```python
frappe.call({
    method: 'erpnext_github_integration.github_api.add_pr_reviewer',
    args: {
        repo_full_name: 'owner/repo',
        pr_number: 456,
        reviewers: ['reviewer1', 'reviewer2']
    }
})
```

## Webhooks Setup

### Configure GitHub Webhooks

1. **In GitHub Repository:**
   - Go to Settings > Webhooks
   - Add webhook URL: `https://your-site.com/api/method/erpnext_github_integration.webhooks.github_webhook`
   - Set Content type: `application/json`
   - Configure secret (same as in GitHub Settings)
   - Select events: `Issues`, `Pull requests`, `Push`, `Member`

2. **Supported Events:**
   - `issues` - Issue creation, updates, closure
   - `pull_request` - PR creation, updates, merges
   - `push` - Code pushes and commits
   - `member` - Team member additions/removals
   - `repository` - Repository settings changes

### Webhook Security

- Always use webhook secrets for security
- Webhooks are processed in background jobs
- Failed webhook events are logged for debugging

## Troubleshooting

### Common Issues

#### Authentication Errors
- **Problem**: "Invalid credentials" or "Bad token"
- **Solution**: 
  - Verify Personal Access Token is correct
  - Check token has required scopes
  - Ensure token hasn't expired

#### Rate Limiting
- **Problem**: "API rate limit exceeded"
- **Solution**:
  - Increase sync interval in GitHub Settings
  - Use authenticated requests (tokens have higher limits)
  - Implement exponential backoff (automatic)

#### Sync Issues
- **Problem**: Data not syncing properly
- **Solution**:
  - Check error logs in ERPNext
  - Verify repository exists and is accessible
  - Manual sync via "Sync Repository Data" button

#### Webhook Issues
- **Problem**: Real-time updates not working
- **Solution**:
  - Verify webhook URL is accessible
  - Check webhook secret matches
  - Review webhook delivery logs in GitHub

### Debug Mode

Enable debug logging:
```python
# In site_config.json
{
    "developer_mode": 1,
    "log_level": "DEBUG"
}
```

## Performance Optimization

### Best Practices

1. **Sync Intervals:**
   - Set appropriate sync intervals (60+ minutes)
   - Use webhooks for real-time updates
   - Avoid frequent full syncs

2. **Data Management:**
   - Regularly clean old sync data
   - Archive closed issues/PRs
   - Monitor database size

3. **API Usage:**
   - Use conditional requests when possible
   - Implement proper error handling
   - Respect rate limits

## Contributing

### Development Setup

1. **Clone repository:**
   ```bash
   git clone https://github.com/yourusername/erpnext_github_integration.git
   cd erpnext_github_integration
   ```

2. **Install in development mode:**
   ```bash
   bench get-app ./erpnext_github_integration
   bench --site development.localhost install-app erpnext_github_integration
   ```

3. **Enable developer mode:**
   ```bash
   bench --site development.localhost set-config developer_mode 1
   ```

### Testing

Run tests:
```bash
bench --site test_site run-tests --app erpnext_github_integration
```

### Code Style

- Follow PEP 8 for Python code
- Use ESLint for JavaScript
- Add docstrings to all functions
- Include type hints where appropriate

## Security Considerations

- Store tokens securely (encrypted in database)
- Use webhook secrets for validation
- Implement proper permission checks
- Regular security updates

## License

MIT License - see LICENSE file for details.

## Support

- **Documentation**: [Wiki](https://github.com/yourusername/erpnext_github_integration/wiki)
- **Issues**: [GitHub Issues](https://github.com/yourusername/erpnext_github_integration/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/erpnext_github_integration/discussions)

## Changelog

### v1.0.0
- Initial release
- Repository, issue, and PR sync
- Webhook integration
- User management
- Dashboard views

---

**Made with ❤️ for the ERPNext community**