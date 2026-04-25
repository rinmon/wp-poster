import urllib.request
import json
import base64

AUTH = b'rinmon:Xdr6 Entp HsDz TdOZ cdSS 1QdX'
AUTH_STR = "Basic " + base64.b64encode(AUTH).decode()

url = "https://chotto.news/wp-json/wp/v2/posts?per_page=10&status=future,publish"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Authorization": AUTH_STR})

with urllib.request.urlopen(req) as resp:
    posts = json.loads(resp.read().decode())
    for p in posts:
        print(f"ID: {p['id']}, Title: {p['title']['rendered']}, Status: {p['status']}")
