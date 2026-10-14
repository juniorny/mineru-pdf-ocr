import os
from unittest import result
from urllib import response
import requests
import uuid
import time

# ====================== 配置项 ======================
# MinerU API Token 请通过环境变量提供，不要硬编码在源码里：
#   export MINERU_API_TOKEN="<你的 Token>"     # Linux / macOS
#   set MINERU_API_TOKEN=<你的 Token>          # Windows CMD
token = os.environ.get("MINERU_API_TOKEN", "")

header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

# 待处理的 PDF 目录（改成你自己的路径，或设置环境变量 PDF_FOLDER）
pdf_folder = os.environ.get("PDF_FOLDER", "./input")
# ====================================================
# 1. 获取文件夹下所有PDF
file_list = [f for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf")]
file_paths = [os.path.join(pdf_folder, f) for f in file_list]

# 2. 构造合法 data_id（自动生成唯一ID，兼容中文）
files_data = []
for filename in file_list:
    files_data = [{"name": fn, "data_id": uuid.uuid4().hex} for fn in file_list] 

data = {
    "files": files_data,
    "model_version": "vlm",
    "is_ocr": True
}


def get_upload_urls():
    url = "https://mineru.net/api/v4/file-urls/batch"

    try:
        response = requests.post(url, headers=header, json=data)
        if response.status_code == 200:
            result = response.json()
            print('response success. result:{}'.format(result))
            if result["code"] == 0:
                batch_id = result["data"]["batch_id"]
                urls = result["data"]["file_urls"]
                # print('batch_id:{},urls:{}'.format(batch_id, urls))
                return batch_id, urls
            else:
                print('apply upload url failed,reason:{}'.format(result["msg"]))
        else:
            print('response not success. status:{} ,result:{}'.format(response.status_code, response))
    except Exception as err:
        print(err)
    return None, None


def upload_files(urls):            
    # 批量上传文件
    try_count = 0
    for i in range(len(urls)):
        with open(file_paths[i], 'rb') as f:
            while True:
                try:
                    res_upload = requests.put(urls[i], data=f)
                    if res_upload.status_code == 200:
                        print(f"✅ {file_list[i]} 上传成功")
                        break
                    else:
                        raise Exception(f"上传失败，状态码：{res_upload.status_code}")
                except Exception as err:
                    print(f"❌ {file_list[i]} 上传异常，错误：{err}")
                    try_count += 1
                    if try_count >= 5:
                        print(f"❌ {file_list[i]} 连续5次上传失败，放弃上传")
                        break



if __name__ == "__main__":
    batch_id, file_urls = get_upload_urls()
    if batch_id and file_urls:   
        upload_files(file_urls)
        print(f"上传成功，batch_id: {batch_id}")
                
