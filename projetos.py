import json
from dotenv import load_dotenv
import os
import gitlab

load_dotenv()

print(os.getenv("GITLAB_URL"))
print(os.getenv("PRIVATE_TOKEN"))
gl = gitlab.Gitlab(os.getenv("GITLAB_URL"), private_token=os.getenv("PRIVATE_TOKEN"))

projetosIt = gl.projects.list(iterator=True)
projetos = []
for projeto in projetosIt:
    projetos.append({"id": projeto.id, "name": projeto.name, "url": projeto.web_url})
with open("projetos.json", "w") as file:
    file.write(json.dumps(projetos, indent=2))
