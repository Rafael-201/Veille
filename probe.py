import subprocess, os
cmd = ["curl", "-sS", "-i", "-X", "POST", "https://models.github.ai/inference/chat/completions",
       "-H", "Authorization: Bearer " + os.environ["GITHUB_TOKEN"], "-H", "Content-Type: application/json",
       "-H", "Accept: application/json",
       "-d", '{"model":"openai/gpt-4.1-mini","messages":[{"role":"user","content":"Dis bonjour en un mot."}]}']
print(subprocess.run(cmd, capture_output=True, text=True).stdout[:1500])
print("---- catalog")
print(subprocess.run(["curl", "-sS", "-i", "https://models.github.ai/catalog/models", "-H", "Authorization: Bearer " + os.environ["GITHUB_TOKEN"]], capture_output=True, text=True).stdout[:600])
