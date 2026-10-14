import requests
import os
import zipfile

result = {"code": 0, "msg": "ok", "data": {"batch_id": ""}}  # 示例占位；真实结果请调用 get_extract_results() 获取


batch_id = result["data"]["batch_id"]
# print(batch_id)

# MinerU API Token 请通过环境变量提供，不要硬编码在源码里：
#   export MINERU_API_TOKEN="<你的 Token>"     # Linux / macOS
#   set MINERU_API_TOKEN=<你的 Token>          # Windows CMD
token = os.environ.get("MINERU_API_TOKEN", "")



header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

# 结果 zip 的落地目录（改成你自己的路径，或设置环境变量 MINERU_FOLDER）
folder = os.environ.get("MINERU_FOLDER", "./output")
TASK_BATCH_ID = '2c645557-06c9-4a46-9a44-9ebf44aad9d0'
# folder = "./"


def download_zip(zip_url, save_zip_path):
    """
    从 URL 下载 ZIP 文件
    :param zip_url: ZIP 下载链接
    :param save_zip_path: 本地保存路径（如 result.zip）
    :return: 成功返回 True，失败返回 False
    """
    try:
        print(f"开始下载 ZIP：{zip_url}")
        with requests.get(zip_url, stream=True) as resp:
            resp.raise_for_status()  # 自动抛出 HTTP 错误
            with open(save_zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
        print(f"✅ ZIP 下载完成：{save_zip_path}")
        return True
    except Exception as e:
        print(f"❌ ZIP 下载失败：{e}")
        return False


def unzip_file(zip_path, extract_dir):
    """
    解压 ZIP 文件到指定目录
    :param zip_path: ZIP 文件路径
    :param extract_dir: 解压目标目录
    :return: 成功返回 True，失败返回 False
    """
    try:
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
        print(f"✅ ZIP 解压完成：{extract_dir}")
        return True
    except Exception as e:
        print(f"❌ ZIP 解压失败：{e}")
        return False


def get_extract_results(batch_id):
    url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
    res = requests.get(url, headers=header)
    print(res.status_code)
    # print(res.json())
    # print(res.json()["data"])

    resp = res.json()

    success_count = 0
    waiting_count = 0
    pending_count = 0
    running_count = 0
    failed_count = 0
    converting_count = 0
    for item in resp["data"]["extract_result"]:
        '''
        任务处理状态，完成:done，waiting-file: 等待文件上传排队提交解析任务中，pending: 排队中，running: 正在解析，failed：解析失败，converting：格式转换中
        '''
        if item["state"] == "done":
            print(f"文件 {item['file_name']} 上传成功，data_id: {item['data_id']}")
            success_count += 1
            if os.path.exists(f"{folder}\\{item['file_name'].replace('pdf', 'zip')}"):
                print(f"文件 {item['file_name']} 的 ZIP 文件已存在，跳过下载")
            else:
                ret = download_zip(item["full_zip_url"], f"{folder}\\{item['file_name'].replace('pdf', 'zip')}")
                if ret:
                    unzip_file(f"{folder}\\{item['file_name'].replace('pdf', 'zip')}", f"{folder}\\{item['file_name'].replace('.pdf', '')}")
        elif item["state"] == "waiting-file":
            print(f"文件 {item['file_name']} 需要补上传，data_id: {item['data_id']}")
            waiting_count += 1
        elif item["state"] == "pending":
            print(f"文件 {item['file_name']} 排队中，data_id: {item['data_id']}")
            pending_count += 1
        elif item["state"] == "running":
            print(f"文件 {item['file_name']} 正在解析，data_id: {item['data_id']}")
            running_count += 1
        elif item["state"] == "failed":
            print(f"文件 {item['file_name']} 解析失败，data_id: {item['data_id']}")
            failed_count += 1
        elif item["state"] == "converting":
            print(f"文件 {item['file_name']} 格式转换中，data_id: {item['data_id']}")
            converting_count += 1
        else:
            print(f"文件 {item['file_name']} 状态错误 {item['state']}，data_id: {item['data_id']}")

    print(f"解析成功的文件数：{success_count}")
    print(f"需要补传的文件数：{waiting_count}")
    print(f"排队中的文件数：{pending_count}")
    print(f"正在解析的文件数：{running_count}")
    print(f"解析失败的文件数：{failed_count}")
    print(f"格式转换中的文件数：{converting_count}")


if __name__ == "__main__":
    get_extract_results(TASK_BATCH_ID)