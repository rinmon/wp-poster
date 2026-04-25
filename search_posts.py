import urllib.request, json, urllib.parse
word1 = urllib.parse.quote("エジプト")
url = f"https://chotto.news/wp-json/wp/v2/posts?search={word1}&per_page=1"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    for d in data: print(d['id'], d['title']['rendered'])

word2 = urllib.parse.quote("NATO大使")
url = f"https://chotto.news/wp-json/wp/v2/posts?search={word2}&per_page=1"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    for d in data: print(d['id'], d['title']['rendered'])
