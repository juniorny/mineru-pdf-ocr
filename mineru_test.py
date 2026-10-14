import os

import requests

# MinerU API Token 请通过环境变量提供，不要硬编码在源码里：
#   Linux / macOS :  export MINERU_API_TOKEN="<你的 Token>"
#   Windows CMD   :  set MINERU_API_TOKEN=<你的 Token>
#   PowerShell    :  $env:MINERU_API_TOKEN="<你的 Token>"
token = os.environ.get("MINERU_API_TOKEN", "")

url = "https://mineru.net/api/v4/extract/task"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "vlm"
}

res = requests.post(url,headers=header,json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])

