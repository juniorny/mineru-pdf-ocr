import argparse
import io
import os
import re
import shutil
import time
import uuid
import zipfile

import requests
from PyPDF2 import PdfReader, PdfWriter

API_UPLOAD_ENDPOINT = "https://mineru.net/api/v4/file-urls/batch"
API_RESULT_ENDPOINT = "https://mineru.net/api/v4/extract-results/batch/{}"
DEFAULT_POLL_INTERVAL = 10
DEFAULT_POLL_TIMEOUT = 3600
MAX_SIZE_MB_DEFAULT = 200
MAX_PAGE_DEFAULT = 200
BATCH_COUNT_DEFAULT = 50
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".jp2"}
RESERVED_DIR_NAMES = {"合格PDF", "超页数PDF", "超大小PDF", "汇总MD"}
DEFAULT_MINERU_API_TOKEN = os.environ.get("MINERU_API_TOKEN", "")  # 建议通过环境变量 MINERU_API_TOKEN 提供，或在 GUI 界面中输入


class PipelineAborted(Exception):
    """用户主动中止流程时抛出，用于快速跳出深层调用。"""


def _check_stop(stop_event):
    """若外部已请求中止，则抛出 PipelineAborted。"""
    if stop_event is not None and stop_event.is_set():
        raise PipelineAborted("用户请求中止")


def _sleep_with_stop(seconds, stop_event):
    """可被中止请求立即打断的等待。"""
    if stop_event is None:
        time.sleep(seconds)
        return
    if stop_event.wait(timeout=seconds):
        raise PipelineAborted("用户请求中止")


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def get_pdf_page_count(pdf_path):
    try:
        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            return len(reader.pages)
    except Exception as exc:
        print(f"⚠️  读取PDF页数失败：{pdf_path}，错误：{exc}")
        return -1


def make_unique_file_path(target_dir, file_name):
    base_name, ext = os.path.splitext(file_name)
    candidate = os.path.join(target_dir, file_name)
    count = 1
    while os.path.exists(candidate):
        candidate = os.path.join(target_dir, f"{base_name}_{count}{ext}")
        count += 1
    return candidate


def write_pdf_chunk(reader, output_path, start_page, end_page):
    writer = PdfWriter()
    for page_index in range(start_page, end_page):
        writer.add_page(reader.pages[page_index])
    with open(output_path, "wb") as out_f:
        writer.write(out_f)


