
import os

import requests

# MinerU API Token 请通过环境变量提供，不要硬编码在源码里：
#   export MINERU_API_TOKEN="<你的 Token>"     # Linux / macOS
#   set MINERU_API_TOKEN=<你的 Token>          # Windows CMD
token = os.environ.get("MINERU_API_TOKEN", "")


url = "https://mineru.net/api/v4/file-urls/batch"

header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

data = {
    "files": [
        {"name":"demo.pdf", "data_id": "abcd"}
    ],
    "model_version":"vlm"
}

file_path = ["demo.pdf"]

try:
    response = requests.post(url,headers=header,json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]
            print('batch_id:{},urls:{}'.format(batch_id, urls))
            for i in range(0, len(urls)):
                with open(file_path[i], 'rb') as f:
                    res_upload = requests.put(urls[i], data=f)
                    if res_upload.status_code == 200:
                        print(f"{urls[i]} upload success")
                    else:
                        print(f"{urls[i]} upload failed")
        else:
            print('apply upload url failed,reason:{}'.format(result["msg"]))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)


'''
示例响应（已脱敏）：
    {'code': 0, 'msg': 'ok', 'trace_id': '<trace_id>',
     'data': {'batch_id': '<batch_id>',
              'file_urls': ['https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/extract/<date>/<batch_id>/<file_id>.pdf?<签名参数>']}}
拿到 file_urls 后，用 PUT 直接上传文件到该地址即可。
'''

batch_id = "0d388d59-c3b2-437d-a009-578cfa25e941"
url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

res = requests.get(url, headers=header)
print(res.status_code)
print(res.json())
print(res.json()["data"])
