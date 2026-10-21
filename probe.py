import json, os, urllib.request
token = os.environ.get("GITHUB_TOKEN", "")
print("token len", len(token))
for url in ["https://models.github.ai/inference/chat/completions", "https://models.inference.ai.azure.com/chat/completions"]:
    for model in ["openai/gpt-4.1-mini", "gpt-4o-mini"]:
        body = {"model": model, "temperature": 0.2, "stream": False, "messages": [
            {"role": "user", "content": "Résume en une phrase en français : 'Netflix posts third-quarter earnings beat, but shares fall on advertising guidance'."}]}
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "veille"})
        try:
            r = urllib.request.urlopen(req, timeout=60); raw = r.read()
            print("STATUS", r.status, url, model, "| ct", r.headers.get("content-type"), "| len", len(raw), "|", raw[:400])
        except urllib.error.HTTPError as e:
            print("HTTPERR", e.code, url, model, e.read()[:300])
        except Exception as e:
            print("ERR", url, model, repr(e))