def split_pdf_file(src_path, valid_pdf_dir, max_page, max_size_mb, stop_event=None):
    ensure_dir(valid_pdf_dir)
    try:
        with open(src_path, "rb") as f:
            data = f.read()
        reader = PdfReader(io.BytesIO(data))
        total_pages = len(reader.pages)
    except Exception as exc:
        print(f"❌ 无法读取PDF进行拆分：{src_path}，错误：{exc}")
        return []

    max_size_bytes = max_size_mb * 1024 * 1024
    split_paths = []
    page_start = 0
    segment_index = 1

    while page_start < total_pages:
        _check_stop(stop_event)
        pages_in_chunk = min(max_page, total_pages - page_start)
        while True:
            _check_stop(stop_event)
            chunk_filename = f"{os.path.splitext(os.path.basename(src_path))[0]}_part{segment_index}.pdf"
            chunk_path = make_unique_file_path(valid_pdf_dir, chunk_filename)
            write_pdf_chunk(reader, chunk_path, page_start, page_start + pages_in_chunk)
            current_size = os.path.getsize(chunk_path)
            if current_size <= max_size_bytes or pages_in_chunk == 1:
                break
            os.remove(chunk_path)
            pages_in_chunk = max(1, pages_in_chunk // 2)
            print(f"⚠️ 当前片段仍超大小，缩小拆分数量为 {pages_in_chunk} 页后重试")

        if os.path.getsize(chunk_path) > max_size_bytes:
            print(f"⚠️ 拆分后单页文件仍超大小，保留该文件作为异常文件：{chunk_path}")
        else:
            print(f"✅ 已生成合规PDF：{os.path.basename(chunk_path)}")

        split_paths.append(chunk_path)
        page_start += pages_in_chunk
        segment_index += 1

    return split_paths


def move_file(src_file, target_dir):
    ensure_dir(target_dir)
    file_name = os.path.basename(src_file)
    target_path = os.path.join(target_dir, file_name)
    if os.path.exists(target_path):
        name, ext = os.path.splitext(file_name)
        count = 1
        while True:
            new_name = f"{name}_{count}{ext}"
            target_path = os.path.join(target_dir, new_name)
            if not os.path.exists(target_path):
                break
            count += 1
    shutil.copy2(src_file, target_path)
    print(f"✅ 已复制：{file_name} -> {target_dir}")
    return target_path


def iter_source_files(source_dir, recursive=False):
    """按名称顺序枚举源目录下的文件；recursive=True 时递归子文件夹。

    递归过程中会跳过程序自身生成的临时目录（合格PDF / 超页数PDF / 超大小PDF / 汇总MD），
    避免二次扫描造成重复处理。
    """
    if not recursive:
        for name in sorted(os.listdir(source_dir)):
            path = os.path.join(source_dir, name)
            if os.path.isfile(path):
                yield path
        return

    for dirpath, dirnames, filenames in os.walk(source_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in RESERVED_DIR_NAMES)
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def organize_pdf_files(source_dir, max_page, max_size_mb, include_images=False, recursive=False, stop_event=None):
    source_dir = os.path.abspath(source_dir)
    over_page_dir = os.path.join(source_dir, "超页数PDF")
    over_size_dir = os.path.join(source_dir, "超大小PDF")
    valid_pdf_dir = os.path.join(source_dir, "合格PDF")

    ensure_dir(source_dir)
    ensure_dir(over_page_dir)
    ensure_dir(over_size_dir)
    ensure_dir(valid_pdf_dir)

    valid_pdf_list = []
    image_count = 0
    print("=" * 60)
    print(f"开始扫描源目录：{source_dir}")
    print(f"扫描模式：{'递归子文件夹' if recursive else '仅当前目录'}")
    print("=" * 60)

    _check_stop(stop_event)

    for file_path in iter_source_files(source_dir, recursive=recursive):
        _check_stop(stop_event)
        file_name = os.path.basename(file_path)
        lower_name = file_name.lower()
        is_pdf = lower_name.endswith(".pdf")
        is_image = include_images and os.path.splitext(lower_name)[1] in IMAGE_EXTS
        if not is_pdf and not is_image:
            continue

        if recursive:
            rel_name = os.path.relpath(file_path, source_dir)
        else:
            rel_name = file_name

        print(f"\n正在处理：{rel_name}")

        # 图片文件：直接归入合格目录，不做页数/大小判断
        if is_image:
            moved_path = move_file(file_path, valid_pdf_dir)
            valid_pdf_list.append(moved_path)
            image_count += 1
            print("✅ 图片文件，已移动到合格目录")
            continue

        page_count = get_pdf_page_count(file_path)
        if page_count == -1:
            continue

        file_size = os.path.getsize(file_path)
        if page_count > max_page:
            moved_original = move_file(file_path, over_page_dir)
            split_paths = split_pdf_file(moved_original, valid_pdf_dir, max_page, max_size_mb, stop_event=stop_event)
            valid_pdf_list.extend(split_paths)
            continue

        if file_size > max_size_mb * 1024 * 1024:
            moved_original = move_file(file_path, over_size_dir)
            split_paths = split_pdf_file(moved_original, valid_pdf_dir, max_page, max_size_mb, stop_event=stop_event)
            valid_pdf_list.extend(split_paths)
            continue

        moved_path = move_file(file_path, valid_pdf_dir)
        valid_pdf_list.append(moved_path)
        print("✅ 符合要求，已移动到合格PDF目录")

    print("\n" + "=" * 60)
    print("🎉 文件整理完成！")
    print(f"📄 合格PDF总数：{len(valid_pdf_list) - image_count}")
    if include_images:
        print(f"🖼️ 图片文件：{image_count} 个")
    print(f"📂 超页数文件：{len(os.listdir(over_page_dir))} 个")
    print(f"📂 超大小文件：{len(os.listdir(over_size_dir))} 个")
    print("=" * 60)
    return valid_pdf_dir, valid_pdf_list


def request_upload_urls(file_names, token, model_version="vlm", is_ocr=True):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    files_data = [{"name": name, "data_id": uuid.uuid4().hex, "is_ocr": is_ocr} for name in file_names]
    payload = {
        "files": files_data,
        "model_version": model_version,
    }
    try:
        response = requests.post(API_UPLOAD_ENDPOINT, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 0:
            print(f"❌ 获取上传URL失败：{result.get('msg')}")
            return None, None, None
        batch_id = result["data"]["batch_id"]
        urls = result["data"]["file_urls"]
        return batch_id, urls, files_data
    except Exception as exc:
        print(f"❌ 请求上传URL异常：{exc}")
        return None, None, None


def upload_files(file_paths, urls, max_retries=5, stop_event=None):
    if len(file_paths) != len(urls):
        print("❌ 本次上传的文件数与URL数不一致")
        return False

    for idx, pdf_path in enumerate(file_paths):
        _check_stop(stop_event)
        file_name = os.path.basename(pdf_path)
        for attempt in range(1, max_retries + 1):
            try:
                with open(pdf_path, "rb") as f:
                    response = requests.put(urls[idx], data=f, timeout=300)
                if response.status_code == 200:
                    print(f"✅ {file_name} 上传成功")
                    break
                raise Exception(f"状态码 {response.status_code}")
            except Exception as exc:
                print(f"❌ {file_name} 上传第{attempt}次失败：{exc}")
                if attempt == max_retries:
                    print(f"❌ {file_name} 连续{max_retries}次上传失败，跳过")
                    return False
                _sleep_with_stop(3, stop_event)
    return True


def download_and_extract_zip(zip_url, zip_path, extract_dir):
    try:
        print(f"开始下载 ZIP：{zip_path}")
        with requests.get(zip_url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        ensure_dir(extract_dir)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
        print(f"✅ 已解压：{extract_dir}")
        return True
    except Exception as exc:
        print(f"❌ ZIP 下载或解压失败：{exc}")
        return False


def get_extract_results(batch_id, token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        response = requests.get(API_RESULT_ENDPOINT.format(batch_id), headers=headers, timeout=60)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"❌ 查询解析结果失败：{exc}")
        return None


def process_extract_results_for_files(batch_files, base_dir, batch_id, token):
    result = get_extract_results(batch_id, token)
    if not result or result.get("code") != 0:
        print("❌ 获取解析结果失败，稍后重试")
        return None

    items = result["data"].get("extract_result", [])
    status_counts = {
        "done": 0,
        "waiting-file": 0,
        "pending": 0,
        "running": 0,
        "failed": 0,
        "converting": 0,
        "other": 0,
    }

    for item in items:
        state = item.get("state")
        status_counts[state] = status_counts.get(state, 0) + 1
        if state == "done":
            file_name = item.get("file_name")
            zip_name = os.path.splitext(file_name)[0] + ".zip"
            zip_path = os.path.join(base_dir, zip_name)
            extract_dir = os.path.join(base_dir, os.path.splitext(file_name)[0])
            if os.path.exists(extract_dir):
                print(f"文件 {file_name} 已解压，跳过")
            else:
                zip_url = item.get("full_zip_url")
                if zip_url:
                    download_and_extract_zip(zip_url, zip_path, extract_dir)
                else:
                    print(f"❌ 文件 {file_name} 的 full_zip_url 不可用")

    return status_counts


def wait_for_batch_files(batch_files, base_dir, batch_id, token, poll_interval, timeout, stop_event=None):
    start = time.time()
    last_status = None
    while True:
        _check_stop(stop_event)
        status_counts = process_extract_results_for_files(batch_files, base_dir, batch_id, token)
        if status_counts is None:
            print("等待下一次重试...")
        else:
            last_status = status_counts
            pending = status_counts.get("pending", 0) + status_counts.get("running", 0) + status_counts.get("converting", 0)
            waiting_file = status_counts.get("waiting-file", 0)
            if pending == 0 and waiting_file == 0:
                print("🎉 当前批次已不再排队或处理中")
                break
            print(f"当前状态：pending={status_counts.get('pending')} running={status_counts.get('running')} converting={status_counts.get('converting')} waiting-file={status_counts.get('waiting-file')}")

        if time.time() - start > timeout:
            print("⚠️  等待超时，停止轮询")
            break
        _sleep_with_stop(poll_interval, stop_event)

    return last_status


def merge_full_md(root_dir, output_dir, extract_images=True):
    ensure_dir(output_dir)
    groups = {}

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower() == "full.md":
                folder_name = os.path.basename(dirpath)
                match = re.search(r"_part(\d+)$", folder_name)
                if match:
                    base_name = folder_name[: match.start()]
                    if not base_name:
                        base_name = folder_name
                else:
                    base_name = folder_name
                groups.setdefault(base_name, []).append((folder_name, os.path.join(dirpath, filename)))

    if not groups:
        print("⚠️ 未找到任何 full.md 文件，无法生成合并MD")
        return False

    for base_name, items in groups.items():
        items.sort(key=lambda x: x[0])
        merged_path = os.path.join(output_dir, f"{base_name}.md")
        # assets directory holds copied images for this merged MD
        assets_basename = f"{base_name}_assets"
        assets_dir = os.path.join(output_dir, assets_basename)

        image_link_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

        with open(merged_path, "w", encoding="utf-8") as merged_f:
            for folder_name, md_path in items:
                merged_f.write(f"<!-- source: {os.path.relpath(md_path, root_dir)} -->\n")
                folder_dir = os.path.dirname(md_path)

                # load the extracted full.md content
                try:
                    with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception as exc:
                    print(f"⚠️ 读取 MD 失败：{md_path}，错误：{exc}")
                    content = ""

                if extract_images:
                    ensure_dir(assets_dir)
                    # copy image folders ("images" or "image") from the extracted folder to assets
                    for img_dirname in ("images", "image"):
                        src_images = os.path.join(folder_dir, img_dirname)
                        if os.path.isdir(src_images):
                            dest_images = os.path.join(assets_dir, folder_name, img_dirname)
                            try:
                                ensure_dir(os.path.dirname(dest_images))
                                shutil.copytree(src_images, dest_images, dirs_exist_ok=True)
                                print(f"✅ 已复制图片目录：{src_images} -> {dest_images}")
                            except Exception as exc:
                                print(f"⚠️ 复制图片目录失败：{src_images}，错误：{exc}")

                def _replace_image_link(m):
                    alt = m.group(1)
                    path = m.group(2).strip()
                    # keep absolute/remote/data URIs unchanged
                    if path.startswith("http://") or path.startswith("https://") or path.startswith("data:"):
                        return m.group(0)

                    norm_path = path.lstrip("./").lstrip("/")

                    # if the path contains an images/ or image/ segment, map it to our assets structure
                    for img_dirname in ("images", "image"):
                        idx = norm_path.find(img_dirname + "/")
                        if idx != -1:
                            subpath = norm_path[idx + len(img_dirname) + 1:]
                            new_path = "/".join([os.path.basename(assets_dir), folder_name, img_dirname, subpath.replace('\\\\', '/')])
                            return f"![{alt}]({new_path})"

                    # otherwise, try to locate the referenced file under images/image subfolders
                    target_found = None
                    for root, _, files in os.walk(folder_dir):
                        if os.path.basename(root).lower() in ("images", "image"):
                            if os.path.basename(path) in files:
                                rel = os.path.relpath(os.path.join(root, os.path.basename(path)), folder_dir).replace('\\\\', '/')
                                parts = rel.split('/', 1)
                                if len(parts) >= 2 and parts[0] in ("images", "image"):
                                    img_dirname = parts[0]
                                    subpath = parts[1]
                                    target_found = "/".join([os.path.basename(assets_dir), folder_name, img_dirname, subpath])
                                    break

                    if target_found:
                        return f"![{alt}]({target_found})"

                    # fallback: leave unchanged
                    return m.group(0)

                if extract_images:
                    new_content = image_link_pattern.sub(_replace_image_link, content)
                else:
                    new_content = content
                merged_f.write(new_content.rstrip())
                merged_f.write("\n\n")
        print(f"✅ 已生成合并 MD：{merged_path}")

    print(f"\n🎉 全部完成！共生成 {len(groups)} 个合并 MD 文件")
    return True


def process_batch_files(batch_files, base_dir, token, poll_interval, timeout, stop_event=None):
    if not batch_files:
        print("跳过空批次")
        return False
    _check_stop(stop_event)

    file_names = [os.path.basename(f) for f in batch_files]
    print("\n" + "-" * 60)
    print(f"开始上传批次，文件数：{len(batch_files)}")

    batch_id, urls, files_data = request_upload_urls(file_names, token)
    if not batch_id or not urls:
        return False

    if not upload_files(batch_files, urls, stop_event=stop_event):
        return False

    print(f"✅ 上传完成，batch_id={batch_id}")
    print("开始轮询解析结果，请耐心等待...")
    wait_for_batch_files(batch_files, base_dir, batch_id, token, poll_interval, timeout, stop_event=stop_event)
    return True


def cleanup_temp_files(base_dir):
    """删除下载的ZIP文件和解压文件夹，只保留汇总MD"""
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if item.lower().endswith('.zip') or os.path.isdir(item_path):
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                    print(f"🗑️ 已删除文件：{item}")
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"🗑️ 已删除目录：{item}")
            except Exception as exc:
                print(f"⚠️ 删除失败：{item_path}，错误：{exc}")


def cleanup_temp_dirs(source_dir):
    for folder_name in ["合格PDF", "超页数PDF", "超大小PDF"]:
        folder_path = os.path.join(source_dir, folder_name)
        if os.path.isdir(folder_path):
            try:
                shutil.rmtree(folder_path)
                print(f"🗑️ 已删除临时目录：{folder_path}")
            except Exception as exc:
                print(f"⚠️ 删除临时目录失败：{folder_path}，错误：{exc}")


def cleanup_on_abort(source_dir, valid_pdf_dir=None):
    """用户中止流程时清理临时产物（保留源目录原始文件与已生成的汇总MD）。"""
    print("\n🧹 开始清理本次运行产生的临时文件…")
    if valid_pdf_dir and os.path.isdir(valid_pdf_dir):
        try:
            cleanup_temp_files(valid_pdf_dir)
        except Exception as exc:
            print(f"⚠️ 清理临时文件失败：{exc}")
    cleanup_temp_dirs(source_dir)
    print("✅ 临时目录与文件已清理完毕")


def resolve_token(token):
    token_value = str(token).strip() if token is not None else ""
    if token_value == "123":
        return DEFAULT_MINERU_API_TOKEN
    return token_value


def parse_args():
    parser = argparse.ArgumentParser(description="一键完成 PDF 过滤、上传、下载解压、汇总 full.md 的流程")
    parser.add_argument("pdf_dir", help="PDF 源目录，程序会直接在该目录下筛选并处理 PDF")
    parser.add_argument("--token", default=None, help="Mineru API Bearer Token，可通过环境变量 MINERU_API_TOKEN 提供")
    parser.add_argument("--max-page", type=int, default=MAX_PAGE_DEFAULT, help="最大页数，超过则移到超页数目录")
    parser.add_argument("--max-size-mb", type=int, default=MAX_SIZE_MB_DEFAULT, help="最大文件大小（MB），超过则移到超大小目录")
    parser.add_argument("--batch-size", type=int, default=BATCH_COUNT_DEFAULT, help="每批次上传 PDF 数量")
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL, help="轮询解析结果间隔秒数")
    parser.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT, help="轮询解析结果超时秒数")
    parser.add_argument("--recursive", action="store_true", help="递归处理源目录下所有子文件夹中的文件（默认关闭）")
    return parser.parse_args()


