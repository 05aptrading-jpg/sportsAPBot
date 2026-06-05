import requests, time, sys

def fetch(url, headers, retries=3, cooldown=5):
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=15)
            print(f'Status {r.status_code}')
            if r.status_code == 200:
                print(r.text[:300])
                return r.text
            else:
                print('Non‑200 response, retry...')
        except Exception as e:
            print('Error:', e)
        if i < retries - 1:
            print(f'Waiting {cooldown}s before next attempt')
            time.sleep(cooldown)
    return None

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python test_user_agent.py <url>')
        sys.exit(1)
    url = sys.argv[1]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/json,*/*',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    fetch(url, headers)
