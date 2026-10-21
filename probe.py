import json, os, urllib.request
token = os.environ.get("GITHUB_TOKEN", "")
for model in ["openai/gpt-4.1-mini", "openai/gpt-4o-mini", "meta/Llama-3.3-70B-Instruct", "mistral-ai/mistral-medium-2505"]:
    body = {"model": model, "temperature": 0.2, "messages": [
        {"role": "system", "content": "Tu résumes l'actualité en français, sobrement."},
        {"role": "user", "content": "Résume en une phrase : 'Netflix posts third-quarter earnings beat, but shares fall on advertising guidance' ; 'Carrefour shares plunge 14% after warning unrest will hit sales'."}]}
    req = urllib.request.Request("https://models.github.ai/inference/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())
        print("OK", model, "|", d["choices"][0]["message"]["content"][:300].replace("\n", " "), "| usage", d.get("usage"))
    except urllib.error.HTTPError as e:
        print("ERR", model, e.code, e.read()[:300])
    except Exception as e:
        print("ERR", model, e)