def main():
    args = parse_args()
    source_dir = os.path.abspath(args.pdf_dir)
    if not os.path.isdir(source_dir):
        print(f"❌ 源目录不存在：{source_dir}")
        return

    token = resolve_token(args.token or os.environ.get("MINERU_API_TOKEN"))
    if not token:
        token = input("请输入 Mineru API Bearer Token：").strip()
        token = resolve_token(token)
        if not token:
            print("❌ 未提供 token，无法继续执行")
            return

    valid_pdf_dir, valid_pdf_list = organize_pdf_files(
        source_dir,
        max_page=args.max_page,
        max_size_mb=args.max_size_mb,
        recursive=args.recursive,
    )

    if not valid_pdf_list:
        print("⚠️  未找到合格PDF，结束执行")
        return

    # 按批次分组
    batch_size = args.batch_size
    batches = [valid_pdf_list[i:i + batch_size] for i in range(0, len(valid_pdf_list), batch_size)]

    for batch_files in batches:
        success = process_batch_files(batch_files, valid_pdf_dir, token, args.poll_interval, args.poll_timeout)
        if not success:
            print("⚠️  批次处理失败")

    output_md_dir = os.path.join(source_dir, "汇总MD")
    merged_ok = merge_full_md(valid_pdf_dir, output_md_dir)

    if merged_ok:
        cleanup_temp_files(valid_pdf_dir)
        cleanup_temp_dirs(source_dir)
        print("\n🎯 整体流程执行完毕")
        print(f"最终MD文件保存在：{output_md_dir}")
    else:
        print("\n⚠️ 未生成合并MD，保留临时文件供排查")
        print(f"请检查临时目录：{valid_pdf_dir}")


if __name__ == "__main__":
    main()
