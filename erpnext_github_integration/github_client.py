import requests, time
from frappe import _

GITHUB_API = "https://api.github.com"

def _get_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "erpnext-github-integration"
    }

def _handle_rate_limit(resp):
    remaining = resp.headers.get('X-RateLimit-Remaining')
    reset = resp.headers.get('X-RateLimit-Reset')
    if remaining is not None:
        try:
            remaining = int(remaining)
            if remaining <= 0 and reset:
                reset = int(reset)
                wait = max(0, reset - int(time.time()) + 2)
                time.sleep(wait)
                return True
        except Exception:
            pass
    return False

def _get_with_pagination(url, headers, params=None, retry=2):
    results = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
            if _handle_rate_limit(resp):
                continue
            link = resp.headers.get('Link')
            next_url = None
            if link:
                parts = link.split(',')
                for p in parts:
                    if 'rel="next"' in p:
                        next_url = p[p.find('<')+1:p.find('>')]
                        break
            url = next_url
            params = None
        elif resp.status_code == 403:
            if 'rate limit' in (resp.text or "").lower():
                if _handle_rate_limit(resp):
                    continue
            resp.raise_for_status()
        else:
            resp.raise_for_status()
    return results

def github_request(method, path, token, params=None, data=None, retry=2):
    url = f"{GITHUB_API}{path}" if path.startswith('/') else path
    headers = _get_headers(token)
    for _ in range(retry):
        resp = requests.request(method, url, headers=headers, params=params, json=data, timeout=30)
        if resp.status_code in (200,201,204):
            if resp.status_code == 204:
                return None
            if 'Link' in resp.headers:
                return _get_with_pagination(url, headers, params=params)
            try:
                return resp.json()
            except ValueError:
                return resp.text
        elif resp.status_code == 403 and 'rate limit' in (resp.text or "").lower():
            if _handle_rate_limit(resp):
                continue
            resp.raise_for_status()
        else:
            try:
                resp.raise_for_status()
            except Exception as e:
                raise
    return None
